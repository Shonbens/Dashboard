const ils0 = new Intl.NumberFormat('he-IL', { style: 'currency', currency: 'ILS', maximumFractionDigits: 0 })
const compact = new Intl.NumberFormat('he-IL', { notation: 'compact', maximumFractionDigits: 1 })

export const fmtILS = (v) => (v == null || Number.isNaN(v) ? '—' : ils0.format(v))
export const fmtCompactILS = (v) => (v == null ? '—' : `₪${compact.format(v)}`)
export const fmtPct = (v, d = 2) => (v == null || Number.isNaN(v) ? '—' : `${v.toFixed(d)}%`)
export const fmtSignedPct = (v, d = 2) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(d)}%`)
export const fmtInt = (v) => (v == null ? '—' : new Intl.NumberFormat('he-IL').format(Math.round(v)))

const SYMBOL = { ILS: '₪', USD: '$', EUR: '€', GBP: '£' }
export function fmtPrice(v, ccy) {
  if (!v) return '—'
  const digits = v < 10 ? 4 : 2
  return `${SYMBOL[ccy] ?? ''}${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: digits })}`
}
export const ccySymbol = (c) => SYMBOL[c] ?? c
