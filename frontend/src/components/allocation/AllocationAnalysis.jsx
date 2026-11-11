import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { SERIES, GAIN, LOSS, OTHER_COLOR } from '../palette'
import { FOREIGN_COLUMNS, IL_COLUMNS } from '../../lib/allocation'

const pct = (v, d = 2) => (v == null || Number.isNaN(v) ? '—' : `${v.toFixed(d)}%`)
const tip = { contentStyle: { direction: 'rtl', borderRadius: 8, fontSize: 12 } }

/** One cell of the Excel's summary column (U5…U21), with the band it is checked against. */
function Tile({ label, value, sub, band, ok, hint }) {
  const state = ok == null ? 'none' : ok ? 'ok' : 'bad'
  return (
    <div className={`rounded-xl border px-3 py-2.5 ${state === 'bad' ? 'border-red-300 bg-red-50' : 'border-slate-200 bg-surface'}`} title={hint}>
      <div className="flex items-center justify-between gap-2 text-[11px] text-slate-500">
        <span className="truncate">{label}</span>
        {state === 'ok' && <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-600" aria-label="בטווח" />}
        {state === 'bad' && <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-red-600" aria-label="מחוץ לטווח" />}
      </div>
      <div className={`num text-lg font-bold ${state === 'bad' ? 'text-red-800' : 'text-slate-900'}`}>{value}</div>
      {(sub || band) && <div className="truncate text-[11px] text-slate-400">{band ? <>טווח <span className="num">{band}</span>{sub ? ` · ${sub}` : ''}</> : sub}</div>}
    </div>
  )
}

const inBand = (v, b) => v != null && v >= b[0] - 1e-9 && v <= b[1] + 1e-9

export function SummaryTiles({ res, equityTarget }) {
  const s = res.summary
  const b = res.config.settings.bands
  const global = res.config.template === 'global'
  const hasBonds = s.bonds > 0.01
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
      <Tile label="סה״כ מח״מ בתיק" value={hasBonds ? s.duration.toFixed(2) : '—'} band={`${b.duration[0]}–${b.duration[1]}`}
        ok={hasBonds ? inBand(s.duration, b.duration) : null} hint="Σ מח״מ × משקל ÷ (100% − מניות)"
        sub={s.missingDuration ? `חסר מח״מ ל-${s.missingDuration} ניירות` : undefined} />
      <Tile label="תשואה פנימית של התיק" value={pct(s.irr)} sub={s.missingYield ? `חסרה תשואה ברוטו ל-${s.missingYield} ניירות` : 'כולל אינפלציה גלומה'}
        hint="Σ (אינפ׳ גלומה + תשואה ברוטו) × משקל ÷ סה״כ אג״ח" />
      <Tile label="סה״כ אג״ח" value={pct(s.bonds)} sub={`קונצרני ${pct(s.corp, 1)} · ממשלתי ${pct(s.gov, 1)}`} />
      <Tile label="עו״ש התיק" value={pct(s.cash)} ok={s.cash >= -0.005 ? null : false} />
      <Tile label="סה״כ מניות" value={pct(s.equity)} sub={s.equityPosition != null ? `פוזיציה מנייתית ${pct(s.equityPosition, 1)} מהיעד (${equityTarget}%)` : ''}
        ok={equityTarget > 0 ? Math.abs(s.equityPosition - 100) < 1 : null} hint="כולל מניות דרך קרנות" />
      {global
        ? <Tile label="חשיפה מנייתית לחו״ל" value={pct(s.foreignEqShare, 1)} band={`${b.foreign_eq[0]}%–${b.foreign_eq[1]}%`}
            ok={s.equity > 0 ? inBand(s.foreignEqShare, b.foreign_eq) : null} sub={`ישראל ${pct(s.ilEqShare, 1)}`} hint="מניות חו״ל ÷ סך המניות" />
        : <Tile label="חשיפה מנייתית לארץ" value={pct(s.ilEqShare, 1)} sub="מתוך סך המניות" />}
      <Tile label="סה״כ צמוד" value={pct(s.linked)} band={`${b.linked[0]}%–${b.linked[1]}%`} sub={`יחסי ${pct(s.linkedShare, 1)}`}
        ok={s.linked + s.shekel > 0 ? inBand(s.linkedShare, b.linked) : null} hint="ממשלתי + קונצרני צמוד מדד; הטווח נבדק על החלק היחסי מתוך צמוד + שקלי" />
      <Tile label="סה״כ שקלי" value={pct(s.shekel)} band={`${b.shekel[0]}%–${b.shekel[1]}%`} sub={`יחסי ${pct(s.shekelShare, 1)}`}
        ok={s.linked + s.shekel > 0 ? inBand(s.shekelShare, b.shekel) : null} />
      <Tile label="סה״כ מט״ח" value={pct(s.fx)} sub="מניות חו״ל + אג״ח דולרי − מנוטרל" />
      <Tile label="סה״כ אמריקאיות" value={pct(s.us)} sub={`מתוכן דרך קרנות ${pct(s.usFunds, 1)}`} />
      <Tile label="סה״כ קרנות" value={pct(s.funds)} band={`עד ${res.config.settings.fund_cap}%`} ok={s.funds <= res.config.settings.fund_cap + 0.005} />
      <Tile label="דמי ניהול של הקרנות" value={pct(s.fundFees, 3)} sub="מהתיק" />
      <Tile label="סה״כ דמי ניהול בתיק" value={pct(s.totalFees, 3)} sub={`חוזה ${pct(s.feeVat, 3)} כולל מע״מ`} />
      <Tile label="הכנסות לבית ההשקעות" value={pct(s.revenue, 3)} sub={`ללא מע״מ ${pct(s.revenueExVat, 3)}`}
        hint={`ניירות ישירים ועו״ש לפי דמי החוזה; קרנות אג״ח ${res.config.settings.rev_share_bond}% וקרנות מניות ${res.config.settings.rev_share_equity}% מדמי הקרן`} />
    </div>
  )
}

export function Checks({ checks }) {
  if (!checks.length) {
    return <p className="flex items-center gap-2 rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800"><CheckCircle2 className="h-4 w-4" />כל הבדיקות עברו: משקלים, מח״מ, צמוד/שקלי, חשיפה לחו״ל ומגבלת קרנות</p>
  }
  return (
    <ul className="space-y-1">
      {checks.map((c, i) => (
        <li key={i} className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm ${c.level === 'error' ? 'bg-red-50 text-red-800' : 'bg-amber-50 text-amber-900'}`}>
          <AlertTriangle className="h-4 w-4 shrink-0" />{c.text}
        </li>
      ))}
    </ul>
  )
}

function Donut({ data, title, empty, foot = 'אחוז מתוך המניות · אחוז מהתיק בצד' }) {
  const rows = data.filter((d) => d.share > 0.05)
  return (
    <div className="card p-4">
      <h4 className="card-title mb-2">{title}</h4>
      {!rows.length ? <p className="py-10 text-center text-sm text-slate-400">{empty}</p> : (
        <div className="flex items-center gap-4">
          <div className="h-40 w-40 shrink-0">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={rows} dataKey="share" nameKey="label" innerRadius="58%" outerRadius="100%" stroke="rgb(var(--surface))" strokeWidth={2} isAnimationActive={false}>
                  {rows.map((r) => <Cell key={r.label} fill={r.color} />)}
                </Pie>
                <Tooltip formatter={(v, n) => [pct(v, 1), n]} {...tip} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="flex-1 space-y-1.5 text-sm">
            {rows.map((r) => (
              <li key={r.label} className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: r.color }} />
                <span className="flex-1 truncate text-slate-700">{r.label}</span>
                <span className="num font-semibold text-slate-900">{pct(r.share, 1)}</span>
                <span className="num w-14 text-left text-xs text-slate-400">{pct(r.F, 1)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-2 text-[11px] text-slate-400">{foot}</p>
    </div>
  )
}

/** Sector share (bars) with the gap from the benchmark index – the Excel's "יחסי בפועל" and "פער מהמדד". */
function SectorBars({ title, rows, benchKey, benchLabel, columns, exposures, note }) {
  const main = rows.filter((r) => !r.memo)
  const memo = rows.filter((r) => r.memo && r.total > 0.0005)
  const max = Math.max(1, ...main.map((r) => Math.max(r.share, r.weights[benchKey] || 0)))
  const any = main.some((r) => r.total > 0)
  return (
    <div className="card p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="card-title">{title}</h4>
        <span className="text-[11px] text-slate-400">חשיפה: {columns.filter((c) => exposures[c.key] > 0.0005).map((c) => `${c.label} ${pct(exposures[c.key], 1)}`).join(' · ') || '—'}</span>
      </div>
      {!any ? <p className="py-8 text-center text-sm text-slate-400">אין חשיפה מנייתית</p> : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[11px] text-slate-500">
              <th className="pb-1 text-right font-medium">ענף</th>
              <th className="pb-1 text-right font-medium">משקל בפועל <span className="text-slate-400">| {benchLabel}</span></th>
              <th className="pb-1 text-left font-medium">פער מהמדד</th>
            </tr>
          </thead>
          <tbody>
            {main.map((r) => {
              const bench = r.weights[benchKey] || 0
              const gap = r.share - bench
              return (
                <tr key={r.sector}>
                  <td className="w-36 py-1 pl-2 text-xs text-slate-700">{r.label}</td>
                  <td className="py-1">
                    <div className="relative h-4 rounded bg-slate-100" title={`${pct(r.share, 1)} בפועל · ${pct(bench, 1)} במדד`}>
                      <div className="absolute inset-y-0 right-0 rounded" style={{ width: `${(r.share / max) * 100}%`, background: SERIES[0] }} />
                      <div className="absolute -inset-y-0.5 w-0.5 bg-slate-800" style={{ right: `${(bench / max) * 100}%` }} />
                      <span className="num absolute inset-y-0 left-1 text-[10px] leading-4 text-slate-600">{pct(r.share, 1)}</span>
                    </div>
                  </td>
                  <td className="num w-16 py-1 text-left text-xs font-semibold" style={{ color: Math.abs(gap) < 0.05 ? undefined : gap > 0 ? GAIN : LOSS }}>
                    {gap > 0 ? '+' : ''}{gap.toFixed(1)}%
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {memo.length > 0 && <p className="mt-2 text-[11px] text-slate-500">{memo.map((m) => `${m.label}: ${pct(m.total, 2)} מהתיק`).join(' · ')}</p>}
      {note && <p className="mt-2 text-[11px] text-slate-400">{note}</p>}
    </div>
  )
}

function Ratings({ res }) {
  // Sequential (one hue, light -> dark) because the buckets are ordered by risk
  const shades = ['rgb(150 226 245)', 'rgb(90 170 215)', 'rgb(52 110 185)', 'rgb(31 60 150)']
  const max = Math.max(1, ...res.ratingRows.map((r) => r.share))
  return (
    <div className="card p-4">
      <h4 className="card-title mb-1">פיזור סיכון באג״ח הקונצרני</h4>
      <p className="mb-3 text-[11px] text-slate-400">ניירות קונצרניים וקרנות לפי קבוצת סיכון · {pct(res.ratingTotal, 2)} מהתיק{res.unrated > 0.005 ? ` · ${pct(res.unrated, 2)} ללא סיווג` : ''}</p>
      <div className="space-y-2.5">
        {res.ratingRows.map((r, i) => (
          <div key={r.key} className="flex items-center gap-3 text-sm" title={`${pct(r.share, 1)} מהקונצרני · ${pct(r.F, 2)} מהתיק`}>
            <span className="w-24 shrink-0 text-slate-700">{r.label}</span>
            <div className="relative h-5 flex-1 rounded bg-slate-100">
              <div className="absolute inset-y-0 right-0 rounded" style={{ width: `${(r.share / max) * 100}%`, background: shades[i] }} />
            </div>
            <span className="num w-14 text-left font-semibold text-slate-900">{pct(r.share, 1)}</span>
            <span className="num w-14 text-left text-xs text-slate-400">{pct(r.F, 2)}</span>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-slate-400">אחוז מתוך האג״ח המסווגות · אחוז מהתיק בצד. קרנות מסווגות לפי הדירוג הדומיננטי בגילוי הנאות.</p>
    </div>
  )
}

function RealEstate({ re }) {
  return (
    <div className="card p-4">
      <h4 className="card-title mb-1">נדל״ן מניב בישראל – באג״ח הקונצרני</h4>
      <p className="mb-3 text-[11px] text-slate-400">שיעור הנדל״ן המניב בכל מדד/קרן × המשקל, ואג״ח ישירות שסווגו לענף</p>
      <div className="mb-3 flex items-end gap-6">
        <div><div className="text-[11px] text-slate-500">יחסי בפועל</div><div className="num text-2xl font-bold text-slate-900">{pct(re.share, 1)}</div></div>
        <div><div className="text-[11px] text-slate-500">תל בונד 60</div><div className="num text-lg font-semibold text-slate-600">{pct(re.benchmark, 1)}</div></div>
        {re.gap != null && <div><div className="text-[11px] text-slate-500">פער מהמדד</div><div className="num text-lg font-semibold" style={{ color: re.gap > 0 ? LOSS : GAIN }}>{re.gap > 0 ? '+' : ''}{re.gap.toFixed(1)}%</div></div>}
      </div>
      <ul className="max-h-36 space-y-1 overflow-auto text-xs">
        {re.rows.sort((a, b) => b.contrib - a.contrib).map((r) => (
          <li key={r.id} className="flex items-center gap-2">
            <span dir="auto" className="flex-1 truncate text-slate-600">{r.name}</span>
            <span className="num text-slate-400">{pct(r.share, 1)} × {pct(r.F, 2)}</span>
            <span className="num w-14 text-left font-semibold text-slate-800">{pct(r.contrib, 2)}</span>
          </li>
        ))}
        {!re.rows.length && <li className="py-4 text-center text-slate-400">אין חשיפה מזוהה</li>}
      </ul>
    </div>
  )
}

export default function AllocationAnalysis({ res }) {
  const global = res.config.template === 'global'
  const geo = res.geography.map((g, i) => ({ ...g, color: SERIES[i] }))
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
      {global && <Donut title="פיזור גיאוגרפי – מניות" data={geo} empty="אין מניות במודל" />}
      <SectorBars title="ענפים – מניות בישראל" rows={res.ilSectors} benchKey="ta125" benchLabel="קו: ת״א 125" columns={IL_COLUMNS} exposures={res.ilexp}
        note="משקל הענף בכל מדד/קרן × החשיפה אליה, ועוד מניות ישירות לפי ענף. הנחות הרכב המדדים ניתנות לעריכה בהגדרות." />
      {global && (
        <SectorBars title="ענפים – מניות בחו״ל" rows={res.foreignSectors} benchKey="SP" benchLabel="קו: S&P 500" columns={FOREIGN_COLUMNS} exposures={res.fexp}
          note="קרנות ללא שיוך מפוצלות לפי האזורים בגילוי הנאות: ארה״ב → S&P, אירופה → STOXX, שאר העולם." />
      )}
      <Ratings res={res} />
      <RealEstate re={res.realEstate} />
      {!global && <Donut title="פיזור לפי רכיבים" data={[
        { label: 'מניות', share: res.summary.equity, F: res.summary.equity, color: SERIES[0] },
        { label: 'אג״ח ממשלתי', share: res.summary.gov, F: res.summary.gov, color: SERIES[1] },
        { label: 'אג״ח קונצרני', share: res.summary.corp, F: res.summary.corp, color: SERIES[2] },
        { label: 'עו״ש', share: Math.max(0, res.summary.cash), F: res.summary.cash, color: OTHER_COLOR },
      ]} empty="המודל ריק" foot="אחוז מהתיק (מניות ואג״ח כולל שיקוף קרנות)" />}
    </div>
  )
}
