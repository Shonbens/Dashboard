import { Fragment, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertCircle, ChevronDown, ChevronLeft, Globe2, Layers, Loader2, ScanSearch, Timer, Coins } from 'lucide-react'
import useDebouncedRequest from '../lib/useDebouncedRequest'
import { fundXray } from '../lib/api'
import { fmtILS, fmtPct } from '../lib/format'
import { SERIES } from './palette'

const METHOD = {
  maya: { label: 'מאי״ה', cls: 'bg-brand-50 text-brand-700' },
  static: { label: 'מיפוי מדד', cls: 'bg-violet-50 text-violet-700' },
  live: { label: 'yfinance', cls: 'bg-emerald-50 text-emerald-700' },
  direct: { label: 'נייר בודד', cls: 'bg-slate-100 text-slate-600' },
  default: { label: 'הנחה', cls: 'bg-amber-50 text-amber-800' },
}
// Fixed categorical order for the composition mini-bars (entity -> slot, never by rank)
const COMPOSITION = [
  { key: 'equity', label: 'מניות', color: SERIES[0] },
  { key: 'gov_bonds', label: 'אג״ח ממשלתי', color: SERIES[1] },
  { key: 'corp_bonds', label: 'אג״ח קונצרני', color: SERIES[2] },
  { key: 'cash', label: 'מזומן', color: SERIES[3] },
  { key: 'other', label: 'אחר', color: 'rgb(var(--s-other))' },
]

export default function XRayView({ rows, aum }) {
  const key = useMemo(() => JSON.stringify(rows.map((r) => [r.input_id, r.weight])) + aum, [rows, aum])
  const { data, loading, error } = useDebouncedRequest((signal) => fundXray(rows, aum, signal), rows.length ? key : null, 400)

  if (error && !data) return <ErrorCard msg={error} />
  if (!data) return <LoadingCard text="מבצע שיקוף (Look-Through) של הקרנות… נתוני מאי״ה ו-yfinance" />

  const m = data.metrics
  return (
    <div className={`space-y-5 transition-opacity ${loading ? 'opacity-60' : ''}`}>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 2xl:grid-cols-6">
        <Tile icon={ScanSearch} label="כיסוי שיקוף" value={fmtPct(m.coverage, 1)} sub="מהתיק פורק לרכיבי בסיס" />
        <Tile icon={Layers} label="חשיפה מנייתית בפועל" value={fmtPct(m.equity_weight, 1)} sub="לאחר שיקוף קרנות" />
        <Tile icon={Coins} label="חשיפה למט״ח" value={fmtPct(m.fx_exposure, 1)} sub={fmtILS((aum * m.fx_exposure) / 100)} />
        <Tile icon={Timer} label="מח״מ רכיב האג״ח" value={m.bond_duration ? m.bond_duration.toFixed(2) : '—'} sub={`אג״ח: ${fmtPct(m.bond_weight, 1)} מהתיק`} />
        <Tile icon={Globe2} label="DV01 – רגישות לריבית" value={fmtILS(m.dv01_ils)} sub="שינוי שווי לכל נקודת בסיס" />
        <Tile icon={Coins} label="דמי ניהול משוקללים" value={m.weighted_fee != null ? `${m.weighted_fee.toFixed(2)}%` : '—'}
          sub={m.weighted_fee != null ? `${fmtILS(m.annual_cost_ils)} בשנה · כיסוי ${fmtPct(m.fee_coverage, 0)}` : 'אין נתוני עלות'} />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <BarsCard title="סוגי נכסים בפועל" data={data.asset_classes} />
        <BarsCard title="פיזור גיאוגרפי אמיתי" data={data.geography} />
        <SectorChart data={data.sectors} />
      </div>

      <TopUnderlying items={data.top_underlying} />
      <HoldingsLookThrough rows={data.holdings} />
    </div>
  )
}

function Tile({ icon: Icon, label, value, sub }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 text-sm text-slate-500"><Icon className="h-4 w-4 text-brand-700" />{label}</div>
      <div className="mt-1.5 text-xl font-bold text-slate-900"><span className="num">{value}</span></div>
      <div className="mt-0.5 text-xs text-slate-500">{sub}</div>
    </div>
  )
}

function BarsCard({ title, data }) {
  const entries = Object.entries(data)
  const max = Math.max(...entries.map(([, v]) => v), 1)
  return (
    <div className="card p-5">
      <h3 className="card-title mb-4">{title}</h3>
      <div className="space-y-3">
        {entries.map(([k, v]) => (
          <div key={k}>
            <div className="mb-1 flex justify-between text-sm"><span className="text-slate-700">{k}</span><span className="num font-medium text-slate-900">{fmtPct(v)}</span></div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full" style={{ width: `${Math.max(0, (v / max) * 100)}%`, background: SERIES[0] }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function SectorChart({ data }) {
  const rows = Object.entries(data).map(([name, v]) => ({ name, v }))
  return (
    <div className="card p-5">
      <h3 className="card-title mb-1">חשיפה סקטוריאלית (מניות)</h3>
      <p className="mb-3 text-xs text-slate-500">כאחוז מסך התיק, לאחר שיקוף תעודות סל וקרנות</p>
      <div style={{ height: Math.max(220, rows.length * 26 + 20) }} dir="ltr">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid horizontal={false} stroke="rgb(var(--slate-100))" />
            <XAxis type="number" reversed tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11, fill: 'rgb(var(--slate-500))' }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="name" orientation="right" width={92} tick={{ fontSize: 12, fill: 'rgb(var(--slate-700))' }} axisLine={false} tickLine={false} />
            <Tooltip cursor={{ fill: 'rgb(var(--slate-100))' }} formatter={(v) => [fmtPct(v), 'משקל בתיק']} contentStyle={{ direction: 'rtl', borderRadius: 8, fontSize: 13 }} />
            <Bar dataKey="v" fill={SERIES[0]} radius={[4, 0, 0, 4]} maxBarSize={14} isAnimationActive={false}>
              {rows.map((r) => <Cell key={r.name} fill={r.name === 'לא מסווג' ? 'rgb(var(--s-other))' : SERIES[0]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function TopUnderlying({ items }) {
  const max = Math.max(...items.map((i) => i.total), 1)
  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4">
        <div>
          <h3 className="card-title">ריכוזיות אמיתית – חשיפה לנכסי הבסיס</h3>
          <p className="text-xs text-slate-500">אחזקה ישירה + חשיפה עקיפה דרך קרנות ותעודות סל</p>
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-600">
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: SERIES[0] }} />ישירה</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: SERIES[1] }} />דרך קרנות</span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50/80">
            <tr><th className="th">#</th><th className="th">נכס בסיס</th><th className="th">ישירה</th><th className="th">עקיפה</th><th className="th">סה״כ</th><th className="th w-1/4">התפלגות</th><th className="th">שווי (₪)</th><th className="th">דרך</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.slice(0, 15).map((u, i) => (
              <tr key={u.key} className="hover:bg-slate-50/70">
                <td className="td text-slate-400">{i + 1}</td>
                <td className="td max-w-[240px]"><div dir="auto" className="truncate font-medium text-slate-800" title={u.name}>{u.name}</div></td>
                <td className="td"><span className="num">{u.direct ? fmtPct(u.direct) : '—'}</span></td>
                <td className="td"><span className="num">{u.indirect ? fmtPct(u.indirect) : '—'}</span></td>
                <td className="td font-semibold text-slate-900"><span className="num">{fmtPct(u.total)}</span></td>
                <td className="td">
                  <div className="flex h-2.5 w-full gap-[2px] overflow-hidden rounded-full bg-slate-100" dir="rtl" title={`ישירה ${fmtPct(u.direct)} · עקיפה ${fmtPct(u.indirect)}`}>
                    {u.direct > 0 && <div style={{ width: `${(u.direct / max) * 100}%`, background: SERIES[0] }} />}
                    {u.indirect > 0 && <div style={{ width: `${(u.indirect / max) * 100}%`, background: SERIES[1] }} />}
                  </div>
                </td>
                <td className="td"><span className="num">{fmtILS(u.value_ils)}</span></td>
                <td className="td max-w-[220px]">
                  <div className="truncate text-xs text-slate-500" title={u.via.map((v) => `${v.fund}: ${v.weight.toFixed(2)}%`).join('\n')}>
                    {u.via.length ? u.via.map((v) => v.fund).join(', ') : 'אחזקה ישירה'}
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

function HoldingsLookThrough({ rows }) {
  const [open, setOpen] = useState(null)
  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4">
        <h3 className="card-title">פירוק לפי אחזקה</h3>
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
          {COMPOSITION.map((c) => (
            <span key={c.key} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: c.color }} />{c.label}</span>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50/80">
            <tr><th className="th w-8" /><th className="th">נייר</th><th className="th">משקל</th><th className="th">שיטה</th><th className="th w-1/4">הרכב בפועל</th><th className="th">מט״ח</th><th className="th">מח״מ</th><th className="th">דמי ניהול</th><th className="th">מקור</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r) => {
              const m = METHOD[r.method] ?? METHOD.default
              const expandable = r.top_holdings.length > 0
              const isOpen = open === r.input_id
              return (
                <Fragment key={r.input_id}>
                  <tr className={`hover:bg-slate-50/70 ${expandable ? 'cursor-pointer' : ''}`} onClick={() => expandable && setOpen(isOpen ? null : r.input_id)}>
                    <td className="td text-slate-400">{expandable && (isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />)}</td>
                    <td className="td max-w-[240px]">
                      <div dir="auto" className="truncate font-medium text-slate-800" title={r.name}>{r.name}</div>
                      <div className="num text-xs text-slate-400">{r.ticker}</div>
                    </td>
                    <td className="td"><span className="num">{fmtPct(r.weight)}</span></td>
                    <td className="td"><span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${m.cls}`}>{m.label}</span></td>
                    <td className="td">
                      <div className="flex h-2.5 w-full gap-[2px] overflow-hidden rounded-full bg-slate-100" dir="rtl"
                        title={COMPOSITION.map((c) => `${c.label}: ${fmtPct(r[c.key], 1)}`).join(' · ')}>
                        {COMPOSITION.map((c) => r[c.key] > 0.05 && <div key={c.key} style={{ width: `${Math.min(100, r[c.key])}%`, background: c.color }} />)}
                      </div>
                    </td>
                    <td className="td"><span className="num">{r.fx_exposure ? fmtPct(r.fx_exposure, 0) : '—'}</span></td>
                    <td className="td"><span className="num">{r.duration ?? '—'}</span></td>
                    <td className="td" title={r.fee_source === 'manual' ? 'הוזן ידנית' : r.fee_source === 'data' ? 'ממקור נתונים' : 'לא ידוע'}>
                      <span className="num">{r.fee != null ? `${r.fee.toFixed(2)}%` : '—'}</span>
                      {r.fee_source === 'manual' && <span className="mr-1 text-[10px] text-slate-400">ידני</span>}
                    </td>
                    <td className="td max-w-[260px]"><div className="truncate text-xs text-slate-500" title={`${r.source}${r.label ? ` · ${r.label}` : ''}`}>{r.label || r.source}</div></td>
                  </tr>
                  {isOpen && (
                    <tr className="bg-slate-50/60">
                      <td />
                      <td colSpan={8} className="px-3 pb-4 pt-1">
                        <div className="mb-2 text-xs font-semibold text-slate-500">10 האחזקות הגדולות בקרן · {r.source}</div>
                        <div className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
                          {r.top_holdings.map((t, i) => (
                            <div key={i} className="flex items-center justify-between gap-3 text-sm">
                              <span dir="auto" className="truncate text-slate-700" title={t.name}>{t.name}</span>
                              <span className="num shrink-0 text-slate-500">{fmtPct(t.weight)}</span>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function LoadingCard({ text }) {
  return (
    <div className="space-y-5" aria-busy="true">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 2xl:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => <div key={i} className="card space-y-3 p-4"><div className="skeleton h-3 w-24" /><div className="skeleton h-6 w-16" /></div>)}
      </div>
      <div className="card flex items-center gap-3 p-5 text-sm text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin text-brand-600" />{text}
      </div>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        {[0, 1, 2].map((i) => <div key={i} className="card space-y-3 p-5">{[0, 1, 2, 3].map((j) => <div key={j} className="skeleton h-4" />)}</div>)}
      </div>
    </div>
  )
}

export function ErrorCard({ msg }) {
  return (
    <div className="card flex items-center gap-3 border-red-200 p-5 text-sm text-red-800">
      <AlertCircle className="h-5 w-5 shrink-0" />{msg}
    </div>
  )
}
