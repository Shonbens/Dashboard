import { Wallet } from 'lucide-react'
import { fmtILS } from '../lib/format'

const MIN = 100_000
const MAX = 50_000_000

export default function AumControl({ aum, setAum }) {
  const pct = Math.min(100, Math.max(0, ((aum - MIN) / (MAX - MIN)) * 100))
  return (
    <div className="card flex flex-col gap-3 p-5 lg:flex-row lg:items-center lg:gap-6">
      <div className="flex items-center gap-3 lg:w-56">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand-50 text-brand-700"><Wallet className="h-5 w-5" /></div>
        <div>
          <div className="text-sm font-semibold text-slate-800">היקף נכסי הלקוח (AUM)</div>
          <div className="text-xs text-slate-500">שווי הפוזיציות מחושב בזמן אמת</div>
        </div>
      </div>
      <input
        type="range"
        min={MIN}
        max={MAX}
        step={50_000}
        value={Math.min(MAX, Math.max(MIN, aum))}
        onChange={(e) => setAum(Number(e.target.value))}
        className="aum-range flex-1"
        dir="ltr"
        aria-label="היקף נכסים"
        style={{ '--p': `${pct}%` }}
      />
      <div className="flex items-center gap-2">
        <span className="text-sm text-slate-500">₪</span>
        <input
          type="number"
          className="input num w-40 text-left font-semibold"
          value={Math.round(aum)}
          min={0}
          step={10_000}
          onChange={(e) => setAum(Math.max(0, Number(e.target.value) || 0))}
        />
        <span className="hidden text-xs text-slate-400 xl:inline num">{fmtILS(aum)}</span>
      </div>
    </div>
  )
}
