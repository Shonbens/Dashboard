import { Fragment, useEffect, useRef, useState } from 'react'
import { ArrowDownUp, Trash2 } from 'lucide-react'
import {
  COUNTRIES, FOREIGN_EXPOSURES, GICS_HE, GROUP_TOTAL, IL_INDEX_LABELS, IL_MEMO_SECTORS, IL_SECTORS, RATING_BUCKETS, SECTIONS, sectionsFor,
} from '../../lib/allocation'

const p2 = (v, d = 2) => (v == null || Number.isNaN(v) ? '' : `${v.toFixed(d)}%`)
const d2 = (v) => (v == null || Number.isNaN(v) ? '' : v.toFixed(2))

const SRC_LABEL = { maya: 'מאי״ה', yfinance: 'Yahoo Finance', estimate: 'הערכה', manual: 'הוזן ידנית', name: 'לפי שם הנייר' }

/** Excel-like movement between editable cells: Enter / ↓ next row, ↑ previous row. */
function gridKeys(e) {
  if (!['Enter', 'ArrowDown', 'ArrowUp'].includes(e.key)) return
  const { col, row } = e.currentTarget.dataset
  const all = [...document.querySelectorAll(`[data-col="${col}"]`)]
  const i = all.findIndex((x) => x.dataset.row === row)
  const next = all[i + (e.key === 'ArrowUp' ? -1 : 1)]
  if (next) { e.preventDefault(); next.focus(); next.select?.() }
}

/**
 * Paste a column copied from Excel into "אחוז ראשי": fills this row and the ones below it.
 * Accepts "2.5%", "2.5", "1,250" and Excel fractions (0.025 when the copied cells were formatted as plain numbers).
 */
export function parseColumn(text) {
  const cells = text.split(/\r?\n/).map((ln) => ln.split('\t')[0].trim()).filter((c, i, a) => c !== '' || i < a.length - 1)
  while (cells.length && cells[cells.length - 1] === '') cells.pop()
  const hasPct = cells.some((c) => c.includes('%'))
  const nums = cells.map((c) => {
    const v = Number(c.replace(/[%,\s₪]/g, ''))
    return c === '' || Number.isNaN(v) ? null : v
  })
  const vals = nums.filter((v) => v != null)
  const fractions = !hasPct && vals.length > 0 && vals.every((v) => v <= 1) && cells.some((c) => /\.\d{3,}/.test(c))
  return nums.map((v) => (v == null ? null : fractions ? v * 100 : v))
}

function pasteKeys(e, onWeights) {
  const text = e.clipboardData?.getData('text') || ''
  const vals = parseColumn(text)
  if (vals.length < 2 && !text.includes('%')) return // a single plain number: let the input handle it
  e.preventDefault()
  const all = [...document.querySelectorAll('[data-col="E"]')]
  const start = all.findIndex((x) => x === e.currentTarget)
  const updates = []
  vals.forEach((v, k) => {
    const el = all[start + k]
    if (el && v != null) updates.push([Number(el.dataset.ri), Math.max(0, v)])
  })
  onWeights(updates, vals.length > all.length - start ? vals.length - (all.length - start) : 0)
}

/** A value that comes from the market data (Maya / Yahoo) and can be overridden by hand for all models. */
function DataCell({ value, source, by, kind = 'num', suffix = '', onSave, width = 'w-16', placeholder = '' }) {
  const [edit, setEdit] = useState(false)
  const [v, setV] = useState('')
  const ref = useRef(null)
  useEffect(() => { if (edit) { ref.current?.focus(); ref.current?.select() } }, [edit])
  const show = value == null || value === '' ? '' : kind === 'num' ? `${Number(value).toFixed(2)}${suffix}` : String(value)
  const commit = () => {
    setEdit(false)
    const raw = v.trim()
    const next = raw === '' ? null : kind === 'num' ? Number(raw.replace('%', '')) : raw
    if (kind === 'num' && next != null && Number.isNaN(next)) return
    if (next !== value) onSave(next)
  }
  if (edit) {
    return (
      <input ref={ref} value={v} onChange={(e) => setV(e.target.value)} onBlur={commit} dir="ltr"
        onKeyDown={(e) => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEdit(false) }}
        className={`num ${width} rounded border border-brand-400 bg-surface px-1 py-0.5 text-left text-xs focus:outline-none`} />
    )
  }
  const title = source ? `${SRC_LABEL[source] || source}${by ? ` · ${by}` : ''} · לחיצה לעריכה (מתעדכן בכל המודלים)` : 'אין נתון – לחיצה להזנה (מתעדכן בכל המודלים)'
  return (
    <button type="button" onClick={() => { setV(value == null ? '' : String(value)); setEdit(true) }} title={title}
      className={`num min-w-[2.5rem] rounded px-1 py-0.5 text-left text-xs hover:bg-brand-50 ${source === 'manual' ? 'font-semibold text-brand-800' : source === 'estimate' ? 'italic text-slate-500' : 'text-slate-700'}`}>
      {show || <span className="text-slate-300">{placeholder || '—'}</span>}
      {source === 'estimate' && show && <span className="text-slate-400">~</span>}
    </button>
  )
}

const Sel = ({ value, onChange, children, label, className = '' }) => (
  <select value={value ?? ''} onChange={(e) => onChange(e.target.value || null)} aria-label={label}
    className={`max-w-[9.5rem] rounded border border-transparent bg-transparent px-0.5 py-0.5 text-xs text-slate-600 hover:border-slate-200 focus:border-brand-400 focus:outline-none ${className}`}>
    {children}
  </select>
)

/** The per-row classification that drives the Excel's SUMIF tables (sector, index, rating bucket, sleeve). */
function Classify({ r, onRow, template }) {
  const sec = r.section
  if (sec === 'eq_il') {
    return (
      <Sel value={r.sector} onChange={(v) => onRow({ sector: v })} label="ענף / מדד">
        <option value="">ענף…</option>
        <optgroup label="מדד">{Object.keys(IL_INDEX_LABELS).map((k) => <option key={k} value={k}>{k}</option>)}</optgroup>
        <optgroup label="ענף">{[...IL_SECTORS, ...IL_MEMO_SECTORS].map((k) => <option key={k} value={k}>{k}</option>)}</optgroup>
      </Sel>
    )
  }
  if (sec === 'eq_foreign') {
    return (
      <div className="flex items-center gap-1">
        <Sel value={r.exposure} onChange={(v) => onRow({ exposure: v })} label="חשיפה">
          <option value="">לפי אזורים</option>
          {FOREIGN_EXPOSURES.map((k) => <option key={k} value={k}>{GICS_HE[k] ? `${GICS_HE[k]} (ישיר)` : k}</option>)}
        </Sel>
        <Sel value={r.country} onChange={(v) => onRow({ country: v })} label="מדינת חשיפה" className="max-w-[5.5rem]">
          <option value="">מדינה…</option>
          {COUNTRIES.filter((c) => c !== 'ישראל').map((c) => <option key={c} value={c}>{c}</option>)}
        </Sel>
        <label className="flex items-center gap-0.5 text-[11px] text-slate-500" title="מנוטרל מט״ח – לא נספר בחשיפת המט״ח">
          <input type="checkbox" checked={!!r.hedged} onChange={(e) => onRow({ hedged: e.target.checked })} className="h-3 w-3" />נטרול
        </label>
      </div>
    )
  }
  if (sec === 'funds') {
    const eqFund = r.sleeve === 'equity'
    return (
      <div className="flex items-center gap-1">
        <Sel value={r.row.sleeve || ''} onChange={(v) => onRow({ sleeve: v })} label="רכיב" className="max-w-[5.5rem]">
          <option value="">{eqFund ? 'מניות (אוטו׳)' : 'אג״ח (אוטו׳)'}</option>
          <option value="equity">רכיב מניות</option>
          <option value="bond">רכיב אג״ח</option>
        </Sel>
        {eqFund ? (
          <Sel value={r.row.exposure} onChange={(v) => onRow({ exposure: v })} label="חשיפה">
            <option value="">{template === 'israel' ? 'קרן מניות' : 'לפי אזורים'}</option>
            <option value="יתר">קרן יתר (ישראל)</option>
            {template === 'israel' && <option value="MID">MID (ישראל)</option>}
            {template !== 'israel' && FOREIGN_EXPOSURES.slice(0, 6).map((k) => <option key={k} value={k}>{k}</option>)}
          </Sel>
        ) : (
          <Sel value={r.row.bucket} onChange={(v) => onRow({ bucket: v ? Number(v) : null })} label="קבוצת סיכון">
            <option value="">{r.bucket ? `${RATING_BUCKETS.find((b) => b.key === r.bucket)?.label} (מאי״ה)` : 'סיכון…'}</option>
            {RATING_BUCKETS.map((b) => <option key={b.key} value={b.key}>{b.label}</option>)}
          </Sel>
        )}
      </div>
    )
  }
  if (r.sec?.rated) {
    return (
      <div className="flex items-center gap-1">
        <Sel value={r.row.bucket} onChange={(v) => onRow({ bucket: v ? Number(v) : null })} label="קבוצת סיכון" className="max-w-[6rem]">
          <option value="">סיכון…</option>
          {RATING_BUCKETS.map((b) => <option key={b.key} value={b.key}>{b.label}</option>)}
        </Sel>
        <Sel value={r.row.industry} onChange={(v) => onRow({ industry: v })} label="ענף" className="max-w-[6.5rem]">
          <option value="">ענף…</option>
          {['נדלן מניב בישראל', 'בנקים', 'ביטוח', 'תשתיות ואנרגיה', 'תעשייה', 'מסחר ושרותים', 'השקעה ואחזקות', 'אחר'].map((k) => <option key={k} value={k}>{k}</option>)}
        </Sel>
      </div>
    )
  }
  return <span className="text-xs text-slate-300">—</span>
}

const COLS = [
  ['שיוך', ''], ['אחוז ראשי', 'E – משקל בתוך הרכיב (מניות / אג״ח)'], ['אחוז יחסי', 'F – משקל בתיק'], ['תשואה ברוטו', 'G'],
  ['מתחילת חודש', 'H'], ['מתחילת שנה', 'I'], ['מרווח', 'J'], ['אינפ׳ גלומה', 'K'], ['תשואה פנימית', 'L = (K+G)×F ÷ סה״כ אג״ח'],
  ['מח״מ', 'M'], ['מח״מ בתיק', 'N = M×F ÷ (100% − מניות)'], ['דמי ניהול', 'O – חוזה כולל מע״מ, או דמי הקרן'],
  ['ד״נ בתיק', 'P = O×F'], ['מעלות', 'Q'], ['מידרוג', 'R'],
]

export default function AllocationSheet({ res, template, onWeight, onWeights, onRow, onRemove, onMove, onData }) {
  const groups = []
  for (const sec of sectionsFor(template)) {
    const g = groups.find((x) => x.group === sec.group)
    if (g) g.sections.push(sec)
    else groups.push({ group: sec.group, sections: [sec] })
  }
  let rowIndex = 0
  const totalCells = (t, opts = {}) => (
    <>
      <td className="tdc num text-xs">{opts.noE ? '' : p2(t.E)}</td>
      <td className="tdc num text-xs">{p2(t.F)}</td>
      <td className="tdc num text-xs">{p2(t.G)}</td>
      <td className="tdc num text-xs">{p2(t.H, 3)}</td>
      <td className="tdc num text-xs">{p2(t.I, 3)}</td>
      <td className="tdc" /><td className="tdc" />
      <td className="tdc num text-xs">{p2(t.L, 3)}</td>
      <td className="tdc num text-xs">{d2(t.M)}</td>
      <td className="tdc num text-xs">{d2(t.N)}</td>
      <td className="tdc" />
      <td className="tdc num text-xs">{p2(t.P, 3)}</td>
      <td className="tdc" colSpan={3} />
    </>
  )

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[1500px] text-sm">
        <thead className="sticky top-0 z-10 bg-slate-50">
          <tr>
            <th className="th sticky right-0 z-10 min-w-[230px] bg-slate-50">נייר</th>
            {COLS.map(([l, t]) => <th key={l} className="th" title={t}>{l}</th>)}
            <th className="th w-14" />
          </tr>
        </thead>
        <tbody>
          {groups.map(({ group, sections }) => {
            const gTotal = sections.reduce((acc, s) => {
              const t = res.secTotal[s.key]
              acc.F += t.F; acc.E += t.E; acc.L += t.L || 0; acc.N += t.N || 0; acc.P += t.P || 0
              return acc
            }, { E: 0, F: 0, L: 0, N: 0, P: 0 })
            return (
              <Fragment key={group}>
                {sections.map((sec) => {
                  const rows = res.rows.filter((r) => r.section === sec.key)
                  const t = res.secTotal[sec.key]
                  const contrib = res.contrib[sec.key] || 0
                  if (!rows.length && contrib < 0.0005 && sec.key !== 'funds' && !['eq_il', 'eq_foreign'].includes(sec.key)) {
                    return (
                      <tr key={sec.key} className="border-t border-slate-100">
                        <td className="tdc sticky right-0 bg-surface text-xs font-semibold text-slate-400">{sec.label}</td>
                        <td className="tdc text-xs text-slate-300" colSpan={COLS.length + 1}>ריק</td>
                      </tr>
                    )
                  }
                  return (
                    <Fragment key={sec.key}>
                      <tr className="border-t-2 border-slate-200 bg-brand-50/40">
                        <td className="tdc sticky right-0 bg-brand-50 text-xs font-bold text-brand-900" colSpan={1}>{sec.label}</td>
                        <td className="tdc text-[11px] text-slate-500" colSpan={COLS.length + 1}>
                          {sec.sleeve === 'equity' ? 'רכיב מניות' : sec.sleeve === 'bond' ? 'רכיב אג״ח' : 'לפי סוג הקרן'}
                          {sec.cpi && ' · אינפלציה גלומה נוספת לתשואה'}
                        </td>
                      </tr>
                      {rows.map((r) => {
                        const i = rowIndex++
                        const src = r.d.sources || {}
                        const dup = res.dupIds.has(r.id)
                        return (
                          <tr key={`${r.id}-${r.i}`} className={`group border-t border-slate-100 hover:bg-slate-50/70 ${dup ? 'bg-red-50' : ''}`}>
                            <td className="tdc sticky right-0 max-w-[260px] bg-surface group-hover:bg-slate-50">
                              <div dir="auto" className="truncate text-[13px] font-medium text-slate-800" title={r.name}>{r.name}</div>
                              <div className="num text-[11px] text-slate-400">{r.id}{r.d.priced === false && <span className="text-amber-700"> · לא זוהה</span>}{dup && <span className="text-red-700"> · כפול</span>}</div>
                            </td>
                            <td className="tdc"><Classify r={{ ...r, row: res.config.rows[r.i] }} template={template} onRow={(patch) => onRow(r.i, patch)} /></td>
                            <td className="tdc">
                              <div className="flex items-center gap-0.5">
                                <input type="number" min="0" step="0.5" value={Number((r.E || 0).toFixed(4))} onChange={(e) => onWeight(r.i, e.target.value)}
                                  data-col="E" data-row={i} data-ri={r.i} onKeyDown={gridKeys} onFocus={(e) => e.target.select()} aria-label={`אחוז ראשי ${r.name}`}
                                  onPaste={(e) => onWeights && pasteKeys(e, onWeights)} title="אפשר להדביק עמודה שלמה מאקסל"
                                  className="num w-16 rounded border border-slate-200 bg-surface px-1 py-0.5 text-left text-xs font-semibold focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100" />
                                <span className="text-[11px] text-slate-400">%</span>
                              </div>
                            </td>
                            <td className="tdc num text-xs font-semibold text-slate-800">{p2(r.F)}</td>
                            <td className="tdc"><DataCell value={r.G} source={src.yield} by={r.d.manual_by} suffix="%" onSave={(v) => onData(r.id, { yield: v })} /></td>
                            <td className={`tdc num text-xs ${r.H < 0 ? 'text-red-700' : ''}`}>{p2(r.H)}</td>
                            <td className={`tdc num text-xs ${r.I < 0 ? 'text-red-700' : ''}`}>{p2(r.I)}</td>
                            <td className="tdc"><DataCell value={r.J} source={src.spread} by={r.d.manual_by} suffix="%" onSave={(v) => onData(r.id, { spread: v })} /></td>
                            <td className="tdc num text-xs text-slate-500">{p2(r.K)}</td>
                            <td className="tdc num text-xs">{p2(r.L, 3)}</td>
                            <td className="tdc"><DataCell value={r.M} source={src.duration} by={r.d.manual_by} onSave={(v) => onData(r.id, { duration: v })} /></td>
                            <td className="tdc num text-xs">{d2(r.N)}</td>
                            <td className="tdc">
                              {r.section === 'funds'
                                ? <DataCell value={r.O} source={src.fee} by={r.d.manual_by} suffix="%" onSave={(v) => onData(r.id, { fee: v })} />
                                : <span className="num text-xs text-slate-500" title="דמי ניהול חוזה כולל מע״מ">{p2(r.O)}</span>}
                            </td>
                            <td className="tdc num text-xs">{p2(r.P, 3)}</td>
                            <td className="tdc"><DataCell kind="text" value={r.Q} source={src.maalot} by={r.d.manual_by} width="w-14" onSave={(v) => onData(r.id, { maalot: v })} /></td>
                            <td className="tdc"><DataCell kind="text" value={r.R} source={src.midroog} by={r.d.manual_by} width="w-14" onSave={(v) => onData(r.id, { midroog: v })} /></td>
                            <td className="tdc">
                              <div className="flex items-center opacity-0 transition focus-within:opacity-100 group-hover:opacity-100">
                                <label className="relative rounded p-1 text-slate-400 hover:bg-slate-100" title="העברה לסעיף אחר">
                                  <ArrowDownUp className="h-3.5 w-3.5" />
                                  <select className="absolute inset-0 cursor-pointer opacity-0" value={r.section} onChange={(e) => onMove(r.i, e.target.value)} aria-label="העברה לסעיף">
                                    {sectionsFor(template).map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
                                  </select>
                                </label>
                                <button onClick={() => onRemove(r.i)} aria-label={`הסרת ${r.name}`} className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600">
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                      {contrib >= 0.0005 && (
                        <tr className="border-t border-dashed border-slate-200 text-slate-500">
                          <td className="tdc sticky right-0 bg-surface text-xs italic" title="חלק הקרנות (שיקוף מאי״ה) שמושקע בסעיף זה">תרומת קרנות</td>
                          <td className="tdc" /><td className="tdc" />
                          <td className="tdc num text-xs italic">{p2(contrib)}</td>
                          <td className="tdc" colSpan={COLS.length - 2} />
                        </tr>
                      )}
                      <tr className="border-t border-slate-200 bg-slate-50/80 font-semibold text-slate-700">
                        <td className="tdc sticky right-0 bg-slate-50 text-xs">{sec.total || `סה״כ ${sec.label}`}</td>
                        <td className="tdc" />
                        {totalCells(t)}
                        <td className="tdc" />
                      </tr>
                    </Fragment>
                  )
                })}
                {sections.length > 1 && (
                  <tr className="border-t-2 border-slate-300 bg-slate-100 font-bold text-slate-900">
                    <td className="tdc sticky right-0 bg-slate-100 text-xs">{GROUP_TOTAL[group]}</td>
                    <td className="tdc" />
                    {totalCells({ ...gTotal, G: null, H: null, I: null, M: null }, { noE: group !== 'equity' })}
                    <td className="tdc" />
                  </tr>
                )}
              </Fragment>
            )
          })}
          <tr className="border-t-2 border-slate-300 bg-slate-100 font-bold text-slate-900">
            <td className="tdc sticky right-0 bg-slate-100 text-xs">עו״ש</td>
            <td className="tdc" /><td className="tdc" />
            <td className={`tdc num text-xs ${res.summary.cash < -0.005 ? 'text-red-700' : ''}`}>{p2(res.summary.cash)}</td>
            <td className="tdc" colSpan={7} />
            <td className="tdc num text-xs text-slate-500">{p2(res.summary.feeVat)}</td>
            <td className="tdc num text-xs">{p2((res.summary.feeVat * Math.max(0, res.summary.cash)) / 100, 3)}</td>
            <td className="tdc" colSpan={3} />
          </tr>
        </tbody>
      </table>
    </div>
  )
}

export { SECTIONS }
