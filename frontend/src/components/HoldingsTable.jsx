import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, Search, Trash2 } from 'lucide-react'
import { fmtILS, fmtInt, fmtPct, fmtPrice, fmtSignedPct } from '../lib/format'
import { MarketBadge, SourceBadge } from './Badges'

const COLS = [
  { key: 'ticker', label: 'טיקר / מספר' },
  { key: 'name', label: 'שם הנייר' },
  { key: 'market', label: 'שוק' },
  { key: 'asset_class', label: 'סוג נכס' },
  { key: 'price', label: 'מחיר', num: true },
  { key: 'change_pct', label: 'שינוי יומי', num: true },
  { key: 'currency', label: 'מטבע' },
  { key: 'weight', label: 'משקל', num: true },
  { key: 'value_ils', label: 'שווי (₪)', num: true },
  { key: 'units', label: 'יחידות', num: true },
  { key: 'source', label: 'מקור' },
]

export default function HoldingsTable({ rows, onWeightChange, onRemove, toolbar }) {
  const [sort, setSort] = useState({ key: 'weight', dir: 'desc' })
  const [filter, setFilter] = useState('')

  const view = useMemo(() => {
    const f = filter.trim().toLowerCase()
    const list = f
      ? rows.filter((r) => [r.ticker, r.input_id, r.name, r.name_en, r.asset_class].some((v) => String(v ?? '').toLowerCase().includes(f)))
      : rows
    const dir = sort.dir === 'asc' ? 1 : -1
    return [...list].sort((a, b) => {
      const x = a[sort.key], y = b[sort.key]
      if (x == null) return 1
      if (y == null) return -1
      return (typeof x === 'number' ? x - y : String(x).localeCompare(String(y), 'he')) * dir
    })
  }, [rows, sort, filter])

  const toggle = (key) => setSort((s) => ({ key, dir: s.key === key && s.dir === 'desc' ? 'asc' : 'desc' }))
  const totals = rows.reduce((t, r) => ({ w: t.w + (r.weight || 0), v: t.v + (r.value_ils || 0) }), { w: 0, v: 0 })

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4">
        <h3 className="card-title">פירוט אחזקות <span className="text-sm font-normal text-slate-400">({rows.length})</span></h3>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="input w-44 pr-9" placeholder="סינון…" value={filter} onChange={(e) => setFilter(e.target.value)} />
          </div>
          {toolbar}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50/80">
            <tr>
              {COLS.map((c) => (
                <th key={c.key} className="th">
                  <button className="inline-flex items-center gap-1 hover:text-slate-800" onClick={() => toggle(c.key)}>
                    {c.label}
                    {sort.key === c.key
                      ? (sort.dir === 'desc' ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />)
                      : <ArrowUpDown className="h-3 w-3 opacity-30" />}
                  </button>
                </th>
              ))}
              <th className="th" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {view.map((r) => (
              <tr key={r.input_id} className={`group hover:bg-slate-50/70 ${!r.priced ? 'bg-red-50/40' : ''}`}>
                <td className="td">
                  <div className="num font-semibold text-slate-800">{r.ticker}</div>
                  {r.ticker !== r.input_id && <div className="num text-xs text-slate-400">{r.input_id}</div>}
                </td>
                <td className="td max-w-[260px]">
                  <div dir="auto" className="truncate font-medium text-slate-800" title={r.name}>{r.name}</div>
                  {r.name_en && r.name_en !== r.name && <div dir="auto" className="truncate text-xs text-slate-400" title={r.name_en}>{r.name_en}</div>}
                </td>
                <td className="td"><MarketBadge market={r.market} /></td>
                <td className="td text-slate-600">{r.asset_class}</td>
                <td className="td"><span className="num">{fmtPrice(r.price, r.currency)}</span></td>
                <td className={`td ${r.change_pct > 0 ? 'text-emerald-700' : r.change_pct < 0 ? 'text-red-700' : 'text-slate-400'}`}>
                  <span className="num">{r.change_pct == null ? '—' : fmtSignedPct(r.change_pct)}</span>
                </td>
                <td className="td text-slate-600">{r.currency}{r.fx_rate !== 1 && r.priced && <span className="num mr-1 text-xs text-slate-400">@{r.fx_rate.toFixed(3)}</span>}</td>
                <td className="td">
                  <div className="flex items-center gap-1">
                    <input type="number" step="0.1" min="0" className="num w-20 rounded-md border border-transparent bg-transparent px-1.5 py-1 text-left font-medium hover:border-slate-200 focus:border-brand-400 focus:bg-surface focus:outline-none"
                      value={Number((r.weight ?? 0).toFixed(4))} onChange={(e) => onWeightChange(r.input_id, e.target.value)} aria-label={`משקל ${r.name}`} />
                    <span className="text-slate-400">%</span>
                  </div>
                </td>
                <td className="td font-semibold text-slate-900"><span className="num">{fmtILS(r.value_ils)}</span></td>
                <td className="td text-slate-600"><span className="num">{fmtInt(r.units)}</span></td>
                <td className="td"><SourceBadge tier={r.tier} source={r.source} /></td>
                <td className="td">
                  <button className="rounded p-1 text-slate-300 opacity-0 transition hover:bg-red-50 hover:text-red-600 group-hover:opacity-100 focus:opacity-100"
                    onClick={() => onRemove(r.input_id)} title="הסרה" aria-label={`הסרת ${r.name}`}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t-2 border-slate-200 bg-slate-50/80 font-semibold">
            <tr>
              <td className="td" colSpan={7}>סה״כ</td>
              <td className="td"><span className="num">{fmtPct(totals.w)}</span></td>
              <td className="td"><span className="num">{fmtILS(totals.v)}</span></td>
              <td className="td" colSpan={3} />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}
