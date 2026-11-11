/**
 * The house Excel's side panel – same blocks and same numbers (summary column, risk buckets, equity geography,
 * Israeli / foreign sector tables with pies, real-estate table) – styled with the site's design tokens.
 */
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { FOREIGN_COLUMNS, GICS_HE } from '../../lib/allocation'
import { GAIN, LOSS, SERIES } from '../palette'

// Fixed categorical order (site palette); sectors beyond 8 reuse the first hues at lower intensity
const PIE = [...SERIES, 'rgb(var(--s1) / 0.5)', 'rgb(var(--s2) / 0.5)', 'rgb(var(--s3) / 0.5)']
// Risk buckets are ordered -> one hue, light to dark
const RISK = ['rgb(150 226 245)', 'rgb(90 170 215)', 'rgb(52 110 185)', 'rgb(31 60 150)']

const p = (v, d = 2) => (v == null || Number.isNaN(v) || !Number.isFinite(v) ? '—' : `${v.toFixed(d)}%`)
const inBand = (v, b) => v != null && v >= b[0] - 1e-9 && v <= b[1] + 1e-9

const Card = ({ title, sub, children, className = '' }) => (
  <section className={`card overflow-hidden ${className}`}>
    {title && (
      <header className="border-b border-slate-100 px-4 py-3">
        <h4 className="card-title">{title}</h4>
        {sub && <p className="mt-0.5 text-[11px] text-slate-400">{sub}</p>}
      </header>
    )}
    {children}
  </section>
)
const Th = ({ children, accent, className = '' }) => (
  <th className={`whitespace-nowrap px-2.5 py-2 text-[11px] font-semibold ${accent ? 'bg-brand-50 text-brand-800' : 'text-slate-500'} ${className}`}>{children}</th>
)
const Td = ({ children, className = '', style }) => (
  <td className={`num whitespace-nowrap px-2.5 py-1.5 text-[12px] ${className}`} style={style}>{children}</td>
)
const Gap = ({ v }) => (v == null ? <span className="text-slate-300">—</span>
  : <span className="font-semibold" style={{ color: Math.abs(v) < 0.05 ? undefined : v > 0 ? GAIN : LOSS }}>{v > 0 ? '+' : ''}{v.toFixed(2)}%</span>)

/** The Excel's U column, as a list with status for the banded lines. */
function Summary({ res }) {
  const s = res.summary
  const st = res.config.settings
  const b = st.bands
  const global = res.config.template === 'global'
  const hasLS = s.linked + s.shekel > 0
  const hasBonds = s.bonds > 0.01
  const groups = [
    ['אג״ח', [
      ['סה״כ מח״מ בתיק', hasBonds ? s.duration.toFixed(2) : '—', null, hasBonds ? inBand(s.duration, b.duration) : null, `${b.duration[0]}–${b.duration[1]}`],
      ['תשואה פנימית של התיק', p(s.irr)],
      ['סה״כ אג״ח', p(s.bonds)],
      ['סה״כ קונצרני בתיק', p(s.corp)],
      ['סה״כ צמוד', p(s.linked), hasLS ? p(s.linkedShare, 1) : null, hasLS ? inBand(s.linkedShare, b.linked) : null, `${b.linked[0]}–${b.linked[1]}%`],
      ['סה״כ שקלי', p(s.shekel), hasLS ? p(s.shekelShare, 1) : null, hasLS ? inBand(s.shekelShare, b.shekel) : null, `${b.shekel[0]}–${b.shekel[1]}%`],
    ]],
    ['חשיפות', [
      ['עו״ש התיק', p(s.cash), null, s.cash < -0.005 ? false : null],
      ['סה״כ מט״ח', p(s.fx)],
      ['סה״כ אמריקאיות (כולל קרנות)', p(s.us)],
      ['סה״כ אמריקאיות ישיר', p(s.usDirect)],
      ['פוזיציה מנייתית', s.equityPosition == null ? '—' : p(s.equityPosition, 1)],
      ['סה״כ חשיפה מנייתית לחו״ל', p(s.foreignEqShare, 1), null, global && s.equity > 0 ? inBand(s.foreignEqShare, b.foreign_eq) : null, global ? `${b.foreign_eq[0]}–${b.foreign_eq[1]}%` : null],
      ['סה״כ חשיפה מנייתית לארץ', p(s.ilEqShare, 1)],
    ]],
    ['עמלות והכנסות', [
      ['דמי ניהול של הקרנות בתיק', p(s.fundFees, 3)],
      ['סה״כ דמי ניהול בתיק', p(s.totalFees, 3)],
      ['סה״כ הכנסות לאמבן', p(s.revenue, 3)],
      ['סה״כ הכנסות לאמבן ללא מע״מ', p(s.revenueExVat, 3)],
    ]],
  ]
  return (
    <Card title="סיכום המודל" sub={`דמי ניהול חוזה ${p(st.contract_fee)} · כולל מע״מ ${p(s.feeVat)} · אינפלציה גלומה ${p(st.inflation)}`}>
      <div className="divide-y divide-slate-100">
        {groups.map(([g, rows]) => (
          <div key={g} className="px-4 py-2.5">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{g}</div>
            {rows.map(([label, val, rel, ok, band]) => (
              <div key={label} className={`-mx-2 flex items-center gap-2 rounded-md px-2 py-1 text-[13px] ${ok === false ? 'bg-red-50' : ''}`}>
                <span className="flex-1 text-slate-600">{label}</span>
                {band && <span className="num text-[10px] text-slate-400">{band}</span>}
                {rel && <span className="num rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600" title="יחסי מתוך צמוד + שקלי">{rel}</span>}
                <span className={`num w-16 text-left font-semibold ${ok === false ? 'text-red-700' : 'text-slate-900'}`}>{val}</span>
                <span className="w-4">
                  {ok === true && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" aria-label="בטווח" />}
                  {ok === false && <AlertTriangle className="h-3.5 w-3.5 text-red-600" aria-label="מחוץ לטווח" />}
                </span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </Card>
  )
}

function Ratings({ res }) {
  const has = res.ratingTotal > 0
  return (
    <Card title="פיזור סיכון – קונצרני" sub={`${p(res.ratingTotal)} מהתיק${res.unrated > 0.005 ? ` · ${p(res.unrated)} ללא סיווג` : ''}`}>
      <div className="space-y-2.5 p-4">
        {res.ratingRows.map((r, i) => (
          <div key={r.key} className="flex items-center gap-3 text-[13px]">
            <span className="num grid h-5 w-5 shrink-0 place-items-center rounded text-[10px] font-bold text-white" style={{ background: RISK[i] }}>{r.key}</span>
            <span className="w-24 shrink-0 text-slate-700">{r.label}</span>
            <div className="relative h-2 flex-1 rounded-full bg-slate-100">
              <div className="absolute inset-y-0 right-0 rounded-full" style={{ width: `${has ? r.share : 0}%`, background: RISK[i] }} />
            </div>
            <span className="num w-12 text-left font-semibold text-slate-900">{has ? p(r.share, 1) : '—'}</span>
            <span className="num w-14 text-left text-xs text-slate-400">{p(r.F)}</span>
          </div>
        ))}
      </div>
    </Card>
  )
}

function Geography({ res, withPie }) {
  const has = res.summary.equity > 0
  const data = res.geography.map((g, i) => ({ name: g.label, value: g.F, color: SERIES[i] }))
  return (
    <Card title="פיזור מניות" sub="אחוז מהתיק · יחסי מתוך המניות">
      <div className="flex flex-wrap items-center gap-4 p-4">
        {withPie && <Donut data={data} size="h-36 w-36" />}
        <table className="flex-1">
          <tbody className="divide-y divide-slate-100">
            {res.geography.map((g, i) => (
              <tr key={g.key}>
                <Td className="text-slate-700"><span className="ml-2 inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ background: SERIES[i] }} />{g.label}</Td>
                <Td className="text-left text-slate-500">{p(g.F)}</Td>
                <Td className="text-left font-semibold text-slate-900">{has ? p(g.share, 1) : '—'}</Td>
              </tr>
            ))}
            <tr className="border-t-2 border-slate-200">
              <Td className="font-semibold text-slate-700">סה״כ</Td>
              <Td className="text-left font-semibold">{p(res.geography.reduce((t, g) => t + g.F, 0))}</Td>
              <Td className="text-left font-semibold">{has ? '100.0%' : '—'}</Td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function Donut({ data, size = 'h-64 w-full', labels = false }) {
  const rows = data.filter((d) => d.value > 0.0001)
  const total = rows.reduce((t, d) => t + d.value, 0)
  const RAD = Math.PI / 180
  const label = ({ cx, cy, midAngle, outerRadius, index }) => {
    const d = rows[index]
    if (d.value / total < 0.03) return null // small slices: legend + tooltip only
    const r = outerRadius + 16
    const x = cx + r * Math.cos(-midAngle * RAD)
    const y = cy + r * Math.sin(-midAngle * RAD)
    return <text x={x} y={y} textAnchor={x > cx ? 'start' : 'end'} dominantBaseline="central" fontSize={11} fontWeight={600} fill="rgb(var(--slate-600))">{((d.value / total) * 100).toFixed(0)}%</text>
  }
  if (!rows.length) return <div className={`${size} grid place-items-center text-sm text-slate-400`}>אין נתונים</div>
  return (
    <div className={size}>
      <ResponsiveContainer>
        <PieChart margin={labels ? { top: 16, bottom: 16, left: 30, right: 30 } : undefined}>
          <Pie data={rows} dataKey="value" nameKey="name" innerRadius="58%" outerRadius={labels ? '82%' : '100%'} startAngle={90} endAngle={-270}
            stroke="rgb(var(--surface))" strokeWidth={2} isAnimationActive={false} label={labels ? label : false} labelLine={false}>
            {rows.map((d) => <Cell key={d.name} fill={d.color} />)}
          </Pie>
          <Tooltip formatter={(v, n) => [`${((v / total) * 100).toFixed(1)}%`, n]} contentStyle={{ direction: 'rtl', fontSize: 12, borderRadius: 8 }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Sector table (index weights × exposure + direct -> actual mix) next to its donut. */
function SectorBlock({ title, sub, columns, exposures, rows, total, labelOf, accent, extraHeader, extraExposure, extraCell, gapOf, pieName, memoLabel }) {
  const has = total > 0
  const main = rows.filter((r) => !r.memo)
  const pie = main.map((r, i) => ({ name: pieName(r), value: r.total, color: PIE[i % PIE.length] }))
  return (
    <Card title={title} sub={sub}>
      <div className="grid grid-cols-1 items-start 2xl:grid-cols-[1fr_300px]">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-50/80">
              <tr>
                <Th className="text-right">ענף</Th>
                {columns.map((c) => <Th key={c.key} accent={accent(c)} className="text-left">{c.label}</Th>)}
                {extraHeader}
                <Th className="text-left">ישיר</Th><Th className="text-left">סה״כ</Th><Th className="text-left">יחסי בפועל</Th>
                {gapOf && <Th className="text-left">פער מהמדד</Th>}
              </tr>
              <tr className="border-b border-slate-200 bg-brand-50/40 text-brand-900">
                <Td className="text-[11px] font-medium">חשיפה בתיק</Td>
                {columns.map((c) => <Td key={c.key} className="text-left font-semibold">{p(exposures[c.key])}</Td>)}
                {extraExposure}
                <Td /><Td /><Td />{gapOf && <Td />}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r, i) => (
                <tr key={r.sector} className={r.memo ? 'border-t-2 border-slate-200 text-slate-500' : 'hover:bg-slate-50/60'}>
                  <Td className="text-slate-700">
                    {!r.memo && <span className="ml-2 inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ background: PIE[i % PIE.length] }} />}
                    {r.memo ? memoLabel(r) : labelOf(r)}
                  </Td>
                  {columns.map((c) => <Td key={c.key} className="text-left text-slate-400">{r.weights[c.key] ? p(r.weights[c.key]) : ''}</Td>)}
                  {extraCell?.(r)}
                  <Td className="text-left text-slate-600">{p(r.direct)}</Td>
                  <Td className="text-left text-slate-600">{p(r.total)}</Td>
                  <Td className="text-left font-semibold text-slate-900">{r.memo ? (has ? p((r.total / total) * 100, 1) : '—') : has ? p(r.share, 1) : '—'}</Td>
                  {gapOf && <Td className="text-left">{r.memo || !has ? '' : <Gap v={gapOf(r)} />}</Td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="border-t border-slate-100 p-4 2xl:border-r 2xl:border-t-0">
          <Donut data={pie} labels />
          <ul className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-slate-600">
            {pie.filter((d) => d.value > 0.0001).map((d) => (
              <li key={d.name} className="flex items-center gap-1.5 truncate"><span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: d.color }} />{d.name}</li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  )
}

function RealEstate({ res }) {
  const re = res.realEstate
  return (
    <Card title="נדל״ן מניב בישראל – באג״ח הקונצרני" sub={`שיעור הנדל״ן בכל מדד/קרן × החשיפה אליה, ועוד אג״ח ישירות מהענף · מדד ייחוס: תל בונד 60 (${p(re.benchmark)})`}>
      <div className="flex flex-wrap items-stretch">
        <div className="flex gap-6 border-b border-slate-100 p-4 lg:border-b-0 lg:border-l">
          <div><div className="text-[11px] text-slate-500">יחסי בפועל</div><div className="num text-2xl font-bold text-slate-900">{p(re.share, 1)}</div></div>
          <div><div className="text-[11px] text-slate-500">פער מהמדד</div><div className="num text-xl font-semibold" style={{ color: re.gap == null ? undefined : re.gap > 0 ? LOSS : GAIN }}>
              {re.gap == null ? '—' : `${re.gap > 0 ? '+' : ''}${re.gap.toFixed(2)}%`}</div>
            <div className="text-[10px] text-slate-400">יחסי בפועל פחות תל בונד 60</div></div>
        </div>
        <div className="flex-1 overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-50/80">
              <tr><Th className="text-right" />{re.columns.map((c) => <Th key={c.label} className="text-left">{c.label}</Th>)}<Th className="text-left">ישיר</Th><Th className="text-left">סה״כ</Th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              <tr className="bg-brand-50/40 text-brand-900">
                <Td className="text-[11px] font-medium">חשיפה בתיק</Td>
                {re.columns.map((c) => <Td key={c.label} className="text-left font-semibold">{p(c.F)}</Td>)}
                <Td /><Td />
              </tr>
              <tr>
                <Td className="text-slate-700">שיעור נדל״ן מניב</Td>
                {re.columns.map((c) => <Td key={c.label} className="text-left text-slate-400">{p(c.share)}</Td>)}
                <Td className="text-left text-slate-600">{p(re.direct)}</Td>
                <Td className="text-left font-semibold text-slate-900">{p(re.total)}</Td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </Card>
  )
}

export default function ExcelStats({ res }) {
  const global = res.config.template === 'global'
  const directTotal = res.foreignSectors.filter((r) => !r.memo).reduce((t, r) => t + r.direct, 0)
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-2">
        <Summary res={res} />
        <div className="space-y-5">
          <Ratings res={res} />
          <Geography res={res} withPie={global} />
        </div>
      </div>
      <SectorBlock
        title="מניות ישראל – פיזור ענפי" sub="משקל הענף בכל מדד/קרן × החשיפה אליה, ועוד מניות ישירות · פער מהמדד מול ת״א 125"
        columns={res.ilCols} exposures={res.ilexp} rows={res.ilSectors} total={res.ilTotal}
        labelOf={(r) => r.label} pieName={(r) => r.label} memoLabel={(r) => `${r.label} (מחוץ לפילוח)`}
        accent={(c) => c.key === 'ta125' || c.key === 'ta90'} gapOf={(r) => r.gap} />
      {global && (
        <SectorBlock
          title="מניות חו״ל – פיזור ענפי" sub="משקל הענף בכל מדד × החשיפה אליו, ועוד מניות ישירות · שבבים מוצג כפירוט מתוך טכנולוגיה"
          columns={FOREIGN_COLUMNS} exposures={res.fexp} rows={res.foreignSectors} total={res.fsTotal}
          labelOf={(r) => GICS_HE[r.sector] || r.sector} pieName={(r) => GICS_HE[r.sector] || r.sector} memoLabel={() => 'מתוכו שבבים'}
          accent={(c) => ['SP', 'NDX', 'STOXX', 'RUSSELL'].includes(c.key)}
          extraExposure={null} extraHeader={null}
        />
      )}
      {global && directTotal > 0 && <p className="-mt-3 text-[11px] text-slate-400">מניות חו״ל ישירות מהתיק: {p(directTotal)}</p>}
      <RealEstate res={res} />
    </div>
  )
}
