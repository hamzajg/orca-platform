import { Card, Badge, Chip, StatusDot } from './ui'
import { timeSince } from '../lib/utils'

export default function NodeCard({ node }) {
  const nodeStatusClass = {
    healthy:  'node-healthy',
    degraded: 'node-degraded',
    offline:  'node-offline',
    unknown:  'node-unknown',
  }[node.status] || 'node-unknown'

  const statusBadge = {
    healthy:  { variant: 'green', label: 'HEALTHY' },
    degraded: { variant: 'amber', label: 'DEGRADED' },
    offline:  { variant: 'red', label: 'OFFLINE' },
    unknown:  { variant: 'gray', label: 'UNKNOWN' },
  }[node.status] || { variant: 'gray', label: 'UNKNOWN' }

  return (
    <Card className={`p-3 md:p-4 ${nodeStatusClass}`}>
      <div className="flex justify-between items-start mb-2 md:mb-3">
        <div className="min-w-0 flex-1">
          <div className="font-mono text-sm font-semibold text-[#f0f4f8] truncate">{node.id}</div>
          <div className="font-mono text-xs text-[#7a8a9a] mt-0.5 truncate">
            {node.host}:{node.port} · {node.os}
            {node.ollama_version && <span className="text-[#a78bfa]"> v{node.ollama_version}</span>}
          </div>
        </div>
        <Badge variant={statusBadge.variant} size="sm">
          <StatusDot status={node.status} pulse={node.status === 'healthy'} />
          <span className="hidden sm:inline">{statusBadge.label}</span>
        </Badge>
      </div>

      <div className="font-mono text-xs text-[#7a8a9a] mb-2 md:mb-3 flex items-center gap-2 flex-wrap">
        <span>Seen: {timeSince(node.last_seen)}</span>
        {node.failure_count > 0 && (
          <span className="text-[#f04d4d]">{node.failure_count}F</span>
        )}
      </div>

      {node.tags?.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2 md:mb-3">
          {node.tags.map(t => <Chip key={t} variant="blue">{t}</Chip>)}
        </div>
      )}

      <div className="flex flex-wrap gap-1">
        {node.available_models?.length > 0
          ? node.available_models.slice(0, 4).map(m => (
              <Chip key={m} variant="purple">{m}</Chip>
            ))
          : <span className="font-mono text-xs text-[#7a8a9a]">No models</span>
        }
        {node.available_models?.length > 4 && (
          <Chip>+{node.available_models.length - 4}</Chip>
        )}
      </div>
    </Card>
  )
}