import { OTHER_COLOR, SERIES } from '../palette'

// Fixed category -> color mapping (entity, never rank)
export const ASSET_ORDER = [
  { key: 'מניות', color: SERIES[0] },
  { key: 'אג״ח ממשלתי', color: SERIES[1] },
  { key: 'אג״ח קונצרני', color: SERIES[2] },
  { key: 'מזומן ופיקדונות', color: SERIES[3], darkInk: true },
  { key: 'אחר', color: OTHER_COLOR },
]
export const GEO_ORDER = [
  { key: 'ישראל', color: SERIES[0] },
  { key: 'ארה״ב', color: SERIES[1] },
  { key: 'אירופה', color: SERIES[2] },
  { key: 'אסיה ופסיפיק', color: SERIES[3], darkInk: true },
  { key: 'שווקים מתעוררים', color: SERIES[4] },
  { key: 'אחר', color: OTHER_COLOR },
]
export { GAIN, LOSS } from '../palette'

export const STATUS = {
  approved: { label: 'מאושר', cls: 'bg-emerald-50 text-emerald-800 ring-emerald-200' },
  draft: { label: 'טיוטה', cls: 'bg-amber-50 text-amber-800 ring-amber-200' },
  archived: { label: 'בארכיון', cls: 'bg-slate-100 text-slate-600 ring-slate-200' },
}

export const fmtDate = (ts) => (ts ? new Date(ts * 1000).toLocaleString('he-IL', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—')

export function heat(v, maxAbs) {
  if (v == null || !maxAbs) return 'transparent'
  const a = Math.min(1, Math.abs(v) / maxAbs) * 0.55 + 0.05
  return v >= 0 ? `rgb(var(--gain) / ${a})` : `rgb(var(--loss) / ${a})`
}

/** Sequential risk color (one hue family, light -> dark) from an equity share 0-100: light cyan -> deep blue. */
export function riskColor(eq) {
  const t = Math.max(0, Math.min(1, (eq ?? 0) / 100))
  const a = [150, 226, 245], b = [31, 60, 150] // readable on light and dark surfaces
  const mix = a.map((x, i) => Math.round(x + (b[i] - x) * t))
  return `rgb(${mix.join(' ')})`
}
export const riskLevel = (eq) => Math.max(1, Math.min(5, Math.ceil((eq ?? 0) / 20)))
