import { useState, useEffect } from 'react'
import { RefreshCw, Zap } from 'lucide-react'
import { SectionTitle, Btn, Empty, Spinner } from '../components/ui'
import NodeCard from '../components/NodeCard'
import { getNodes, api } from '../lib/api'

export default function Nodes({ toast }) {
  const [nodes, setNodes] = useState([])
  const [loading, setLoading] = useState(true)
  const [checking, setChecking] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const d = await getNodes()
      setNodes(d.nodes || [])
    } finally { setLoading(false) }
  }

  const forceCheck = async () => {
    setChecking(true)
    try {
      await api('/api/nodes/check', { method: 'POST' })
      toast('Health check triggered', 'ok')
      setTimeout(load, 1800)
    } catch (e) {
      toast(e.message, 'err')
    } finally { setChecking(false) }
  }

  useEffect(() => { load() }, [])

  const healthy  = nodes.filter(n => n.status === 'healthy').length
  const degraded = nodes.filter(n => n.status === 'degraded').length
  const offline  = nodes.filter(n => n.status === 'offline' || n.status === 'unknown').length

  return (
    <div className="animate-fade-in">
      <div className="flex justify-between items-center mb-4">
        <div className="flex gap-4 font-mono text-[10px]">
          <span className="text-jade">{healthy} healthy</span>
          {degraded > 0 && <span className="text-amber">{degraded} degraded</span>}
          {offline  > 0 && <span className="text-crimson">{offline} offline</span>}
        </div>
        <div className="flex gap-2">
          <Btn size="sm" variant="ghost" onClick={forceCheck} disabled={checking}>
            <Zap size={11} className={checking ? 'text-amber' : ''} />
            {checking ? 'Checking…' : 'Check now'}
          </Btn>
          <Btn size="sm" variant="ghost" onClick={load}>
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          </Btn>
        </div>
      </div>

      {loading && !nodes.length
        ? <div className="flex items-center gap-2 text-ink-2 font-mono text-[11px]"><Spinner /> Loading…</div>
        : nodes.length === 0
          ? <Empty message="No nodes registered" />
          : (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-3">
              {nodes.map(n => <NodeCard key={n.id} node={n} />)}
            </div>
          )
      }
    </div>
  )
}
