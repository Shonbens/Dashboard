import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ArrowLeft, Download, FileSpreadsheet, FileText, Loader2, Plus, RefreshCw, Upload } from 'lucide-react'
import { modelsOverview } from '../../lib/api'
import { navigate } from '../../lib/useHashRoute'
import { fmtILS, fmtPct, fmtSignedPct } from '../../lib/format'
import StackedBar, { Legend } from './StackedBar'
import { ASSET_ORDER, GEO_ORDER, STATUS, fmtDate, heat, riskColor, riskLevel } from './shared'
import { scenarioIcon } from '../scenarioIcons'
import ImportDialog from './ImportDialog'
import NewModelDialog from './NewModelDialog'
import ModelsSummaryTable from './ModelsSummaryTable'

const byRisk = (a, b) => (a.equity_target ?? a.metrics?.equity_weight ?? 999) - (b.equity_target ?? b.metrics?.equity_weight ?? 999)

export default function ModelsHome() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [dialog, setDialog] = useState(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    const ctrl = new AbortController()
    setLoading(true)
    modelsOverview(1_000_000, ctrl.signal)
      .then((d) => { setData(d); setError(null) })
      .catch((e) => !ctrl.signal.aborted && setError(e.message))
      .finally(() => !ctrl.signal.aborted && setLoading(false))
    return () => ctrl.abort()
  }, [tick])

  const models = useMemo(() => [...(data?.models ?? [])].sort(byRisk), [data])
  const ok = models.filter((m) => !m.error && !m.empty)
  const reload = () => setTick((t) => t + 1)

  return (
    <main className="mx-auto max-w-[1440px] space-y-6 px-4 py-7 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow">מודלי הבית</div>
          <h1 className="mt-1 text-[28px] font-extrabold leading-tight tracking-tight text-slate-900">סולם המודלים</h1>
          <p className="mt-1 text-sm text-slate-500">
            {models.length ? `${models.length} מודלים פעילים, מהסולידי למנייתי · הנתונים לאחר שיקוף קרנות, לפי תיק של ₪1,000,000` : 'ניהול, השוואה וניתוח של מודלי ההשקעה'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn-ghost" onClick={reload} disabled={loading} title="רענון נתונים">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}<span className="hidden lg:inline">רענון</span>
          </button>
          <a className="btn-ghost" href="/api/models/demo-workbook" download><FileSpreadsheet className="h-4 w-4" /><span className="hidden lg:inline">קובץ דוגמה</span></a>
          <a className="btn-outline" href="/api/models/report.pdf" target="_blank" rel="noopener" title="דוח PDF ממותג: עמוד השוואה + דף לכל מודל">
            <FileText className="h-4 w-4" />דוח PDF
          </a>
          <a className="btn-outline" href="/api/models/export" download><Download className="h-4 w-4" />ייצוא</a>
          <button className="btn-outline" onClick={() => setDialog('import')}><Upload className="h-4 w-4" />ייבוא מאקסל</button>
          <button className="btn-primary" onClick={() => setDialog('new')}><Plus className="h-4 w-4" />מודל חדש</button>
        </div>
      </div>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>}
      {!data && loading && <LadderSkeleton />}

      {data && models.length === 0 && (
        <div className="card p-12 text-center">
          <p className="text-lg font-semibold text-slate-800">אין עדיין מודלים</p>
          <p className="mt-1 text-sm text-slate-500">צרו מודל חדש או ייבאו את קובץ המודלים מאקסל (כל גיליון = מודל).</p>
        </div>
      )}

      {models.length > 0 && (
        <div className={`space-y-6 transition-opacity duration-300 ${loading ? 'opacity-70' : ''}`}>
          <section aria-label="סולם המודלים">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
              {models.map((m) => <LadderCard key={m.id} m={m} />)}
            </div>
            <div className="mt-3 flex items-center gap-3 px-1 text-xs font-medium text-slate-400" aria-hidden>
              <span>סולידי</span>
              <div className="h-1.5 flex-1 rounded-full" style={{ background: `linear-gradient(to left, ${riskColor(10)}, ${riskColor(100)})` }} />
              <span className="flex items-center gap-1">מנייתי <ArrowLeft className="h-3.5 w-3.5" /></span>
            </div>
          </section>

          <ModelsSummaryTable tick={tick} />
          {ok.length > 0 && <CompositionCompare models={ok} />}
          {ok.length > 0 && <ScenarioHeatmap models={ok} />}
          {ok.length > 0 && <MetricsTable models={ok} />}
        </div>
      )}

      {dialog === 'import' && <ImportDialog onClose={() => setDialog(null)} onDone={() => { setDialog(null); reload() }} />}
      {dialog === 'new' && <NewModelDialog models={models} onClose={() => setDialog(null)} />}
    </main>
  )
}

function LadderCard({ m }) {
  const st = STATUS[m.status] ?? STATUS.draft
  const open = () => navigate(`/models/${m.id}`)
  if (m.error || m.empty) {
    return (
      <button onClick={open} className="card p-5 text-right hover:shadow-card-hover">
        <div className="num text-3xl font-extrabold text-slate-900">{m.name}</div>
        <p className="mt-2 text-sm text-slate-500">{m.error ? `שגיאה בניתוח: ${m.error}` : 'מודל ריק – לחצו להוספת ניירות'}</p>
      </button>
    )
  }
  const eq = m.metrics.equity_weight
  const color = riskColor(eq)
  const level = riskLevel(eq)
  const worst = [...m.scenarios].sort((a, b) => a.pnl_pct - b.pnl_pct)[0]
  const off = m.kind !== 'allocation' && Math.abs(m.total_weight - 100) > 0.01
  const drift = m.equity_drift
  const fee = m.metrics.weighted_fee

  return (
    <button onClick={open}
      className="card group relative flex flex-col overflow-hidden text-right transition duration-200 hover:-translate-y-0.5 hover:shadow-card-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400">
      <div className="h-1.5 w-full" style={{ background: color }} />
      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-start justify-between gap-2">
          <div className={`num font-extrabold leading-none tracking-tight text-slate-900 ${m.name.length > 9 ? 'text-xl leading-tight' : 'text-[34px]'}`}>{m.name}</div>
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${st.cls}`}>{st.label}</span>
        </div>
        <div className="mt-2 line-clamp-1 min-h-[1rem] text-xs text-slate-500">
          {m.kind === 'allocation' && <span className="ml-1.5 rounded bg-navy-50 px-1.5 py-0.5 text-[10px] font-medium text-navy-700">גיליון הקצאה</span>}{m.description}
        </div>

        <div className="mt-3 flex items-center gap-2" title={`רמת סיכון ${level} מתוך 5`}>
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map((i) => (
              <span key={i} className="h-1.5 w-5 rounded-full" style={{ background: i <= level ? color : 'rgb(var(--slate-200))' }} />
            ))}
          </div>
          <span className="text-[11px] text-slate-400">סיכון {level}/5</span>
        </div>

        <div className="mt-5">
          <div className="text-xs text-slate-500">הפסד בתרחיש הגרוע</div>
          <div className="num mt-0.5 text-[26px] font-bold leading-none text-red-700">{fmtSignedPct(worst?.pnl_pct, 1)}</div>
          <div className="mt-1 truncate text-[11px] text-slate-400">{worst?.name}</div>
        </div>

        <div className="mt-4"><StackedBar data={m.asset_classes} order={ASSET_ORDER} height="h-2" /></div>

        <dl className="mt-4 grid grid-cols-2 gap-x-3 gap-y-3 border-t border-slate-100 pt-4 text-sm">
          <Stat k="מניות בפועל" v={fmtPct(eq, 0)}
            chip={drift != null && Math.abs(drift) >= 0.5 ? fmtSignedPct(drift, 1) : null} />
          <Stat k="חשיפת מט״ח" v={fmtPct(m.metrics.fx_exposure, 0)} />
          <Stat k="מח״מ אג״ח" v={m.metrics.bond_duration ? m.metrics.bond_duration.toFixed(1) : '—'} />
          <Stat k="דמי ניהול" v={fee != null ? `${fee.toFixed(2)}%` : '—'} coverage={fee != null ? m.metrics.fee_coverage : null} />
        </dl>

        {(off || m.unpriced?.length > 0) && (
          <div className="mt-4 flex items-center gap-1.5 rounded-lg bg-amber-50 px-2 py-1.5 text-xs text-amber-800">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            {off ? <>סך משקלים <span className="num">{fmtPct(m.total_weight, 1)}</span></> : `${m.unpriced.length} ניירות לא מזוהים`}
          </div>
        )}

        <div className="mt-auto flex items-center justify-between gap-2 pt-4 text-[11px] text-slate-400">
          <span><span className="num">v{m.version}</span> · {m.holdings_count} ניירות</span>
          <span className="num">{fmtDate(m.updated_at).split(',')[0]}</span>
        </div>
      </div>
    </button>
  )
}

function Stat({ k, v, chip, coverage }) {
  return (
    <div>
      <dt className="text-[11px] text-slate-500">{k}</dt>
      <dd className="mt-0.5 flex items-center gap-1.5">
        <span className="num text-[15px] font-semibold text-slate-900">{v}</span>
        {chip && <span className="num rounded bg-amber-50 px-1 text-[10px] font-medium text-amber-800" title="סטייה מיעד המניות">{chip}</span>}
      </dd>
      {coverage != null && coverage < 99.5 && (
        <div className="mt-1 flex items-center gap-1" title={`נתוני דמי ניהול קיימים ל-${coverage.toFixed(0)}% מהמודל`}>
          <div className="h-1 w-10 overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-slate-400" style={{ width: `${coverage}%` }} /></div>
          <span className="num text-[10px] text-slate-400">{coverage.toFixed(0)}%</span>
        </div>
      )}
    </div>
  )
}

function SectionCard({ title, subtitle, actions, children, flush = false }) {
  return (
    <section className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div>
          <h2 className="card-title">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
        </div>
        {actions}
      </div>
      <div className={flush ? '' : 'p-5'}>{children}</div>
    </section>
  )
}

function CompositionCompare({ models }) {
  const [mode, setMode] = useState('asset')
  const order = mode === 'asset' ? ASSET_ORDER : GEO_ORDER
  return (
    <SectionCard title="הרכב המודלים לאחר שיקוף" subtitle="החשיפה בפועל לנכסי הבסיס, לאחר פירוק קרנות ותעודות סל"
      actions={
        <div className="flex rounded-lg bg-slate-100 p-0.5 text-xs" role="tablist">
          {[['asset', 'סוגי נכסים'], ['geo', 'גיאוגרפיה']].map(([k, l]) => (
            <button key={k} role="tab" aria-selected={mode === k} onClick={() => setMode(k)}
              className={`rounded-md px-3 py-1 font-medium transition ${mode === k ? 'bg-surface text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>{l}</button>
          ))}
        </div>
      }>
      <div className="space-y-2.5">
        {models.map((m) => (
          <div key={m.id} className="grid grid-cols-[64px_1fr] items-center gap-4">
            <button onClick={() => navigate(`/models/${m.id}`)} className="flex items-center gap-2 text-right">
              <span className="h-6 w-1 rounded-full" style={{ background: riskColor(m.metrics.equity_weight) }} />
              <span className="num text-sm font-bold text-slate-800 hover:text-brand-700">{m.name}</span>
            </button>
            <StackedBar data={mode === 'asset' ? m.asset_classes : m.geography} order={order} height="h-7" labels />
          </div>
        ))}
      </div>
      <div className="mt-5"><Legend order={order} /></div>
    </SectionCard>
  )
}

function ScenarioHeatmap({ models }) {
  const scenarios = models[0]?.scenarios ?? []
  const maxAbs = Math.max(...models.flatMap((m) => m.scenarios.map((s) => Math.abs(s.pnl_pct))), 1)
  return (
    <SectionCard title="מבחני קיצון – תשואה משוערת לפי מודל" subtitle="תרחישים היפותטיים · כחול = רווח, אדום = הפסד · עוצמת הצבע לפי גודל השינוי" flush>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="th sticky right-0 z-10 bg-slate-50">תרחיש</th>
              {models.map((m) => <th key={m.id} className="th text-center"><span className="num text-[13px] text-slate-700">{m.name}</span></th>)}
            </tr>
          </thead>
          <tbody>
            {scenarios.map((s, i) => {
              const Icon = scenarioIcon(s.id)
              return (
                <tr key={s.id} className="border-t border-slate-100">
                  <td className="td sticky right-0 z-10 bg-surface">
                    <span className="flex items-center gap-2 text-slate-700"><Icon className="h-4 w-4 text-slate-400" />{s.name}</span>
                  </td>
                  {models.map((m) => {
                    const v = m.scenarios[i]?.pnl_pct
                    return (
                      <td key={m.id} className="min-w-[88px] px-1.5 py-1.5 text-center">
                        <div className="num rounded-md py-2 text-[13px] font-semibold text-slate-900" style={{ background: heat(v, maxAbs) }}>{fmtSignedPct(v, 1)}</div>
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </SectionCard>
  )
}

function MetricsTable({ models }) {
  const rows = useMemo(() => [
    ['יעד מניות (לפי שם)', (m) => (m.equity_target != null ? fmtPct(m.equity_target, 0) : '—')],
    ['מניות בפועל', (m) => fmtPct(m.metrics.equity_weight, 1)],
    ['חשיפה לישראל', (m) => fmtPct(m.geography['ישראל'] || 0, 1)],
    ['חשיפת מט״ח', (m) => fmtPct(m.metrics.fx_exposure, 1)],
    ['מח״מ רכיב האג״ח', (m) => (m.metrics.bond_duration ? m.metrics.bond_duration.toFixed(2) : '—')],
    ['DV01 לכל ₪1M', (m) => fmtILS(m.metrics.dv01_ils)],
    ['דמי ניהול משוקללים', (m) => (m.metrics.weighted_fee != null ? `${m.metrics.weighted_fee.toFixed(2)}% (כיסוי ${m.metrics.fee_coverage.toFixed(0)}%)` : '—')],
    ['שינוי יומי משוקלל', (m) => fmtSignedPct(m.day_change_pct)],
    ['ריכוז הגדול ביותר', (m) => (m.top_underlying[0] ? `${m.top_underlying[0].name} · ${m.top_underlying[0].total.toFixed(1)}%` : '—')],
  ], [])
  return (
    <SectionCard title="מדדי סיכון ועלות" subtitle="השוואה מספרית בין המודלים" flush>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="th sticky right-0 z-10 bg-slate-50">מדד</th>
              {models.map((m) => <th key={m.id} className="th"><span className="num text-[13px] text-slate-700">{m.name}</span></th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, f]) => (
              <tr key={label} className="border-t border-slate-100 hover:bg-slate-50">
                <td className="td sticky right-0 z-10 bg-surface text-slate-600">{label}</td>
                {models.map((m) => (
                  <td key={m.id} className="td min-w-[120px] max-w-[200px] truncate font-medium text-slate-900" title={String(f(m))}>
                    <span dir="auto">{f(m)}</span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  )
}

function LadderSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="card space-y-4 p-5">
          <div className="skeleton h-8 w-20" />
          <div className="skeleton h-3 w-32" />
          <div className="skeleton h-7 w-24" />
          <div className="skeleton h-2 w-full" />
          <div className="grid grid-cols-2 gap-3">{[0, 1, 2, 3].map((j) => <div key={j} className="skeleton h-9" />)}</div>
        </div>
      ))}
    </div>
  )
}
