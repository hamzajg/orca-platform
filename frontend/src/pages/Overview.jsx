import { useState, useEffect } from 'react'
import { RefreshCw } from 'lucide-react'
import { StatCard, SectionTitle, Card, HourlyChart, BarChart, Btn, Spinner } from '../components/ui'
import NodeCard from '../components/NodeCard'
import { getHealth, getNodes, getMetrics } from '../lib/api'

export default function Overview() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [health, metrics, nodes] = await Promise.all([
        getHealth(),
        getMetrics('24h'),
        getNodes(),
      ])
      setData({ health, metrics, nodes: nodes.nodes || [] })
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  if (loading && !data) return (
    <div className="flex items-center justify-center h-48 gap-2 text-ink-2 font-mono text-[11px]">
      <Spinner /> Loading…
    </div>
  )
  if (!data) return null

  const ov = data.metrics?.overview || {}
  const lat = ov.latency_ms || {}
  const tok = ov.tokens || {}
  const errPct = ov.error_rate_pct || 0
  const errAccent = errPct > 5 ? 'text-crimson' : errPct > 1 ? 'text-amber' : 'text-jade'

  return (
    <div className="animate-fade-in">
      <div className="flex justify-between items-center mb-4">
        <div className="font-mono text-[9px] tracking-widest text-ink-2 uppercase">Last 24 hours</div>
        <Btn size="sm" variant="ghost" onClick={load} className="gap-1">
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          Refresh
        </Btn>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-4 gap-3 mb-1">
        <StatCard label="Requests" value={fmt(ov.total_requests)} sub={`${ov.streaming_ratio_pct ?? 0}% streaming`} accent="text-amber" />
        <StatCard label="Error rate" value={`${errPct.toFixed(1)}%`} sub={`${ov.error_count ?? 0} errors`} accent={errAccent} />
        <StatCard label="P95 latency" value={lat.p95 != null ? lat.p95 + 'ms' : '—'} sub={`p50: ${lat.p50 ?? '—'}ms`} accent="text-teal" />
        <StatCard label="Tokens" value={fmt(tok.total)} sub={`${tok.per_second ?? '—'} tok/s`} accent="text-jade" />
      </div>

      <SectionTitle>Nodes at a glance</SectionTitle>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3">
        {data.nodes.map(n => <NodeCard key={n.id} node={n} />)}
      </div>

      <div className="grid grid-cols-2 gap-3 mt-1">
        <div>
          <SectionTitle>Requests by model</SectionTitle>
          <Card className="p-4">
            <BarChart data={data.metrics?.by_model || []} labelKey="model" valueKey="requests" color="bg-amber" />
          </Card>
        </div>
        <div>
          <SectionTitle>Requests by node</SectionTitle>
          <Card className="p-4">
            <BarChart data={data.metrics?.by_node || []} labelKey="node_id" valueKey="requests" color="bg-teal" />
          </Card>
        </div>
      </div>

      <SectionTitle>Hourly throughput — 24h</SectionTitle>
      <Card className="p-4">
        <HourlyChart data={data.metrics?.by_hour || []} height={56} />
        <div className="flex justify-between mt-2">
          <span className="font-mono text-[9px] text-ink-2">
            {data.metrics?.by_hour?.[0]?.hour?.slice(0, 16).replace('T', ' ')}
          </span>
          <span className="font-mono text-[9px] text-ink-2">now</span>
        </div>
      </Card>
    </div>
  )
}

function fmt(n) {
  if (n == null) return '—'
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return String(n)
}
