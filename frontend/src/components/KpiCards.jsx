import { Landmark, PieChart, TrendingDown, TrendingUp } from 'lucide-react'
import { fmtILS, fmtPct, fmtSignedPct } from '../lib/format'

function Card({ label, value, sub, icon: Icon, accent, children }) {
  return (
    <div className="card p-5 transition hover:shadow-card-hover">
      <div className="flex items-start justify-between">
        <div className="text-sm font-medium text-slate-500">{label}</div>
        <div className={`grid h-9 w-9 place-items-center rounded-xl ${accent}`}>
          {typeof Icon === 'string' ? <span className="text-lg leading-none">{Icon}</span> : <Icon className="h-[18px] w-[18px]" />}
        </div>
      </div>
      <div className="mt-2 text-[26px] font-bold leading-tight text-slate-900"><span className="num">{value}</span></div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
      {children}
    </div>
  )
}

function Meter({ value, color }) {
  return (
    <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
      <div className="h-full rounded-full transition-all" style={{ width: `${Math.min(100, Math.max(0, value))}%`, background: color }} />
    </div>
  )
}

export default function KpiCards({ d, aum }) {
  const up = d.weightedDayChange >= 0
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Card
        label="סך נכסי הלקוח"
        value={fmtILS(aum)}
        icon={Landmark}
        accent="bg-brand-50 text-brand-700"
        sub={
          <span className={`inline-flex items-center gap-1 ${up ? 'text-emerald-700' : 'text-red-700'}`}>
            {up ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
            שינוי יומי משוקלל <span className="num">{fmtSignedPct(d.weightedDayChange)}</span>
          </span>
        }
      />
      <Card
        label="סך הקצאה"
        value={fmtPct(d.totalWeight)}
        icon={PieChart}
        accent="bg-slate-100 text-slate-700"
        sub={Math.abs(d.cashWeight) > 0.01
          ? <>{d.cashWeight > 0 ? 'לא מוקצה / מזומן' : 'הקצאת יתר'}: <span className="num">{fmtPct(Math.abs(d.cashWeight))}</span></>
          : 'התיק מוקצה במלואו'}
      >
        <Meter value={d.totalWeight} color="rgb(var(--brand-600))" />
      </Card>
      <Card label="חשיפה לשוק הישראלי" value={fmtPct(d.ilExposure)} icon="🇮🇱" accent="bg-sky-50" sub={fmtILS((aum * d.ilExposure) / 100)}>
        <Meter value={d.ilExposure} color="rgb(var(--s1))" />
      </Card>
      <Card label="חשיפה לשוק האמריקאי" value={fmtPct(d.usExposure)} icon="🇺🇸" accent="bg-orange-50" sub={fmtILS((aum * d.usExposure) / 100)}>
        <Meter value={d.usExposure} color="rgb(var(--s2))" />
      </Card>
    </div>
  )
}
