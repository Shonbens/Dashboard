import { useRef, useState } from 'react'
import { FileSpreadsheet, Loader2, UploadCloud, Download, Sparkles } from 'lucide-react'

export default function UploadZone({ onFile, onSample, loading, compact = false }) {
  const inputRef = useRef(null)
  const [drag, setDrag] = useState(false)

  const pick = (files) => {
    const f = files?.[0]
    if (f) onFile(f)
  }

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls" hidden onChange={(e) => { pick(e.target.files); e.target.value = '' }} />
        <button className="btn-outline" disabled={loading} onClick={() => inputRef.current?.click()}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
          העלאת תיק חדש
        </button>
      </div>
    )
  }

  return (
    <div className="card p-6">
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files) }}
        onClick={() => !loading && inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-14 text-center transition
          ${drag ? 'border-brand-500 bg-brand-50' : 'border-slate-300 hover:border-brand-400 hover:bg-slate-50'}`}
      >
        <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls" hidden onChange={(e) => { pick(e.target.files); e.target.value = '' }} />
        {loading ? (
          <>
            <Loader2 className="mb-4 h-12 w-12 animate-spin text-brand-600" />
            <p className="text-lg font-semibold text-slate-700">מתמחר את התיק…</p>
            <p className="mt-1 text-sm text-slate-500">yfinance ← מאי״ה (TASE) ← ביזפורטל</p>
          </>
        ) : (
          <>
            <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-brand-50 text-brand-700">
              <FileSpreadsheet className="h-7 w-7" />
            </div>
            <p className="text-lg font-semibold text-slate-800">גררו לכאן קובץ תיק השקעות</p>
            <p className="mt-1 text-sm text-slate-500">CSV או Excel · עמודות: מספר נייר / ticker, משקל, (אופציונלי) משקל יעד או כמות</p>
            <span className="btn-primary mt-5"><UploadCloud className="h-4 w-4" /> בחירת קובץ</span>
          </>
        )}
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-sm">
        <button className="btn-ghost" disabled={loading} onClick={onSample}>
          <Sparkles className="h-4 w-4" /> טעינת תיק לדוגמה
        </button>
        <a className="btn-ghost" href="/api/template" download>
          <Download className="h-4 w-4" /> הורדת תבנית CSV
        </a>
      </div>
    </div>
  )
}
