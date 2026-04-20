import { useState, useEffect } from 'react'
import { RefreshCw, Activity, Zap } from 'lucide-react'
import { StatCard, SectionTitle, Card, HourlyChart, BarChart, Btn, Spinner, Badge } from '../components/ui'
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
    <div className="flex items-center justify-center h-64 gap-3">
      <Spinner /> <span className="font-sans text-sm text-[#7a8a9a]">Loading...</span>
    </div>
  )
  if (!data) return null

  const ov = data.metrics?.overview || {}
  const lat = ov.latency_ms || {}
  const tok = ov.tokens || {}
  const errPct = ov.error_rate_pct || 0
  const errVariant = errPct > 5 ? 'red' : errPct > 1 ? 'amber' : 'green'

  const healthyNodes = data.nodes.filter(n => n.status === 'healthy').length
  const totalNodes = data.nodes.length

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 md:mb-6">
        <div className="flex items-center gap-2 md:gap-3">
          <Activity size={16} className="text-[#00d4ff] md:hidden" />
          <Activity size={18} className="hidden md:block text-[#00d4ff]" />
          <span className="font-sans text-sm md:text-base text-[#7a8a9a]">Last 24 hours</span>
        </div>
        <Btn variant="ghost" size="sm" onClick={load}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          <span className="hidden sm:inline">Refresh</span>
        </Btn>
      </div>

      {/* KPI Grid - 2x2 on mobile, 4 col on desktop */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4 mb-4">
        <StatCard 
          label="Requests" 
          value={fmt(ov.total_requests)} 
          sub={`${ov.streaming_ratio_pct ?? 0}% stream`}
          accent="text-[#00d4ff]"
        />
        <StatCard 
          label="Errors" 
          value={`${errPct.toFixed(2)}%`} 
          sub={`${ov.error_count ?? 0} total`}
          accent={errVariant === 'red' ? 'text-[#f04d4d]' : errVariant === 'amber' ? 'text-[#f59e0b]' : 'text-[#10b981]'}
        />
        <StatCard 
          label="P95 Latency" 
          value={lat.p95 != null ? `${lat.p95}ms` : '—'} 
          sub={`p50: ${lat.p50 ?? '—'}ms`}
          accent="text-[#a78bfa]"
        />
        <StatCard 
          label="Tokens/s" 
          value={tok.per_second ? fmt(tok.per_second) : '—'} 
          sub={`${fmt(tok.total)} total`}
          accent="text-[#22d3c8]"
        />
      </div>

      {/* Node Health */}
      <SectionTitle action={
        <Badge variant={healthyNodes === totalNodes ? 'green' : healthyNodes > 0 ? 'amber' : 'red'} size="sm">
            {healthyNodes}/{totalNodes} healthy
        </Badge>
      }>Cluster</SectionTitle>
      
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 md:gap-4 mb-4 md:mb-6">
        {data.nodes.map(n => <NodeCard key={n.id} node={n} />)}
      </div>

      {/* Charts */}
      <div className="grid lg:grid-cols-2 gap-3 md:gap-4">
        <Card className="p-4 md:p-5">
          <SectionTitle>By Model</SectionTitle>
          <BarChart 
            data={data.metrics?.by_model || []} 
            labelKey="model" 
            valueKey="requests" 
            color="metric-bar-requests" 
          />
        </Card>
        <Card className="p-4 md:p-5">
          <SectionTitle>By Node</SectionTitle>
          <BarChart 
            data={data.metrics?.by_node || []} 
            labelKey="node_id" 
            valueKey="requests" 
            color="metric-bar-throughput" 
          />
        </Card>
      </div>

      {/* Hourly */}
      <SectionTitle>Throughput</SectionTitle>
      <Card className="p-4 md:p-5">
        <div className="hidden md:block">
          <HourlyChart data={data.metrics?.by_hour || []} height={64} />
        </div>
        <div className="md:hidden">
          <HourlyChart data={data.metrics?.by_hour || []} height={48} />
        </div>
        <div className="flex justify-between mt-3 pt-3 border-t border-[rgba(100,180,255,0.08)]">
          <span className="font-mono text-xs text-[#5a6a7a]">
            {data.metrics?.by_hour?.[0]?.hour?.slice(0, 16).replace('T', ' ')}
          </span>
          <span className="font-mono text-xs text-[#5a6a7a]">now</span>
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