import { ArrowLeft, Lock, Trophy } from 'lucide-react'
import { navigate } from '../../lib/useHashRoute'
import { STATUS } from '../models/shared'

/**
 * Which IBI model is closest to the prospect's portfolio (internal – not part of the client review).
 * Every model is measured exactly like the prospect (same look-through); the score is 100 minus the
 * weighted average gap over the exposures below (equity counts most).
 */
const fmt = (key, v) => (v == null ? '—' : key === 'duration' ? v.toFixed(2) : `${v.toFixed(1)}%`)
const fmtGap = (key, g) => (g == null ? '' : `${g > 0 ? '+' : g < 0 ? '−' : ''}${key === 'duration' ? Math.abs(g).toFixed(1) : Math.abs(g).toFixed(1)}`)
const gapLevel = (key, g) => {
  const a = Math.abs(g ?? 0)
  const [s, m] = key === 'duration' ? [0.3, 1] : [3, 10]
  return a < s ? 'text-slate-400' : a < m ? 'text-amber-700' : 'text-red-700 font-semibold'
}
const TEMPLATE = { global: 'ישראל + חו״ל', israel: 'ישראל בלבד' }

export default function ModelMatch({ res }) {
  const list = res.matches || []
  const dims = res.match_dims || []
  if (!list.length) return null
  const best = list[0]
  const top = dims.filter((d) => best.gaps[d.key] != null)
    .sort((a, b) => Math.abs(best.gaps[b.key]) * (b.key === 'duration' ? 10 : 1) - Math.abs(best.gaps[a.key]) * (a.key === 'duration' ? 10 : 1))
    .slice(0, 3)

  return (
    <section className="card overflow-hidden">
      <header className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-3">
        <Trophy className="h-4 w-4 text-brand-700" />
        <h3 className="card-title">המודל שלנו הקרוב ביותר לתיק</h3>
        <span className="text-xs text-slate-400">כל מודל נמדד בדיוק כמו התיק של הלקוח, לאחר שיקוף קרנות</span>
        <span className="mr-auto flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500"><Lock className="h-3 w-3" />פנימי – לא מופיע בסקירה ללקוח</span>
      </header>

      <div className="flex flex-wrap items-center gap-4 border-b border-slate-100 bg-brand-50/40 px-4 py-4">
        <div className="grid h-16 w-16 shrink-0 place-items-center rounded-2xl bg-navy-900 text-white">
          <div className="text-center leading-tight"><div className="num text-lg font-extrabold">{best.score.toFixed(0)}%</div><div className="text-[10px] opacity-80">התאמה</div></div>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-bold text-slate-900">{best.name}</span>
            {best.template && <span className="rounded-full bg-surface px-2 py-0.5 text-[11px] text-slate-600 ring-1 ring-slate-200">{TEMPLATE[best.template]}</span>}
          </div>
          <p className="mt-1 text-sm text-slate-600">
            ההבדלים העיקריים (המודל מול התיק):{' '}
            {top.map((d, i) => (
              <span key={d.key}>{i > 0 && ' · '}{d.label} <b className={gapLevel(d.key, best.gaps[d.key])}>{fmtGap(d.key, best.gaps[d.key])}{d.key === 'duration' ? ' שנים' : ' נק׳'}</b></span>
            ))}
          </p>
        </div>
        <button className="btn-outline" onClick={() => navigate(`/models/${best.id}`)}>פתיחת המודל<ArrowLeft className="h-4 w-4" /></button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[1100px] text-sm">
          <thead className="bg-slate-50/80">
            <tr>
              <th className="th">מודל</th>
              <th className="th text-left">התאמה</th>
              {dims.map((d) => <th key={d.key} className="th text-left" title={`משקל בציון: ${d.weight}`}>{d.label}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            <tr className="bg-slate-50/60">
              <td className="td font-semibold text-slate-800">התיק של הלקוח</td>
              <td className="td" />
              {dims.map((d) => <td key={d.key} className="td num text-left font-semibold text-slate-900">{fmt(d.key, res.profile?.[d.key])}</td>)}
            </tr>
            {list.map((m, i) => {
              const st = STATUS[m.status] ?? STATUS.draft
              return (
                <tr key={m.id} className={`cursor-pointer hover:bg-brand-50/50 ${i === 0 ? 'bg-brand-50/30' : ''}`} onClick={() => navigate(`/models/${m.id}`)}>
                  <td className="td">
                    <div className="flex items-center gap-2">
                      <span className="num w-5 text-xs text-slate-400">{i + 1}</span>
                      <span className="font-medium text-slate-800">{m.name}</span>
                      <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${st.cls}`}>{st.label}</span>
                    </div>
                  </td>
                  <td className="td">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-[#00ADDC]" style={{ width: `${m.score}%` }} /></div>
                      <span className="num text-xs font-bold text-slate-900">{m.score.toFixed(0)}%</span>
                    </div>
                  </td>
                  {dims.map((d) => (
                    <td key={d.key} className="td num text-left">
                      <div className="text-slate-800">{fmt(d.key, m.profile?.[d.key])}</div>
                      {m.gaps[d.key] != null && <div className={`text-[11px] ${gapLevel(d.key, m.gaps[d.key])}`}>{fmtGap(d.key, m.gaps[d.key])}</div>}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500">
        ציון ההתאמה = 100 פחות הפער הממוצע המשוקלל בין המודל לתיק (בנקודות אחוז מהתיק; חשיפה למניות נספרת כפול שלוש, שנת מח״מ = 10 נקודות).
        מתחת לכל ערך – הפער מהתיק: אפור קטן, כתום בינוני, אדום גדול.
      </p>
    </section>
  )
}
