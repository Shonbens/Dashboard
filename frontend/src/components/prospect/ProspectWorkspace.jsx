import { useRef, useState } from 'react'
import {
  AlertTriangle, CheckCircle2, Eye, EyeOff, Download, FileSearch, PlayCircle, FileText, Info, Lightbulb, ListChecks, Loader2, RefreshCw, RotateCcw, X,
} from 'lucide-react'
import { getUser, prospectAnalyze, prospectAnalyzeFile, prospectPdf, secdataUpdate, setUser } from '../../lib/api'
import { fmtILS } from '../../lib/format'
import StackedBar, { Legend } from '../models/StackedBar'
import { ASSET_ORDER } from '../models/shared'
import { SERIES } from '../palette'
import ModelMatch from './ModelMatch'
import RulesDialog from './RulesDialog'

const KIND = { equity: 'מניה', bond: 'אג״ח', etf: 'קרן סל', cash: 'פיקדון / מזומן', other: 'לא מסווג' }
const kindLabel = (r) => (r.kind === 'fund' ? (r.tracker ? 'קרן מחקה' : 'קרן מנוהלת') : KIND[r.kind] ?? 'אחר')
const STATE = {
  ok: ['בטווח', 'bg-emerald-50 text-emerald-800 ring-emerald-200'],
  high: ['גבוה', 'bg-red-50 text-red-700 ring-red-200'],
  low: ['נמוך', 'bg-amber-50 text-amber-800 ring-amber-200'],
  null: ['אין נתון', 'bg-slate-100 text-slate-500 ring-slate-200'],
}
const p1 = (v) => (v == null ? '—' : `${v.toFixed(1)}%`)

export default function ProspectWorkspace() {
  const inputRef = useRef(null)
  const [res, setRes] = useState(null)
  const [holdings, setHoldings] = useState([])
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [pdfBusy, setPdfBusy] = useState(false)
  const [error, setError] = useState(null)
  const [drag, setDrag] = useState(false)
  const [client, setClient] = useState('')
  const [advisor, setAdvisor] = useState(getUser())
  const [contact, setContact] = useState(() => { try { return localStorage.getItem('ibi_contact') || '' } catch { return '' } })
  const [rulesOpen, setRulesOpen] = useState(false)
  const [excluded, setExcluded] = useState(() => new Set()) // recommendations the advisor chose not to send
  const toggleInsight = (id) => setExcluded((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n })

  const take = (r) => {
    setRes(r)
    setHoldings(r.holdings.map((h) => ({ ...h })))
    setDirty(false)
  }
  const upload = async (file) => {
    if (!file) return
    setBusy(true); setError(null)
    try { setExcluded(new Set()); take({ ...(await prospectAnalyzeFile(file)), source_file: file.name }) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  // Demo: fetch the sample statement and run it through the same upload path as a real file
  const demo = async () => {
    setBusy(true); setError(null)
    try {
      const r = await fetch('/api/prospect/demo.xlsx')
      if (!r.ok) throw new Error('טעינת קובץ ההדגמה נכשלה')
      const file = new File([await r.blob()], 'תיק_לדוגמה.xlsx')
      setClient((c) => c || 'לקוח לדוגמה')
      setExcluded(new Set())
      take({ ...(await prospectAnalyzeFile(file)), source_file: file.name })
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const reanalyze = async () => {
    setBusy(true); setError(null)
    try {
      const r = await prospectAnalyze(holdings.map(({ id, name, weight, fee, asset_type }) => ({ id, name, weight, fee, asset_type: asset_type || null })), res.aum)
      take({ ...r, source_file: res.source_file })
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const setFee = (id, v) => {
    setHoldings((hs) => hs.map((h) => (h.id === id ? { ...h, fee: v === '' ? null : Math.max(0, Number(v)) } : h)))
    setDirty(true)
  }
  // Advisor's classification of a paper (non-traded fund, structured product…). Applied on "עדכון הניתוח" and
  // saved to the securities data so the same paper is pre-classified next time.
  const setType = (id, v) => {
    setHoldings((hs) => hs.map((h) => (h.id === id ? { ...h, asset_type: v || null } : h)))
    setDirty(true)
    secdataUpdate(id, { asset_type: v || null }, advisor || getUser()).catch(() => { /* still applies to this analysis */ })
  }
  const pdf = async () => {
    setPdfBusy(true); setError(null); setUser(advisor)
    try { localStorage.setItem('ibi_contact', contact) } catch { /* storage unavailable */ }
    try {
      const blob = await prospectPdf({
        holdings: holdings.map(({ id, name, weight, fee, asset_type }) => ({ id, name, weight, fee, asset_type: asset_type || null })), aum: res.aum || null,
        client_name: client, advisor_name: advisor, advisor_contact: contact, source: res.source_file || '',
        exclude: [...excluded],
      })
      const u = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = u
      a.download = `IBI_סקירת_תיק_${client || 'לקוח'}_${new Date().toISOString().slice(0, 10)}.pdf`
      a.click()
      setTimeout(() => URL.revokeObjectURL(u), 2000)
    } catch (e) { setError(e.message) } finally { setPdfBusy(false) }
  }

  return (
    <main className="mx-auto max-w-[1440px] space-y-5 px-4 py-6 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="text-xs font-medium text-brand-700">ניתוח תיק פוטנציאלי</div>
          <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">ניתוח תיק של לקוח פוטנציאלי</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">העלו את פירוט האחזקות שהלקוח קיבל מבית ההשקעות הנוכחי. המערכת משקפת את הקרנות, בודקת את התיק מול כללי צוות ההשקעות ומפיקה דוח PDF ממותג עם תובנות.</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={() => setRulesOpen(true)}><ListChecks className="h-4 w-4" />כללי התובנות</button>
          {res && <button className="btn-outline" onClick={() => { setRes(null); setHoldings([]) }}><RotateCcw className="h-4 w-4" />תיק חדש</button>}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          <AlertTriangle className="h-4 w-4" /><span className="flex-1">{error}</span>
          <button onClick={() => setError(null)} aria-label="סגירה"><X className="h-4 w-4" /></button>
        </div>
      )}

      {!res ? (
        <div className="card p-6">
          <button onClick={() => inputRef.current?.click()} disabled={busy}
            onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files?.[0]) }}
            className={`flex w-full flex-col items-center rounded-2xl border-2 border-dashed px-6 py-16 text-center transition ${drag ? 'border-brand-500 bg-brand-50' : 'border-slate-300 hover:border-brand-400 hover:bg-slate-50'}`}>
            {busy ? <Loader2 className="h-10 w-10 animate-spin text-brand-600" /> : <FileSearch className="h-10 w-10 text-brand-600" />}
            <span className="mt-3 text-lg font-semibold text-slate-800">{busy ? 'מנתח את התיק…' : 'גררו לכאן את קובץ האחזקות או לחצו לבחירה'}</span>
            <span className="mt-1 text-sm text-slate-500">Excel או CSV · עמודת ״מספר נייר״ ועמודה אחת מתוך: משקל / שווי / כמות · שורות כותרת ושורת סה״כ מזוהות אוטומטית</span>
          </button>
          <input ref={inputRef} type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={(e) => { upload(e.target.files?.[0]); e.target.value = '' }} />
          <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
            <button className="btn-primary" onClick={demo} disabled={busy}><PlayCircle className="h-4 w-4" />הדגמה עם תיק לדוגמה</button>
            <a className="btn-ghost" href="/api/prospect/demo.xlsx" download><Download className="h-4 w-4" />הורדת קובץ לדוגמה</a>
          </div>
        </div>
      ) : (
        <Results res={res} holdings={holdings} dirty={dirty} busy={busy} onFee={setFee} onType={setType} onReanalyze={reanalyze}
          client={client} setClient={setClient} advisor={advisor} setAdvisor={setAdvisor} contact={contact} setContact={setContact}
          onPdf={pdf} pdfBusy={pdfBusy} excluded={excluded} onToggle={toggleInsight} />
      )}
      {rulesOpen && <RulesDialog onClose={() => setRulesOpen(false)} onChanged={() => res && reanalyze()} />}
    </main>
  )
}

function Results({ res, holdings, dirty, busy, onFee, onType, onReanalyze, client, setClient, advisor, setAdvisor, contact, setContact, onPdf, pdfBusy, excluded, onToggle }) {
  const { comp, eval: ev } = res
  const m = comp.metrics
  const ex = comp.extras
  const byId = Object.fromEntries(holdings.map((h) => [h.id, h]))
  const lim = 5
  const tiles = [
    res.aum ? ['שווי התיק', fmtILS(res.aum), `${m.Holdings_Count} ניירות`] : ['מספר ניירות', String(m.Holdings_Count), ''],
    ['חשיפה למניות', p1(m.Equity_Total * 100), `ישראל ${p1(ex.eq_il)} · חו״ל ${p1(ex.eq_foreign)}`],
    ['חשיפה למט״ח', p1(m.FX_Exposure * 100), 'מכלל התיק'],
    ['אג״ח', p1(ex.bonds), `ממשלתי ${p1(ex.gov)} · קונצרני ${p1(ex.corp)}`],
    ['דמי ניהול אפקטיביים', ex.effective_fee == null ? '—' : `${ex.effective_fee.toFixed(2)}%`, `כיסוי נתונים ${ex.fee_coverage.toFixed(0)}% מהתיק`],
  ]
  return (
    <>
      {/* Report bar */}
      <div className="card sticky top-[67px] z-20 flex flex-wrap items-end gap-3 p-4">
        <div className="min-w-0 flex-1">
          <div className="text-xs text-slate-500">קובץ</div>
          <div className="truncate font-semibold text-slate-800">{res.source_file}</div>
          <div className="text-[11px] text-slate-400">הסקירה מנוסחת ללקוח ומוכנה לשליחה · שם הקובץ ונתונים פנימיים לא מופיעים בה</div>
        </div>
        <label className="text-xs text-slate-500">שם הלקוח (מופיע בדוח בלבד)
          <input className="input mt-1 block w-48" value={client} onChange={(e) => setClient(e.target.value)} placeholder="אופציונלי" />
        </label>
        <label className="text-xs text-slate-500">שם היועץ
          <input className="input mt-1 block w-40" value={advisor} onChange={(e) => setAdvisor(e.target.value)} />
        </label>
        <label className="text-xs text-slate-500">טלפון / מייל של היועץ
          <input className="input mt-1 block w-52" dir="auto" value={contact} onChange={(e) => setContact(e.target.value)} placeholder="יופיע ב״השלב הבא״ בדוח" />
        </label>
        {dirty && <button className="btn-outline" onClick={onReanalyze} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}עדכון הניתוח</button>}
        <button className="btn-primary" onClick={onPdf} disabled={pdfBusy || dirty}>
          {pdfBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}הורדת סקירה ללקוח (PDF)
        </button>
      </div>

      {(res.warnings?.length > 0) && (
        <div className="flex items-start gap-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-900"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{res.warnings.join(' · ')}</div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {tiles.map(([l, v, s]) => (
          <div key={l} className="card px-4 py-3">
            <div className="text-xs text-slate-500">{l}</div>
            <div className="num text-xl font-bold text-slate-900">{v}</div>
            {s && <div className="truncate text-[11px] text-slate-400">{s}</div>}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-5">
        {/* Insights */}
        <section className="card overflow-hidden xl:col-span-3">
          <header className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
            <Lightbulb className="h-4 w-4 text-brand-700" />
            <h3 className="card-title">תובנות והמלצות</h3>
            <span className="text-xs text-slate-400">
              {ev.insights.length} נקודות · {ev.insights.filter((x) => !excluded.has(x.id)).length} ייכללו בסקירה ללקוח · אפשר להסתיר המלצה בלחיצה על ״מוצג ללקוח״
            </span>
          </header>
          <div className="space-y-3 p-4">
            {ev.insights.length === 0 && <p className="flex items-center gap-2 text-sm text-emerald-800"><CheckCircle2 className="h-4 w-4" />התיק עומד בכל הטווחים שנבדקו</p>}
            {(() => {
              let n = 0
              return ev.insights.map((ins) => {
                const off = excluded.has(ins.id)
                if (!off) n += 1
                return (
                  <article key={ins.id} className={`relative rounded-xl p-4 pr-5 transition ${off ? 'bg-slate-50/40 opacity-60' : 'bg-slate-50'}`}>
                    <span className={`absolute inset-y-3 right-0 w-1 rounded-full ${off ? 'bg-slate-300' : 'bg-[#00ADDC]'}`} />
                    <div className="mb-1.5 flex items-center gap-2">
                      <span className={`num grid h-6 w-6 place-items-center rounded-full text-xs font-bold ${off ? 'bg-slate-200 text-slate-500' : 'bg-navy-900 text-white'}`}>{off ? '–' : n}</span>
                      <h4 className={`font-semibold ${off ? 'text-slate-500 line-through' : 'text-slate-900'}`}>{ins.title}</h4>
                      <span className="num text-[10px] text-slate-400">{ins.id}</span>
                      <button onClick={() => onToggle(ins.id)} aria-pressed={!off}
                        className={`mr-auto flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ring-inset transition ${off ? 'bg-surface text-slate-500 ring-slate-200 hover:text-slate-700' : 'bg-emerald-50 text-emerald-800 ring-emerald-200 hover:bg-emerald-100'}`}
                        title={off ? 'ההמלצה לא תופיע בסקירה – לחיצה להחזרה' : 'לחיצה להסתרת ההמלצה מהסקירה ללקוח'}>
                        {off ? <><EyeOff className="h-3.5 w-3.5" />מוסתר מהלקוח</> : <><Eye className="h-3.5 w-3.5" />מוצג ללקוח</>}
                      </button>
                    </div>
                    {ins.text.split('\n').filter(Boolean).map((ln, j) => <p key={j} className={`mt-1 text-sm leading-relaxed ${off ? 'text-slate-400' : 'text-slate-700'}`}>{ln}</p>)}
                  </article>
                )
              })
            })()}
          </div>
        </section>

        {/* Metric checks + composition */}
        <div className="space-y-5 xl:col-span-2">
          <section className="card overflow-hidden">
            <header className="border-b border-slate-100 px-4 py-3"><h3 className="card-title">מדדי הבדיקה</h3>
              <p className="text-[11px] text-slate-400">ערך בתיק מול הטווח שקבע צוות ההשקעות</p></header>
            <table className="w-full text-sm">
              <tbody className="divide-y divide-slate-100">
                {ev.status.map((s) => {
                  const [lab, cls] = STATE[s.state] ?? STATE.null
                  return (
                    <tr key={s.metric}>
                      <td className="td whitespace-normal text-slate-700">{s.label}</td>
                      <td className="td num text-left font-semibold text-slate-900">{s.display}</td>
                      <td className="td num text-left text-xs text-slate-400">{s.range}</td>
                      <td className="td text-left"><span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${cls}`}>{lab}</span></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {(ex.low_rated_coverage != null && ex.low_rated_coverage < 99) && (
              <p className="flex gap-1.5 border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500"><Info className="h-3.5 w-3.5 shrink-0" />דירוג ידוע ל-{ex.low_rated_coverage.toFixed(0)}% מהאג״ח הקונצרני. דירוגי אג״ח בודדות ניתן להזין בנתוני השוק במודלים.</p>
            )}
          </section>
          <section className="card space-y-4 p-4">
            <h3 className="card-title">הרכב התיק <span className="text-xs font-normal text-slate-400">לאחר שיקוף קרנות</span></h3>
            <StackedBar data={ex.asset_classes} order={ASSET_ORDER} height="h-4" />
            <Legend order={ASSET_ORDER.filter((o) => ex.asset_classes[o.key])} />
            {[['מניות', [['ישראל', ex.eq_il], ['חו״ל', ex.eq_foreign]]], ['אג״ח לפי מנפיק', [['ממשלתי', ex.gov], ['קונצרני', ex.corp]]],
              ['אג״ח לפי הצמדה', [['שקלי', ex.shekel], ['צמוד מדד', ex.linked]]]].map(([name, parts]) => {
              const tot = parts.reduce((t, [, v]) => t + v, 0)
              return (
                <div key={name}>
                  <div className="mb-1 flex justify-between text-xs"><span className="font-medium text-slate-600">{name}</span>
                    <span className="num text-slate-400">{tot > 0 ? parts.map(([l, v]) => `${l} ${((v / tot) * 100).toFixed(0)}%`).join(' · ') : 'אין חשיפה'}</span></div>
                  <div className="flex h-2 overflow-hidden rounded-full bg-slate-100">
                    {tot > 0 && parts.map(([l, v], i) => <div key={l} style={{ width: `${(v / tot) * 100}%`, background: SERIES[i] }} />)}
                  </div>
                </div>
              )
            })}
          </section>
        </div>
      </div>

      <ModelMatch res={res} />

      {/* Holdings */}
      <section className="card overflow-hidden">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <h3 className="card-title">האחזקות <span className="text-sm font-normal text-slate-400">({comp.rows.length})</span></h3>
          <span className="text-[11px] text-slate-400">נייר שלא זוהה (קרן לא סחירה, מוצר מובנה…) – בחרו את סוגו בעמודה ״סוג״; דמי ניהול חסרים אפשר להזין כאן. אחר כך ״עדכון הניתוח״ · הסיווג נשמר לפעם הבאה · אדום = נייר ישיר מעל {lim}%</span>
        </header>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50/80"><tr><th className="th">נייר</th><th className="th">סוג</th><th className="th">דמי ניהול</th><th className="th">משקל</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {comp.rows.map((r) => {
                const flag = (r.kind === 'equity' || r.kind === 'bond') && r.weight > lim
                const h = byId[r.id]
                const isFund = r.kind === 'fund' || r.kind === 'etf'
                return (
                  <tr key={r.id} className={flag ? 'bg-red-50/60' : (r.kind === 'other' && !r.asset_type) ? 'bg-amber-50/50' : ''}>
                    <td className="td max-w-[340px]">
                      <div dir="auto" className="truncate font-medium text-slate-800">{r.name}</div>
                      <div className="num text-xs text-slate-400">{r.id}{!r.priced && !r.asset_type && ' · לא זוהה'}</div>
                    </td>
                    <td className="td">
                      <TypePick r={r} value={h?.asset_type ?? ''} types={res.asset_types || []} onChange={(v) => onType(r.id, v)} />
                    </td>
                    <td className="td">
                      {isFund ? (
                        <div className="flex items-center gap-1">
                          <input type="number" min="0" step="0.01" value={h?.fee ?? ''} placeholder={r.fee != null ? Number(r.fee).toFixed(2) : 'חסר'}
                            onChange={(e) => onFee(r.id, e.target.value)} aria-label={`דמי ניהול ${r.name}`}
                            className={`num w-16 rounded-md border px-1.5 py-1 text-left text-xs focus:border-brand-400 focus:outline-none ${r.fee == null && h?.fee == null ? 'border-amber-300 bg-amber-50 placeholder:text-amber-700' : 'border-slate-200 bg-surface'}`} />
                          <span className="text-xs text-slate-400">%</span>
                        </div>
                      ) : <span className="text-xs text-slate-300">—</span>}
                    </td>
                    <td className={`td num font-semibold ${flag ? 'text-red-700' : 'text-slate-800'}`}>{r.weight.toFixed(2)}%</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}

/** Type column: the automatic classification, or the advisor's choice for a paper the data sources don't know. */
function TypePick({ r, value, types, onChange }) {
  const unknown = r.kind === 'other' && !value
  const auto = r.asset_type && !value ? 'סיווג ידני הוסר' : kindLabel(r)
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={`סוג הנייר ${r.name}`}
      title={value ? 'סווג ידנית' : 'סיווג אוטומטי – אפשר לבחור סוג אחר'}
      className={`max-w-[190px] rounded-md border px-1.5 py-1 text-xs focus:border-brand-400 focus:outline-none ${unknown ? 'border-amber-300 bg-amber-50 font-semibold text-amber-800' : value ? 'border-brand-300 bg-brand-50 text-brand-800' : 'border-transparent bg-transparent text-slate-600 hover:border-slate-200'}`}>
      <option value="">{unknown ? 'לא זוהה – בחרו סוג…' : `${r.asset_type && !value ? auto : kindLabel(r)} (אוטומטי)`}</option>
      {types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
    </select>
  )
}
