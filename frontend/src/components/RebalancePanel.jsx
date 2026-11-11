import { useMemo } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Equal, Scale, Copy } from 'lucide-react'
import { fmtILS, fmtInt, fmtPct, fmtSignedPct } from '../lib/format'
import { SERIES } from './palette'

function CompareTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="rounded-lg border border-slate-200 bg-surface px-3 py-2 text-sm shadow-card-hover">
      <div className="mb-1 font-semibold text-slate-800">{p.fullName}</div>
      {payload.map((s) => (
        <div key={s.dataKey} className="flex items-center justify-between gap-6 text-slate-600">
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: s.color }} />{s.name}</span>
          <span className="num font-medium text-slate-900">{fmtPct(s.value)}</span>
        </div>
      ))}
      <div className="mt-1 border-t border-slate-100 pt-1 text-xs text-slate-500">סטייה: <span className="num">{fmtSignedPct(p.current - p.target)}</span></div>
    </div>
  )
}

export default function RebalancePanel({ d, threshold, setThreshold, onTargetChange, onBulk }) {
  const chartData = useMemo(
    () => d.rows
      .filter((r) => r.target_weight != null && r.target_weight !== '')
      .sort((a, b) => Math.max(b.weight, b.target_weight) - Math.max(a.weight, a.target_weight))
      .map((r) => ({ label: r.ticker.length > 9 ? r.ticker.slice(0, 9) : r.ticker, fullName: r.name, current: r.weight, target: Number(r.target_weight) })),
    [d.rows],
  )
  const trades = d.rows.filter((r) => r.trade_value_ils && Math.abs(r.trade_value_ils) >= 1).sort((a, b) => a.trade_value_ils - b.trade_value_ils)
  const targetOk = Math.abs(d.targetTotal - 100) < 0.05

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <Stat label="סך משקלי יעד" value={fmtPct(d.targetTotal)} warn={d.hasTargets && !targetOk} />
        <Stat label="קניות" value={fmtILS(d.buys)} tone="text-emerald-700" />
        <Stat label="מכירות" value={fmtILS(d.sells)} tone="text-red-700" />
        <Stat label="מחזור (Turnover)" value={fmtPct(d.turnoverPct)} sub={`${d.breaches} חריגות מעל סף ${threshold}%`} />
      </div>

      <div className="card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2">
            <button className="btn-outline" onClick={() => onBulk('copy')}><Copy className="h-4 w-4" />יעד = נוכחי</button>
            <button className="btn-outline" onClick={() => onBulk('equal')}><Equal className="h-4 w-4" />משקל שווה</button>
            <button className="btn-outline" onClick={() => onBulk('normalize')} disabled={!d.hasTargets}><Scale className="h-4 w-4" />נרמול יעד ל-100%</button>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            סף סטייה להתראה
            <input type="number" min="0" step="0.5" className="input num w-20 text-left" value={threshold} onChange={(e) => setThreshold(Math.max(0, Number(e.target.value) || 0))} />
            %
          </label>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
        <div className="card overflow-hidden xl:col-span-3">
          <div className="border-b border-slate-100 p-4"><h3 className="card-title">משקל נוכחי מול יעד</h3></div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50/80">
                <tr>
                  <th className="th">נייר</th><th className="th">נוכחי</th><th className="th">יעד</th>
                  <th className="th">סטייה</th><th className="th">פעולה</th><th className="th">סכום (₪)</th><th className="th">יחידות</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {d.rows.map((r) => {
                  const buy = (r.trade_value_ils || 0) > 0
                  const act = r.trade_value_ils == null || Math.abs(r.trade_value_ils) < 1 ? null : buy ? 'קנייה' : 'מכירה'
                  return (
                    <tr key={r.input_id} className={r.breach ? 'bg-amber-50/60' : ''}>
                      <td className="td max-w-[200px]">
                        <div dir="auto" className="truncate font-medium text-slate-800" title={r.name}>{r.name}</div>
                        <div className="num text-xs text-slate-400">{r.ticker}</div>
                      </td>
                      <td className="td"><span className="num">{fmtPct(r.weight)}</span></td>
                      <td className="td">
                        <input type="number" step="0.5" min="0" placeholder="—"
                          className="num w-20 rounded-md border border-slate-200 bg-surface px-1.5 py-1 text-left focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
                          value={r.target_weight ?? ''} onChange={(e) => onTargetChange(r.input_id, e.target.value)} aria-label={`משקל יעד ${r.name}`} />
                      </td>
                      <td className={`td ${r.breach ? 'font-semibold text-amber-800' : 'text-slate-500'}`}>
                        <span className="inline-flex items-center gap-1">
                          {r.breach && <AlertTriangle className="h-3.5 w-3.5" />}
                          <span className="num">{r.drift == null ? '—' : fmtSignedPct(r.drift)}</span>
                        </span>
                      </td>
                      <td className="td">
                        {act ? (
                          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${buy ? 'bg-emerald-50 text-emerald-800' : 'bg-red-50 text-red-800'}`}>
                            {buy ? <ArrowUpRight className="h-3.5 w-3.5" /> : <ArrowDownRight className="h-3.5 w-3.5" />}{act}
                          </span>
                        ) : <span className="text-xs text-slate-400">ללא שינוי</span>}
                      </td>
                      <td className="td"><span className="num">{r.trade_value_ils == null ? '—' : fmtILS(Math.abs(r.trade_value_ils))}</span></td>
                      <td className="td"><span className="num">{r.trade_units == null ? '—' : fmtInt(Math.abs(r.trade_units))}</span></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card p-4 xl:col-span-2">
          <h3 className="card-title mb-3">השוואה ויזואלית</h3>
          {chartData.length ? (
            <div style={{ height: Math.max(260, chartData.length * 34 + 60) }} dir="ltr">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 8, left: 8, bottom: 4 }} barGap={2} barCategoryGap="22%">
                  <CartesianGrid horizontal={false} stroke="rgb(var(--slate-100))" />
                  <XAxis type="number" tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11, fill: 'rgb(var(--slate-500))' }} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="label" width={74} tick={{ fontSize: 11, fill: 'rgb(var(--slate-700))' }} axisLine={false} tickLine={false} />
                  <Tooltip content={<CompareTooltip />} cursor={{ fill: 'rgb(var(--slate-100))' }} />
                  <Legend iconType="square" iconSize={10} wrapperStyle={{ fontSize: 12, direction: 'rtl' }} />
                  <ReferenceLine x={0} stroke="rgb(var(--slate-300))" />
                  <Bar dataKey="current" name="נוכחי" fill={SERIES[0]} radius={[0, 4, 4, 0]} maxBarSize={12} />
                  <Bar dataKey="target" name="יעד" fill={SERIES[1]} radius={[0, 4, 4, 0]} maxBarSize={12} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="py-16 text-center text-sm text-slate-500">הזינו משקלי יעד בטבלה (או לחצו ״יעד = נוכחי״) כדי לחשב פקודות איזון.</p>
          )}
          {trades.length > 0 && (
            <p className="mt-3 text-xs text-slate-500">
              {trades.length} פקודות · היקף מסחר כולל <span className="num">{fmtILS(d.buys + d.sells)}</span>. יחידות מעוגלות כלפי מטה לפי מחיר אחרון.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, sub, tone = 'text-slate-900', warn }) {
  return (
    <div className={`card p-4 ${warn ? 'ring-1 ring-amber-300' : ''}`}>
      <div className="text-sm text-slate-500">{label}</div>
      <div className={`mt-1 text-xl font-bold ${warn ? 'text-amber-700' : tone}`}><span className="num">{value}</span></div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
      {warn && <div className="mt-0.5 text-xs text-amber-700">משקלי היעד אינם מסתכמים ל-100%</div>}
    </div>
  )
}
