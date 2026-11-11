import { Fragment, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronLeft, FileSpreadsheet, Loader2, UploadCloud } from 'lucide-react'
import { commitImport, getUser, previewImport, setUser } from '../../lib/api'
import { fmtPct } from '../../lib/format'
import Modal from './Modal'

const ACTION_LABEL = { create: 'יצירת מודל חדש', update: 'עדכון (גרסה חדשה)', skip: 'דילוג' }

export default function ImportDialog({ onClose, onDone }) {
  const inputRef = useRef(null)
  const [preview, setPreview] = useState(null)
  const [items, setItems] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [open, setOpen] = useState(null)
  const [user, setU] = useState(getUser())
  const [note, setNote] = useState('ייבוא מאקסל')

  const pick = async (file) => {
    if (!file) return
    setBusy(true); setError(null)
    try {
      const p = await previewImport(file)
      setPreview(p)
      setItems(p.sheets.map((s) => ({ ...s, action: s.suggested_action, newName: s.name })))
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const setItem = (i, patch) => setItems((xs) => xs.map((x, j) => (j === i ? { ...x, ...patch } : x)))

  const commit = async () => {
    setBusy(true); setError(null); setUser(user)
    try {
      const res = await commitImport({
        user, note,
        items: items.map((s) => ({
          name: s.action === 'create' ? s.newName : s.name, action: s.action, target_id: s.match?.id ?? null,
          holdings: s.holdings.map((h) => ({ id: h.id, name: h.name, weight: h.weight, fee: h.fee })),
          ...(s.config ? { config: s.config, equity_target: s.equity_target } : {}),
        })),
      })
      setResult(res)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const active = items.filter((s) => s.action !== 'skip').length

  if (result) {
    return (
      <Modal title="הייבוא הושלם" onClose={onDone} footer={<button className="btn-primary" onClick={onDone}>חזרה למודלים</button>}>
        <div className="space-y-2 text-sm">
          <p className="flex items-center gap-2 text-emerald-800"><CheckCircle2 className="h-4 w-4" />נוצרו {result.created.length} · עודכנו {result.updated.length} · דולגו {result.skipped.length}</p>
          {result.updated.map((u) => <p key={u.id} className="text-slate-600">״{u.name}״ – גרסה <span className="num">{u.version}</span></p>)}
          {result.errors.map((e) => <p key={e.name} className="text-red-700">״{e.name}״: {e.error}</p>)}
        </div>
      </Modal>
    )
  }

  return (
    <Modal wide title="ייבוא מודלים מאקסל" subtitle="כל גיליון בקובץ = מודל. שם הגיליון הוא שם המודל (״80-20״ מותאם ל״80/20״)." onClose={onClose}
      footer={preview && <>
        <input className="input ml-auto w-44" value={user} onChange={(e) => setU(e.target.value)} placeholder="שם העורך" />
        <input className="input w-56" value={note} onChange={(e) => setNote(e.target.value)} placeholder="הערת גרסה" />
        <button className="btn-ghost" onClick={onClose}>ביטול</button>
        <button className="btn-primary" disabled={busy || !active} onClick={commit}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}ייבוא {active} מודלים</button>
      </>}>
      {!preview ? (
        <div>
          <input ref={inputRef} type="file" accept=".xlsx,.xls,.xlsm,.csv" hidden onChange={(e) => pick(e.target.files?.[0])} />
          <button onClick={() => inputRef.current?.click()} disabled={busy}
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files?.[0]) }}
            className="flex w-full flex-col items-center rounded-xl border-2 border-dashed border-slate-300 px-6 py-12 text-center hover:border-brand-400 hover:bg-slate-50">
            {busy ? <Loader2 className="mb-3 h-10 w-10 animate-spin text-brand-600" /> : <UploadCloud className="mb-3 h-10 w-10 text-brand-600" />}
            <span className="font-semibold text-slate-800">{busy ? 'קורא ומזהה ניירות…' : 'גררו לכאן את קובץ המודלים או לחצו לבחירה'}</span>
            <span className="mt-1 text-sm text-slate-500">עמודות נתמכות: מספר נייר / ticker, משקל, (אופציונלי) שם נייר, דמי ניהול</span>
          </button>
          <a href="/api/models/demo-workbook" download className="mt-3 inline-flex items-center gap-1.5 text-sm text-brand-700 hover:underline">
            <FileSpreadsheet className="h-4 w-4" />הורדת קובץ דוגמה במבנה הנתמך
          </a>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <p className="mb-3 text-sm text-slate-500">קובץ: <span className="font-medium text-slate-700">{preview.file}</span> · {items.length} גיליונות. דבר לא נשמר עד ללחיצה על ״ייבוא״.</p>
          {preview.kind === 'allocation' && (
            <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg bg-navy-50 p-3 text-sm text-navy-900">
              <span className="flex-1">זוהה קובץ אלוקציה: כל גיליון ייובא כ<b>גיליון הקצאה</b> מלא – סעיפים, אחוז מנייתי, דמי ניהול חוזה, אינפלציה גלומה, טווחי הבקרה וטבלאות הרכב המדדים. גיליונות מוסתרים מסומנים לדילוג כברירת מחדל.</span>
              <button className="btn-outline px-2.5 py-1 text-xs" onClick={() => setItems((xs) => xs.map((x) => (x.error ? x : { ...x, action: x.match ? 'update' : 'create' })))}>סימון הכל לייבוא</button>
            </div>
          )}
          <table className="w-full text-sm">
            <thead className="bg-slate-50/80">
              <tr><th className="th w-8" /><th className="th">גיליון</th><th className="th">ניירות</th><th className="th">סך משקל</th><th className="th">שינויים</th><th className="th">פעולה</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((s, i) => {
                const off = Math.abs(s.total_weight - 100) > 0.01
                const ch = s.changes
                return (
                  <Fragment key={s.sheet}>
                    <tr>
                      <td className="td">
                        {s.holdings.length > 0 && (
                          <button onClick={() => setOpen(open === i ? null : i)} className="text-slate-400">{open === i ? <ChevronDown className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}</button>
                        )}
                      </td>
                      <td className="td">
                        <div className="flex flex-wrap items-center gap-1.5 font-semibold text-slate-800">{s.sheet}
                          {s.kind === 'allocation' && <span className="rounded bg-navy-50 px-1.5 text-[10px] font-medium text-navy-700">{s.template === 'israel' ? 'ישראל' : 'ישראל + חו״ל'} · מניות <span className="num">{s.equity_target ?? '—'}%</span></span>}
                          {s.hidden && <span className="rounded bg-slate-100 px-1.5 text-[10px] font-medium text-slate-500">מוסתר באקסל</span>}
                        </div>
                        {s.error ? <div className="text-xs text-red-700">{s.error}</div>
                          : s.match ? <div className="text-xs text-slate-500">תואם למודל ״{s.match.name}״ (גרסה <span className="num">{s.match.version}</span>)</div>
                            : <div className="text-xs text-slate-500">מודל חדש</div>}
                        {s.unpriced.length > 0 && <div className="flex items-center gap-1 text-xs text-amber-800"><AlertTriangle className="h-3 w-3" />לא זוהו: {s.unpriced.join(', ')}</div>}
                      </td>
                      <td className="td"><span className="num">{s.rows_count ?? s.holdings.length}</span></td>
                      <td className={`td ${off && s.kind !== 'allocation' ? 'font-semibold text-amber-700' : ''}`}>
                        <span className="num">{fmtPct(s.total_weight)}</span>
                        {s.kind === 'allocation' && s.total_weight < 100 && s.total_weight > 0 && <div className="text-[10px] text-slate-400">עו״ש <span className="num">{fmtPct(100 - s.total_weight)}</span></div>}
                      </td>
                      <td className="td text-xs text-slate-600">
                        {!ch ? '—' : !(ch.added.length || ch.removed.length || ch.changed.length) ? 'ללא שינוי'
                          : <>+{ch.added.length} נוספו · −{ch.removed.length} הוסרו · {ch.changed.length} משקלים שונו</>}
                      </td>
                      <td className="td">
                        <select className="input py-1.5" value={s.action} disabled={!!s.error} onChange={(e) => setItem(i, { action: e.target.value })}>
                          {(s.match ? ['update', 'skip'] : ['create', 'skip']).map((a) => <option key={a} value={a}>{ACTION_LABEL[a]}</option>)}
                        </select>
                        {s.action === 'create' && (
                          <input className="input mt-1 w-full py-1" value={s.newName} onChange={(e) => setItem(i, { newName: e.target.value })} aria-label="שם המודל החדש" />
                        )}
                      </td>
                    </tr>
                    {open === i && (
                      <tr className="bg-slate-50/60">
                        <td />
                        <td colSpan={5} className="px-3 pb-3">
                          <div className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
                            {s.holdings.map((h) => (
                              <div key={h.id} className="flex items-center justify-between gap-3 text-sm">
                                <span className="truncate">
                                  <span className="num ml-2 text-xs text-slate-400">{h.id}</span>
                                  <span dir="auto" className={h.priced ? 'text-slate-700' : 'text-amber-800'}>{h.resolved_name || h.name || 'לא מזוהה'}</span>
                                  {ch?.added.includes(h.id) && <span className="mr-1 rounded bg-emerald-50 px-1 text-[10px] text-emerald-800">חדש</span>}
                                  {ch?.changed.includes(h.id) && <span className="mr-1 rounded bg-amber-50 px-1 text-[10px] text-amber-800">שונה</span>}
                                </span>
                                <span className="num shrink-0 text-slate-500">{fmtPct(h.weight)}</span>
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
      )}
      {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
    </Modal>
  )
}
