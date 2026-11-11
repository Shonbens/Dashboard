// Export check: export a saved allocation model to Excel (live formulas), then dump the website's own numbers
// for the same model at its equity share and at a second equity share (to test that the formulas recalculate).
//   node export_check.mjs <modelId> <altEquity> <outDir>
import { writeFileSync } from 'node:fs'
import { compute, hydrate } from '../../frontend/src/lib/allocation.js'
import { exportPayload } from '../../frontend/src/lib/allocationExport.js'

const [id, alt, out] = [process.argv[2], Number(process.argv[3]), process.argv[4]]
const API = 'http://localhost:8000'
const m = await (await fetch(`${API}/api/models/${id}`)).json()
const cfg = hydrate({ ...m.config, equity: m.config?.equity ?? m.equity_target })
const ids = [...new Set(cfg.rows.map((r) => r.id))]
const data = await (await fetch(`${API}/api/secdata/lookup`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }) })).json()
const res = compute(cfg, cfg.equity, data)
const body = exportPayload(res, { name: m.name })
const x = await fetch(`${API}/api/models/allocation.xlsx`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
if (!x.ok) throw new Error(await x.text())
writeFileSync(`${out}/export.xlsx`, Buffer.from(await x.arrayBuffer()))
const pick = (r) => ({ summary: r.summary, rating: r.ratingRows.map((b) => b.F),
  totals: Object.fromEntries(Object.entries(r.secTotal).map(([k, v]) => [k, { F: v.F, L: v.L, N: v.N, P: v.P, G: v.G, M: v.M }])) })
writeFileSync(`${out}/site.json`, JSON.stringify({ base: pick(res), altres: pick(compute(cfg, alt, data)), equity: cfg.equity, alt }))
console.log('exported', m.name, 'rows', body.rows.length)
