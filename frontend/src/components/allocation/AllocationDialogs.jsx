import { useState } from 'react'
import { Loader2, Upload } from 'lucide-react'
import Modal from '../models/Modal'
import { Field } from '../models/NewModelDialog'
import { DEFAULT_REFS, DEFAULT_SETTINGS, FOREIGN_COLUMNS, GICS_HE, IL_COLUMNS } from '../../lib/allocation'
import { getUser, secdataImport, setUser } from '../../lib/api'

const Num = ({ value, onChange, step = '0.01', w = 'w-20', label }) => (
  <input type="number" step={step} value={value ?? ''} aria-label={label} onChange={(e) => onChange(e.target.value === '' ? 0 : Number(e.target.value))}
    className={`num ${w} rounded-md border border-slate-200 bg-surface px-1.5 py-1 text-left text-sm focus:border-brand-400 focus:outline-none`} />
)

function Matrix({ title, rows, columns, value, onChange, labelOf = (r) => r }) {
  return (
    <div>
      <div className="mb-1 text-sm font-semibold text-slate-700">{title}</div>
      <div className="max-h-72 overflow-auto rounded-lg border border-slate-200">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-slate-50"><tr><th className="th">ענף</th>{columns.map((c) => <th key={c.key} className="th">{c.label}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r) => (
              <tr key={r}>
                <td className="td text-slate-700">{labelOf(r)}</td>
                {columns.map((c) => (
                  <td key={c.key} className="px-1 py-1">
                    <Num w="w-16" label={`${r} ${c.label}`} value={value[r]?.[c.key] ?? 0} onChange={(v) => onChange({ ...value, [r]: { ...(value[r] || {}), [c.key]: v } })} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-slate-50 font-semibold">
            <tr><td className="td">סה״כ</td>{columns.map((c) => <td key={c.key} className="td num">{rows.reduce((s, r) => s + (r === 'שבבים' ? 0 : (value[r]?.[c.key] || 0)), 0).toFixed(1)}</td>)}</tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}

/** The constants that sit in the Excel's side cells: contract fee, VAT, embedded inflation, bands and index compositions. */
export function SettingsDialog({ config, onClose, onApply }) {
  const [s, setS] = useState(config.settings)
  const [refs, setRefs] = useState(config.refs)
  const [tab, setTab] = useState('general')
  const band = (k, i, v) => setS({ ...s, bands: { ...s.bands, [k]: s.bands[k].map((x, j) => (j === i ? v : x)) } })
  const BANDS = [['duration', 'סה״כ מח״מ בתיק', ''], ['linked', 'צמוד (יחסי)', '%'], ['shekel', 'שקלי (יחסי)', '%'], ['foreign_eq', 'מניות חו״ל מתוך המניות', '%']]
  return (
    <Modal wide title="הגדרות והנחות המודל" subtitle="התאים הקבועים מגיליון האקסל – נשמרים עם המודל ונרשמים בגרסה" onClose={onClose}
      footer={<>
        <button className="btn-ghost ml-auto" onClick={() => { setS({ ...DEFAULT_SETTINGS, fund_cap: s.fund_cap }); setRefs(structuredClone(DEFAULT_REFS)) }}>איפוס לברירת המחדל</button>
        <button className="btn-ghost" onClick={onClose}>ביטול</button>
        <button className="btn-primary" onClick={() => onApply({ settings: s, refs })}>החלה</button>
      </>}>
      <div className="mb-4 flex gap-1 border-b border-slate-200">
        {[['general', 'כללי וטווחים'], ['il', 'הרכב מדדים – ישראל'], ['foreign', 'הרכב מדדים – חו״ל'], ['re', 'נדל״ן מניב']].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === k ? 'border-brand-700 font-semibold text-brand-800' : 'border-transparent text-slate-500'}`}>{l}</button>
        ))}
      </div>
      {tab === 'general' && (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <div className="space-y-3">
            <Field label="דמי ניהול חוזה (%)"><Num value={s.contract_fee} onChange={(v) => setS({ ...s, contract_fee: v })} /></Field>
            <Field label="מע״מ (%)"><Num value={s.vat} onChange={(v) => setS({ ...s, vat: v })} step="1" /></Field>
            <Field label="אינפלציה גלומה (%) – מתווספת לתשואת האג״ח הצמודות"><Num value={s.inflation} onChange={(v) => setS({ ...s, inflation: v })} /></Field>
            <Field label="מגבלת קרנות (% מהתיק)"><Num value={s.fund_cap} onChange={(v) => setS({ ...s, fund_cap: v })} step="1" /></Field>
            <Field label="חלק בית ההשקעות בדמי ניהול קרנות (%)">
              <div className="flex items-center gap-2 text-xs text-slate-500">
                אג״ח <Num value={s.rev_share_bond} onChange={(v) => setS({ ...s, rev_share_bond: v })} step="1" w="w-16" />
                מניות <Num value={s.rev_share_equity} onChange={(v) => setS({ ...s, rev_share_equity: v })} step="1" w="w-16" />
              </div>
            </Field>
          </div>
          <div>
            <div className="mb-2 text-sm font-medium text-slate-700">טווחי בקרה (מסומנים באדום כשחורגים)</div>
            <div className="space-y-2">
              {BANDS.map(([k, l, u]) => (
                <div key={k} className="flex items-center gap-2 text-sm">
                  <span className="w-44 text-slate-600">{l}</span>
                  <Num value={s.bands[k][0]} onChange={(v) => band(k, 0, v)} w="w-16" label={`${l} מינימום`} />–
                  <Num value={s.bands[k][1]} onChange={(v) => band(k, 1, v)} w="w-16" label={`${l} מקסימום`} /><span className="text-slate-400">{u}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      {tab === 'il' && (
        <Matrix title="משקל כל ענף בכל מדד/קרן (%)" rows={Object.keys(refs.il_sectors)} columns={IL_COLUMNS} value={refs.il_sectors}
          onChange={(v) => setRefs({ ...refs, il_sectors: v })} />
      )}
      {tab === 'foreign' && (
        <Matrix title="משקל כל ענף בכל מדד (%) · ״שבבים״ הוא פירוט מתוך טכנולוגיה" rows={Object.keys(refs.foreign_sectors)} columns={FOREIGN_COLUMNS}
          value={refs.foreign_sectors} onChange={(v) => setRefs({ ...refs, foreign_sectors: v })} labelOf={(r) => GICS_HE[r] || r} />
      )}
      {tab === 're' && (
        <div className="space-y-3">
          <Field label="מדד ייחוס – תל בונד 60 (%)"><Num value={refs.re_benchmark} onChange={(v) => setRefs({ ...refs, re_benchmark: v })} /></Field>
          <div className="text-sm text-slate-600">שיעור הנדל״ן המניב לפי שם הנייר/הקרן (ביטוי רגולרי). ערך שהוזן לנייר בנתוני השוק גובר.</div>
          {refs.re_patterns.map((p, i) => (
            <div key={i} className="flex items-center gap-2">
              <input className="input flex-1 text-xs" dir="auto" value={p.pattern} onChange={(e) => setRefs({ ...refs, re_patterns: refs.re_patterns.map((x, j) => (j === i ? { ...x, pattern: e.target.value } : x)) })} />
              <Num value={p.share} onChange={(v) => setRefs({ ...refs, re_patterns: refs.re_patterns.map((x, j) => (j === i ? { ...x, share: v } : x)) })} />
              <button className="btn-ghost px-2 text-xs" onClick={() => setRefs({ ...refs, re_patterns: refs.re_patterns.filter((_, j) => j !== i) })}>הסרה</button>
            </div>
          ))}
          <button className="btn-outline text-xs" onClick={() => setRefs({ ...refs, re_patterns: [...refs.re_patterns, { pattern: '', share: 0 }] })}>הוספת שורה</button>
        </div>
      )}
    </Modal>
  )
}

const FIELD_HE = { yield: 'תשואה ברוטו', duration: 'מח״מ', spread: 'מרווח', maalot: 'דירוג מעלות', midroog: 'דירוג מידרוג', sector: 'ענף', industry: 'ענף אג״ח', fee: 'דמי ניהול', rating_bucket: 'קבוצת סיכון' }

/** Upload the ACE columns (yield, duration, spread, ratings…) for many securities at once. */
export function MarketDataDialog({ onClose, onDone }) {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [user, setU] = useState(getUser())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const pick = async (f) => {
    setFile(f); setPreview(null); setError(null)
    if (!f) return
    setBusy(true)
    try { setPreview(await secdataImport(f, user, false)) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const commit = async () => {
    if (!user.trim()) { setError('יש להזין שם עורך'); return }
    setBusy(true); setUser(user)
    try { const r = await secdataImport(file, user, true); onDone(r) } catch (e) { setError(e.message); setBusy(false) }
  }
  return (
    <Modal wide title="ייבוא נתוני שוק" subtitle="קובץ אקסל/CSV עם ״מספר נייר״ ועמודות כמו תשואה ברוטו, מח״מ, מרווח, דירוג מעלות, דירוג מידרוג – למשל ייצוא מתוסף ACE" onClose={onClose}
      footer={<>
        <button className="btn-ghost" onClick={onClose}>ביטול</button>
        <button className="btn-primary" disabled={!preview?.count || busy} onClick={commit}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}עדכון {preview?.count || 0} ניירות</button>
      </>}>
      <div className="space-y-4">
        <label className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-300 p-6 text-sm text-slate-600 hover:border-brand-400 hover:bg-brand-50/40">
          <Upload className="h-5 w-5" />{file ? file.name : 'בחירת קובץ'}
          <input type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
        </label>
        {busy && !preview && <p className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="h-4 w-4 animate-spin" />קורא את הקובץ…</p>}
        {preview && (
          <>
            <p className="text-sm text-slate-700">נמצאו <b>{preview.count}</b> ניירות · עמודות: {preview.fields.map((f) => FIELD_HE[f] || f).join(', ')}</p>
            <div className="max-h-56 overflow-auto rounded-lg border border-slate-200">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-50"><tr><th className="th">מספר נייר</th>{preview.fields.map((f) => <th key={f} className="th">{FIELD_HE[f] || f}</th>)}</tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {preview.rows.slice(0, 50).map((r) => (
                    <tr key={r.id}><td className="td num">{r.id}</td>{preview.fields.map((f) => <td key={f} className="td num">{r[f] ?? ''}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-slate-500">ערכי אחוז ששמורים באקסל כשבר (0.0483) מומרים אוטומטית ל-4.83%. הערכים מתעדכנים בכל המודלים וגוברים על נתוני מאי״ה.</p>
          </>
        )}
        <Field label="שם העורך"><input className="input w-full" value={user} onChange={(e) => setU(e.target.value)} /></Field>
        {error && <p className="text-sm text-red-700">{error}</p>}
      </div>
    </Modal>
  )
}
