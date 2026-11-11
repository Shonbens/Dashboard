import { MARKET_FLAG, MARKET_LABEL } from '../lib/portfolio'

const MARKET_STYLE = {
  IL: 'bg-sky-50 text-sky-800 ring-sky-200',
  US: 'bg-orange-50 text-orange-800 ring-orange-200',
  OTHER: 'bg-slate-100 text-slate-700 ring-slate-200',
}
export function MarketBadge({ market }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${MARKET_STYLE[market] ?? MARKET_STYLE.OTHER}`}>
      <span>{MARKET_FLAG[market]}</span>{MARKET_LABEL[market] ?? market}
    </span>
  )
}

const TIER_STYLE = {
  1: 'text-emerald-700 bg-emerald-50',
  2: 'text-brand-700 bg-brand-50',
  3: 'text-amber-800 bg-amber-50',
  4: 'text-red-700 bg-red-50',
}
export function SourceBadge({ tier, source }) {
  return (
    <span title={`Tier ${tier}`} className={`inline-flex rounded px-1.5 py-0.5 text-[11px] font-medium ${TIER_STYLE[tier] ?? TIER_STYLE[4]}`}>
      T{tier} · {source === 'fallback' ? 'לא תומחר' : source}
    </span>
  )
}
