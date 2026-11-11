import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ChevronDown, Download, Loader2, Pencil, Plus, Trash2, Upload } from 'lucide-react'
import Modal from '../models/Modal'
import { Field } from '../models/NewModelDialog'
import { getUser, prospectRules, prospectRulesImport, prospectRulesSave, setUser } from '../../lib/api'
import { fmtDate } from '../models/shared'

// --------------------------------------------------------------------------- units
// Rules store fractions for percentages (0.05 = 5%); the editor shows and accepts the familiar units.
const isPct = (kind) => kind === 'pct' || kind === 'pct2'
const toShow = (kind, v) => (v == null || v === '' ? '' : isPct(kind) ? +(Number(v) * 100).toFixed(4) : Number(v))
const fromShow = (kind, v) => (v === '' || v == null ? null : isPct(kind) ? Number(v) / 100 : Number(v))
const unit = (kind) => (isPct(kind) ? '%' : kind === 'years' ? 'שנים' : kind === 'int' ? 'ניירות' : '')

const bound = (c) => (c.dir === 'ABOVE' ? c.max : c.min)
const fmtVal = (kinds, metric, v) => {
  if (v == null || v === '') return '—'
  const k = kinds[metric]
  return isPct(k) ? `${+(Number(v) * 100).toFixed(2)}%` : k === 'years' ? Number(v).toFixed(2) : String(v)
}
const condText = (c, metrics, kinds) => `${metrics[c.metric] || c.metric} ${c.dir === 'ABOVE' ? 'מעל' : 'מתחת ל-'} ${fmtVal(kinds, c.metric, bound(c))}`
const ruleText = (r, metrics, kinds) => (r.type === 'AND'
  ? r.conditions.map((c) => condText(c, metrics, kinds)).join(' וגם ')
  : condText(r, metrics, kinds))

function nextId(rules) {
  const nums = rules.map((r) => Number(String(r.id).match(/^R(\d+)$/)?.[1])).filter((n) => !Number.isNaN(n))
  return `R${String((nums.length ? Math.max(...nums) : 0) + 1).padStart(3, '0')}`
}

// --------------------------------------------------------------------------- view-only table
function RulesTable({ rules, metrics, kinds }) {
  return (
    <div className="max-h-[50vh] overflow-auto rounded-lg border border-slate-200">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-slate-50"><tr><th className="th">כלל</th><th className="th">מתי מופיעה התובנה</th><th className="th">ניסוח</th></tr></thead>
        <tbody className="divide-y divide-slate-100">
          {rules.map((r) => (
            <tr key={r.id} className={`align-top ${r.active === false ? 'opacity-50' : ''}`}>
              <td className="td num text-xs text-slate-500">{r.id}{r.active === false && <div className="text-[10px] text-amber-700">כבוי</div>}</td>
              <td className="td whitespace-normal text-xs font-medium text-slate-700">{ruleText(r, metrics, kinds)}</td>
              <td className="td whitespace-normal text-xs text-slate-500"><span className="line-clamp-3">{r.text}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// --------------------------------------------------------------------------- editor pieces
function CondEditor({ c, onChange, onRemove, metrics, kinds }) {
  const kind = kinds[c.metric]
  const setBound = (raw) => {
    const v = fromShow(kind, raw)
    onChange(c.dir === 'ABOVE' ? { max: v } : { min: v })
  }
  const setDir = (dir) => {
    const v = bound(c)
    onChange(dir === 'ABOVE' ? { dir, max: v } : { dir, min: v })
  }
  const setMetric = (metric) => {
    const k2 = kinds[metric]
    const changedUnits = isPct(k2) !== isPct(kind)
    onChange({ metric, ...(changedUnits ? { min: null, max: null } : {}) })
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select className="input py-1.5 text-sm" value={c.metric} onChange={(e) => setMetric(e.target.value)} aria-label="הנתון שנבדק">
        {Object.entries(metrics).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
      <select className="input py-1.5 text-sm" value={c.dir} onChange={(e) => setDir(e.target.value)} aria-label="כיוון">
        <option value="ABOVE">גבוה מ-</option>
        <option value="BELOW">נמוך מ-</option>
      </select>
      <div className="flex items-center gap-1">
        <input type="number" step="any" className="input num w-24 py-1.5 text-left text-sm" value={toShow(kind, bound(c))}
          onChange={(e) => setBound(e.target.value)} aria-label="סף" />
        <span className="text-xs text-slate-500">{unit(kind)}</span>
      </div>
      {onRemove && <button className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600" onClick={onRemove} aria-label="הסרת תנאי"><Trash2 className="h-4 w-4" /></button>}
    </div>
  )
}

function RuleEditor({ r, onChange, onDelete, metrics, kinds, titles, open, onOpen }) {
  const set = (patch) => onChange({ ...r, ...patch })
  const metric = r.type === 'AND' ? r.conditions[0]?.metric : r.metric
  return (
    <div className={`rounded-xl border ${open ? 'border-brand-300 bg-surface shadow-sm' : 'border-slate-200'} ${r.active === false ? 'opacity-60' : ''}`}>
      <div className="flex items-center gap-2 px-3 py-2">
        <button className="flex min-w-0 flex-1 items-center gap-2 text-right" onClick={onOpen} aria-expanded={open}>
          <ChevronDown className={`h-4 w-4 shrink-0 text-slate-400 transition ${open ? 'rotate-180' : ''}`} />
          <span className="num shrink-0 text-xs text-slate-400">{r.id}</span>
          <span className="truncate text-sm font-medium text-slate-800">{r.title || titles[metric] || r.name}</span>
          <span className="hidden truncate text-xs text-slate-500 md:inline">· {ruleText(r, metrics, kinds)}</span>
        </button>
        <label className="flex shrink-0 items-center gap-1 text-xs text-slate-500" title="כלל כבוי לא נבדק ולא מופיע בדוחות">
          <input type="checkbox" checked={r.active !== false} onChange={(e) => set({ active: e.target.checked })} className="h-3.5 w-3.5 accent-[#00ADDC]" />פעיל
        </label>
        <button className="rounded p-1 text-slate-400 hover:bg-slate-100" onClick={onOpen} aria-label="עריכה"><Pencil className="h-4 w-4" /></button>
        <button className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600" onClick={onDelete} aria-label={`מחיקת ${r.id}`}><Trash2 className="h-4 w-4" /></button>
      </div>
      {open && (
        <div className="space-y-3 border-t border-slate-100 px-3 py-3">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Field label="כותרת ההמלצה (בדוח)">
              <input className="input w-full" value={r.title || ''} placeholder={titles[metric] || ''} onChange={(e) => set({ title: e.target.value })} />
            </Field>
            <Field label="שם הנתון (לשימוש פנימי)">
              <input className="input w-full" value={r.name || ''} onChange={(e) => set({ name: e.target.value })} />
            </Field>
          </div>
          <div>
            <div className="mb-1 text-xs font-medium text-slate-600">מתי ההמלצה מופיעה</div>
            {r.type === 'AND' ? (
              <div className="space-y-2">
                {r.conditions.map((c, k) => (
                  <div key={k} className="flex items-center gap-2">
                    {k > 0 && <span className="text-xs font-bold text-brand-700">וגם</span>}
                    <CondEditor c={c} metrics={metrics} kinds={kinds}
                      onChange={(patch) => set({ conditions: r.conditions.map((x, j) => (j === k ? { ...x, ...patch } : x)) })}
                      onRemove={r.conditions.length > 2 ? () => set({ conditions: r.conditions.filter((_, j) => j !== k) }) : null} />
                  </div>
                ))}
                <button className="btn-ghost px-2 text-xs" onClick={() => set({ conditions: [...r.conditions, { metric: 'Equity_Total', dir: 'ABOVE', min: 0, max: null }] })}>
                  <Plus className="h-3.5 w-3.5" />תנאי נוסף
                </button>
              </div>
            ) : (
              <CondEditor c={r} metrics={metrics} kinds={kinds} onChange={(patch) => set(patch)} />
            )}
          </div>
          <Field label="ניסוח ההמלצה">
            <textarea className="input min-h-[120px] w-full leading-relaxed" value={r.text || ''} onChange={(e) => set({ text: e.target.value })} />
          </Field>
          <p className="text-[11px] leading-relaxed text-slate-500">
            <b>XX</b> מוחלף בערך מהתיק{r.type === 'AND' ? ' (התנאי הראשון)' : ''}{r.type === 'AND' ? <>; <b>YY</b> – בערך של התנאי השני</> : ''}.
            {' '}מקרים מיוחדים: בריכוזיות בנייר בודד XX = מספר הניירות מעל הסף; בקרנות מנוהלות YY = דמי הניהול האפקטיביים.
            {' '}״גבוה מ-״ / ״נמוך מ-״ הם השוואה חזקה (ערך ששווה בדיוק לסף לא מפעיל את הכלל).
          </p>
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------- dialog
export default function RulesDialog({ onClose, onChanged }) {
  const [doc, setDoc] = useState(null)
  const [preview, setPreview] = useState(null)
  const [file, setFile] = useState(null)
  const [draft, setDraft] = useState(null) // rules being edited on the site
  const [openId, setOpenId] = useState(null)
  const [user, setU] = useState(getUser())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => { prospectRules().then(setDoc).catch((e) => setError(e.message)) }, [])
  const metrics = doc?.metrics || {}
  const kinds = doc?.metric_kinds || {}
  const titles = doc?.titles || {}
  const changed = useMemo(() => draft && doc && JSON.stringify(draft) !== JSON.stringify(doc.rules), [draft, doc])

  const pick = async (f) => {
    if (!f) return
    setFile(f); setBusy(true); setError(null)
    try { setPreview(await prospectRulesImport(f, user, false)) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const commitImport = async () => {
    if (!user.trim()) { setError('יש להזין שם עורך'); return }
    setBusy(true); setUser(user)
    try {
      await prospectRulesImport(file, user, true)
      setDoc(await prospectRules()); setPreview(null); setFile(null); onChanged?.()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const saveDraft = async () => {
    if (!user.trim()) { setError('יש להזין שם עורך'); return }
    setBusy(true); setError(null); setUser(user)
    try {
      await prospectRulesSave(draft.map(({ _new, ...r }) => r), user.trim())
      setDoc(await prospectRules()); setDraft(null); setOpenId(null); onChanged?.()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const add = (type) => {
    const id = nextId(draft)
    const r = type === 'AND'
      ? { id, type: 'AND', name: '', title: '', text: '', conditions: [
        { metric: 'Funds_Fee_Avg', dir: 'ABOVE', min: 0, max: 0.008 }, { metric: 'Funds_ETF_Share', dir: 'ABOVE', min: 0, max: 0.5 }] }
      : { id, type: 'SINGLE', metric: 'Equity_Total', name: '', title: '', dir: 'ABOVE', min: 0, max: 0.7, text: '' }
    setDraft([...draft, r]); setOpenId(id)
  }
  const del = (id) => {
    if (!window.confirm(`למחוק את הכלל ${id}? אפשר גם רק לכבות אותו (״פעיל״).`)) return
    setDraft(draft.filter((r) => r.id !== id))
  }
  const close = () => {
    if (changed && !window.confirm('יש שינויים בכללים שלא נשמרו. לסגור בכל זאת?')) return
    onClose()
  }

  const footer = preview ? (
    <>
      <button className="btn-ghost" onClick={() => { setPreview(null); setFile(null) }}>ביטול</button>
      <button className="btn-primary" disabled={busy} onClick={commitImport}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}החלפת הכללים ({preview.rules.length})</button>
    </>
  ) : draft ? (
    <>
      <input className="input ml-auto w-40" value={user} onChange={(e) => setU(e.target.value)} placeholder="שם העורך" aria-label="שם העורך" />
      <button className="btn-ghost" onClick={() => { if (!changed || window.confirm('לבטל את השינויים?')) { setDraft(null); setOpenId(null) } }}>ביטול</button>
      <button className="btn-primary" disabled={busy || !changed} onClick={saveDraft}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}שמירת הכללים</button>
    </>
  ) : <button className="btn-ghost" onClick={close}>סגירה</button>

  return (
    <Modal wide title="כללי התובנות" onClose={close}
      subtitle={doc ? `מקור: ${doc.source || '—'} · עודכן ע״י ${doc.updated_by || '—'}${doc.updated_at ? ` · ${fmtDate(doc.updated_at)}` : ''}` : 'טוען…'}
      footer={footer}>
      <div className="space-y-4">
        {error && <p className="flex items-center gap-2 text-sm text-red-700"><AlertTriangle className="h-4 w-4 shrink-0" />{error}</p>}
        {draft ? (
          <>
            <p className="text-sm text-slate-600">
              עריכת הכללים ישירות באתר. כל כלל בודק נתון מהתיק מול סף – כשהתנאי מתקיים ההמלצה מופיעה בניתוח ובסקירה ללקוח.
              השינויים נשמרים לכל המשתמשים רק בלחיצה על ״שמירת הכללים״.
            </p>
            <div className="max-h-[58vh] space-y-2 overflow-auto pl-1">
              {draft.map((r) => (
                <RuleEditor key={r.id} r={r} metrics={metrics} kinds={kinds} titles={titles} open={openId === r.id}
                  onOpen={() => setOpenId(openId === r.id ? null : r.id)}
                  onChange={(nr) => setDraft(draft.map((x) => (x.id === r.id ? nr : x)))} onDelete={() => del(r.id)} />
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="btn-outline" onClick={() => add('SINGLE')}><Plus className="h-4 w-4" />כלל חדש</button>
              <button className="btn-ghost" onClick={() => add('AND')} title="כמה תנאים שכולם צריכים להתקיים"><Plus className="h-4 w-4" />כלל משולב (וגם)</button>
            </div>
          </>
        ) : (
          <>
            <p className="text-sm text-slate-600">
              כל כלל בודק נתון אחד מול סף: <b>גבוה מ-</b> – ההמלצה מופיעה כשהערך מעל הסף, <b>נמוך מ-</b> – כשהוא מתחת לו. XX / YY בניסוח מוחלפים בערכים מהתיק.
              אפשר לערוך, להוסיף ולכבות כללים כאן באתר, או לעבוד באקסל ולהעלות את הקובץ.
            </p>
            <div className="flex flex-wrap gap-2">
              <button className="btn-primary" disabled={!doc || !!preview} onClick={() => { setDraft(structuredClone(doc.rules)); setError(null) }}>
                <Pencil className="h-4 w-4" />עריכת הכללים באתר
              </button>
              <a className="btn-outline" href="/api/prospect/rules.xlsx" download><Download className="h-4 w-4" />הורדת הכללים (Excel)</a>
              <label className="btn-outline cursor-pointer"><Upload className="h-4 w-4" />העלאת קובץ כללים מעודכן
                <input type="file" accept=".xlsx" className="hidden" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = '' }} />
              </label>
            </div>
            {preview ? (
              <>
                <div className="rounded-lg bg-brand-50 p-3 text-sm text-brand-900">תצוגה מקדימה של {file?.name}: {preview.rules.length} כללים. שום דבר לא נשמר עד לאישור.</div>
                {preview.warnings.length > 0 && <ul className="space-y-1 text-xs text-amber-800">{preview.warnings.map((w) => <li key={w}>• {w}</li>)}</ul>}
                <RulesTable rules={preview.rules} metrics={metrics} kinds={kinds} />
                <Field label="שם העורך"><input className="input w-full" value={user} onChange={(e) => setU(e.target.value)} /></Field>
              </>
            ) : doc && <RulesTable rules={doc.rules} metrics={metrics} kinds={kinds} />}
          </>
        )}
      </div>
    </Modal>
  )
}
