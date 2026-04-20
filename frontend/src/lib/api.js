// API client — injects X-API-Key on every request.
// BASE always resolves to the origin (the FastAPI server), not /ui/.

export const BASE = typeof window !== 'undefined' ? window.location.origin : ''

let _apiKey = ''
export const setApiKey = (k) => { _apiKey = k }
export const getApiKey = () => _apiKey

export async function api(path, opts = {}) {
  const res = await fetch(BASE + path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': _apiKey,
      ...(opts.headers || {}),
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

// Returns the raw Response (for streaming)
export async function apiFetch(path, opts = {}) {
  const res = await fetch(BASE + path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': _apiKey,
      ...(opts.headers || {}),
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res
}

// Parse an SSE stream; calls onChunk(parsedObject) for each data event
export async function streamSSE(res, onChunk, shouldStop = () => false) {
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  while (true) {
    if (shouldStop()) break
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop()
    for (const line of lines) {
      if (!line.startsWith('data: ') || line === 'data: [DONE]') continue
      try { onChunk(JSON.parse(line.slice(6))) } catch (_) {}
    }
  }
  try { reader.releaseLock() } catch (_) {}
}

// Convenience wrappers
export const getHealth    = ()        => fetch(BASE + '/api/health').then(r => r.json())
export const getNodes     = ()        => api('/api/nodes')
export const getModels    = ()        => api('/v1/models')
export const getModelList = ()        => api('/api/models')
export const getJobs      = ()        => api('/api/models/jobs')
export const getMetrics   = (w='24h') => api(`/api/metrics?window=${w}`)
export const getKeys      = ()        => api('/api/auth/keys')
export const getAudit     = (n=50)    => api(`/api/auth/audit?limit=${n}`)
export const getLog       = (params)  => {
  const q = new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) => v != null && v !== ''))
  ).toString()
  return api('/api/metrics/requests?' + q)
}

export const discoverNodes = () => api('/api/nodes/scan')
export const quickDiscoverNodes = () => api('/api/nodes/scan/quick')
