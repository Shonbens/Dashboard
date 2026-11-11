// Client-side derivations so AUM / target edits recalculate instantly without a round trip.
export const MARKET_LABEL = { IL: 'ישראל', US: 'ארה״ב', OTHER: 'אחר' }
export const MARKET_FLAG = { IL: '🇮🇱', US: '🇺🇸', OTHER: '🌐' }

export function derive(holdings, aum, driftThreshold = 1) {
  const rows = holdings.map((h) => {
    const value = (aum * (h.weight || 0)) / 100
    const hasTarget = h.target_weight != null && h.target_weight !== ''
    const target = hasTarget ? Number(h.target_weight) : null
    const trade = hasTarget ? (aum * (target - (h.weight || 0))) / 100 : null
    const drift = hasTarget ? (h.weight || 0) - target : null
    return {
      ...h,
      value_ils: value,
      units: h.price_ils > 0 ? Math.floor(value / h.price_ils) : null,
      target_value_ils: hasTarget ? (aum * target) / 100 : null,
      drift,
      trade_value_ils: trade,
      trade_units: trade != null && h.price_ils > 0 ? Math.trunc(trade / h.price_ils) : null,
      breach: drift != null && Math.abs(drift) >= driftThreshold,
    }
  })

  const sumBy = (key) =>
    rows.reduce((acc, r) => {
      acc[r[key]] = (acc[r[key]] || 0) + (r.weight || 0)
      return acc
    }, {})

  const totalWeight = rows.reduce((s, r) => s + (r.weight || 0), 0)
  const targets = rows.filter((r) => r.target_weight != null && r.target_weight !== '')
  const buys = rows.filter((r) => (r.trade_value_ils || 0) > 0).reduce((s, r) => s + r.trade_value_ils, 0)
  const sells = rows.filter((r) => (r.trade_value_ils || 0) < 0).reduce((s, r) => s - r.trade_value_ils, 0)
  const byMarket = sumBy('market')
  const dayChange = rows.reduce((s, r) => s + ((r.change_pct || 0) * (r.weight || 0)) / 100, 0)

  return {
    rows,
    totalWeight,
    cashWeight: 100 - totalWeight,
    ilExposure: byMarket.IL || 0,
    usExposure: byMarket.US || 0,
    otherExposure: byMarket.OTHER || 0,
    byMarket,
    byAssetClass: sumBy('asset_class'),
    byCurrency: sumBy('currency'),
    hasTargets: targets.length > 0,
    targetTotal: targets.reduce((s, r) => s + Number(r.target_weight), 0),
    buys,
    sells,
    turnoverPct: aum > 0 ? ((buys + sells) / 2 / aum) * 100 : 0,
    breaches: rows.filter((r) => r.breach).length,
    weightedDayChange: dayChange,
    unpriced: rows.filter((r) => !r.priced).length,
  }
}

export function toCSV(rows, aum) {
  const head = ['מזהה', 'טיקר', 'שם', 'שוק', 'סוג נכס', 'מטבע', 'מחיר', 'מחיר ₪', 'משקל %', 'שווי ₪', 'יחידות',
    'משקל יעד %', 'סטייה %', 'עסקה ₪', 'יחידות לעסקה', 'מקור מחיר']
  const esc = (v) => {
    if (v == null) return ''
    const s = String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = rows.map((r) => [
    r.input_id, r.ticker, r.name, MARKET_LABEL[r.market], r.asset_class, r.currency, r.price, r.price_ils?.toFixed(4),
    r.weight?.toFixed(4), r.value_ils?.toFixed(2), r.units, r.target_weight ?? '', r.drift?.toFixed(4) ?? '',
    r.trade_value_ils?.toFixed(2) ?? '', r.trade_units ?? '', r.source,
  ].map(esc).join(','))
  return '﻿' + [`היקף נכסים,${aum}`, head.join(','), ...lines].join('\n')
}

export function download(filename, content, type = 'text/csv;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
