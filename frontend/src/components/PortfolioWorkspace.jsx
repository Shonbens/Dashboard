import { useCallback, useEffect, useMemo, useState } from 'react'
import { Activity, AlertCircle, AlertTriangle, BarChart3, Clock, DollarSign, FileDown, FileText, LayoutDashboard, Loader2, RefreshCw, Scale, ScanSearch, X } from 'lucide-react'
import UploadZone from './UploadZone'
import AumControl from './AumControl'
import KpiCards from './KpiCards'
import AllocationDonut from './AllocationDonut'
import HoldingsTable from './HoldingsTable'
import RebalancePanel from './RebalancePanel'
import AddHolding from './AddHolding'
import XRayView from './XRayView'
import StressTestView from './StressTestView'
import ClientReportDialog from './ClientReportDialog'
import { analyzeHoldings, getQuote, getSampleFile, uploadPortfolio } from '../lib/api'
import { derive, download, toCSV } from '../lib/portfolio'
import { fmtPct } from '../lib/format'

const TABS = [
  { key: 'overview', label: 'סקירת תיק', icon: LayoutDashboard },
  { key: 'rebalance', label: 'איזון תיק', icon: Scale },
  { key: 'xray', label: 'שיקוף קרנות (X-Ray)', icon: ScanSearch },
  { key: 'stress', label: 'מבחני קיצון', icon: Activity },
]

export default function PortfolioWorkspace() {
  const [holdings, setHoldings] = useState([])
  const [summary, setSummary] = useState(null)
  const [warnings, setWarnings] = useState([])
  const [aum, setAum] = useState(1_000_000)
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('overview')
  const [threshold, setThreshold] = useState(1)
  const [sourceFile, setSourceFile] = useState(null)
  const [reportOpen, setReportOpen] = useState(false)

  const d = useMemo(() => derive(holdings, aum, threshold), [holdings, aum, threshold])

  const applyResult = useCallback((res, { keepAum = false } = {}) => {
    setHoldings(res.holdings)
    setSummary(res.summary)
    setWarnings(res.warnings || [])
    if (!keepAum && res.summary.mode === 'quantities') setAum(res.summary.aum)
  }, [])

  const handleFile = async (file) => {
    setLoading(true)
    setError(null)
    try {
      const res = await uploadPortfolio(file, aum)
      applyResult(res)
      setSourceFile(file.name)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const loadSample = async () => {
    try { await handleFile(await getSampleFile()) } catch (e) { setError(e.message) }
  }

  const refresh = async () => {
    if (!holdings.length) return
    setRefreshing(true)
    setError(null)
    try {
      applyResult(await analyzeHoldings(holdings, aum, true), { keepAum: true })
    } catch (e) {
      setError(e.message)
    } finally {
      setRefreshing(false)
    }
  }

  const addHolding = async (id) => {
    if (holdings.some((h) => h.input_id === id)) { setError(`הנייר ${id} כבר קיים בתיק`); return }
    setRefreshing(true)
    try {
      const q = await getQuote(id)
      setHoldings((hs) => [...hs, { ...q, weight: 0, target_weight: null, file_name: null }])
      if (!q.priced) setWarnings((w) => [...w, `הנייר ${id} נוסף אך לא תומחר`])
    } catch (e) {
      setError(e.message)
    } finally {
      setRefreshing(false)
    }
  }

  const setField = (field) => (id, raw) =>
    setHoldings((hs) => hs.map((h) => (h.input_id === id
      ? { ...h, [field]: raw === '' ? (field === 'weight' ? 0 : null) : Math.max(0, Number(raw)) }
      : h)))

  const removeHolding = (id) => setHoldings((hs) => hs.filter((h) => h.input_id !== id))

  const bulk = (action) => setHoldings((hs) => {
    if (action === 'copy') return hs.map((h) => ({ ...h, target_weight: Number((h.weight || 0).toFixed(4)) }))
    if (action === 'equal') return hs.map((h) => ({ ...h, target_weight: Number((100 / hs.length).toFixed(4)) }))
    if (action === 'normalize') {
      const tot = hs.reduce((s, h) => s + (Number(h.target_weight) || 0), 0)
      return tot > 0 ? hs.map((h) => ({ ...h, target_weight: h.target_weight == null ? null : Number(((h.target_weight / tot) * 100).toFixed(4)) })) : hs
    }
    return hs
  })

  const exportCsv = () => {
    const stamp = new Date().toISOString().slice(0, 10)
    download(`portfolio_analysis_${stamp}.csv`, toCSV(d.rows, aum))
  }

  const reset = () => { setHoldings([]); setSummary(null); setWarnings([]); setSourceFile(null); setError(null) }

  const hasData = holdings.length > 0

  return (
    <div>
      <Header summary={summary} hasData={hasData} sourceFile={sourceFile} onRefresh={refresh} refreshing={refreshing}
        onExport={exportCsv} onReset={reset} onFile={handleFile} loading={loading} onReport={() => setReportOpen(true)} />
      {reportOpen && <ClientReportDialog rows={d.rows} aum={aum} onClose={() => setReportOpen(false)} />}

      <main className="mx-auto max-w-[1440px] space-y-5 px-4 py-6 sm:px-6">
        {error && (
          <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="flex-1">{error}</div>
            <button onClick={() => setError(null)} aria-label="סגירה"><X className="h-4 w-4" /></button>
          </div>
        )}

        {!hasData ? (
          <EmptyState onFile={handleFile} onSample={loadSample} loading={loading} />
        ) : (
          <>
            {warnings.length > 0 && <Warnings items={warnings} onClose={() => setWarnings([])} />}
            <AumControl aum={aum} setAum={setAum} />
            <KpiCards d={d} aum={aum} />

            <div className="flex items-center gap-1 overflow-x-auto border-b border-slate-200">
              {TABS.map(({ key, label, icon: Icon }) => (
                <button key={key} onClick={() => setTab(key)}
                  className={`-mb-px inline-flex shrink-0 items-center gap-2 whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition
                    ${tab === key ? 'border-brand-700 text-brand-800' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>
                  <Icon className="h-4 w-4" />{label}
                  {key === 'rebalance' && d.breaches > 0 && (
                    <span className="rounded-full bg-amber-100 px-1.5 text-xs font-semibold text-amber-800">{d.breaches}</span>
                  )}
                </button>
              ))}
            </div>

            {tab === 'overview' ? (
              <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
                <div className="xl:col-span-1"><AllocationDonut rows={d.rows} aum={aum} totalWeight={d.totalWeight} /></div>
                <div className="space-y-5 xl:col-span-2">
                  <BreakdownCard d={d} />
                </div>
                <div className="xl:col-span-3">
                  <HoldingsTable rows={d.rows} onWeightChange={setField('weight')} onRemove={removeHolding}
                    toolbar={<AddHolding onAdd={addHolding} disabled={refreshing} />} />
                </div>
              </div>
            ) : tab === 'rebalance' ? (
              <RebalancePanel d={d} threshold={threshold} setThreshold={setThreshold} onTargetChange={setField('target_weight')} onBulk={bulk} />
            ) : tab === 'xray' ? (
              <XRayView rows={d.rows} aum={aum} />
            ) : (
              <StressTestView rows={d.rows} aum={aum} />
            )}
          </>
        )}
      </main>
    </div>
  )
}

function Header({ summary, hasData, sourceFile, onRefresh, refreshing, onExport, onReset, onFile, loading, onReport }) {
  const usd = summary?.fx?.USD
  const time = summary?.priced_at ? new Date(summary.priced_at * 1000).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' }) : null
  return (
    <div className="border-b border-slate-200 bg-surface">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <div>
            <button onClick={onReset} className="text-base font-bold leading-tight text-slate-900 hover:text-brand-800">ניתוח ואיזון תיק לקוח</button>
            <p className="text-xs text-slate-500">{sourceFile ? `קובץ: ${sourceFile}` : 'העלאת תיק לקוח לניתוח'}</p>
          </div>
        </div>
        {hasData && (
          <div className="flex flex-wrap items-center gap-2">
            {usd && (
              <span className="inline-flex items-center gap-1 rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs font-medium text-slate-600">
                <DollarSign className="h-3.5 w-3.5" />USD/ILS <span className="num font-semibold text-slate-800">{usd.toFixed(4)}</span>
              </span>
            )}
            {time && (
              <span className="inline-flex items-center gap-1 rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs text-slate-600">
                <Clock className="h-3.5 w-3.5" />תומחר ב-<span className="num">{time}</span>
              </span>
            )}
            <button className="btn-ghost" onClick={onRefresh} disabled={refreshing}>
              {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}רענון מחירים
            </button>
            <button className="btn-ghost" onClick={onExport}><FileDown className="h-4 w-4" />ייצוא CSV</button>
            <button className="btn-primary" onClick={onReport}><FileText className="h-4 w-4" />דוח ללקוח</button>
            <UploadZone compact onFile={onFile} loading={loading} />
          </div>
        )}
      </div>
    </div>
  )
}

function EmptyState({ onFile, onSample, loading }) {
  const features = [
    { icon: BarChart3, t: 'תמחור מדורג (Waterfall)', s: 'yfinance ← קרנות נאמנות במאי״ה ← ביזפורטל, עם המרת אגורות לשקלים' },
    { icon: DollarSign, t: 'נרמול מטבעות', s: 'המרה אוטומטית לשקלים לפי שער דולר עדכני' },
    { icon: Scale, t: 'איזון מול תיק יעד', s: 'סטיות, התראות חריגה ופקודות קנייה/מכירה ביחידות' },
  ]
  return (
    <div className="mx-auto max-w-3xl space-y-6 pt-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-slate-900">העלו תיק השקעות כדי להתחיל</h2>
        <p className="mt-2 text-slate-500">מניות ואג״ח בת״א, קרנות נאמנות, מניות ותעודות סל בארה״ב – בתצוגה אחת.</p>
      </div>
      <UploadZone onFile={onFile} onSample={onSample} loading={loading} />
      <div className="grid gap-4 sm:grid-cols-3">
        {features.map(({ icon: Icon, t, s }) => (
          <div key={t} className="card p-4">
            <Icon className="mb-2 h-5 w-5 text-brand-700" />
            <div className="text-sm font-semibold text-slate-800">{t}</div>
            <div className="mt-1 text-xs leading-relaxed text-slate-500">{s}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Warnings({ items, onClose }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <ul className="flex-1 space-y-0.5">{items.map((w, i) => <li key={i}>{w}</li>)}</ul>
      <button onClick={onClose} aria-label="סגירה"><X className="h-4 w-4" /></button>
    </div>
  )
}

function BreakdownCard({ d }) {
  const groups = [
    { title: 'לפי סוג נכס', data: d.byAssetClass },
    { title: 'לפי מטבע', data: d.byCurrency },
  ]
  const top = [...d.rows].sort((a, b) => (b.weight || 0) - (a.weight || 0)).slice(0, 5)
  const top5 = top.reduce((s, r) => s + (r.weight || 0), 0)
  return (
    <div className="grid h-full grid-cols-1 gap-5 md:grid-cols-2">
      {groups.map((g) => (
        <div key={g.title} className="card p-5">
          <h3 className="card-title mb-4">{g.title}</h3>
          <div className="space-y-3">
            {Object.entries(g.data).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
              <div key={k}>
                <div className="mb-1 flex justify-between text-sm"><span className="text-slate-700">{k}</span><span className="num font-medium text-slate-900">{fmtPct(v)}</span></div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-brand-600" style={{ width: `${Math.min(100, v)}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
      <div className="card p-5 md:col-span-2">
        <div className="mb-3 flex items-baseline justify-between">
          <h3 className="card-title">ריכוזיות – 5 האחזקות הגדולות</h3>
          <span className="text-sm text-slate-500">סה״כ <span className="num font-semibold text-slate-800">{fmtPct(top5)}</span></span>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-5">
          {top.map((r, i) => (
            <div key={r.input_id} className="rounded-xl bg-slate-50 p-3">
              <div className="text-xs text-slate-400">#{i + 1}</div>
              <div className="truncate text-sm font-medium text-slate-800" title={r.name}>{r.name}</div>
              <div className="num text-lg font-bold text-brand-800">{fmtPct(r.weight, 1)}</div>
            </div>
          ))}
        </div>
        {d.unpriced > 0 && <p className="mt-3 text-xs text-red-700">{d.unpriced} ניירות ללא מחיר – שווי ויחידות לא חושבו עבורם.</p>}
      </div>
    </div>
  )
}
