// Run the website's allocation engine on a test case and dump the results.
import { readFileSync, writeFileSync } from 'node:fs'
import { compute } from '../../frontend/src/lib/allocation.js'

const c = JSON.parse(readFileSync(process.argv[2], 'utf8'))
const r = compute(c.config, c.equity, c.data)
const out = {
  summary: r.summary,
  secTotal: Object.fromEntries(Object.entries(r.secTotal).map(([k, v]) => [k, { F: v.F, L: v.L, N: v.N, P: v.P }])),
  rating: r.ratingRows.map((x) => ({ key: x.key, F: x.F, share: x.share })),
  ilSectors: r.ilSectors.map((x) => ({ sector: x.sector, total: x.total, share: x.share, gap: x.gap })),
  ilexp: r.ilexp,
  foreignSectors: r.foreignSectors.map((x) => ({ sector: x.sector, total: x.total, share: x.share })),
  fexp: r.fexp,
  geography: r.geography,
  rows: r.rows.map((x) => ({ id: x.id, F: x.F, L: x.L, N: x.N, P: x.P })),
}
writeFileSync(process.argv[3], JSON.stringify(out))
console.log('ok')
