import { useState } from 'react'
import { Search, ChevronLeft, ChevronRight } from 'lucide-react'
import { SectionTitle, FormGroup, Input, Select, Btn, Table, Th, Td, Tr, Spinner } from '../components/ui'
import { getLog } from '../lib/api'

const LIMIT = 50

export default function RequestLog({ toast }) {
  const [window, setWindow]     = useState('1h')
  const [model, setModel]       = useState('')
  const [nodeId, setNodeId]     = useState('')
  const [errOnly, setErrOnly]   = useState(false)
  const [offset, setOffset]     = useState(0)
  const [data, setData]         = useState(null)
  const [loading, setLoading]   = useState(false)

  const search = async (off = 0) => {
    setLoading(true)
    try {
      const params = { window, limit: LIMIT, offset: off }
      if (model)  params.model   = model
      if (nodeId) params.node_id = nodeId
      if (errOnly) params.errors_only = 'true'
      setData(await getLog(params))
      setOffset(off)
    } catch (e) { toast(e.message, 'err') }
    finally { setLoading(false) }
  }

  const rows   = data?.rows   || []
  const total  = data?.total  || 0

  return (
    <div className="animate-fade-in">
      {/* Filter bar */}
      <div className="flex flex-wrap gap-3 items-end mb-4">
        <FormGroup label="Window">
          <Select value={window} onChange={e => setWindow(e.target.value)} className="w-28">
            {['1h','6h','24h','7d'].map(w => <option key={w} value={w}>{w}</option>)}
          </Select>
        </FormGroup>
        <FormGroup label="Model">
          <Input value={model} onChange={e => setModel(e.target.value)} placeholder="any" className="w-32" />
        </FormGroup>
        <FormGroup label="Node">
          <Input value={nodeId} onChange={e => setNodeId(e.target.value)} placeholder="any" className="w-32" />
        </FormGroup>
        <FormGroup label="Filter">
          <label className="flex items-center gap-2 cursor-pointer font-mono text-[10px] text-ink-1 h-[30px]">
            <input type="checkbox" checked={errOnly} onChange={e => setErrOnly(e.target.checked)} className="accent-amber" />
            Errors only
          </label>
        </FormGroup>
        <Btn variant="amber" onClick={() => search(0)} disabled={loading} className="self-end">
          <Search size={11} /> Search
        </Btn>
      </div>

      {loading && <div className="flex items-center gap-2 text-ink-2 font-mono text-[11px] mb-3"><Spinner /> Loading…</div>}

      <Table>
        <thead>
          <tr>
            <Th>Timestamp</Th><Th>Model</Th><Th>Node</Th><Th>Status</Th>
            <Th>Latency</Th><Th>Tokens</Th><Th>Stream</Th><Th>Key</Th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0
            ? <tr><td colSpan={8} className="px-3 py-8 text-center font-mono text-[10px] text-ink-2">
                {data ? 'No requests found' : 'Run a search to see requests'}
              </td></tr>
            : rows.map((r, i) => {
                const sc = r.status_code
                const scColor = sc >= 500 ? 'text-crimson' : sc >= 400 ? 'text-amber' : 'text-jade'
                return (
                  <Tr key={i}>
                    <Td className="text-ink-2 whitespace-nowrap">
                      {r.ts?.replace('T',' ').split('.')[0] ?? '—'}
                    </Td>
                    <Td className="text-ink-0 font-medium">{r.model || '—'}</Td>
                    <Td className="text-ink-2">{r.node_id || '—'}</Td>
                    <Td><span className={`font-mono text-[11px] font-semibold ${scColor}`}>{sc ?? '—'}</span></Td>
                    <Td className="text-ink-2">{r.latency_ms != null ? r.latency_ms.toFixed(0)+'ms' : '—'}</Td>
                    <Td className="text-ink-2">{r.total_tokens ?? '—'}</Td>
                    <Td className="text-ink-2">{r.streaming ? '↻' : '—'}</Td>
                    <Td className="text-ink-2">{r.api_key_hint ? r.api_key_hint+'…' : '—'}</Td>
                  </Tr>
                )
              })
          }
        </tbody>
      </Table>

      {data && (
        <div className="flex justify-between items-center mt-3 font-mono text-[10px] text-ink-2">
          <span>{offset + 1}–{Math.min(offset + LIMIT, total)} of {total}</span>
          <div className="flex gap-2">
            <Btn size="sm" variant="ghost" disabled={offset === 0} onClick={() => search(Math.max(0, offset - LIMIT))}>
              <ChevronLeft size={11} /> Prev
            </Btn>
            <Btn size="sm" variant="ghost" disabled={offset + LIMIT >= total} onClick={() => search(offset + LIMIT)}>
              Next <ChevronRight size={11} />
            </Btn>
          </div>
        </div>
      )}
    </div>
  )
}
