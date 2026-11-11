/**
 * Inputs for the "export to Excel with live formulas" workbook.
 * Only the inputs travel (weights, market data, classifications, fund look-through); the backend writes every
 * calculated cell as an Excel formula, so the managers can change the equity share or a weight and Excel recalculates.
 */
import { SECTIONS } from './allocation.js'

const LT_KEYS = ['eq_il', 'eq_foreign', 'gov_cpi', 'gov_usd', 'gov_nominal', 'gov_float', 'corp_usd', 'corp_cpi', 'corp_nominal',
  'corp_float', 'corp_hedged', 'cash']

export function exportPayload(res, meta = {}) {
  const cfg = res.config
  const s = cfg.settings
  const rows = res.rows.map((r) => {
    const lt = r.d?.lookthrough || {}
    const isFund = r.section === 'funds'
    const us = isFund
      ? Number(r.d?.us_share) || 0
      : r.country === 'ארה״ב' ? 100 : r.section === 'eq_foreign' && r.d?.us_share != null ? Number(r.d.us_share) : 0
    return {
      id: r.id, name: r.name, section: r.section, sleeve: r.sleeve, E: r.E,
      G: r.G, H: r.H, I: r.I, J: r.J, M: r.M, fee: isFund ? r.O : null, Q: r.Q, R: r.R,
      bucket: SECTIONS.find((x) => x.key === r.section)?.rated ? r.bucket ?? null : null,
      label: r.section === 'eq_il' ? r.sector : r.section === 'eq_foreign' ? r.exposure : (r.industry || r.row?.industry || null),
      hedged: !!r.hedged, us,
      lt: isFund ? Object.fromEntries(LT_KEYS.map((k) => [k, Number(lt[k]) || 0])) : null,
    }
  })
  return {
    name: meta.name || '', template: cfg.template, equity: Number(cfg.equity) || 0,
    settings: {
      contract_fee: s.contract_fee, vat: s.vat, inflation: s.inflation, fund_cap: s.fund_cap,
      rev_share_bond: s.rev_share_bond, rev_share_equity: s.rev_share_equity, bands: s.bands,
    },
    rows,
  }
}
