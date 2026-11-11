import { fmtPct } from '../../lib/format'

/**
 * 100% stacked bar with a fixed category order and a 2px surface gap between segments.
 * `labels` prints the share inside segments wide enough to hold it (ink chosen per category for contrast).
 */
export default function StackedBar({ data, order, height = 'h-3', labels = false, minLabel = 9 }) {
  const total = order.reduce((s, o) => s + Math.max(0, data?.[o.key] || 0), 0) || 1
  return (
    <div className={`flex w-full gap-[2px] overflow-hidden rounded-md bg-slate-100 ${height}`}
      role="img" aria-label={order.filter((o) => data?.[o.key]).map((o) => `${o.key} ${fmtPct(data[o.key], 1)}`).join(', ')}>
      {order.map((o) => {
        const v = Math.max(0, data?.[o.key] || 0)
        if (v <= 0.05) return null
        const share = (v / total) * 100
        return (
          <div key={o.key} className="flex items-center justify-center overflow-hidden" style={{ width: `${share}%`, background: o.color }}
            title={`${o.key}: ${fmtPct(v, 1)}`}>
            {labels && share >= minLabel && (
              <span className={`num text-[11px] font-semibold ${o.darkInk ? 'text-[#161932]' : 'text-white'}`}>{v.toFixed(0)}%</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

export function Legend({ order }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600">
      {order.map((o) => (
        <span key={o.key} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: o.color }} />{o.key}</span>
      ))}
    </div>
  )
}
