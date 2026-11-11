import { useEffect, useMemo, useState } from 'react'
import { Check, ClipboardCopy, Loader2 } from 'lucide-react'
import { listModels, secdataLookup } from '../../lib/api'
import { TEMPLATES, compute, hydrate } from '../../lib/allocation'
import { navigate } from '../../lib/useHashRoute'
import { STATUS } from './shared'

/**
 * Bird's-eye summary of every allocation model – the managers' "summary" sheet: one row per model,
 * computed live with the same engine as each model's sheet.
 * Benchmark = blended reference return: bond benchmark × (1 − equity) + equity benchmark × equity (Excel column Y).
 */
const BENCH_KEY = 'ibi_benchmarks'
const DEFAULT_BENCH = { bond: 2.3, equity: 9.09 }
const loadBench = () => { try { return { ...DEFAULT_BENCH, ...JSON.parse(localStorage.getItem(BENCH_KEY) || '{}') } } catch { return DEFAULT_BENCH } }

const pct = (v, d = 2) => (v == null || Number.isNaN(v) ? '—' : `${v.toFixed(d)}%`)
const inBand = (v, b) => !b || v == null || (v >= b[0] - 1e-9 && v <= b[1] + 1e-9)

const COLS = [
  { key: 'banks', label: 'בנקים', title: 'משקל הבנקים מתוך המניות בישראל' },
  { key: 'semis', label: 'שבבים', title: 'משקל השבבים מתוך המניות בחו״ל' },
  { key: 'fx', label: 'חשיפה למט״ח', title: 'מכלל התיק' },
  { key: 'il', label: 'מניות ישראל', title: 'מתוך סך המניות' },
  { key: 'foreign', label: 'מניות חו״ל', title: 'מתוך סך המניות', band: 'foreign_eq' },
  { key: 'position', label: 'פוזיציה מנייתית', title: 'מניות בפועל ÷ אחוז מנייתי' },
  { key: 'funds', label: 'אחוז קרנות', title: 'מכלל התיק', cap: true },
  { key: 'cash', label: 'עו״ש', title: 'מכלל התיק', cash: true },
  { key: 'shekel', label: 'שקלי', title: 'מכלל התיק' },
  { key: 'linked', label: 'צמוד', title: 'מכלל התיק' },
  { key: 'shekelShare', label: 'שיעור שקלי', title: 'מתוך צמוד + שקלי', band: 'shekel' },
  { key: 'linkedShare', label: 'שיעור צמוד', title: 'מתוך צמוד + שקלי', band: 'linked' },
  { key: 'duration', label: 'מח״מ', title: 'מח״מ התיק', band: 'duration', num: true },
  { key: 'irr', label: 'תשואה פנימית', title: 'תשואה פנימית של התיק' },
  { key: 'bench', label: 'בנצ׳מרק', title: 'אג״ח × (1 − מניות) + מניות × מניות' },
]

function rowOf(m, data, bench) {
  const cfg = hydrate({ ...m.config, equity: m.config?.equity ?? m.equity_target ?? 0 })
  const r = compute(cfg, cfg.equity, data)
  const s = r.summary
  const share = (list, name) => list.find((x) => x.sector === name)?.share ?? null
  const eq = Number(cfg.equity) || 0
  return {
    id: m.id, name: m.name, status: m.status, equity: eq, template: cfg.template,
    type: `${TEMPLATES[cfg.template]?.label ?? ''} · מוגבל קרנות ${cfg.settings.fund_cap}%`,
    bands: cfg.settings.bands, fundCap: cfg.settings.fund_cap,
    missing: { irr: s.missingYield, duration: s.missingDuration },
    empty: cfg.rows.length === 0,
    v: {
      banks: share(r.ilSectors, 'בנקים'), semis: cfg.template === 'israel' ? 0 : share(r.foreignSectors, 'שבבים'),
      fx: s.fx, il: s.ilEqShare, foreign: s.foreignEqShare ?? 0, position: s.equityPosition, funds: s.funds, cash: s.cash,
      shekel: s.shekel, linked: s.linked, shekelShare: s.shekelShare, linkedShare: s.linkedShare, duration: s.duration, irr: s.irr,
      bench: bench.bond * (1 - eq / 100) + bench.equity * (eq / 100),
    },
  }
}

export default function ModelsSummaryTable({ tick = 0 }) {
  const [models, setModels] = useState(null)
  const [data, setData] = useState({})
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState(null)
  const [bench, setBench] = useState(loadBench)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let live = true
    setBusy(true)
    ;(async () => {
      try {
        const all = ((await listModels()).models || []).filter((m) => m.config && m.status !== 'archived')
        const ids = [...new Set(all.flatMap((m) => m.config.rows.map((r) => r.id)))]
        const d = ids.length ? await secdataLookup(ids) : {}
        if (live) { setModels(all); setData(d); setError(null) }
      } catch (e) { if (live) setError(e.message) } finally { if (live) setBusy(false) }
    })()
    return () => { live = false }
  }, [tick])

  const rows = useMemo(() => (models || []).map((m) => rowOf(m, data, bench))
    .sort((a, b) => (a.template === b.template ? a.equity - b.equity : a.template === 'global' ? -1 : 1)), [models, data, bench])

  const setB = (k, v) => {
    const next = { ...bench, [k]: v === '' ? 0 : Number(v) }
    setBench(next)
    try { localStorage.setItem(BENCH_KEY, JSON.stringify(next)) } catch { /* storage unavailable */ }
  }

  const copy = async () => {
    const head = ['מודל', 'סוג חשיפה', 'סוג מודל', ...COLS.map((c) => c.label)]
    const lines = rows.map((r) => [r.name, `מדיניות ${r.equity}%`, r.type,
      ...COLS.map((c) => (r.v[c.key] == null ? '' : c.num ? r.v[c.key].toFixed(2) : `${r.v[c.key].toFixed(2)}%`))])
    try {
      await navigator.clipboard.writeText([head, ...lines].map((l) => l.join('\t')).join('\n'))
      setCopied(true); setTimeout(() => setCopied(false), 1800)
    } catch { setError('ההעתקה נחסמה בדפדפן') }
  }

  if (!busy && !error && rows.length === 0) return null
  return (
    <section className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div>
          <h2 className="card-title">סיכום המודלים</h2>
          <p className="mt-0.5 text-xs text-slate-500">כל גיליונות ההקצאה במבט אחד · מחושב באותו מנוע כמו הגיליון של כל מודל · אדום = מחוץ לטווח שהוגדר במודל · ״חסרים״ = ניירות בלי תשואה / מח״מ, הערך חלקי · לחיצה על שורה פותחת את המודל</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span title="תשואת ייחוס לחישוב עמודת הבנצ׳מרק (נשמר בדפדפן הזה)">בנצ׳מרק:</span>
          <label className="flex items-center gap-1">אג״ח
            <input type="number" step="0.01" value={bench.bond} onChange={(e) => setB('bond', e.target.value)} className="num w-14 rounded border border-slate-200 bg-surface px-1 py-0.5 text-left" />%
          </label>
          <label className="flex items-center gap-1">מניות
            <input type="number" step="0.01" value={bench.equity} onChange={(e) => setB('equity', e.target.value)} className="num w-14 rounded border border-slate-200 bg-surface px-1 py-0.5 text-left" />%
          </label>
          <button className="btn-ghost px-2" onClick={copy} disabled={!rows.length} title="העתקת הטבלה להדבקה באקסל">
            {copied ? <Check className="h-4 w-4 text-emerald-600" /> : <ClipboardCopy className="h-4 w-4" />}{copied ? 'הועתק' : 'העתקה לאקסל'}
          </button>
        </div>
      </div>
      {error && <p className="px-5 py-3 text-sm text-red-700">{error}</p>}
      <div className={`overflow-x-auto ${busy ? 'opacity-60' : ''}`}>
        <table className="w-full min-w-[1400px] text-[13px]">
          <thead className="bg-slate-50">
            <tr>
              <th className="th sticky right-0 z-10 min-w-[220px] bg-slate-50">מודל</th>
              <th className="th">סוג חשיפה</th>
              <th className="th">סוג מודל</th>
              {COLS.map((c) => <th key={c.key} className="th text-left" title={c.title}>{c.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {busy && !rows.length && (
              <tr><td className="td text-slate-400" colSpan={COLS.length + 3}><Loader2 className="ml-2 inline h-4 w-4 animate-spin" />מחשב…</td></tr>
            )}
            {rows.map((r, i) => {
              const st = STATUS[r.status] ?? STATUS.draft
              const newGroup = i > 0 && rows[i - 1].template !== r.template
              return (
                <tr key={r.id} onClick={() => navigate(`/models/${r.id}`)}
                  className={`group cursor-pointer hover:bg-brand-50/50 ${newGroup ? 'border-t-2 border-slate-300' : 'border-t border-slate-100'}`}>
                  <td className="td sticky right-0 z-10 bg-surface group-hover:bg-brand-50">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-semibold text-slate-900" title={r.name}>{r.name}</span>
                      <span className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${st.cls}`}>{st.label}</span>
                    </div>
                  </td>
                  <td className="td whitespace-nowrap text-slate-600">מדיניות {r.equity}%</td>
                  <td className="td whitespace-nowrap text-slate-600">{r.type}</td>
                  {COLS.map((c) => {
                    const v = r.v[c.key]
                    const banded = c.band && !r.empty && !(c.band === 'foreign_eq' && r.template === 'israel')
                    const out = (banded && !inBand(v, r.bands?.[c.band])) || (c.cap && v > r.fundCap + 0.005) || (c.cash && v < -0.005)
                    const band = banded && r.bands?.[c.band]
                    const miss = r.missing[c.key] || 0
                    const tip = [band && `טווח: ${band[0]}–${band[1]}`, miss && `חסר נתון ל-${miss} ניירות אג״ח – הערך חלקי (יושלם ממגמה / הזנה ידנית בגיליון)`].filter(Boolean).join(' · ')
                    return (
                      <td key={c.key} title={tip || undefined}
                        className={`td num text-left ${out ? 'bg-red-50 font-semibold text-red-700' : c.cash ? 'bg-emerald-50/70 text-slate-800' : 'text-slate-800'}`}>
                        {c.num ? (v == null ? '—' : v.toFixed(2)) : pct(v)}
                        {miss > 0 && <span className="mr-1 rounded bg-amber-100 px-1 text-[10px] font-bold text-amber-800">{miss} חסרים</span>}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
