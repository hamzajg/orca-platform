import { useState, useEffect } from 'react'
import { RefreshCw, Zap, Search, Wifi, WifiOff, X, Plus, Loader2 } from 'lucide-react'
import { SectionTitle, Btn, Empty, Spinner, Badge, Card, Chip } from '../components/ui'
import NodeCard from '../components/NodeCard'
import { getNodes, discoverNodes, quickDiscoverNodes, api } from '../lib/api'

function DiscoveryModal({ onClose, onAddNode, toast }) {
  const [discovering, setDiscovering] = useState(false)
  const [discoveredNodes, setDiscoveredNodes] = useState([])
  const [error, setError] = useState(null)

  const runDiscovery = async (quick = false) => {
    setDiscovering(true)
    setError(null)
    try {
      const d = quick 
        ? await quickDiscoverNodes() 
        : await discoverNodes()
      setDiscoveredNodes(d.nodes || [])
      if (d.nodes?.length === 0) {
        toast('No Ollama nodes found on network', 'err')
      }
    } catch (e) {
      setError(e.message)
      toast(e.message, 'err')
    } finally {
      setDiscovering(false)
    }
  }

  useEffect(() => {
    runDiscovery(true)
  }, [])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-[#121b2e] border border-[rgba(100,180,255,0.20)] rounded-xl w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-[rgba(100,180,255,0.12)]">
          <div className="flex items-center gap-3">
            <Wifi size={20} className="text-[#00d4ff]" />
            <div>
              <h2 className="font-sans text-lg font-semibold text-[#f0f4f8]">Discover Nodes</h2>
              <p className="text-xs text-[#7a8a9a]">Scan local network for Ollama instances</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 text-[#7a8a9a] hover:text-[#f0f4f8]">
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {discovering && (
            <div className="flex flex-col items-center gap-4 py-12">
              <Loader2 size={32} className="text-[#00d4ff] animate-spin" />
              <p className="text-sm text-[#a8b8c8]">Scanning network...</p>
              <p className="text-xs text-[#5a6a7a]">This may take a few seconds</p>
            </div>
          )}

          {error && (
            <div className="text-center py-8">
              <WifiOff size={32} className="text-[#f04d4d] mx-auto mb-3" />
              <p className="text-sm text-[#f04d4d]">{error}</p>
            </div>
          )}

          {!discovering && discoveredNodes.length > 0 && (
            <div className="space-y-3">
              <p className="text-xs text-[#7a8a9a] mb-4">
                Found {discoveredNodes.length} node{discoveredNodes.length !== 1 ? 's' : ''} on network
              </p>
              {discoveredNodes.map((node, i) => (
                <Card key={i} className="p-4 hover:border-[#00d4ff] cursor-pointer" onClick={() => onAddNode(node)}>
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="font-mono text-sm font-semibold text-[#f0f4f8]">{node.host}</div>
                      <div className="font-mono text-xs text-[#7a8a9a] mt-1">
                        Port {node.port} · {node.os || 'unknown'} · v{node.ollama_version || '?'}
                      </div>
                      {node.latency_ms && (
                        <div className="font-mono text-xs text-[#22d3c8] mt-1">{node.latency_ms}ms</div>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {node.available_models?.length > 0 && (
                        <Chip variant="purple">{node.available_models.length} models</Chip>
                      )}
                      <Plus size={16} className="text-[#00d4ff]" />
                    </div>
                  </div>
                  {node.available_models?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-3">
                      {node.available_models.slice(0, 5).map(m => (
                        <Chip key={m} variant="blue">{m}</Chip>
                      ))}
                      {node.available_models.length > 5 && <Chip>+{node.available_models.length - 5}</Chip>}
                    </div>
                  )}
                </Card>
              ))}
            </div>
          )}

          {!discovering && discoveredNodes.length === 0 && !error && (
            <div className="text-center py-12">
              <WifiOff size={32} className="text-[#5a6a7a] mx-auto mb-3" />
              <p className="text-sm text-[#a8b8c8]">No Ollama nodes found</p>
              <p className="text-xs text-[#5a6a7a] mt-1">Make sure Ollama is running on your network</p>
            </div>
          )}
        </div>

        <div className="flex justify-between gap-3 p-4 border-t border-[rgba(100,180,255,0.12)]">
          <Btn variant="ghost" onClick={() => runDiscovery(false)} disabled={discovering}>
            <Search size={14} />
            Full Scan
          </Btn>
          <div className="flex gap-2">
            <Btn variant="ghost" onClick={onClose}>Close</Btn>
            <Btn variant="primary" onClick={() => runDiscovery(true)} disabled={discovering}>
              <RefreshCw size={14} className={discovering ? 'animate-spin' : ''} />
              Rescan
            </Btn>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Nodes({ toast }) {
  const [nodes, setNodes] = useState([])
  const [loading, setLoading] = useState(true)
  const [checking, setChecking] = useState(false)
  const [showDiscovery, setShowDiscovery] = useState(false)

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

  const handleAddNode = async (discoveredNode) => {
    toast(`Node ${discoveredNode.host} added (manual registration coming soon)`, 'ok')
  }

  useEffect(() => { load() }, [])

  const healthy  = nodes.filter(n => n.status === 'healthy').length
  const degraded = nodes.filter(n => n.status === 'degraded').length
  const offline  = nodes.filter(n => n.status === 'offline' || n.status === 'unknown').length

  return (
    <div className="animate-fade-in">
      <div className="flex justify-between items-center mb-4">
        <div className="flex gap-4 font-mono text-xs">
          <span className="text-[#10b981]">{healthy} healthy</span>
          {degraded > 0 && <span className="text-[#f59e0b]">{degraded} degraded</span>}
          {offline  > 0 && <span className="text-[#f04d4d]">{offline} offline</span>}
        </div>
        <div className="flex gap-2">
          <Btn size="sm" variant="amber" onClick={() => setShowDiscovery(true)}>
            <Wifi size={12} />
            Discover
          </Btn>
          <Btn size="sm" variant="ghost" onClick={forceCheck} disabled={checking}>
            <Zap size={12} className={checking ? 'text-[#f59e0b]' : ''} />
            {checking ? 'Checking…' : 'Check'}
          </Btn>
          <Btn size="sm" variant="ghost" onClick={load}>
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          </Btn>
        </div>
      </div>

      {loading && !nodes.length
        ? <div className="flex items-center gap-2 text-[#7a8a9a] font-sans text-sm"><Spinner /> Loading…</div>
        : nodes.length === 0
          ? <Empty message="No nodes registered. Click Discover to find nodes." />
          : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {nodes.map(n => <NodeCard key={n.id} node={n} />)}
            </div>
          )
      }

      {showDiscovery && (
        <DiscoveryModal 
          onClose={() => setShowDiscovery(false)}
          onAddNode={handleAddNode}
          toast={toast}
        />
      )}
    </div>
  )
}