import { useEffect, useState } from 'react'

/** Minimal hash router: '#/models/3' -> ['models', '3'] */
export default function useHashRoute() {
  const parse = () => window.location.hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  const [parts, setParts] = useState(parse)
  useEffect(() => {
    const on = () => setParts(parse())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return parts
}

export const navigate = (path) => { window.location.hash = path }
