/**
 * Allocation sheet engine – a faithful port of the house Excel ("חדש מ.ק.20" / "חדש ישראל מ.ק 30").
 *
 * Inputs: per-row "אחוז ראשי" (E = weight inside its sleeve) and the model's equity share (F3).
 * F (אחוז יחסי, weight in the portfolio) = E × equity share for the equity sleeve, E × (1 − equity share) for bonds.
 * All percentages in this module are in % units (4.83 means 4.83%).
 */

// --------------------------------------------------------------------------- //
//  Sections (same order and names as the Excel)
// --------------------------------------------------------------------------- //
export const SECTIONS = [
  { key: 'eq_il', label: 'מניות בארץ', group: 'equity', sleeve: 'equity', total: 'סה״כ מניות בארץ' },
  { key: 'eq_foreign', label: 'מניות בחו״ל', group: 'equity', sleeve: 'equity', total: 'סה״כ מניות בחו״ל', globalOnly: true },
  { key: 'gov_cpi', label: 'ממשלתי צמוד', group: 'gov', sleeve: 'bond', linkage: 'linked', cpi: true },
  { key: 'gov_usd', label: 'ממשלתי חו״ל דולר', group: 'gov', sleeve: 'bond', linkage: 'fx' },
  { key: 'gov_nominal', label: 'ממשלתי שקלי', group: 'gov', sleeve: 'bond', linkage: 'shekel' },
  { key: 'gov_float', label: 'ממשלתי משתנה', group: 'gov', sleeve: 'bond', linkage: 'shekel' },
  { key: 'corp_usd', label: 'קונצרני צמוד דולר', group: 'corp', sleeve: 'bond', linkage: 'fx', rated: true },
  { key: 'corp_cpi', label: 'קונצרני צמוד', group: 'corp', sleeve: 'bond', linkage: 'linked', cpi: true, rated: true },
  { key: 'corp_nominal', label: 'קונצרני שקלי', group: 'corp', sleeve: 'bond', linkage: 'shekel', rated: true },
  { key: 'corp_float', label: 'קונצרני ריבית משתנה', group: 'corp', sleeve: 'bond', linkage: 'shekel', rated: true },
  { key: 'corp_hedged', label: 'קונצרני חו״ל מנוטרל מטבע', group: 'corp', sleeve: 'bond', linkage: 'shekel', rated: true },
  { key: 'funds', label: 'קרנות', group: 'funds', sleeve: null, rated: true },
]
export const GROUPS = {
  equity: 'מניות', gov: 'אג״ח ממשלתי', corp: 'אג״ח קונצרני', funds: 'קרנות',
}
export const GROUP_TOTAL = { equity: 'סה״כ מניות', gov: 'סה״כ ממשלתי', corp: 'סה״כ קונצרני', funds: 'סה״כ קרנות' }

export const TEMPLATES = {
  global: { label: 'ישראל + חו״ל', excel: 'חדש מ.ק.20', fund_cap: 20 },
  israel: { label: 'ישראל בלבד', excel: 'חדש ישראל מ.ק 30', fund_cap: 30 },
}

export const sectionsFor = (template) => SECTIONS.filter((s) => !(s.globalOnly && template === 'israel'))

export const RATING_BUCKETS = [
  { key: 1, label: 'תחליף ממשלתי' }, { key: 2, label: 'חזק' }, { key: 3, label: 'בינוני' }, { key: 4, label: 'סיכון גבוה' },
]

export const IL_SECTORS = ['טכנולוגיה', 'בנקים', 'שרותים פיננסים', 'ביטוח', 'נדלן ובנייה', 'ביומד', 'מסחר ושרותים', 'תעשייה',
  'אנרגיה וחיפושי נפט וגז', 'השקעה ואחזקות']
export const IL_MEMO_SECTORS = ['ביטחונית'] // shown in the table but outside the pie (as in the Excel)
export const IL_INDEX_LABELS = { 'ת"א 125': 'ta125', 'ת"א90': 'ta90', MID: 'mid' }
// Columns of the Israeli sector table. MID appears in the Israel-only sheet ("חדש ישראל מ.ק 30").
export const IL_COLUMNS = [
  { key: 'ta125', label: 'ת״א 125', excel: 'ת"א 125' }, { key: 'ta90', label: 'ת״א 90', excel: 'ת"א 90' },
  { key: 'fund_eq', label: 'קרן מניות', excel: 'מניות' }, { key: 'fund_other', label: 'קרן יתר', excel: 'יתר' },
  { key: 'mid', label: 'MID', excel: 'MID', israelOnly: true },
]

export const GICS = ['Information Technology', 'Health Care', 'Financials', 'Consumer Discretionary', 'Communication Services',
  'Industrials', 'Consumer Staples', 'Energy', 'Utilities', 'Real Estate', 'Materials']
export const GICS_HE = {
  'Information Technology': 'טכנולוגיה', 'Health Care': 'בריאות', Financials: 'פיננסים', 'Consumer Discretionary': 'צריכה מחזורית',
  'Communication Services': 'תקשורת', Industrials: 'תעשייה', 'Consumer Staples': 'צריכה בסיסית', Energy: 'אנרגיה',
  Utilities: 'תשתיות', 'Real Estate': 'נדל״ן', Materials: 'חומרי גלם', שבבים: 'מתוכו שבבים',
}
export const FOREIGN_COLUMNS = [
  { key: 'SP', label: 'S&P', exposure: 'S&P 500', region: 'US' },
  { key: 'NDX', label: 'NASDAQ', exposure: 'NASDAQ', region: 'US' },
  { key: 'STOXX', label: 'STOXX', exposure: 'STOXX 600', region: 'EUROPE' },
  { key: 'ROW', label: 'שאר העולם', exposure: 'שאר העולם', region: 'EM' },
  { key: 'GLOBAL', label: 'ישיר גלובל', exposure: 'גלובלי', region: 'US' },
  { key: 'RUSSELL', label: 'RUSSELL', exposure: 'RUSSELL', region: 'US' },
]
// 'שבבים' = a direct semiconductor holding: counted as Information Technology and in the semiconductors memo line (Excel row 24)
export const FOREIGN_EXPOSURES = [...FOREIGN_COLUMNS.map((c) => c.exposure), ...GICS, 'שבבים']
export const COUNTRIES = ['ישראל', 'ארה״ב', 'אירופה', 'שווקים מתעוררים']
export const GEO = [['IL', 'ישראל'], ['US', 'ארה״ב'], ['EUROPE', 'אירופה'], ['EM', 'שווקים מתעוררים']]

/** Assumption tables, copied from the Excel at full precision (editable per model, like the hard-coded cells in each sheet).
 *  'ישיר גלובל' (GLOBAL) keeps the Excel's own expressions, e.g. =13.83/28. */
export const DEFAULT_REFS = {
  il_sectors: {
    'טכנולוגיה': { ta125: 30.08, ta90: 21.89, fund_eq: 26.981919332406, fund_other: 13.437195715677, mid: 21.16 },
    'בנקים': { ta125: 18.51, ta90: 1.91, fund_eq: 20.317570700046, fund_other: 0, mid: 2.18 },
    'שרותים פיננסים': { ta125: 2.5, ta90: 4.98, fund_eq: 1.692165044043, fund_other: 5.128205128205, mid: 5.33 },
    'ביטוח': { ta125: 11.2, ta90: 1.8, fund_eq: 6.363004172462, fund_other: 1.211727794006, mid: 5.4 },
    'נדלן ובנייה': { ta125: 12.01, ta90: 26.28, fund_eq: 19.286045433472, fund_other: 25.554473655739, mid: 28.33 },
    'ביומד': { ta125: 5.15, ta90: 0.25, fund_eq: 5.876216968011, fund_other: 0.649139889646, mid: 1.84 },
    'מסחר ושרותים': { ta125: 6.37, ta90: 16.63, fund_eq: 8.484005563282, fund_other: 21.48653034729, mid: 13.9 },
    'תעשייה': { ta125: 4.45, ta90: 7.8, fund_eq: 2.50347705146, fund_other: 23.044466082441, mid: 4.21 },
    'אנרגיה וחיפושי נפט וגז': { ta125: 8.22, ta90: 11.53, fund_eq: 7.093184979138, fund_other: 0, mid: 11.87 },
    'השקעה ואחזקות': { ta125: 1.52, ta90: 6.92, fund_eq: 1.402410755679, fund_other: 9.488261386996, mid: 5.79 },
    'ביטחונית': { ta125: 7, ta90: 1.53, fund_eq: 2, fund_other: 3, mid: 0 },
  },
  foreign_sectors: {
    'Information Technology': { SP: 35.62, NDX: 54.42, STOXX: 7.8, ROW: 28, GLOBAL: 13.83 / 28 * 100, RUSSELL: 16.46 },
    'Health Care': { SP: 8.86, NDX: 4.22, STOXX: 12.9, ROW: 11.1, GLOBAL: 0, RUSSELL: 16.18 },
    Financials: { SP: 13.2, NDX: 0.34, STOXX: 23.49, ROW: 16.2, GLOBAL: 0, RUSSELL: 17.03 },
    'Consumer Discretionary': { SP: 10.67, NDX: 13.31, STOXX: 7.64, ROW: 10.3, GLOBAL: 6 / 0.28, RUSSELL: 9.68 },
    'Communication Services': { SP: 10.48, NDX: 16.53, STOXX: 3.84, ROW: 8.6, GLOBAL: 2.35 / 0.28, RUSSELL: 2.61 },
    Industrials: { SP: 7.52, NDX: 3.35, STOXX: 20.29, ROW: 11, GLOBAL: 0, RUSSELL: 15.98 },
    'Consumer Staples': { SP: 4.91, NDX: 4.59, STOXX: 8.82, ROW: 5.2, GLOBAL: 2.61 / 0.28, RUSSELL: 2.88 },
    Energy: { SP: 2.89, NDX: 0.48, STOXX: 4.48, ROW: 3.1, GLOBAL: 1.9 / 0.28, RUSSELL: 4.68 },
    Utilities: { SP: 2.35, NDX: 1.37, STOXX: 4.03, ROW: 1.6, GLOBAL: 0, RUSSELL: 3.25 },
    'Real Estate': { SP: 1.94, NDX: 0.19, STOXX: 1.33, ROW: 1.8, GLOBAL: 0, RUSSELL: 6.75 },
    Materials: { SP: 1.58, NDX: 1.19, STOXX: 5.38, ROW: 3.1, GLOBAL: 0, RUSSELL: 4.5 },
    שבבים: { SP: 11, NDX: 22, STOXX: 0, ROW: 0, GLOBAL: 0, RUSSELL: 0 },
  },
  // Share of Israeli income-producing real estate inside bond indices / funds (matched by name)
  re_benchmark: 47.29,
  re_patterns: [ // same column order as the Excel table
    { label: 'תל בונד 60', pattern: 'תלבונד 60|תל בונד 60|תל-בונד 60', share: 47.29 },
    { label: 'תל בונד שקלי', pattern: 'תלבונד שקלי|תל בונד שקלי|תל-בונד שקלי', share: 32.11 },
    { label: 'אג"ח ללא מניות', pattern: 'ללא מניות', share: 28 },
    { label: 'אג"ח חברות מדורג', pattern: 'חברות מדורג', share: 45 },
    { label: 'אג"ח חברות', pattern: 'אג"ח חברות(?! מדורג)', share: 53 },
    { label: 'תשואות', pattern: 'תשואות|תשו ', share: 84.2 },
    { label: 'תיק קונצרני', pattern: 'תיק קונצרני', share: 39.79 },
  ],
  re_industry: 'נדלן מניב בישראל',
}

export const DEFAULT_SETTINGS = {
  contract_fee: 0.65, vat: 17, inflation: 2.8, fund_cap: 20, rev_share_bond: 78, rev_share_equity: 65,
  bands: { duration: [3.29, 3.81], linked: [45, 50], shekel: [50, 55], foreign_eq: [60, 65] },
}

export function newConfig(template = 'global') {
  return {
    template,
    settings: { ...DEFAULT_SETTINGS, bands: { ...DEFAULT_SETTINGS.bands }, fund_cap: TEMPLATES[template]?.fund_cap ?? 20 },
    refs: structuredClone(DEFAULT_REFS),
    rows: [],
  }
}

/** Fill missing keys after loading an older/partial config. */
export function hydrate(config) {
  const base = newConfig(config?.template || 'global')
  return {
    ...base, ...config,
    settings: { ...base.settings, ...(config?.settings || {}), bands: { ...base.settings.bands, ...(config?.settings?.bands || {}) } },
    refs: {
      ...base.refs, ...(config?.refs || {}),
      re_patterns: (config?.refs?.re_patterns || base.refs.re_patterns).map((p) => ({ ...p, label: p.label || p.pattern.split('|')[0] })),
    },
    rows: (config?.rows || []).map((r) => ({ ...r, weight: Number(r.weight) || 0 })),
  }
}

// --------------------------------------------------------------------------- //
//  Helpers
// --------------------------------------------------------------------------- //
const n = (v) => (v == null || v === '' || Number.isNaN(Number(v)) ? null : Number(v))
const sum = (xs) => xs.reduce((s, x) => s + (Number(x) || 0), 0)
const lt = (d) => d?.lookthrough || {}
export const eqShare = (d) => (lt(d).eq_il || 0) + (lt(d).eq_foreign || 0)

/** Which sleeve a row belongs to. Funds: equity if the fund is mostly equities (overridable per row). */
export function sleeveOf(row, d) {
  const sec = SECTIONS.find((s) => s.key === row.section)
  if (sec?.sleeve) return sec.sleeve
  if (row.sleeve) return row.sleeve
  return eqShare(d) >= 0.5 ? 'equity' : 'bond'
}

/** Suggest a section for a newly added security from its data. */
export function suggestSection(d, template) {
  if (!d) return template === 'israel' ? 'eq_il' : 'eq_il'
  const L = lt(d)
  if (d.kind === 'equity') return d.country === 'ישראל' || d.market === 'IL' || template === 'israel' ? 'eq_il' : 'eq_foreign'
  if (d.kind === 'bond') {
    const gov = (d.asset_class || '').includes('ממשלתי')
    const k = { cpi: 'cpi', usd: 'usd', float: 'float', nominal: 'nominal' }[d.linkage] || 'nominal'
    return `${gov ? 'gov' : 'corp'}_${k}`
  }
  // index trackers (ETF / tracking fund): dominant section; active funds -> funds section
  const tracker = d.kind === 'etf' || /מחקה|KTF|MTF|TTF|סל/.test(d.name || '')
  if (d.kind === 'fund' && !tracker) return 'funds'
  const entries = Object.entries(L).filter(([k]) => k !== 'cash').sort((a, b) => b[1] - a[1])
  if (entries.length && entries[0][1] >= 0.6) {
    const top = entries[0][0]
    if (top === 'eq_foreign' && template === 'israel') return 'funds'
    return top
  }
  return 'funds'
}

/** Real-estate share of a bond holding and which Excel column (index product) it belongs to. */
function reMatch(row, d, refs) {
  const text = `${d?.name || ''} ${row.name || ''}`
  const pats = refs.re_patterns || []
  for (let i = 0; i < pats.length; i += 1) {
    try { if (new RegExp(pats[i].pattern).test(text)) return { share: n(d?.re_share) ?? pats[i].share, col: i } } catch { /* bad pattern */ }
  }
  return { share: n(d?.re_share) ?? 0, col: null }
}

/** Foreign-equity column (S&P, NASDAQ…) or a GICS sector for a row/fund. */
function exposureOf(row, d) {
  return row.exposure || d?.exposure || null
}

const inBand = (v, band) => (band ? v >= band[0] - 1e-9 && v <= band[1] + 1e-9 : true)

// --------------------------------------------------------------------------- //
//  The sheet
// --------------------------------------------------------------------------- //
export function compute(config, equityTarget, data = {}) {
  const cfg = hydrate(config)
  const s = cfg.settings
  const eq = Math.min(100, Math.max(0, Number(equityTarget) || 0)) / 100
  const feeVat = s.contract_fee * (1 + s.vat / 100) // T3
  const sections = sectionsFor(cfg.template)

  // ---- rows: E, F and per-security data
  const rows = cfg.rows.map((r, i) => {
    const d = data[r.id] || {}
    const sleeve = sleeveOf(r, d)
    const E = Number(r.weight) || 0
    const F = E * (sleeve === 'equity' ? eq : 1 - eq)
    const sec = SECTIONS.find((x) => x.key === r.section)
    const isFund = r.section === 'funds'
    const O = isFund ? n(d.fee) : feeVat
    return {
      ...r, i, d, sleeve, E, F, sec,
      name: r.name || d.name || r.id,
      G: n(r.yield ?? d.yield), H: n(d.mtd), I: n(d.ytd), J: n(r.spread ?? d.spread),
      K: sec?.cpi ? s.inflation : null,
      M: n(r.duration ?? d.duration),
      O, P: O == null ? null : (O * F) / 100,
      Q: r.maalot ?? d.maalot ?? null, R: r.midroog ?? d.midroog ?? null,
      bucket: n(r.bucket ?? d.rating_bucket),
      sector: r.sector || d.sector || null,
      country: r.country || d.country || (r.section === 'eq_il' ? 'ישראל' : null),
      exposure: exposureOf(r, d),
      hedged: r.hedged ?? d.hedged ?? false,
    }
  })

  // ---- fund look-through contributions ("תרומת קרנות")
  const funds = rows.filter((r) => r.section === 'funds')
  const contrib = {}
  for (const sec of sections) {
    if (sec.key === 'funds') continue
    contrib[sec.key] = sum(funds.map((f) => f.F * (lt(f.d)[sec.key] || 0)))
  }

  // ---- totals before yields (needed for the denominators)
  const secTotal = {}
  for (const sec of sections) {
    const own = rows.filter((r) => r.section === sec.key)
    secTotal[sec.key] = { E: sum(own.map((r) => r.E)), F: sum(own.map((r) => r.F)) + (contrib[sec.key] || 0), own: sum(own.map((r) => r.F)), contrib: contrib[sec.key] || 0, count: own.length }
  }
  const T = (k) => secTotal[k]?.F || 0
  const eqIL = T('eq_il')
  const eqForeign = T('eq_foreign')
  const equity = eqIL + eqForeign // F31 (incl. fund look-through)
  const directF = sum(rows.map((r) => r.F))
  const cash = 100 - directF // U8
  const bonds = 100 - equity - cash // U7
  const gov = T('gov_cpi') + T('gov_usd') + T('gov_nominal') + T('gov_float')
  const corp = T('corp_usd') + T('corp_cpi') + T('corp_nominal') + T('corp_float') + T('corp_hedged')
  const fundsF = sum(funds.map((f) => f.F))

  // ---- per-row yield / duration contributions
  const nonEqDenom = 100 - equity
  for (const r of rows) {
    if (r.sec?.group === 'equity') { r.L = null; r.N = null; continue }
    r.L = r.G == null && r.K == null ? null : bonds > 0 ? ((r.K || 0) + (r.G || 0)) * r.F / bonds : null
    r.N = r.M == null || nonEqDenom <= 0 ? null : (r.M * r.F) / nonEqDenom
  }
  for (const sec of sections) {
    const own = rows.filter((r) => r.section === sec.key)
    const fw = sum(own.map((r) => r.F))
    const wavg = (key) => {
      const xs = own.filter((r) => r[key] != null)
      const w = sum(xs.map((r) => r.F))
      return w > 0 ? sum(xs.map((r) => r[key] * r.F)) / w : null
    }
    Object.assign(secTotal[sec.key], {
      G: wavg('G'), M: wavg('M'), H: fw > 0 ? sum(own.map((r) => (r.H || 0) * r.F)) / 100 : null,
      I: fw > 0 ? sum(own.map((r) => (r.I || 0) * r.F)) / 100 : null,
      L: sum(own.map((r) => r.L || 0)), N: sum(own.map((r) => r.N || 0)), P: sum(own.map((r) => r.P || 0)),
    })
  }

  // ---- summary column (U5 … U21)
  const cashFee = (feeVat * Math.max(0, cash)) / 100
  const fundFees = sum(funds.map((f) => f.P || 0))
  const directFees = sum(rows.filter((r) => r.section !== 'funds').map((r) => r.P || 0))
  const fundFeesEq = sum(funds.filter((f) => f.sleeve === 'equity').map((f) => f.P || 0))
  const revenue = directFees + cashFee + (s.rev_share_bond / 100) * (fundFees - fundFeesEq) + (s.rev_share_equity / 100) * fundFeesEq
  const linked = T('gov_cpi') + T('corp_cpi')
  const shekel = T('gov_nominal') + T('gov_float') + T('corp_nominal') + T('corp_float') + T('corp_hedged')
  const hedgedEq = sum(rows.filter((r) => r.section === 'eq_foreign' && r.hedged).map((r) => r.F))
    + sum(funds.filter((f) => f.hedged).map((f) => f.F * (lt(f.d).eq_foreign || 0)))
  const fx = eqForeign + T('gov_usd') + T('corp_usd') - hedgedEq
  const usDirect = sum(rows.filter((r) => r.section !== 'funds').map((r) => {
    if (r.country === 'ארה״ב') return r.F
    if (r.d.us_share != null && r.section === 'eq_foreign') return (r.F * r.d.us_share) / 100
    return 0
  }))
  const usFunds = sum(funds.map((f) => (f.F * (n(f.d.us_share) || 0)) / 100))
  const duration = sum(rows.map((r) => r.N || 0)) // U5
  const missingYield = rows.filter((r) => r.sec?.group !== 'equity' && r.sleeve === 'bond' && r.F > 0 && r.G == null).length
  const missingDuration = rows.filter((r) => r.sec?.group !== 'equity' && r.sleeve === 'bond' && r.F > 0 && r.M == null).length
  const irr = sum(rows.map((r) => r.L || 0)) // U6

  const summary = {
    duration, irr, bonds, cash, corp, gov, funds: fundsF, equity, eqIL, eqForeign,
    linked, shekel, linkedShare: linked + shekel > 0 ? (linked / (linked + shekel)) * 100 : null,
    shekelShare: linked + shekel > 0 ? (shekel / (linked + shekel)) * 100 : null,
    fx, us: usDirect + usFunds, usDirect, usFunds,
    equityPosition: eq > 0 ? (equity / (eq * 100)) * 100 : null,
    foreignEqShare: equity > 0 ? (eqForeign / equity) * 100 : null,
    ilEqShare: equity > 0 ? (eqIL / equity) * 100 : null,
    fundFees, totalFees: directFees + fundFees + cashFee, revenue, revenueExVat: revenue / (1 + s.vat / 100),
    feeVat, missingYield, missingDuration,
  }

  // ---- checks (the Excel's red conditional formats + sanity)
  const b = s.bands
  const checks = []
  const add = (ok, level, text) => !ok && checks.push({ level, text })
  const eqSleeveE = sum(rows.filter((r) => r.sleeve === 'equity').map((r) => r.E))
  const bondSleeveE = sum(rows.filter((r) => r.sleeve === 'bond').map((r) => r.E))
  add(cash >= -0.005, 'error', `העו״ש שלילי (${cash.toFixed(2)}%) – סך המשקלים עולה על 100%`)
  add(eq === 0 || Math.abs(eqSleeveE - 100) < 0.01, 'warn', `רכיב המניות מסתכם ל-${eqSleeveE.toFixed(2)}% (אחוז ראשי) ולא ל-100%`)
  add(bondSleeveE <= 100.005, 'error', `רכיב האג״ח מסתכם ל-${bondSleeveE.toFixed(2)}% – מעל 100%`)
  add(bonds <= 0.01 || inBand(duration, b.duration), 'warn', `מח״מ ${duration.toFixed(2)} מחוץ לטווח ${b.duration[0]}–${b.duration[1]}`)
  if (linked + shekel > 0) {
    add(inBand(summary.linkedShare, b.linked), 'warn', `שיעור הצמוד ${summary.linkedShare.toFixed(1)}% מחוץ לטווח ${b.linked[0]}%–${b.linked[1]}%`)
    add(inBand(summary.shekelShare, b.shekel), 'warn', `שיעור השקלי ${summary.shekelShare.toFixed(1)}% מחוץ לטווח ${b.shekel[0]}%–${b.shekel[1]}%`)
  }
  if (cfg.template === 'global' && equity > 0) {
    add(inBand(summary.foreignEqShare, b.foreign_eq), 'warn', `חשיפה מנייתית לחו״ל ${summary.foreignEqShare.toFixed(1)}% מסך המניות – מחוץ לטווח ${b.foreign_eq[0]}%–${b.foreign_eq[1]}%`)
  }
  add(fundsF <= s.fund_cap + 0.005, 'warn', `סך הקרנות ${fundsF.toFixed(2)}% – מעל מגבלת ${s.fund_cap}% (מוגבל קרנות)`)
  const seen = new Map()
  for (const r of rows) {
    if (seen.has(r.id)) checks.push({ level: 'error', text: `הנייר ${r.id} מופיע פעמיים`, ids: [r.id] })
    seen.set(r.id, true)
  }
  const dupIds = new Set(rows.filter((r, i) => rows.findIndex((x) => x.id === r.id) !== i).map((r) => r.id))

  // ---- corporate rating buckets (U23:V26) – corporate rows and funds
  const rated = rows.filter((r) => r.sec?.rated)
  const ratingRows = RATING_BUCKETS.map((rb) => ({ ...rb, F: sum(rated.filter((r) => r.bucket === rb.key).map((r) => r.F)) }))
  const ratingTotal = sum(ratingRows.map((r) => r.F))
  ratingRows.forEach((r) => { r.share = ratingTotal > 0 ? (r.F / ratingTotal) * 100 : 0 })
  const unrated = sum(rated.filter((r) => !r.bucket).map((r) => r.F))

  // ---- foreign equity exposure by index column (V52:AA52) + direct sectors (AB)
  const fexp = Object.fromEntries(FOREIGN_COLUMNS.map((c) => [c.key, 0]))
  const directSector = {}
  const geo = { IL: eqIL, US: 0, EUROPE: 0, EM: 0 }
  const addForeign = (amount, exposure, regions, country) => {
    if (amount <= 0) return
    const col = FOREIGN_COLUMNS.find((c) => c.exposure === exposure)
    if (col) { fexp[col.key] += amount; geo[col.region] += amount; return }
    if (GICS.includes(exposure) || exposure === 'שבבים') {
      const sector = exposure === 'שבבים' ? 'Information Technology' : exposure
      directSector[sector] = (directSector[sector] || 0) + amount
      if (exposure === 'שבבים') directSector['שבבים'] = (directSector['שבבים'] || 0) + amount
      const g = country === 'אירופה' ? 'EUROPE' : country === 'שווקים מתעוררים' ? 'EM' : 'US'
      geo[g] += amount
      return
    }
    // unknown: split by the fund's regions (US -> S&P, Europe -> STOXX, rest -> rest of world)
    const R = regions && Object.keys(regions).length ? regions : { US: 1 }
    const tot = sum(Object.values(R)) || 1
    fexp.SP += (amount * (R.US || 0)) / tot; geo.US += (amount * (R.US || 0)) / tot
    fexp.STOXX += (amount * (R.EUROPE || 0)) / tot; geo.EUROPE += (amount * (R.EUROPE || 0)) / tot
    fexp.ROW += (amount * (R.ROW || 0)) / tot; geo.EM += (amount * (R.ROW || 0)) / tot
  }
  for (const r of rows.filter((x) => x.section === 'eq_foreign')) addForeign(r.F, r.exposure, r.d.regions, r.country)
  for (const f of funds) addForeign(f.F * (lt(f.d).eq_foreign || 0), f.exposure, f.d.regions, f.country)
  // Equities that sit in the bond sections through funds' look-through are already in eqIL/eqForeign via contributions
  const foreignSectors = [...GICS, 'שבבים'].map((sector) => {
    const w = cfg.refs.foreign_sectors[sector] || {}
    const total = sum(FOREIGN_COLUMNS.map((c) => ((w[c.key] || 0) / 100) * fexp[c.key])) + (directSector[sector] || 0)
    return { sector, label: GICS_HE[sector] || sector, weights: w, direct: directSector[sector] || 0, total, memo: sector === 'שבבים' }
  })
  const fsTotal = sum(foreignSectors.filter((x) => !x.memo).map((x) => x.total))
  foreignSectors.forEach((x) => { x.share = fsTotal > 0 ? (x.total / fsTotal) * 100 : 0 })

  // ---- Israeli equity sectors (T35:AB46)
  const ilexp = { ta125: 0, ta90: 0, fund_eq: 0, fund_other: 0, mid: 0 }
  const ilCols = IL_COLUMNS.filter((c) => !c.israelOnly || cfg.template === 'israel')
  const ilDirect = {}
  for (const r of rows.filter((x) => x.section === 'eq_il')) {
    const idx = IL_INDEX_LABELS[r.sector]
    if (idx) ilexp[idx] += r.F
    else if (r.sector) ilDirect[r.sector] = (ilDirect[r.sector] || 0) + r.F
    else if (r.d.kind === 'etf' || r.d.kind === 'fund') ilexp.ta125 += r.F // an Israeli index tracker without a label
    else ilDirect['לא מסווג'] = (ilDirect['לא מסווג'] || 0) + r.F
  }
  for (const f of funds) {
    const amount = f.F * (lt(f.d).eq_il || 0)
    if (amount > 0) ilexp[f.exposure === 'יתר' ? 'fund_other' : f.exposure === 'MID' ? 'mid' : 'fund_eq'] += amount
  }
  const ilSectors = [...IL_SECTORS, ...IL_MEMO_SECTORS].map((sector) => {
    const w = cfg.refs.il_sectors[sector] || {}
    const total = sum(IL_COLUMNS.map((c) => ((w[c.key] || 0) / 100) * ilexp[c.key])) + (ilDirect[sector] || 0)
    return { sector, label: sector, weights: w, direct: ilDirect[sector] || 0, total, memo: IL_MEMO_SECTORS.includes(sector) }
  })
  const ilTotal = sum(ilSectors.filter((x) => !x.memo).map((x) => x.total))
  ilSectors.forEach((x) => {
    x.share = ilTotal > 0 ? (x.total / ilTotal) * 100 : 0
    x.gap = x.share - (x.weights.ta125 || 0) // פער מהמדד (vs. TA-125)
  })

  // ---- real-estate exposure inside the corporate bonds (T67:AE69)
  const reRows = rows.filter((r) => r.sleeve === 'bond' && r.sec?.group !== 'equity').map((r) => {
    const direct = r.sec?.group === 'corp' && (r.sector === cfg.refs.re_industry || r.industry === cfg.refs.re_industry)
    const m = direct ? { share: 100, col: null } : reMatch(r, r.d, cfg.refs)
    return { id: r.id, name: r.name, F: r.F, share: m.share, col: m.col, direct, contrib: (r.F * m.share) / 100 }
  }).filter((x) => x.share > 0 && x.F > 0)
  const reTotal = sum(reRows.map((x) => x.contrib))
  const reColumns = cfg.refs.re_patterns.map((p, i) => ({ label: p.label, share: p.share, F: sum(reRows.filter((x) => x.col === i).map((x) => x.F)) }))
  const reDirect = sum(reRows.filter((x) => x.col == null).map((x) => x.contrib))
  const realEstate = { rows: reRows, columns: reColumns, direct: reDirect, total: reTotal, share: corp > 0 ? (reTotal / corp) * 100 : null, benchmark: cfg.refs.re_benchmark }
  if (realEstate.share != null) realEstate.gap = realEstate.share - realEstate.benchmark

  const geoTotal = sum(Object.values(geo))
  const geography = GEO.map(([k, label]) => ({ key: k, label, F: geo[k], share: geoTotal > 0 ? (geo[k] / geoTotal) * 100 : 0 }))

  // Flat holdings for the rest of the app (X-Ray, stress tests, PDFs, client comparison)
  const holdings = []
  for (const r of rows) {
    const h = holdings.find((x) => x.id === r.id)
    if (h) h.weight += r.F
    else holdings.push({ id: r.id, name: r.name, weight: r.F, fee: null })
  }
  holdings.forEach((h) => { h.weight = Math.round(h.weight * 10000) / 10000 })

  return {
    config: cfg, rows, sections, secTotal, contrib, summary, checks, dupIds,
    ratingRows, ratingTotal, unrated, fexp, geography, foreignSectors, ilSectors, ilexp, ilCols, realEstate, holdings, fsTotal, ilTotal,
    sleeves: { equity: eqSleeveE, bond: bondSleeveE },
  }
}
