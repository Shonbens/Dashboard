import { useEffect, useState } from 'react'

const read = () => { try { return localStorage.getItem('ibi_theme') || 'system' } catch { return 'system' } }

/** 'light' | 'dark' | 'system' – toggles the `dark` class on <html> and follows the OS when on system. */
export default function useTheme() {
  const [theme, setTheme] = useState(read)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => document.documentElement.classList.toggle('dark', theme === 'dark' || (theme === 'system' && mq.matches))
    apply()
    try { localStorage.setItem('ibi_theme', theme) } catch { /* storage unavailable */ }
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [theme])
  return [theme, setTheme]
}
