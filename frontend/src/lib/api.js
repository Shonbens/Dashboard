async function handle(res) {
  if (!res.ok) {
    let msg = `שגיאת שרת (${res.status})`
    try {
      const body = await res.json()
      if (body?.detail) msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* non-JSON error */ }
    throw new Error(msg)
  }
  return res.json()
}

async function safeFetch(url, opts) {
  try {
    return await fetch(url, opts)
  } catch {
    throw new Error('לא ניתן להתחבר לשרת. ודאו שה-backend רץ על localhost:8000')
  }
}

export async function uploadPortfolio(file, aum) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('aum', String(aum))
  return handle(await safeFetch('/api/analyze-portfolio', { method: 'POST', body: fd }))
}

export async function analyzeHoldings(holdings, aum, refresh = false) {
  const body = {
    aum,
    refresh,
    holdings: holdings.map((h) => ({
      id: h.input_id ?? h.id,
      name: h.file_name ?? h.name ?? null,
      weight: h.weight ?? 0,
      target_weight: h.target_weight ?? null,
      fee: h.fee ?? null,
    })),
  }
  return handle(await safeFetch('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}

export async function searchSecurities(q, signal) {
  return handle(await safeFetch(`/api/search?q=${encodeURIComponent(q)}`, { signal }))
}

export async function getHealth() {
  return handle(await safeFetch('/api/health'))
}

export async function getQuote(id) {
  return handle(await safeFetch(`/api/quote/${encodeURIComponent(id)}`))
}

export async function getSampleFile() {
  const res = await safeFetch('/api/template')
  if (!res.ok) throw new Error('טעינת קובץ הדוגמה נכשלה')
  const blob = await res.blob()
  return new File([blob], 'sample_portfolio.csv', { type: 'text/csv' })
}

const riskPayload = (rows, aum) => ({
  aum,
  holdings: rows.map((r) => ({
    input_id: r.input_id, ticker: r.ticker, name: r.name, name_en: r.name_en || null, weight: r.weight || 0,
    market: r.market, asset_class: r.asset_class, currency: r.currency, sector: r.sector || null,
    fee: r.fee ?? null,
  })),
})

export async function fundXray(rows, aum, signal) {
  return handle(await safeFetch('/api/fund-xray', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
    body: JSON.stringify(riskPayload(rows, aum)),
  }))
}

export async function getStressScenarios() {
  return handle(await safeFetch('/api/stress-scenarios'))
}

export async function stressTest(rows, aum, shocks, useBeta, signal) {
  return handle(await safeFetch('/api/stress-test', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, signal,
    body: JSON.stringify({ ...riskPayload(rows, aum), shocks, use_beta: useBeta, compare_presets: true }),
  }))
}

// ---- Base models -------------------------------------------------------------
const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const listModels = async () => handle(await safeFetch('/api/models'))
export const modelsOverview = async (aum, signal) => handle(await safeFetch(`/api/models/overview?aum=${aum}`, { signal }))
export const getModel = async (id) => handle(await safeFetch(`/api/models/${id}`))
export const getModelVersion = async (id, v) => handle(await safeFetch(`/api/models/${id}/versions/${v}`))
export const createModel = async (body) => handle(await safeFetch('/api/models', json('POST', body)))
export const updateModel = async (id, body) => handle(await safeFetch(`/api/models/${id}`, json('PUT', body)))
export const duplicateModel = async (id, name, user) => handle(await safeFetch(`/api/models/${id}/duplicate`, json('POST', { name, user })))
export const archiveModel = async (id, user) => handle(await safeFetch(`/api/models/${id}?user=${encodeURIComponent(user || '')}`, { method: 'DELETE' }))
export const commitImport = async (body) => handle(await safeFetch('/api/models/import/commit', json('POST', body)))

export async function previewImport(file) {
  const fd = new FormData()
  fd.append('file', file)
  return handle(await safeFetch('/api/models/import', { method: 'POST', body: fd }))
}

export const getUser = () => { try { return localStorage.getItem('ibi_user') || '' } catch { return '' } }
export const setUser = (u) => { try { localStorage.setItem('ibi_user', u) } catch { /* storage unavailable */ } }

/** Plain-language client report (PDF blob). The client name is only placed inside the PDF – nothing is stored. */
export async function clientReportPdf(rows, aum, clientName, advisorName) {
  const res = await safeFetch('/api/portfolio/client-report.pdf', json('POST', {
    aum,
    client_name: clientName || '',
    advisor_name: advisorName || '',
    holdings: rows.map((r) => ({ id: r.input_id, name: r.file_name || r.name, weight: Number(r.weight) || 0, fee: r.fee ?? null })),
  }))
  if (!res.ok) await handle(res)
  return res.blob()
}

// ---- Allocation sheet: security reference data --------------------------------
export const secdataLookup = async (ids, refresh = false, signal) =>
  handle(await safeFetch('/api/secdata/lookup', { ...json('POST', { ids, refresh }), signal }))
export async function allocationXlsx(body) {
  const res = await safeFetch('/api/models/allocation.xlsx', json('POST', body))
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'הייצוא נכשל')
  return res.blob()
}
export const secdataUpdate = async (id, fields, user) =>
  handle(await safeFetch(`/api/secdata/${encodeURIComponent(id)}`, json('PUT', { fields, user })))
export async function secdataImport(file, user, commit) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('user', user || '')
  fd.append('commit', commit ? 'true' : 'false')
  return handle(await safeFetch('/api/secdata/import', { method: 'POST', body: fd }))
}
export const deleteModel = async (id, user) => handle(await safeFetch(`/api/models/${id}/permanent?user=${encodeURIComponent(user || '')}`, { method: 'DELETE' }))

// ---- Potential-client portfolio analysis ---------------------------------------
export async function prospectAnalyzeFile(file, aum) {
  const fd = new FormData()
  fd.append('file', file)
  if (aum) fd.append('aum', String(aum))
  return handle(await safeFetch('/api/prospect/analyze', { method: 'POST', body: fd }))
}
export const prospectAnalyze = async (holdings, aum) => handle(await safeFetch('/api/prospect/analyze-json', json('POST', { holdings, aum })))
export async function prospectPdf(body) {
  const res = await safeFetch('/api/prospect/report.pdf', json('POST', body))
  if (!res.ok) await handle(res)
  return res.blob()
}
export const prospectRules = async () => handle(await safeFetch('/api/prospect/rules'))
export const prospectRulesSave = async (rules, user) => handle(await safeFetch('/api/prospect/rules', json('PUT', { rules, user })))
export async function prospectRulesImport(file, user, commit) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('user', user || '')
  fd.append('commit', commit ? 'true' : 'false')
  return handle(await safeFetch('/api/prospect/rules/import', { method: 'POST', body: fd }))
}
