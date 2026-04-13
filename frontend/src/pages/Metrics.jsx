import { useState, useEffect } from 'react'
import { SectionTitle, Card, StatCard, Select, FormGroup, Table, Th, Td, Tr, HourlyChart, Spinner, Empty } from '../components/ui'
import { getMetrics } from '../lib/api'

export default function Metrics() {
  const [window, setWindow] = useState('24h')
  const [data, setData]     = useState(null)
  const [loading, setLoading] = useState(true)

  const load = async (w) => {
    setLoading(true)
    try { setData(await getMetrics(w)) }
    catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { load(window) }, [window])

  const ov  = data?.overview || {}
  const lat = ov.latency_ms || {}

  return (
    <div className="animate-fade-in">
      <div className="flex items-center gap-3 mb-4">
        <FormGroup label="Time window">
          <Select value={window} onChange={e => { setWindow(e.target.value); }} className="w-36">
            {['1h','6h','24h','7d','30d','all'].map(w => (
              <option key={w} value={w}>{w === 'all' ? 'All time' : `Last ${w}`}</option>
            ))}
          </Select>
        </FormGroup>
        {loading && <Spinner />}
      </div>

      {/* Latency cards */}
      <div className="grid grid-cols-4 gap-3 mb-1">
        <StatCard label="Avg latency"  value={lat.avg  != null ? lat.avg  + 'ms' : '—'} accent="text-teal" />
        <StatCard label="P50 latency"  value={lat.p50  != null ? lat.p50  + 'ms' : '—'} accent="text-sky" />
        <StatCard label="P95 latency"  value={lat.p95  != null ? lat.p95  + 'ms' : '—'} accent="text-amber" />
        <StatCard label="P99 latency"  value={lat.p99  != null ? lat.p99  + 'ms' : '—'} accent="text-crimson" />
      </div>

      <div className="grid grid-cols-2 gap-3 mt-1">
        {/* By model */}
        <div>
          <SectionTitle>By model</SectionTitle>
          <Table>
            <thead><tr><Th>Model</Th><Th>Req</Th><Th>Err</Th><Th>Avg ms</Th><Th>Tokens</Th></tr></thead>
            <tbody>
              {(data?.by_model || []).map(r => (
                <Tr key={r.model}>
                  <Td className="text-ink-0 font-medium">{r.model}</Td>
                  <Td>{r.requests}</Td>
                  <Td className={r.errors > 0 ? 'text-crimson' : 'text-ink-2'}>{r.errors}</Td>
                  <Td>{r.avg_latency_ms ?? '—'}</Td>
                  <Td className="text-ink-2">{fmtK(r.total_tokens)}</Td>
                </Tr>
              ))}
              {!data?.by_model?.length && <tr><td colSpan={5} className="px-3 py-4 text-center font-mono text-[10px] text-ink-2">No data</td></tr>}
            </tbody>
          </Table>
        </div>

        {/* By node */}
        <div>
          <SectionTitle>By node</SectionTitle>
          <Table>
            <thead><tr><Th>Node</Th><Th>Req</Th><Th>Err</Th><Th>Avg ms</Th><Th>P95 ms</Th></tr></thead>
            <tbody>
              {(data?.by_node || []).map(r => (
                <Tr key={r.node_id}>
                  <Td className="text-ink-0 font-medium">{r.node_id}</Td>
                  <Td>{r.requests}</Td>
                  <Td className={r.errors > 0 ? 'text-crimson' : 'text-ink-2'}>{r.errors}</Td>
                  <Td>{r.avg_latency_ms ?? '—'}</Td>
                  <Td className="text-amber">{r.p95_latency_ms ?? '—'}</Td>
                </Tr>
              ))}
              {!data?.by_node?.length && <tr><td colSpan={5} className="px-3 py-4 text-center font-mono text-[10px] text-ink-2">No data</td></tr>}
            </tbody>
          </Table>
        </div>
      </div>

      {/* By key */}
      <SectionTitle>By API key</SectionTitle>
      <Table>
        <thead><tr><Th>Key hint</Th><Th>Requests</Th><Th>Errors</Th><Th>Avg ms</Th><Th>Tokens</Th></tr></thead>
        <tbody>
          {(data?.by_key || []).map(r => (
            <Tr key={r.key_hint}>
              <Td className="text-ink-0 font-medium">{r.key_hint}…</Td>
              <Td>{r.requests}</Td>
              <Td className={r.errors > 0 ? 'text-crimson' : 'text-ink-2'}>{r.errors}</Td>
              <Td>{r.avg_latency_ms ?? '—'}</Td>
              <Td className="text-ink-2">{fmtK(r.total_tokens)}</Td>
            </Tr>
          ))}
          {!data?.by_key?.length && <tr><td colSpan={5} className="px-3 py-4 text-center font-mono text-[10px] text-ink-2">No data</td></tr>}
        </tbody>
      </Table>

      {/* Hourly chart */}
      <SectionTitle>Token throughput by hour</SectionTitle>
      <Card className="p-4">
        <HourlyChart data={data?.by_hour || []} height={60} />
      </Card>
    </div>
  )
}

function fmtK(n) {
  if (!n) return '0'
  if (n >= 1e6) return (n/1e6).toFixed(1)+'M'
  if (n >= 1e3) return (n/1e3).toFixed(1)+'K'
  return String(n)
}
