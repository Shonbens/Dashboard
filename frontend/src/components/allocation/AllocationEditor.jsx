import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity, AlertTriangle, Archive, ArrowRight, Copy, Database, Download, FileText, History, Loader2, PieChart as PieIcon, RefreshCw,
  RotateCcw, Save, ScanSearch, Settings2, Table2, Trash2, X,
} from 'lucide-react'
import { allocationXlsx, analyzeHoldings, getModelVersion, getUser, secdataLookup, secdataUpdate, setUser, updateModel } from '../../lib/api'
import { navigate } from '../../lib/useHashRoute'
import useDebouncedRequest from '../../lib/useDebouncedRequest'
import { TEMPLATES, compute, hydrate, sectionsFor, suggestSection } from '../../lib/allocation'
import { exportPayload } from '../../lib/allocationExport'
import { fmtILS } from '../../lib/format'
import AddHolding from '../AddHolding'
import XRayView from '../XRayView'
import StressTestView from '../StressTestView'
import { STATUS, fmtDate } from '../models/shared'
import { ArchiveDialog, DeleteDialog, DuplicateDialog, HistoryDialog, SaveDialog, diffRows } from '../models/ModelEditor'
import AllocationSheet from './AllocationSheet'
import AllocationAnalysis, { Checks, SummaryTiles } from './AllocationAnalysis'
import { MarketDataDialog, SettingsDialog } from './AllocationDialogs'
import ExcelStats from './ExcelStats'

const NOTIONAL = 1_000_000
const initial = (m) => hydrate({ ...m.config, equity: m.config?.equity ?? m.equity_target ?? 50 })
const snapshot = (cfg, meta) => JSON.stringify({ cfg, meta })

export default function AllocationEditor({ model: initialModel }) {
  const [model, setModel] = useState(initialModel)
  const [config, setConfig] = useState(() => initial(initialModel))
  const [meta, setMeta] = useState({ name: initialModel.name, description: initialModel.description, status: initialModel.status })
  const [baseline, setBaseline] = useState(() => snapshot(initial(initialModel), { name: initialModel.name, description: initialModel.description, status: initialModel.status }))
  const [baseHoldings, setBaseHoldings] = useState(initialModel.holdings)
  const [data, setData] = useState({})
  const [dataBusy, setDataBusy] = useState(false)
  const [addTo, setAddTo] = useState('auto')
  const [dialog, setDialog] = useState(null)
  const [tab, setTab] = useState('analysis')
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)

  // ---- market data for every security on the sheet
  const ids = useMemo(() => [...new Set(config.rows.map((r) => r.id))].sort(), [config.rows])
  const idsKey = ids.join(',')
  const loadData = useCallback(async (list, refresh = false) => {
    if (!list.length) return
    setDataBusy(true)
    try {
      const d = await secdataLookup(list, refresh)
      setData((cur) => ({ ...cur, ...d }))
    } catch (e) { setError(e.message) } finally { setDataBusy(false) }
  }, [])
  useEffect(() => {
    const missing = idsKey ? idsKey.split(',').filter((id) => !data[id]) : []
    if (missing.length) loadData(missing)
  }, [idsKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const res = useMemo(() => compute(config, config.equity, data), [config, data])
  const dirty = snapshot(config, meta) !== baseline

  useEffect(() => {
    const warn = (e) => { if (dirty) { e.preventDefault(); e.returnValue = '' } }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  // ---- priced holdings for the X-Ray / stress tabs
  const hKey = useMemo(() => JSON.stringify(res.holdings), [res.holdings])
  const priced = useDebouncedRequest(() => analyzeHoldings(res.holdings, NOTIONAL), res.holdings.length ? hKey : null, 600)
  const pricedRows = priced.data?.holdings ?? []

  // ---- edits
  const patchRows = (fn) => setConfig((c) => ({ ...c, rows: fn(c.rows) }))
  const setWeight = (i, raw) => patchRows((rows) => rows.map((r, j) => (j === i ? { ...r, weight: raw === '' ? 0 : Math.max(0, Number(raw)) } : r)))
  const setWeights = (updates, overflow) => {
    const m = new Map(updates)
    patchRows((rows) => rows.map((r, j) => (m.has(j) ? { ...r, weight: m.get(j) } : r)))
    setNotice(`הודבקו ${updates.length} משקלים מאקסל${overflow ? ` · ${overflow} ערכים נוספים לא הודבקו (אין עוד שורות)` : ''}`)
  }
  const setRow = (i, patch) => patchRows((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const remove = (i) => patchRows((rows) => rows.filter((_, j) => j !== i))
  const move = (i, section) => patchRows((rows) => {
    const row = { ...rows[i], section }
    const rest = rows.filter((_, j) => j !== i)
    const at = rest.findLastIndex((r) => r.section === section)
    rest.splice(at + 1, 0, row)
    return rest
  })
  const add = async (id) => {
    let d = data[id]
    if (!d) {
      try { d = (await secdataLookup([id]))[id]; setData((cur) => ({ ...cur, [id]: d })) } catch (e) { setError(e.message); return }
    }
    const section = addTo === 'auto' ? suggestSection(d, config.template) : addTo
    if (config.rows.some((r) => r.id === id)) setNotice(`הנייר ${id} כבר קיים במודל – נוסף שוב (מסומן ככפול)`)
    patchRows((rows) => {
      const at = rows.findLastIndex((r) => r.section === section)
      const next = [...rows]
      next.splice(at + 1, 0, { id, section, weight: 0 })
      return next
    })
    const label = sectionsFor(config.template).find((s) => s.key === section)?.label
    setNotice(`${d?.name || id} נוסף לסעיף ״${label}״${addTo === 'auto' ? ' (שיוך אוטומטי – אפשר להעביר)' : ''}`)
  }
  const saveData = async (id, fields) => {
    const user = getUser() || 'לא ידוע'
    try {
      const d = await secdataUpdate(id, fields, user)
      setData((cur) => ({ ...cur, [id]: d }))
    } catch (e) { setError(e.message) }
  }

  // Excel with live formulas, built from what is on screen now (including unsaved edits)
  const [xlsxBusy, setXlsxBusy] = useState(false)
  const exportXlsx = async () => {
    setXlsxBusy(true)
    try {
      const blob = await allocationXlsx(exportPayload(res, { name: meta.name }))
      const u = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = u
      a.download = `${meta.name || 'גיליון הקצאה'} – ${new Date().toISOString().slice(0, 10)}.xlsx`
      a.click()
      setTimeout(() => URL.revokeObjectURL(u), 2000)
    } catch (e) { setError(e.message) } finally { setXlsxBusy(false) }
  }

  const back = () => {
    if (dirty && !window.confirm('יש שינויים שלא נשמרו. לצאת בכל זאת?')) return
    navigate('/models')
  }
  const discard = () => { const c = initial(model); setConfig(c); setMeta({ name: model.name, description: model.description, status: model.status }) }

  const save = async ({ note, user }) => {
    setUser(user)
    const updated = await updateModel(model.id, {
      name: meta.name.trim(), description: meta.description, status: meta.status, user, note,
      equity_target: Number(config.equity) || 0, holdings: res.holdings, config,
    })
    setModel(updated)
    const c = initial(updated)
    setConfig(c)
    const m = { name: updated.name, description: updated.description, status: updated.status }
    setMeta(m)
    setBaseline(snapshot(c, m))
    setBaseHoldings(updated.holdings)
    setDialog(null)
  }

  const openVersion = async (v) => {
    try {
      const ver = await getModelVersion(model.id, v)
      if (!ver.config) { setError('לגרסה זו אין גיליון הקצאה (נשמרה כרשימת ניירות)'); return }
      if (window.confirm(`לטעון את גרסה ${v} לעורך? (${ver.note || 'ללא הערה'} · ${ver.created_by || '—'})\nשום דבר לא יישמר עד ללחיצה על ״שמירה״.`)) {
        setConfig(hydrate(ver.config))
        setNotice(`גרסה ${v} נטענה לעורך – שמירה תיצור גרסה חדשה`)
      }
    } catch (e) { setError(e.message) }
  }

  const st = STATUS[meta.status] ?? STATUS.draft
  const eq = Number(config.equity) || 0

  return (
    <main className="mx-auto max-w-[1600px] space-y-4 px-4 py-6 sm:px-6">
      <div className="card sticky top-[67px] z-20 p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <button onClick={back} className="mt-1 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100" title="חזרה לכל המודלים" aria-label="חזרה"><ArrowRight className="h-5 w-5" /></button>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <input value={meta.name} onChange={(e) => setMeta({ ...meta, name: e.target.value })} aria-label="שם המודל"
                  size={Math.max(8, meta.name.length + 1)} className="num max-w-full rounded-lg border border-transparent bg-transparent px-1 text-2xl font-extrabold tracking-tight text-slate-900 hover:border-slate-200 focus:border-brand-400 focus:outline-none" />
                <select value={meta.status} onChange={(e) => setMeta({ ...meta, status: e.target.value })} aria-label="סטטוס"
                  className={`rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${st.cls}`}>
                  <option value="draft">טיוטה</option>
                  <option value="approved">מאושר</option>
                </select>
                <span className="num rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">v{model.version}</span>
                <span className="inline-flex items-center gap-1 rounded-full bg-navy-50 px-2 py-0.5 text-xs text-navy-700 ring-1 ring-inset ring-navy-100"><Table2 className="h-3 w-3" />גיליון הקצאה · {TEMPLATES[config.template]?.label}</span>
                {dirty && <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">שינויים שלא נשמרו</span>}
              </div>
              <input value={meta.description} onChange={(e) => setMeta({ ...meta, description: e.target.value })} placeholder="תיאור המודל"
                className="mt-1 w-full max-w-xl rounded-lg border border-transparent bg-transparent px-1 text-sm text-slate-500 hover:border-slate-200 focus:border-brand-400 focus:outline-none" />
              <div className="mt-1 px-1 text-xs text-slate-400">עודכן לאחרונה ע״י {model.updated_by || '—'} · <span className="num">{fmtDate(model.updated_at)}</span></div>
            </div>
          </div>

          {/* The Excel's F3 cell: one number rescales the whole model */}
          <div className="flex items-center gap-3 rounded-xl bg-slate-50 px-4 py-2">
            <div>
              <div className="text-[11px] font-medium text-slate-500">אחוז מנייתי</div>
              <div className="flex items-center gap-1">
                <input type="number" min="0" max="100" step="1" value={config.equity} aria-label="אחוז מנייתי"
                  onChange={(e) => setConfig({ ...config, equity: Math.min(100, Math.max(0, Number(e.target.value) || 0)) })}
                  className="num w-16 rounded-md border border-slate-200 bg-surface px-1.5 py-1 text-left text-lg font-bold focus:border-brand-400 focus:outline-none" />
                <span className="text-slate-500">%</span>
              </div>
            </div>
            <input type="range" min="0" max="100" step="5" value={eq} onChange={(e) => setConfig({ ...config, equity: Number(e.target.value) })}
              aria-label="אחוז מנייתי – מחוון" className="w-36 accent-[rgb(var(--brand-700))]" />
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <button className="btn-ghost px-2.5" onClick={() => setDialog('settings')}><Settings2 className="h-4 w-4" />הגדרות</button>
            <button className="btn-ghost px-2.5" onClick={() => setDialog('history')}><History className="h-4 w-4" />היסטוריה ({model.versions.length})</button>
            <a className="btn-ghost px-2.5" href={`/api/models/${model.id}/report.pdf`} target="_blank" rel="noopener"
              onClick={(e) => { if (dirty && !window.confirm('יש שינויים שלא נשמרו. הדוח יופק מהגרסה השמורה האחרונה – להמשיך?')) e.preventDefault() }}>
              <FileText className="h-4 w-4" />PDF
            </a>
            <button className="btn-ghost px-2.5" onClick={exportXlsx} disabled={xlsxBusy} title="גיליון אקסל עם נוסחאות חיות – כולל שינויים שעוד לא נשמרו">
              {xlsxBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}אקסל
            </button>
            <button className="btn-ghost px-2.5" onClick={() => setDialog('duplicate')}><Copy className="h-4 w-4" />שכפול</button>
            <button className="btn-ghost px-2.5 text-red-700 hover:bg-red-50" onClick={() => setDialog('archive')} title="העברה לארכיון"><Archive className="h-4 w-4" />ארכיון</button>
            <button className="btn-ghost px-2.5 text-red-700 hover:bg-red-50" onClick={() => setDialog('delete')}><Trash2 className="h-4 w-4" />מחיקה</button>
            {dirty && <button className="btn-outline" onClick={discard}><RotateCcw className="h-4 w-4" />ביטול</button>}
            <button className="btn-primary" disabled={!dirty} onClick={() => setDialog('save')}><Save className="h-4 w-4" />שמירה</button>
          </div>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          <AlertTriangle className="h-4 w-4" /><span className="flex-1">{error}</span>
          <button onClick={() => setError(null)} aria-label="סגירה"><X className="h-4 w-4" /></button>
        </div>
      )}
      {notice && (
        <div className="flex items-center gap-3 rounded-xl border border-brand-200 bg-brand-50 p-2.5 text-sm text-brand-900">
          <span className="flex-1">{notice}</span>
          <button onClick={() => setNotice(null)} aria-label="סגירה"><X className="h-4 w-4" /></button>
        </div>
      )}

      <SummaryTiles res={res} equityTarget={eq} />
      <Checks checks={res.checks} />

      <div className="card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-3">
          <div>
            <h3 className="card-title">גיליון ההקצאה <span className="text-sm font-normal text-slate-400">({config.rows.length} ניירות)</span></h3>
            <p className="text-[11px] text-slate-400">
              אחוז ראשי = משקל בתוך הרכיב · רכיב מניות <span className="num">{res.sleeves.equity.toFixed(2)}%</span> · רכיב אג״ח <span className="num">{res.sleeves.bond.toFixed(2)}%</span> (היתרה לעו״ש)
              · ערכים כחולים הוזנו ידנית, נטויים הם הערכה
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-ghost px-2.5" onClick={() => loadData(ids, true)} disabled={dataBusy} title="משיכה מחדש ממאי״ה ו-Yahoo">
              {dataBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}רענון נתונים
            </button>
            <button className="btn-ghost px-2.5" onClick={() => setDialog('market')}><Database className="h-4 w-4" />ייבוא נתוני שוק</button>
            <select className="input py-1.5 text-xs" value={addTo} onChange={(e) => setAddTo(e.target.value)} aria-label="סעיף לנייר חדש">
              <option value="auto">הוספה לסעיף: אוטומטי</option>
              {sectionsFor(config.template).map((s) => <option key={s.key} value={s.key}>הוספה ל: {s.label}</option>)}
            </select>
            <AddHolding onAdd={add} />
          </div>
        </div>
        {config.rows.length === 0 ? (
          <p className="py-16 text-center text-sm text-slate-500">הגיליון ריק. חפשו נייר כדי להוסיף אותו – הוא ישויך לסעיף המתאים (מניות בארץ, ממשלתי צמוד, קונצרני שקלי, קרנות…) לפי נתוני מאי״ה.</p>
        ) : (
          <AllocationSheet res={res} template={config.template} onWeight={setWeight} onWeights={setWeights} onRow={setRow} onRemove={remove} onMove={move} onData={saveData} />
        )}
      </div>

      <div className="flex items-center gap-1 border-b border-slate-200">
        {[['analysis', 'נתונים וגרפים', PieIcon], ['charts', 'השוואה למדדים', Table2], ['xray', 'שיקוף קרנות (X-Ray)', ScanSearch], ['stress', 'מבחני קיצון', Activity]].map(([k, l, Icon]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`-mb-px inline-flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium ${tab === k ? 'border-brand-700 text-brand-800' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>
            <Icon className="h-4 w-4" />{l}
          </button>
        ))}
        {!['analysis', 'charts'].includes(tab) && <span className="mr-auto text-xs text-slate-400">לפי המשקלים בתיק (אחוז יחסי) · תיק נומינלי של {fmtILS(NOTIONAL)}</span>}
      </div>
      {tab === 'analysis' && <ExcelStats res={res} />}
      {tab === 'charts' && <AllocationAnalysis res={res} />}
      {!['analysis', 'charts'].includes(tab) && (pricedRows.length === 0
        ? <p className="py-10 text-center text-sm text-slate-400">{priced.loading ? 'מתמחר…' : 'הוסיפו ניירות עם משקל כדי לראות ניתוח'}</p>
        : tab === 'xray' ? <XRayView rows={pricedRows} aum={NOTIONAL} /> : <StressTestView rows={pricedRows} aum={NOTIONAL} />)}

      {dialog === 'save' && (
        <SaveDialog total={res.summary.cash < -0.005 ? 100 - res.summary.cash : 100} status={meta.status}
          changes={diffRows(baseHoldings, res.holdings)} metaChanged onClose={() => setDialog(null)} onSave={save} />
      )}
      {dialog === 'settings' && <SettingsDialog config={config} onClose={() => setDialog(null)}
        onApply={({ settings, refs }) => { setConfig({ ...config, settings, refs }); setDialog(null) }} />}
      {dialog === 'market' && <MarketDataDialog onClose={() => setDialog(null)}
        onDone={(r) => { setDialog(null); setNotice(`עודכנו נתוני שוק ל-${r.updated} ניירות`); setData({}) }} />}
      {dialog === 'history' && <HistoryDialog model={model} onClose={() => setDialog(null)} onOpen={(v) => { setDialog(null); openVersion(v) }} />}
      {dialog === 'duplicate' && <DuplicateDialog model={model} onClose={() => setDialog(null)} />}
      {dialog === 'archive' && <ArchiveDialog model={model} onClose={() => setDialog(null)} />}
      {dialog === 'delete' && <DeleteDialog model={model} onClose={() => setDialog(null)} />}
    </main>
  )
}
