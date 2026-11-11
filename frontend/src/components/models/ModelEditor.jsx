import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowRight, Archive, ClipboardPaste, Copy, Download, FileText, History, Layers, Loader2, RotateCcw, Save,
  ScanSearch, Scale, Trash2, X,
} from 'lucide-react'
import {
  analyzeHoldings, archiveModel, deleteModel, duplicateModel, fundXray, getModel, getModelVersion, getQuote, getUser, setUser, updateModel,
} from '../../lib/api'
import { navigate } from '../../lib/useHashRoute'
import useDebouncedRequest from '../../lib/useDebouncedRequest'
import { fmtILS, fmtPct, fmtPrice, fmtSignedPct } from '../../lib/format'
import AddHolding from '../AddHolding'
import XRayView from '../XRayView'
import StressTestView from '../StressTestView'
import StackedBar, { Legend } from './StackedBar'
import { ASSET_ORDER, GEO_ORDER, STATUS, fmtDate } from './shared'
import Modal from './Modal'
import { Field } from './NewModelDialog'
import AllocationEditor from '../allocation/AllocationEditor'

const NOTIONAL = 1_000_000
const norm = (rows) => rows.map((r) => ({ id: r.input_id, weight: Number(r.weight) || 0, fee: r.fee ?? null }))
const sameHoldings = (a, b) => JSON.stringify(a) === JSON.stringify(b)

const LISTING = { IL: 'ת״א', US: 'ארה״ב', OTHER: 'חו״ל' }
const REGION = { IL: 'ישראל', US: 'ארה״ב', EUROPE: 'אירופה', ASIA: 'אסיה', EM: 'מתעוררים', OTHER: 'גלובלי' }
/** Where the money is actually exposed (from the look-through), vs. where the security is listed. */
function exposureOf(fd) {
  if (!fd) return null
  const regions = Object.entries(fd.regions || {}).sort((a, b) => b[1] - a[1])
  if (regions.length) {
    const [top, w] = regions[0]
    const eqTotal = regions.reduce((t, [, v]) => t + v, 0)
    return w / eqTotal >= 0.7 ? REGION[top] : 'גלובלי'
  }
  if (fd.gov_bonds + fd.corp_bonds + fd.cash > 0) return fd.fx_exposure > 50 ? 'חו״ל' : 'ישראל'
  return null
}

/** Excel-like movement between editable cells: Enter / ↓ next row, ↑ previous row. */
function gridKeys(e) {
  if (!['Enter', 'ArrowDown', 'ArrowUp'].includes(e.key)) return
  const { col, row } = e.currentTarget.dataset
  const next = document.querySelector(`[data-col="${col}"][data-row="${Number(row) + (e.key === 'ArrowUp' ? -1 : 1)}"]`)
  if (next) { e.preventDefault(); next.focus(); next.select?.() }
}

export default function ModelEditor({ modelId }) {
  const [model, setModel] = useState(null)
  const [rows, setRows] = useState([])
  const [baseline, setBaseline] = useState([])
  const [meta, setMeta] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('xray')
  const [dialog, setDialog] = useState(null)
  const [compare, setCompare] = useState(null) // {version, holdings, note, ...}

  const price = useCallback(async (holdings) => {
    if (!holdings.length) return []
    const res = await analyzeHoldings(holdings.map((h) => ({ id: h.id, name: h.name, weight: h.weight, fee: h.fee })), NOTIONAL)
    return res.holdings
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const m = await getModel(modelId)
      if (m.config) { setModel(m); setError(null); return } // allocation-sheet model: its own editor
      const priced = await price(m.holdings)
      setModel(m)
      setMeta({ name: m.name, description: m.description, equity_target: m.equity_target ?? '', status: m.status })
      setRows(priced)
      setBaseline(norm(priced))
      setError(null)
    } catch (e) { setError(e.message) } finally { setLoading(false) }
  }, [modelId, price])

  useEffect(() => { load() }, [load])

  const dirtyHoldings = !sameHoldings(norm(rows), baseline)
  const dirtyMeta = model && meta && (meta.name !== model.name || meta.description !== model.description
    || String(meta.equity_target ?? '') !== String(model.equity_target ?? '') || meta.status !== model.status)
  const dirty = dirtyHoldings || dirtyMeta

  useEffect(() => {
    const warn = (e) => { if (dirty) { e.preventDefault(); e.returnValue = '' } }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const total = rows.reduce((s, r) => s + (Number(r.weight) || 0), 0)
  const xrKey = useMemo(() => JSON.stringify(norm(rows)), [rows])
  const xr = useDebouncedRequest((signal) => fundXray(rows, NOTIONAL, signal), rows.length ? xrKey : null, 500)
  const feeData = useMemo(() => Object.fromEntries((xr.data?.holdings ?? []).map((h) => [h.input_id, h])), [xr.data])

  const setField = (id, field, raw) => setRows((rs) => rs.map((r) => (r.input_id === id
    ? { ...r, [field]: raw === '' ? (field === 'weight' ? 0 : null) : Math.max(0, Number(raw)) } : r)))
  const remove = (id) => setRows((rs) => rs.filter((r) => r.input_id !== id))
  // Scale to 100%, round to 2 decimals, and put the rounding remainder on the largest holding so the total is exact
  const normalize = () => total > 0 && setRows((rs) => {
    const scaled = rs.map((r) => ({ ...r, weight: Math.round(((Number(r.weight) || 0) / total) * 10000) / 100 }))
    const diff = Math.round((100 - scaled.reduce((s, r) => s + r.weight, 0)) * 100) / 100
    if (diff && scaled.length) {
      const i = scaled.reduce((best, r, j) => (r.weight > scaled[best].weight ? j : best), 0)
      scaled[i] = { ...scaled[i], weight: Math.round((scaled[i].weight + diff) * 100) / 100 }
    }
    return scaled
  })
  const sortRows = () => setRows((rs) => [...rs].sort((a, b) => (b.weight || 0) - (a.weight || 0)))

  const add = async (id) => {
    if (rows.some((r) => r.input_id === id)) { setError(`הנייר ${id} כבר קיים במודל`); return }
    setBusy(true)
    try {
      const q = await getQuote(id)
      setRows((rs) => [...rs, { ...q, weight: 0, fee: null, file_name: null }])
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const replaceHoldings = async (holdings) => {
    setBusy(true)
    try { setRows(await price(holdings)) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const discard = () => {
    setMeta({ name: model.name, description: model.description, equity_target: model.equity_target ?? '', status: model.status })
    replaceHoldings(model.holdings)
  }

  const back = () => {
    if (dirty && !window.confirm('יש שינויים שלא נשמרו. לצאת בכל זאת?')) return
    navigate('/models')
  }

  const save = async ({ note, user }) => {
    setUser(user)
    const eq = meta.equity_target === '' || meta.equity_target == null ? null : Number(meta.equity_target)
    const updated = await updateModel(modelId, {
      name: meta.name.trim(), description: meta.description, status: meta.status, user, note,
      equity_target: eq ?? undefined, clear_equity_target: eq == null,
      holdings: rows.map((r) => ({ id: r.input_id, name: r.file_name || r.name, weight: Number(r.weight) || 0, fee: r.fee ?? null })),
    })
    setModel(updated)
    setMeta({ name: updated.name, description: updated.description, equity_target: updated.equity_target ?? '', status: updated.status })
    setBaseline(norm(rows))
    setDialog(null)
  }

  const openVersion = async (v) => {
    try { setCompare(await getModelVersion(modelId, v)) } catch (e) { setError(e.message) }
  }

  if (loading && !model) return <Centered><Loader2 className="h-8 w-8 animate-spin text-brand-600" /></Centered>
  if (!model) return <Centered><p className="text-red-700">{error || 'המודל לא נמצא'}</p></Centered>
  if (model.config) return <AllocationEditor key={`${model.id}-${model.version}`} model={model} />

  const st = STATUS[meta.status] ?? STATUS.draft
  const offTotal = Math.abs(total - 100) > 0.01

  return (
    <main className="mx-auto max-w-[1440px] space-y-5 px-4 py-6 sm:px-6">
      {/* Header – stays visible while scrolling */}
      <div className="card sticky top-[67px] z-20 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <button onClick={back} className="mt-1 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100" title="חזרה לכל המודלים" aria-label="חזרה"><ArrowRight className="h-5 w-5" /></button>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <input value={meta.name} onChange={(e) => setMeta({ ...meta, name: e.target.value })} aria-label="שם המודל"
                  className="num w-44 rounded-lg border border-transparent bg-transparent px-1 text-3xl font-extrabold tracking-tight text-slate-900 hover:border-slate-200 focus:border-brand-400 focus:outline-none" />
                <select value={meta.status} onChange={(e) => setMeta({ ...meta, status: e.target.value })} aria-label="סטטוס"
                  className={`rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${st.cls}`}>
                  <option value="draft">טיוטה</option>
                  <option value="approved">מאושר</option>
                </select>
                <span className="num rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">v{model.version}</span>
                {dirty && <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">שינויים שלא נשמרו</span>}
              </div>
              <input value={meta.description} onChange={(e) => setMeta({ ...meta, description: e.target.value })} placeholder="תיאור המודל"
                className="mt-1 w-full max-w-xl rounded-lg border border-transparent bg-transparent px-1 text-sm text-slate-500 hover:border-slate-200 focus:border-brand-400 focus:outline-none" />
              <div className="mt-1 px-1 text-xs text-slate-400">עודכן לאחרונה ע״י {model.updated_by || '—'} · <span className="num">{fmtDate(model.updated_at)}</span></div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-ghost" onClick={() => setDialog('history')}><History className="h-4 w-4" />היסטוריה ({model.versions.length})</button>
            <a className="btn-ghost" href={`/api/models/${modelId}/report.pdf`} target="_blank" rel="noopener" title="דף מודל ממותג להצגה בפגישות"
              onClick={(e) => { if (dirty && !window.confirm('יש שינויים שלא נשמרו. הדוח יופק מהגרסה השמורה האחרונה – להמשיך?')) e.preventDefault() }}>
              <FileText className="h-4 w-4" />דוח PDF
            </a>
            <a className="btn-ghost" href={`/api/models/export?ids=${modelId}`} download><Download className="h-4 w-4" />ייצוא</a>
            <button className="btn-ghost" onClick={() => setDialog('duplicate')}><Copy className="h-4 w-4" />שכפול</button>
            <button className="btn-ghost text-red-700 hover:bg-red-50" onClick={() => setDialog('archive')}><Archive className="h-4 w-4" />ארכיון</button>
            <button className="btn-ghost text-red-700 hover:bg-red-50" onClick={() => setDialog('delete')}><Trash2 className="h-4 w-4" />מחיקה</button>
            {dirty && <button className="btn-outline" onClick={discard}><RotateCcw className="h-4 w-4" />ביטול שינויים</button>}
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

      {compare && <VersionCompare compare={compare} rows={rows} onClose={() => setCompare(null)}
        onRestore={() => { replaceHoldings(compare.holdings); setCompare(null) }} />}

      <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-5">
        {/* Holdings grid */}
        <div className="card overflow-hidden xl:col-span-3">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4">
            <h3 className="card-title">הרכב המודל <span className="text-sm font-normal text-slate-400">({rows.length} ניירות)</span></h3>
            <div className="flex flex-wrap items-center gap-2">
              <button className="btn-ghost px-2.5" onClick={() => setDialog('paste')}><ClipboardPaste className="h-4 w-4" />הדבקה מאקסל</button>
              <AddHolding onAdd={add} disabled={busy} />
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50/80">
                <tr>
                  <th className="th">נייר</th><th className="th">סוג נכס</th><th className="th">מסחר · חשיפה</th><th className="th">מחיר</th>
                  <th className="th">משקל</th><th className="th">דמי ניהול</th><th className="th w-8" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.length === 0 && (
                  <tr><td colSpan={7} className="py-14 text-center text-sm text-slate-500">המודל ריק. הוסיפו ניירות בחיפוש או הדביקו טבלה מאקסל.</td></tr>
                )}
                {rows.map((r, i) => {
                  const fd = feeData[r.input_id]
                  const exposure = exposureOf(fd)
                  const dataFee = fd && fd.fee_source === 'data' ? fd.fee : null
                  return (
                    <tr key={r.input_id} className={`group hover:bg-slate-50/70 ${!r.priced ? 'bg-amber-50/50' : ''}`}>
                      <td className="td max-w-[300px]">
                        <div dir="auto" className="truncate font-medium text-slate-800" title={r.name}>{r.priced ? r.name : (r.file_name || r.name)}</div>
                        <div className="num text-xs text-slate-400">{r.input_id}{r.ticker !== r.input_id ? ` · ${r.ticker}` : ''}{!r.priced && ' · לא זוהה'}</div>
                      </td>
                      <td className="td text-slate-600">{r.asset_class}</td>
                      <td className="td">
                        <span className="inline-flex items-center gap-1.5 text-xs">
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-600" title="בורסת מסחר">{LISTING[r.market] ?? r.market}</span>
                          {exposure && <span className="text-slate-500" title="חשיפה בפועל לאחר שיקוף">חשיפה {exposure}</span>}
                        </span>
                      </td>
                      <td className="td text-slate-600"><span className="num">{fmtPrice(r.price, r.currency)}</span></td>
                      <td className="td">
                        <div className="flex items-center gap-1">
                          <input type="number" min="0" step="0.5" value={Number((Number(r.weight) || 0).toFixed(4))}
                            onChange={(e) => setField(r.input_id, 'weight', e.target.value)} aria-label={`משקל ${r.name}`}
                            data-col="weight" data-row={i} onKeyDown={gridKeys} onFocus={(e) => e.target.select()}
                            className="num w-20 rounded-md border border-slate-200 bg-surface px-1.5 py-1 text-left font-semibold focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100" />
                          <span className="text-slate-400">%</span>
                        </div>
                      </td>
                      <td className="td">
                        <div className="flex items-center gap-1">
                          <input type="number" min="0" step="0.01" value={r.fee ?? ''} placeholder={dataFee != null ? dataFee.toFixed(2) : '—'}
                            onChange={(e) => setField(r.input_id, 'fee', e.target.value)} aria-label={`דמי ניהול ${r.name}`}
                            data-col="fee" data-row={i} onKeyDown={gridKeys} onFocus={(e) => e.target.select()}
                            title={dataFee != null ? `ממקור נתונים: ${dataFee.toFixed(2)}% · הזנה ידנית גוברת` : 'אין נתון – ניתן להזין ידנית'}
                            className="num w-16 rounded-md border border-slate-200 bg-surface px-1.5 py-1 text-left placeholder:text-slate-400 focus:border-brand-400 focus:outline-none" />
                          <span className="text-slate-400">%</span>
                        </div>
                      </td>
                      <td className="td">
                        <button onClick={() => remove(r.input_id)} aria-label={`הסרת ${r.name}`}
                          className="rounded p-1 text-slate-300 opacity-0 transition hover:bg-red-50 hover:text-red-600 focus:opacity-100 group-hover:opacity-100">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
              {rows.length > 0 && (
                <tfoot className="border-t-2 border-slate-200 bg-slate-50/80">
                  <tr>
                    <td className="td font-semibold" colSpan={4}>
                      <div className="flex flex-wrap items-center gap-2">
                        סה״כ
                        <button className="btn-ghost px-2 py-1 text-xs" onClick={normalize} disabled={!offTotal}><Scale className="h-3.5 w-3.5" />נרמול ל-100%</button>
                        <button className="btn-ghost px-2 py-1 text-xs" onClick={sortRows}>מיון לפי משקל</button>
                      </div>
                    </td>
                    <td className={`td font-bold ${offTotal ? 'text-amber-700' : 'text-emerald-700'}`}>
                      <span className="num">{fmtPct(total)}</span>
                    </td>
                    <td className="td text-xs text-slate-500" colSpan={2}>{offTotal ? `${total > 100 ? 'עודף' : 'חסר'} ${fmtPct(Math.abs(100 - total))}` : 'מאוזן'}
                      <span className="mr-2 hidden text-[11px] text-slate-400 2xl:inline">Enter / ↑↓ למעבר בין שורות</span>
                    </td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </div>

        {/* Live summary */}
        <SummaryPanel xr={xr} equityTarget={meta.equity_target} onTarget={(v) => setMeta({ ...meta, equity_target: v })} total={total} />
      </div>

      {rows.length > 0 && (
        <>
          <div className="flex items-center gap-1 border-b border-slate-200">
            {[['xray', 'שיקוף קרנות (X-Ray)', ScanSearch], ['stress', 'מבחני קיצון', Activity]].map(([k, l, Icon]) => (
              <button key={k} onClick={() => setTab(k)}
                className={`-mb-px inline-flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium ${tab === k ? 'border-brand-700 text-brand-800' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>
                <Icon className="h-4 w-4" />{l}
              </button>
            ))}
            <span className="mr-auto text-xs text-slate-400">ניתוח לפי תיק נומינלי של {fmtILS(NOTIONAL)} · מתעדכן בזמן עריכה</span>
          </div>
          {tab === 'xray' ? <XRayView rows={rows} aum={NOTIONAL} /> : <StressTestView rows={rows} aum={NOTIONAL} />}
        </>
      )}

      {dialog === 'save' && <SaveDialog total={total} status={meta.status} changes={diffRows(baseline, norm(rows))} metaChanged={dirtyMeta}
        onClose={() => setDialog(null)} onSave={save} />}
      {dialog === 'paste' && <PasteDialog onClose={() => setDialog(null)} rows={rows}
        onApply={(holdings) => { replaceHoldings(holdings); setDialog(null) }} />}
      {dialog === 'history' && <HistoryDialog model={model} onClose={() => setDialog(null)} onOpen={(v) => { setDialog(null); openVersion(v) }} />}
      {dialog === 'duplicate' && <DuplicateDialog model={model} onClose={() => setDialog(null)} />}
      {dialog === 'archive' && <ArchiveDialog model={model} onClose={() => setDialog(null)} />}
      {dialog === 'delete' && <DeleteDialog model={model} onClose={() => setDialog(null)} />}
    </main>
  )
}

const Centered = ({ children }) => <div className="grid min-h-[50vh] place-items-center">{children}</div>

function SummaryPanel({ xr, equityTarget, onTarget, total }) {
  const d = xr.data
  const eq = d?.metrics.equity_weight
  const target = equityTarget === '' || equityTarget == null ? null : Number(equityTarget)
  const drift = eq != null && target != null ? eq - target : null
  return (
    <div className={`card space-y-5 p-5 xl:sticky xl:top-[210px] xl:col-span-2 ${xr.loading ? 'opacity-80' : ''} transition-opacity`}>
      <div className="flex items-center justify-between">
        <h3 className="card-title flex items-center gap-2"><Layers className="h-4 w-4 text-brand-700" />תמונת מצב חיה</h3>
        {xr.loading && <Loader2 className="h-4 w-4 animate-spin text-slate-400" />}
      </div>
      {!d ? <p className="py-10 text-center text-sm text-slate-400">{xr.error || 'הוסיפו ניירות כדי לראות ניתוח'}</p> : (
        <>
          <div>
            <div className="mb-2 flex items-end justify-between">
              <div>
                <div className="text-xs text-slate-500">מניות בפועל (לאחר שיקוף)</div>
                <div className="num text-2xl font-bold text-slate-900">{fmtPct(eq, 1)}</div>
              </div>
              <label className="text-left text-xs text-slate-500">
                יעד מניות
                <div className="flex items-center gap-1">
                  <input type="number" min="0" max="100" value={equityTarget ?? ''} onChange={(e) => onTarget(e.target.value)}
                    className="num w-16 rounded-md border border-slate-200 px-1.5 py-1 text-left text-sm font-semibold focus:border-brand-400 focus:outline-none" aria-label="יעד מניות" />
                  <span>%</span>
                </div>
              </label>
            </div>
            <div className="relative h-3 rounded-full bg-slate-100">
              <div className="absolute inset-y-0 right-0 rounded-full bg-brand-600" style={{ width: `${Math.min(100, eq)}%` }} />
              {target != null && <div className="absolute -inset-y-1 w-0.5 bg-slate-900" style={{ right: `${Math.min(100, target)}%` }} title={`יעד ${target}%`} />}
            </div>
            {drift != null && (
              <p className={`mt-1.5 text-xs ${Math.abs(drift) >= 1 ? 'font-medium text-amber-700' : 'text-emerald-700'}`}>
                {Math.abs(drift) < 1 ? 'תואם ליעד' : <>סטייה מהיעד: <span className="num">{fmtSignedPct(drift, 1)}</span></>}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <div className="text-xs font-medium text-slate-500">סוגי נכסים</div>
            <StackedBar data={d.asset_classes} order={ASSET_ORDER} height="h-4" />
            <Legend order={ASSET_ORDER.filter((o) => d.asset_classes[o.key])} />
          </div>
          <div className="space-y-2">
            <div className="text-xs font-medium text-slate-500">גיאוגרפיה</div>
            <StackedBar data={d.geography} order={GEO_ORDER} height="h-4" />
            <Legend order={GEO_ORDER.filter((o) => d.geography[o.key])} />
          </div>

          <div className="grid grid-cols-2 gap-2 text-sm">
            <Mini label="חשיפת מט״ח" value={fmtPct(d.metrics.fx_exposure, 1)} />
            <Mini label="מח״מ אג״ח" value={d.metrics.bond_duration ? d.metrics.bond_duration.toFixed(2) : '—'} />
            <Mini label="דמי ניהול משוקללים" value={d.metrics.weighted_fee != null ? `${d.metrics.weighted_fee.toFixed(2)}%` : '—'}
              sub={d.metrics.weighted_fee != null ? `כיסוי ${fmtPct(d.metrics.fee_coverage, 0)} מהמודל` : 'הזינו דמי ניהול בטבלה'} />
            <Mini label="ריכוז מרבי" value={d.top_underlying[0] ? fmtPct(d.top_underlying[0].total, 1) : '—'} sub={d.top_underlying[0]?.name} />
          </div>
          {Math.abs(total - 100) > 0.01 && (
            <p className="flex items-center gap-1.5 rounded-lg bg-amber-50 p-2 text-xs text-amber-800">
              <AlertTriangle className="h-3.5 w-3.5" />סך המשקלים <span className="num">{fmtPct(total)}</span> – הניתוח מתייחס לחלק המוקצה בלבד
            </p>
          )}
        </>
      )}
    </div>
  )
}

const Mini = ({ label, value, sub }) => (
  <div className="rounded-lg bg-slate-50 px-3 py-2">
    <div className="text-xs text-slate-500">{label}</div>
    <div className="num font-semibold text-slate-900">{value}</div>
    {sub && <div dir="auto" className="truncate text-[11px] text-slate-400" title={sub}>{sub}</div>}
  </div>
)

export function diffRows(a, b) {
  const A = Object.fromEntries(a.map((h) => [h.id, h])), B = Object.fromEntries(b.map((h) => [h.id, h]))
  return {
    added: Object.keys(B).filter((k) => !A[k]),
    removed: Object.keys(A).filter((k) => !B[k]),
    changed: Object.keys(B).filter((k) => A[k] && (A[k].weight !== B[k].weight || A[k].fee !== B[k].fee)),
  }
}

export function SaveDialog({ total, status, changes, metaChanged, onClose, onSave }) {
  const [note, setNote] = useState('')
  const [user, setU] = useState(getUser())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const off = Math.abs(total - 100) > 0.01
  const blocked = off && status === 'approved'
  const submit = async () => {
    if (!user.trim()) { setError('יש להזין שם עורך'); return }
    setBusy(true); setError(null)
    try { await onSave({ note: note.trim(), user: user.trim() }) } catch (e) { setError(e.message); setBusy(false) }
  }
  const n = changes.added.length + changes.removed.length + changes.changed.length
  return (
    <Modal title="שמירת גרסה חדשה" subtitle="כל שמירה נרשמת בהיסטוריה ואפשר לחזור אליה" onClose={onClose}
      footer={<>
        <button className="btn-ghost" onClick={onClose}>ביטול</button>
        <button className="btn-primary" disabled={busy || blocked} onClick={submit}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}שמירה</button>
      </>}>
      <div className="space-y-4">
        <div className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
          {n > 0 ? <>שינויים בהרכב: <b>{changes.added.length}</b> נוספו · <b>{changes.removed.length}</b> הוסרו · <b>{changes.changed.length}</b> עודכנו</> : 'אין שינוי בהרכב'}
          {metaChanged && <div className="mt-1 text-xs text-slate-500">כולל שינוי בפרטי המודל (שם / תיאור / יעד / סטטוס)</div>}
        </div>
        {off && (
          <p className={`flex items-start gap-2 rounded-lg p-3 text-sm ${blocked ? 'bg-red-50 text-red-800' : 'bg-amber-50 text-amber-800'}`}>
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            {blocked ? <>לא ניתן לשמור מודל בסטטוס ״מאושר״ כשסך המשקלים <span className="num">{fmtPct(total)}</span>. נרמלו ל-100% או שמרו כטיוטה.</>
              : <>סך המשקלים <span className="num">{fmtPct(total)}</span> – המודל יישמר כטיוטה לא מאוזנת.</>}
          </p>
        )}
        <Field label="הערת גרסה"><input autoFocus className="input w-full" value={note} onChange={(e) => setNote(e.target.value)} placeholder="לדוגמה: הגדלת חשיפה לאג״ח ממשלתי בעקבות החלטת ועדה" /></Field>
        <Field label="שם העורך"><input className="input w-full" value={user} onChange={(e) => setU(e.target.value)} /></Field>
        {error && <p className="text-sm text-red-700">{error}</p>}
      </div>
    </Modal>
  )
}

/** Parse clipboard text copied from Excel: tab / comma / semicolon separated, header optional. */
function parsePasted(text) {
  const out = []
  for (const line of text.split(/\r?\n/)) {
    const cells = line.split(/\t|;|,(?=(?:[^"]*"[^"]*")*[^"]*$)/).map((c) => c.trim().replace(/^"|"$/g, ''))
    if (!cells.some(Boolean)) continue
    const id = cells.find((c) => /^\d{3,9}$/.test(c.replace(/\.0+$/, '')) || /^[A-Za-z][A-Za-z0-9.\-]{0,9}$/.test(c))
    const nums = cells.filter((c) => c !== id).map((c) => c.replace(/[%,₪\s]/g, '')).filter((c) => c !== '' && !Number.isNaN(Number(c)))
    if (!id || !nums.length) continue
    const w = Number(nums[0])
    const name = cells.find((c) => c && c !== id && Number.isNaN(Number(c.replace(/[%,₪\s]/g, ''))))
    out.push({ id: id.replace(/\.0+$/, '').toUpperCase(), name: name || null, raw: w, pct: cells.some((c) => c.includes('%')) })
  }
  const fraction = out.length && out.every((h) => !h.pct && h.raw <= 1) && out.reduce((s, h) => s + h.raw, 0) <= 1.0001
  return out.map((h) => ({ id: h.id, name: h.name, weight: Number((fraction ? h.raw * 100 : h.raw).toFixed(4)), fee: null }))
}

function PasteDialog({ rows, onClose, onApply }) {
  const [text, setText] = useState('')
  const [mode, setMode] = useState('replace')
  const parsed = useMemo(() => parsePasted(text), [text])
  const total = parsed.reduce((s, h) => s + h.weight, 0)
  const apply = () => {
    if (mode === 'replace') return onApply(parsed)
    const map = new Map(rows.map((r) => [r.input_id, { id: r.input_id, name: r.file_name || r.name, weight: r.weight, fee: r.fee ?? null }]))
    parsed.forEach((p) => map.set(p.id, { ...(map.get(p.id) || {}), ...p, fee: map.get(p.id)?.fee ?? null }))
    return onApply([...map.values()])
  }
  return (
    <Modal wide title="הדבקה מאקסל" subtitle="סמנו בטבלת האקסל את עמודות מספר הנייר והמשקל (אפשר גם עם שם הנייר), העתיקו והדביקו כאן" onClose={onClose}
      footer={<>
        <select className="input ml-auto" value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="replace">החלפת כל הרכב המודל</option>
          <option value="merge">הוספה ועדכון משקלים קיימים</option>
        </select>
        <button className="btn-ghost" onClick={onClose}>ביטול</button>
        <button className="btn-primary" disabled={!parsed.length} onClick={apply}>החלה על העורך ({parsed.length})</button>
      </>}>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <textarea autoFocus value={text} onChange={(e) => setText(e.target.value)} dir="ltr"
          placeholder={'1148808\t30%\n1148162\t40%\nSPY\t10%'} className="input h-64 w-full resize-none font-mono text-xs" />
        <div className="max-h-64 overflow-auto rounded-lg border border-slate-200">
          {parsed.length === 0 ? <p className="p-6 text-center text-sm text-slate-400">התצוגה המקדימה תופיע כאן</p> : (
            <table className="w-full text-sm">
              <thead className="bg-slate-50"><tr><th className="th">מזהה</th><th className="th">שם</th><th className="th">משקל</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {parsed.map((h) => <tr key={h.id}><td className="td num">{h.id}</td><td className="td truncate text-slate-500">{h.name || '—'}</td><td className="td num">{fmtPct(h.weight)}</td></tr>)}
              </tbody>
              <tfoot className="bg-slate-50 font-semibold"><tr><td className="td" colSpan={2}>סה״כ</td><td className={`td num ${Math.abs(total - 100) > 0.01 ? 'text-amber-700' : ''}`}>{fmtPct(total)}</td></tr></tfoot>
            </table>
          )}
        </div>
      </div>
      <p className="mt-3 text-xs text-slate-500">כל שינוי נכנס לעורך בלבד – שום דבר לא נשמר עד ללחיצה על ״שמירה״.</p>
    </Modal>
  )
}

export function HistoryDialog({ model, onClose, onOpen }) {
  return (
    <Modal title={`היסטוריית גרסאות – ${model.name}`} subtitle="בחרו גרסה כדי להשוות לעורך או לשחזר אותה" onClose={onClose}>
      <ol className="relative space-y-1 border-r-2 border-slate-100 pr-4">
        {model.versions.map((v) => (
          <li key={v.version}>
            <button onClick={() => onOpen(v.version)} className="w-full rounded-lg p-2.5 text-right hover:bg-slate-50">
              <span className="absolute -right-[7px] mt-1.5 h-3 w-3 rounded-full border-2 border-white bg-brand-600" />
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-slate-800">גרסה <span className="num">{v.version}</span>{v.version === model.version && <span className="mr-2 rounded bg-brand-50 px-1.5 text-xs font-medium text-brand-700">נוכחית</span>}</span>
                <span className="num text-xs text-slate-400">{fmtDate(v.created_at)}</span>
              </div>
              <div className="text-sm text-slate-600">{v.note || 'ללא הערה'}</div>
              <div className="text-xs text-slate-400">{v.created_by || '—'} · {v.count} ניירות</div>
            </button>
          </li>
        ))}
      </ol>
    </Modal>
  )
}

function VersionCompare({ compare, rows, onClose, onRestore }) {
  const cur = Object.fromEntries(rows.map((r) => [r.input_id, r]))
  const old = Object.fromEntries(compare.holdings.map((h) => [h.id, h]))
  const ids = [...new Set([...Object.keys(old), ...Object.keys(cur)])]
  const lines = ids.map((id) => ({
    id, name: cur[id]?.name || old[id]?.name || id, a: old[id]?.weight ?? null, b: cur[id] ? Number(cur[id].weight) || 0 : null,
  })).map((l) => ({ ...l, d: (l.b ?? 0) - (l.a ?? 0) })).sort((x, y) => Math.abs(y.d) - Math.abs(x.d))
  const changed = lines.filter((l) => Math.abs(l.d) > 1e-6).length
  return (
    <div className="card overflow-hidden ring-2 ring-brand-200">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 bg-brand-50/50 p-4">
        <div>
          <h3 className="card-title">השוואה: גרסה <span className="num">{compare.version}</span> מול העורך הנוכחי</h3>
          <p className="text-xs text-slate-500">{compare.note || 'ללא הערה'} · {compare.created_by || '—'} · <span className="num">{fmtDate(compare.created_at)}</span> · {changed} שורות שונות</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-outline" onClick={onRestore}><RotateCcw className="h-4 w-4" />שחזור גרסה זו לעורך</button>
          <button className="btn-ghost" onClick={onClose}><X className="h-4 w-4" />סגירה</button>
        </div>
      </div>
      <div className="max-h-80 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-50"><tr><th className="th">נייר</th><th className="th">גרסה {compare.version}</th><th className="th">עורך</th><th className="th">הפרש</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {lines.map((l) => (
              <tr key={l.id} className={Math.abs(l.d) > 1e-6 ? '' : 'text-slate-400'}>
                <td className="td"><span dir="auto">{l.name}</span> <span className="num text-xs text-slate-400">{l.id}</span>
                  {l.a == null && <span className="mr-1 rounded bg-emerald-50 px-1 text-[10px] text-emerald-800">חדש</span>}
                  {l.b == null && <span className="mr-1 rounded bg-red-50 px-1 text-[10px] text-red-700">הוסר</span>}
                </td>
                <td className="td"><span className="num">{l.a == null ? '—' : fmtPct(l.a)}</span></td>
                <td className="td"><span className="num">{l.b == null ? '—' : fmtPct(l.b)}</span></td>
                <td className={`td font-medium ${l.d > 0 ? 'text-brand-700' : l.d < 0 ? 'text-red-700' : ''}`}><span className="num">{Math.abs(l.d) > 1e-6 ? fmtSignedPct(l.d) : '—'}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function DuplicateDialog({ model, onClose }) {
  const [name, setName] = useState(`${model.name} (עותק)`)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const go = async () => {
    setBusy(true)
    try { const m = await duplicateModel(model.id, name.trim(), getUser()); navigate(`/models/${m.id}`) } catch (e) { setError(e.message); setBusy(false) }
  }
  return (
    <Modal title="שכפול מודל" subtitle={`עותק של הגרסה השמורה האחרונה (v${model.version}) ייווצר כטיוטה`} onClose={onClose}
      footer={<><button className="btn-ghost" onClick={onClose}>ביטול</button><button className="btn-primary" disabled={busy || !name.trim()} onClick={go}>שכפול ופתיחה</button></>}>
      <Field label="שם המודל החדש"><input autoFocus className="input w-full" value={name} onChange={(e) => setName(e.target.value)} /></Field>
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
    </Modal>
  )
}

export function ArchiveDialog({ model, onClose }) {
  const [busy, setBusy] = useState(false)
  const go = async () => { setBusy(true); await archiveModel(model.id, getUser()); navigate('/models') }
  return (
    <Modal title={`העברת מודל ${model.name} לארכיון`} onClose={onClose}
      footer={<><button className="btn-ghost" onClick={onClose}>ביטול</button><button className="btn bg-red-600 text-white hover:bg-red-700" disabled={busy} onClick={go}>העברה לארכיון</button></>}>
      <p className="text-sm text-slate-600">המודל יוסתר מהמסך הראשי. ההיסטוריה המלאה נשמרת ואפשר לשחזר אותו בייבוא מחדש או בבקשה ממנהל המערכת.</p>
    </Modal>
  )
}

/** Permanent delete – the model and its full version history are removed. Asks for the model name to confirm. */
export function DeleteDialog({ model, onClose }) {
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const ok = typed.trim() === model.name.trim()
  const go = async () => {
    setBusy(true)
    try { await deleteModel(model.id, getUser()); navigate('/models') } catch (e) { setError(e.message); setBusy(false) }
  }
  return (
    <Modal title={`מחיקת מודל ${model.name}`} subtitle="מחיקה לצמיתות – לא ניתן לשחזר" onClose={onClose}
      footer={<>
        <button className="btn-ghost" onClick={onClose}>ביטול</button>
        <button className="btn bg-red-600 text-white hover:bg-red-700 disabled:opacity-40" disabled={!ok || busy} onClick={go}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" />}<Trash2 className="h-4 w-4" />מחיקה לצמיתות
        </button>
      </>}>
      <div className="space-y-3 text-sm">
        <p className="flex items-start gap-2 rounded-lg bg-red-50 p-3 text-red-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          המודל וכל {model.versions?.length ?? model.version} הגרסאות שלו יימחקו לצמיתות. אם רק רוצים להסתיר אותו – עדיף להעביר לארכיון.
        </p>
        <Field label={`להקלדת שם המודל לאישור: ${model.name}`}>
          <input autoFocus className="input w-full" value={typed} onChange={(e) => setTyped(e.target.value)} dir="auto"
            onKeyDown={(e) => { if (e.key === 'Enter' && ok) go() }} />
        </Field>
        {error && <p className="text-red-700">{error}</p>}
      </div>
    </Modal>
  )
}
