import { useMemo, useState } from 'react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { MARKET_FLAG, MARKET_LABEL } from '../lib/portfolio'
import { fmtILS, fmtPct } from '../lib/format'
import { OTHER_COLOR, SERIES } from './palette'

const MODES = [
  { key: 'holding', label: 'לפי נייר' },
  { key: 'asset_class', label: 'סוג נכס' },
  { key: 'market', label: 'שוק' },
  { key: 'currency', label: 'מטבע' },
]
const MAX_SLICES = 7 // 7 named + "אחר" = 8 validated slots

function buildData(rows, mode, aum) {
  let items
  if (mode === 'holding') {
    items = rows.map((r) => ({ key: r.input_id, name: r.name, weight: r.weight || 0 }))
  } else {
    const acc = {}
    rows.forEach((r) => {
      const k = r[mode] || 'אחר'
      acc[k] = (acc[k] || 0) + (r.weight || 0)
    })
    items = Object.entries(acc).map(([k, w]) => ({
      key: k,
      name: mode === 'market' ? `${MARKET_FLAG[k] ?? ''} ${MARKET_LABEL[k] ?? k}` : k,
      weight: w,
    }))
  }
  items = items.filter((i) => i.weight > 0).sort((a, b) => b.weight - a.weight)
  let out = items
  if (items.length > MAX_SLICES + 1) {
    const rest = items.slice(MAX_SLICES)
    out = [...items.slice(0, MAX_SLICES), { key: '__other', name: `אחר (${rest.length})`, weight: rest.reduce((s, i) => s + i.weight, 0) }]
  }
  return out.map((d, i) => ({ ...d, value_ils: (aum * d.weight) / 100, color: d.key === '__other' ? OTHER_COLOR : SERIES[i] }))
}

function DonutTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg border border-slate-200 bg-surface px-3 py-2 text-sm shadow-card-hover">
      <div className="mb-1 flex items-center gap-2 font-semibold text-slate-800">
        <span className="h-2.5 w-2.5 rounded-sm" style={{ background: d.color }} />{d.name}
      </div>
      <div className="flex justify-between gap-6 text-slate-600"><span>משקל</span><span className="num font-medium text-slate-900">{fmtPct(d.weight)}</span></div>
      <div className="flex justify-between gap-6 text-slate-600"><span>שווי</span><span className="num font-medium text-slate-900">{fmtILS(d.value_ils)}</span></div>
    </div>
  )
}

export default function AllocationDonut({ rows, aum, totalWeight }) {
  const [mode, setMode] = useState('holding')
  const [hover, setHover] = useState(null)
  const data = useMemo(() => buildData(rows, mode, aum), [rows, mode, aum])
  const focus = hover != null ? data[hover] : null

  return (
    <div className="card flex h-full flex-col p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="card-title">התפלגות נכסים</h3>
        <div className="flex rounded-lg bg-slate-100 p-0.5 text-xs">
          {MODES.map((m) => (
            <button key={m.key} onClick={() => setMode(m.key)}
              className={`rounded-md px-2.5 py-1 font-medium transition ${mode === m.key ? 'bg-surface text-brand-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div className="relative h-60">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="weight" nameKey="name" innerRadius="62%" outerRadius="92%" paddingAngle={1}
              stroke="#fff" strokeWidth={2} isAnimationActive={false}
              onMouseEnter={(_, i) => setHover(i)} onMouseLeave={() => setHover(null)}>
              {data.map((d, i) => (
                <Cell key={d.key} fill={d.color} opacity={hover == null || hover === i ? 1 : 0.35} cursor="pointer" />
              ))}
            </Pie>
            <Tooltip content={<DonutTooltip />} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
          <div>
            <div className="text-xs text-slate-500">{focus ? focus.name : 'סך הקצאה'}</div>
            <div className="num text-2xl font-bold text-slate-900">{fmtPct(focus ? focus.weight : totalWeight, 1)}</div>
            <div className="num text-xs text-slate-500">{fmtILS(focus ? focus.value_ils : (aum * totalWeight) / 100)}</div>
          </div>
        </div>
      </div>

      <ul className="mt-4 grid grid-cols-1 gap-x-4 gap-y-1.5 text-sm sm:grid-cols-2">
        {data.map((d, i) => (
          <li key={d.key} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
            className={`flex items-center justify-between gap-2 rounded-md px-1.5 py-0.5 transition ${hover === i ? 'bg-slate-50' : ''}`}>
            <span className="flex min-w-0 items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: d.color }} />
              <span dir="auto" className="truncate text-slate-700" title={d.name}>{d.name}</span>
            </span>
            <span className="num shrink-0 text-slate-500">{fmtPct(d.weight, 1)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
