import { useEffect, useRef, useState } from 'react'
import { Loader2, Plus, Search } from 'lucide-react'
import { searchSecurities } from '../lib/api'

export default function AddHolding({ onAdd, disabled }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const boxRef = useRef(null)

  useEffect(() => {
    if (q.trim().length < 2) { setResults([]); return }
    const ctrl = new AbortController()
    const t = setTimeout(async () => {
      setLoading(true)
      try {
        const r = await searchSecurities(q.trim(), ctrl.signal)
        setResults(r.results)
        setOpen(true)
      } catch { /* aborted or offline */ } finally { setLoading(false) }
    }, 250)
    return () => { clearTimeout(t); ctrl.abort() }
  }, [q])

  useEffect(() => {
    const close = (e) => !boxRef.current?.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const choose = (r) => { onAdd(r.id); setQ(''); setResults([]); setOpen(false) }

  return (
    <div ref={boxRef} className="relative w-full sm:w-80">
      <Search className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input
        className="input w-full pr-9 pl-9"
        placeholder="הוספת נייר: שם, מספר נייר או טיקר"
        value={q}
        disabled={disabled}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => results.length && setOpen(true)}
        onKeyDown={(e) => { if (e.key === 'Enter' && results[0]) choose(results[0]) }}
      />
      {loading && <Loader2 className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-slate-400" />}
      {open && results.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-xl border border-slate-200 bg-surface py-1 shadow-card-hover">
          {results.map((r) => (
            <li key={`${r.market}-${r.id}`}>
              <button className="flex w-full items-center justify-between gap-3 px-3 py-2 text-right text-sm hover:bg-slate-50" onClick={() => choose(r)}>
                <span className="min-w-0">
                  <span className="block truncate font-medium text-slate-800">{r.name}</span>
                  <span className="block truncate text-xs text-slate-500">{r.name_en}{r.asset_class ? ` · ${r.asset_class}` : ''}</span>
                </span>
                <span className="flex shrink-0 items-center gap-1 text-xs text-slate-500">
                  <span className="num">{r.symbol || r.id}</span><Plus className="h-3.5 w-3.5" />
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
