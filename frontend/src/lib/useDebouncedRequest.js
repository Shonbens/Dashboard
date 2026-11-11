import { useEffect, useRef, useState } from 'react'

/** Runs `fn(signal)` whenever `key` changes, debounced, cancelling stale requests. */
export default function useDebouncedRequest(fn, key, delay = 300) {
  const [state, setState] = useState({ data: null, loading: false, error: null })
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (key == null) return undefined
    const ctrl = new AbortController()
    setState((s) => ({ ...s, loading: true, error: null }))
    const t = setTimeout(async () => {
      try {
        const data = await fnRef.current(ctrl.signal)
        if (!ctrl.signal.aborted) setState({ data, loading: false, error: null })
      } catch (e) {
        if (!ctrl.signal.aborted) setState((s) => ({ ...s, loading: false, error: e.message }))
      }
    }, delay)
    return () => { clearTimeout(t); ctrl.abort() }
  }, [key, delay])

  return state
}
