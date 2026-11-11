import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { RotateCcw, SlidersHorizontal, TrendingDown, TrendingUp } from 'lucide-react'
import useDebouncedRequest from '../lib/useDebouncedRequest'
import { getStressScenarios, stressTest } from '../lib/api'
import { fmtCompactILS, fmtILS, fmtPct, fmtSignedPct } from '../lib/format'
import { GAIN, LOSS, SERIES } from './palette'
import { ErrorCard, LoadingCard } from './XRayView'
import { scenarioIcon } from './scenarioIcons'

// Diverging pair (gain / loss) – always shown with a sign, never color alone

const SHOCKS = [
  { key: 'equity_global_pct', label: 'מניות בחו״ל', unit: '%', min: -60, max: 40, step: 1, hint: 'שינוי במדדי המניות העולמיים' },
  { key: 'equity_local_pct', label: 'מניות בישראל', unit: '%', min: -60, max: 40, step: 1, hint: 'שינוי במדדי ת״א' },
  { key: 'fx_pct', label: 'שער דולר/שקל', unit: '%', min: -25, max: 25, step: 0.5, hint: '+ = פיחות השקל (הדולר מתחזק)' },
  { key: 'rate_il_bps', label: 'ריבית בישראל', unit: 'נ״ב', min: -300, max: 400, step: 5, hint: 'הזזה מקבילה בעקום התשואות' },
  { key: 'rate_global_bps', label: 'ריבית בחו״ל', unit: 'נ״ב', min: -300, max: 400, step: 5, hint: 'הזזה מקבילה בתשואות האג״ח בחו״ל' },
  { key: 'credit_bps', label: 'מרווחי אשראי', unit: 'נ״ב', min: -150, max: 600, step: 5, hint: 'התרחבות מרווחים באג״ח קונצרני' },
]
const ZERO = Object.fromEntries(SHOCKS.map((s) => [s.key, 0]))

export default function StressTestView({ rows, aum }) {
  const [presets, setPresets] = useState([])
  const [scenario, setScenario] = useState('global_crisis')
  const [shocks, setShocks] = useState(ZERO)
  const [useBeta, setUseBeta] = useState(true)

  useEffect(() => {
    getStressScenarios().then((r) => {
      setPresets(r.scenarios)
      const first = r.scenarios.find((s) => s.id === 'global_crisis') ?? r.scenarios[0]
      if (first) setShocks({ ...ZERO, ...first.shocks })
    }).catch(() => {})
  }, [])

  const key = useMemo(
    () => JSON.stringify([rows.map((r) => [r.input_id, r.weight]), aum, shocks, useBeta]),
    [rows, aum, shocks, useBeta],
  )
  const { data, loading, error } = useDebouncedRequest((signal) => stressTest(rows, aum, shocks, useBeta, signal), rows.length ? key : null, 250)

  const pick = (p) => { setScenario(p.id); setShocks({ ...ZERO, ...p.shocks }) }
  const setOne = (k, v) => { setScenario('custom'); setShocks((s) => ({ ...s, [k]: v })) }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        {presets.map((p) => (
          <button key={p.id} onClick={() => pick(p)} title={p.description}
            className={`card p-3 text-right transition hover:shadow-card-hover ${scenario === p.id ? 'ring-2 ring-brand-600' : ''}`}>
            {(() => { const Icon = scenarioIcon(p.id); return <Icon className="h-[18px] w-[18px] text-brand-700" /> })()}
            <div className="mt-2 text-sm font-semibold leading-snug text-slate-800">{p.name}</div>
            <div className="mt-1 line-clamp-2 text-[11px] leading-snug text-slate-500">{p.description}</div>
          </button>
        ))}
        <button onClick={() => { setScenario('custom'); setShocks(ZERO) }}
          className={`card flex flex-col p-3 text-right transition hover:shadow-card-hover ${scenario === 'custom' ? 'ring-2 ring-brand-600' : ''}`}>
          <SlidersHorizontal className="h-[18px] w-[18px] text-brand-700" />
          <div className="mt-2 text-sm font-semibold text-slate-800">תרחיש מותאם</div>
          <div className="mt-1 text-[11px] text-slate-500">הגדירו זעזועים ידנית</div>
        </button>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="card p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="card-title">פרמטרי זעזוע</h3>
            <button className="btn-ghost px-2 py-1 text-xs" onClick={() => { setScenario('custom'); setShocks(ZERO) }}><RotateCcw className="h-3.5 w-3.5" />איפוס</button>
          </div>
          <div className="space-y-4">
            {SHOCKS.map((s) => <ShockSlider key={s.key} spec={s} value={shocks[s.key]} onChange={(v) => setOne(s.key, v)} />)}
          </div>
          <label className="mt-5 flex cursor-pointer items-start gap-2 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
            <input type="checkbox" className="mt-0.5 accent-brand-700" checked={useBeta} onChange={(e) => setUseBeta(e.target.checked)} />
            <span>שימוש בבטא למניות בודדות<span className="block text-xs text-slate-500">מכפיל את זעזוע המניות בבטא של כל מניה (מתוך yfinance, בטווח 0.3–2.5)</span></span>
          </label>
        </div>

        <div className="space-y-5 xl:col-span-2">
          {error && !data && <ErrorCard msg={error} />}
          {!data && !error && <LoadingCard text="מחשב תרחיש…" />}
          {data && <Results data={data} loading={loading} />}
        </div>
      </div>

      {data && <ScenarioComparison items={data.scenario_comparison} active={scenario} />}
      {data && <HoldingImpact rows={data.holdings} />}
      <p className="text-xs leading-relaxed text-slate-400">
        המודל הוא קירוב ליניארי: מניות לפי חשיפה גיאוגרפית (ובטא), אג״ח לפי מח״מ (‎-D·Δy‎), מט״ח לפי שיעור החשיפה למט״ח לאחר שיקוף.
        התרחישים המוגדרים מראש הם היפותטיים ומיועדים לדיון – אינם שחזור של אירועים היסטוריים ואינם תחזית.
      </p>
    </div>
  )
}

function ShockSlider({ spec, value, onChange }) {
  const pct = ((value - spec.min) / (spec.max - spec.min)) * 100
  const zero = ((0 - spec.min) / (spec.max - spec.min)) * 100
  const tone = value > 0 ? 'text-brand-700' : value < 0 ? 'text-red-700' : 'text-slate-500'
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-sm font-medium text-slate-700" title={spec.hint}>{spec.label}</span>
        <span className={`text-sm font-semibold ${tone}`}>
          <span className="num">{value > 0 ? '+' : ''}{value}{spec.unit === '%' ? '%' : ''}</span>
          {spec.unit !== '%' && <span className="mr-1 text-xs font-medium">{spec.unit}</span>}
        </span>
      </div>
      <div className="relative" dir="ltr">
        <div className="pointer-events-none absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full"
          style={{ left: `${Math.min(pct, zero)}%`, width: `${Math.abs(pct - zero)}%`, background: value >= 0 ? GAIN : LOSS, opacity: 0.35 }} />
        <input type="range" min={spec.min} max={spec.max} step={spec.step} value={value}
          onChange={(e) => onChange(Number(e.target.value))} className="aum-range relative w-full" aria-label={spec.label} />
      </div>
      <div className="mt-0.5 text-[11px] text-slate-400">{spec.hint}</div>
    </div>
  )
}

function Results({ data, loading }) {
  const up = data.pnl_ils >= 0
  const compare = [
    { name: 'שווי בסיס', value: data.baseline_value, color: SERIES[0] },
    { name: 'שווי לאחר זעזוע', value: data.stressed_value, color: up ? GAIN : LOSS },
  ]
  const attrib = data.attribution.filter((a) => Math.abs(a.pnl_ils) >= 1)
  return (
    <div className={`space-y-5 transition-opacity ${loading ? 'opacity-60' : ''}`}>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Stat label="שווי תיק – בסיס" value={fmtILS(data.baseline_value)} />
        <Stat label="שווי תיק – לאחר זעזוע" value={fmtILS(data.stressed_value)} />
        <div className={`card p-4 ${up ? '' : 'ring-1 ring-red-200'}`}>
          <div className="text-sm text-slate-500">רווח / הפסד משוער</div>
          <div className={`mt-1 flex items-center gap-1.5 text-xl font-bold ${up ? 'text-brand-700' : 'text-red-700'}`}>
            {up ? <TrendingUp className="h-5 w-5" /> : <TrendingDown className="h-5 w-5" />}
            <span className="num">{fmtILS(data.pnl_ils)}</span>
          </div>
          <div className={`num mt-0.5 text-xs font-medium ${up ? 'text-brand-700' : 'text-red-700'}`}>{fmtSignedPct(data.pnl_pct)}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="card p-5">
          <h3 className="card-title mb-3">בסיס מול תרחיש</h3>
          <div className="h-56" dir="ltr">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={compare} margin={{ top: 22, right: 8, left: 8, bottom: 0 }} barCategoryGap="35%">
                <CartesianGrid vertical={false} stroke="rgb(var(--slate-100))" />
                <XAxis dataKey="name" tick={{ fontSize: 12, fill: 'rgb(var(--slate-700))' }} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={fmtCompactILS} tick={{ fontSize: 11, fill: 'rgb(var(--slate-500))' }} axisLine={false} tickLine={false} width={64} />
                <Tooltip cursor={{ fill: 'rgb(var(--slate-100))' }} formatter={(v) => [fmtILS(v), 'שווי']} contentStyle={{ direction: 'rtl', borderRadius: 8, fontSize: 13 }} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={72} isAnimationActive={false}>
                  {compare.map((c) => <Cell key={c.name} fill={c.color} />)}
                  <LabelList dataKey="value" position="top" formatter={fmtCompactILS} style={{ fontSize: 12, fill: 'rgb(var(--slate-700))', fontWeight: 600 }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-5">
          <h3 className="card-title mb-1">ייחוס הרווח/הפסד לגורמי סיכון</h3>
          <p className="mb-3 text-xs text-slate-500">תרומת כל זעזוע לשינוי בשווי התיק (₪)</p>
          <div className="space-y-2.5">
            {attrib.length === 0 && <p className="py-10 text-center text-sm text-slate-400">אין השפעה – כל הזעזועים מאופסים</p>}
            {(() => {
              const max = Math.max(...attrib.map((a) => Math.abs(a.pnl_ils)), 1)
              return attrib.map((a) => (
                <div key={a.factor} className="grid grid-cols-[110px_1fr_88px] items-center gap-2 text-sm">
                  <span className="truncate text-slate-700">{a.label}</span>
                  <div className="relative h-3 rounded bg-slate-50">
                    <div className="absolute inset-y-0 right-1/2 w-px bg-slate-300" />
                    <div className="absolute inset-y-0 rounded" style={{
                      background: a.pnl_ils >= 0 ? GAIN : LOSS,
                      width: `${(Math.abs(a.pnl_ils) / max) * 50}%`,
                      ...(a.pnl_ils >= 0 ? { right: '50%' } : { left: '50%' }),
                    }} />
                  </div>
                  <span className={`num text-left font-medium ${a.pnl_ils >= 0 ? 'text-brand-700' : 'text-red-700'}`}>{fmtCompactILS(a.pnl_ils)}</span>
                </div>
              ))
            })()}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2 border-t border-slate-100 pt-3 text-xs sm:grid-cols-3">
            {data.sensitivities.map((s) => (
              <div key={s.label} className="rounded-lg bg-slate-50 px-2.5 py-2">
                <div className="text-slate-500">{s.label}</div>
                <div className={`num font-semibold ${s.pnl_ils >= 0 ? 'text-brand-700' : 'text-red-700'}`}>{fmtCompactILS(s.pnl_ils)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function ScenarioComparison({ items, active }) {
  const data = items.map((i) => ({ ...i, label: i.name }))
  return (
    <div className="card p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="card-title">השוואת תרחישים – שווי בסיס מול שווי לאחר זעזוע</h3>
        <span className="text-xs text-slate-500">התרחיש הנבחר מודגש</span>
      </div>
      <div className="h-72" dir="ltr">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 22, right: 8, left: 8, bottom: 0 }} barGap={2} barCategoryGap="22%">
            <CartesianGrid vertical={false} stroke="rgb(var(--slate-100))" />
            <XAxis dataKey="label" reversed interval={0} tick={{ fontSize: 11, fill: 'rgb(var(--slate-700))' }} axisLine={false} tickLine={false} height={36} />
            <YAxis orientation="right" tickFormatter={fmtCompactILS} tick={{ fontSize: 11, fill: 'rgb(var(--slate-500))' }} axisLine={false} tickLine={false} width={64} />
            <Tooltip cursor={{ fill: 'rgb(var(--slate-100))' }} content={<ScenarioTooltip />} />
            <Legend iconType="square" iconSize={10} wrapperStyle={{ fontSize: 12, direction: 'rtl' }} />
            <ReferenceLine y={0} stroke="rgb(var(--slate-300))" />
            <Bar dataKey="baseline_value" name="שווי בסיס" fill={SERIES[0]} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false}>
              {data.map((d) => <Cell key={d.id} fillOpacity={active === d.id || active === 'custom' ? 1 : 0.45} />)}
            </Bar>
            <Bar dataKey="stressed_value" name="לאחר זעזוע" fill={SERIES[1]} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false}>
              {data.map((d) => <Cell key={d.id} fillOpacity={active === d.id || active === 'custom' ? 1 : 0.45} />)}
              <LabelList dataKey="pnl_pct" position="top" formatter={(v) => fmtSignedPct(v, 1)} style={{ fontSize: 11, fill: 'rgb(var(--slate-700))', fontWeight: 600 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function ScenarioTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="rounded-lg border border-slate-200 bg-surface px-3 py-2 text-sm shadow-card-hover" dir="rtl">
      <div className="mb-1 font-semibold text-slate-800">{p.name}</div>
      <div className="flex justify-between gap-6 text-slate-600"><span>בסיס</span><span className="num text-slate-900">{fmtILS(p.baseline_value)}</span></div>
      <div className="flex justify-between gap-6 text-slate-600"><span>לאחר זעזוע</span><span className="num text-slate-900">{fmtILS(p.stressed_value)}</span></div>
      <div className={`flex justify-between gap-6 font-medium ${p.pnl_ils >= 0 ? 'text-brand-700' : 'text-red-700'}`}><span>רווח/הפסד</span><span className="num">{fmtILS(p.pnl_ils)} ({fmtSignedPct(p.pnl_pct)})</span></div>
    </div>
  )
}

function HoldingImpact({ rows }) {
  const max = Math.max(...rows.map((r) => Math.abs(r.pnl_ils)), 1)
  return (
    <div className="card overflow-hidden">
      <div className="border-b border-slate-100 p-4">
        <h3 className="card-title">השפעה לפי אחזקה</h3>
        <p className="text-xs text-slate-500">ממוין מההפסד הגדול לרווח הגדול</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50/80">
            <tr><th className="th">נייר</th><th className="th">משקל</th><th className="th">שווי בסיס</th><th className="th">שווי בתרחיש</th><th className="th">רווח/הפסד</th><th className="th">תשואה</th><th className="th w-1/5" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r) => (
              <tr key={r.input_id} className="hover:bg-slate-50/70">
                <td className="td max-w-[240px]">
                  <div dir="auto" className="truncate font-medium text-slate-800" title={r.name}>{r.name}</div>
                  <div className="num text-xs text-slate-400">{r.ticker}</div>
                </td>
                <td className="td"><span className="num">{fmtPct(r.weight)}</span></td>
                <td className="td"><span className="num">{fmtILS(r.value_ils)}</span></td>
                <td className="td"><span className="num">{fmtILS(r.stressed_value_ils)}</span></td>
                <td className={`td font-semibold ${r.pnl_ils >= 0 ? 'text-brand-700' : 'text-red-700'}`}><span className="num">{fmtILS(r.pnl_ils)}</span></td>
                <td className={`td ${r.return_pct >= 0 ? 'text-brand-700' : 'text-red-700'}`}><span className="num">{fmtSignedPct(r.return_pct)}</span></td>
                <td className="td">
                  <div className="relative h-2.5 rounded bg-slate-50">
                    <div className="absolute inset-y-0 right-1/2 w-px bg-slate-300" />
                    <div className="absolute inset-y-0 rounded" style={{
                      background: r.pnl_ils >= 0 ? GAIN : LOSS, width: `${(Math.abs(r.pnl_ils) / max) * 50}%`,
                      ...(r.pnl_ils >= 0 ? { right: '50%' } : { left: '50%' }),
                    }} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="card p-4">
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-bold text-slate-900"><span className="num">{value}</span></div>
    </div>
  )
}
