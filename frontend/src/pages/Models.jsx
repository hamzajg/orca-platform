import { useState, useEffect, useRef } from 'react'
import { RefreshCw, Download, RefreshCcw, X, ChevronRight } from 'lucide-react'
import { Card, SectionTitle, FormGroup, Input, Select, Btn, Progress, Badge, Table, Th, Td, Tr, Empty, Spinner } from '../components/ui'
import { api, getJobs, getModelList, getNodes } from '../lib/api'
import { timeSince, fmtBytes } from '../lib/utils'

const JOB_VARIANTS = { queued: 'gray', pulling: 'amber', done: 'green', error: 'red' }
const PROGRESS_VARIANTS = { done: 'jade', error: 'crimson', pulling: 'amber', queued: 'gray' }

export default function Models({ toast }) {
  const [jobs, setJobs]           = useState([])
  const [models, setModels]       = useState([])
  const [nodes, setNodes]         = useState([])
  const [pullModel, setPullModel] = useState('')
  const [pullNode, setPullNode]   = useState('')
  const [syncing, setSyncing]     = useState(false)
  const [pulling, setPulling]     = useState(false)
  const pollerRef                 = useRef(null)

  const loadAll = async () => {
    const [j, m, n] = await Promise.all([getJobs(), getModelList(), getNodes()])
    setJobs(j.jobs || [])
    setModels(m.models || [])
    setNodes(n.nodes || [])
  }

  useEffect(() => {
    loadAll()
    pollerRef.current = setInterval(loadAll, 6000)
    return () => clearInterval(pollerRef.current)
  }, [])

  const doPull = async () => {
    if (!pullModel.trim()) return toast('Enter a model name', 'err')
    setPulling(true)
    try {
      const body = { model: pullModel.trim() }
      if (pullNode) body.node_ids = [pullNode]
      const d = await api('/api/models/pull', { method: 'POST', body: JSON.stringify(body) })
      toast(`Pull queued: ${d.jobs?.length ?? 0} job(s)`, 'ok')
      setPullModel('')
      loadAll()
    } catch (e) { toast(e.message, 'err') }
    finally { setPulling(false) }
  }

  const doSync = async () => {
    setSyncing(true)
    try {
      const d = await api('/api/models/sync', { method: 'POST' })
      toast(d.message, 'ok')
      loadAll()
    } catch (e) { toast(e.message, 'err') }
    finally { setSyncing(false) }
  }

  const deleteJob = async (id) => {
    try {
      await api(`/api/models/jobs/${id}`, { method: 'DELETE' })
      setJobs(j => j.filter(x => x.job_id !== id))
    } catch (e) { toast(e.message, 'err') }
  }

  const activeJobs = jobs.filter(j => j.status === 'pulling' || j.status === 'queued')
  const doneJobs   = jobs.filter(j => j.status === 'done' || j.status === 'error')

  return (
    <div className="animate-fade-in">
      {/* Pull form */}
      <SectionTitle>Pull a model</SectionTitle>
      <Card className="p-4 mb-1">
        <div className="flex flex-wrap gap-3 items-end">
          <FormGroup label="Model name">
            <Input
              value={pullModel}
              onChange={e => setPullModel(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && doPull()}
              placeholder="llama3.2, mistral:7b …"
              className="w-52"
            />
          </FormGroup>
          <FormGroup label="Target node">
            <Select value={pullNode} onChange={e => setPullNode(e.target.value)} className="w-44">
              <option value="">All nodes</option>
              {nodes.map(n => <option key={n.id} value={n.id}>{n.id} ({n.os})</option>)}
            </Select>
          </FormGroup>
          <Btn variant="amber" onClick={doPull} disabled={pulling} className="self-end">
            <Download size={12} /> {pulling ? 'Queuing…' : 'Pull'}
          </Btn>
          <Btn variant="ghost" onClick={doSync} disabled={syncing} className="self-end">
            <RefreshCcw size={12} className={syncing ? 'animate-spin' : ''} />
            {syncing ? 'Syncing…' : 'Sync manifest'}
          </Btn>
        </div>
      </Card>

      {/* Active jobs */}
      {activeJobs.length > 0 && (
        <>
          <SectionTitle>In progress</SectionTitle>
          <Card className="overflow-hidden">
            {activeJobs.map(j => <JobRow key={j.job_id} job={j} onDelete={deleteJob} />)}
          </Card>
        </>
      )}

      {/* Recent jobs */}
      {doneJobs.length > 0 && (
        <>
          <SectionTitle>Recent jobs</SectionTitle>
          <Card className="overflow-hidden">
            {doneJobs.slice(0, 10).map(j => <JobRow key={j.job_id} job={j} onDelete={deleteJob} />)}
          </Card>
        </>
      )}

      {/* Model inventory */}
      <SectionTitle>Model inventory</SectionTitle>
      {models.length === 0
        ? <Empty message="No models found on any node" />
        : (
          <Table>
            <thead><tr><Th>Model</Th><Th>Available on</Th></tr></thead>
            <tbody>
              {models.map(m => (
                <Tr key={m.name}>
                  <Td className="text-ink-0 font-medium">{m.name}</Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      {m.available_on.map(n => (
                        <span key={n} className="px-1.5 py-0.5 bg-bg-3 border border-border-2 rounded font-mono text-[9px] text-teal">{n}</span>
                      ))}
                    </div>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )
      }
    </div>
  )
}

function JobRow({ job, onDelete }) {
  const pct = job.progress_pct || 0
  const progVariant = PROGRESS_VARIANTS[job.status] || 'amber'
  return (
    <div className="flex items-center gap-3 px-4 py-3 border-b border-border last:border-0">
      <div className="flex-1 min-w-0">
        <div className="font-mono text-[11px] text-ink-0 font-medium">
          {job.model}
          <span className="text-ink-2 font-normal ml-2">→ {job.node_id}</span>
        </div>
        {job.current_layer && (
          <div className="font-mono text-[9px] text-ink-2 mt-0.5 truncate">{job.current_layer}</div>
        )}
        {job.error && (
          <div className="font-mono text-[9px] text-crimson mt-0.5 truncate">⚠ {job.error}</div>
        )}
        {(job.bytes_total > 0) && (
          <div className="font-mono text-[9px] text-ink-2 mt-0.5">
            {fmtBytes(job.bytes_done)} / {fmtBytes(job.bytes_total)}
          </div>
        )}
        <Progress value={pct} variant={progVariant} className="mt-1.5" />
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <Badge variant={JOB_VARIANTS[job.status] || 'gray'}>
          {job.status?.toUpperCase()}
        </Badge>
        <span className="font-mono text-[10px] text-ink-2">{pct.toFixed(0)}%</span>
        {(job.status === 'done' || job.status === 'error') && (
          <button
            onClick={() => onDelete(job.job_id)}
            className="text-ink-2 hover:text-crimson transition-colors cursor-pointer"
          >
            <X size={13} />
          </button>
        )}
      </div>
    </div>
  )
}
