import { useEffect } from 'react'
import { X } from 'lucide-react'

export default function Modal({ title, subtitle, onClose, children, footer, wide = false }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[#0b0d1c]/50 p-4 pt-[8vh] backdrop-blur-[2px]" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" className={`card w-full ${wide ? 'max-w-4xl' : 'max-w-lg'} shadow-card-hover`}>
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 p-5">
          <div>
            <h3 className="text-lg font-bold text-slate-900">{title}</h3>
            {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
          </div>
          <button onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="סגירה"><X className="h-5 w-5" /></button>
        </div>
        <div className="p-5">{children}</div>
        {footer && <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 bg-slate-50/60 p-4">{footer}</div>}
      </div>
    </div>
  )
}
