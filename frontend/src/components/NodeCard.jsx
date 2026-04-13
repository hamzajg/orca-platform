import { Card, Badge, Chip, StatusDot } from './ui'
import { timeSince, statusBadgeClass } from '../lib/utils'

export default function NodeCard({ node }) {
  const borderColor = {
    healthy:  'border-l-jade',
    degraded: 'border-l-amber',
    offline:  'border-l-crimson',
    unknown:  'border-l-border-2',
  }[node.status] || 'border-l-border-2'

  return (
    <div className={`relative bg-bg-2 border border-border border-l-2 rounded-md p-4 hover:border-border-2 transition-colors ${borderColor}`}>
      <div className="flex justify-between items-start mb-3">
        <div>
          <div className="font-mono text-[12px] font-semibold text-ink-0">{node.id}</div>
          <div className="font-mono text-[10px] text-ink-2 mt-0.5">
            {node.host}:{node.port} · {node.os}
            {node.ollama_version && ` · v${node.ollama_version}`}
          </div>
        </div>
        <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border font-mono text-[9px] font-semibold tracking-wider ${statusBadgeClass(node.status)}`}>
          <StatusDot status={node.status} />
          {(node.status || 'unknown').toUpperCase()}
        </span>
      </div>

      <div className="font-mono text-[9px] text-ink-2 mb-2">
        Last seen: {timeSince(node.last_seen)}
        {node.failure_count > 0 && (
          <span className="text-crimson ml-2">· {node.failure_count} failure{node.failure_count !== 1 ? 's' : ''}</span>
        )}
      </div>

      {node.tags?.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {node.tags.map(t => <Chip key={t}>{t}</Chip>)}
        </div>
      )}

      <div className="flex flex-wrap gap-1 mt-2">
        {node.available_models?.length > 0
          ? node.available_models.map(m => (
              <span key={m} className="inline-block px-1.5 py-0.5 bg-bg-3 border border-border-2 rounded font-mono text-[9px] text-teal">
                {m}
              </span>
            ))
          : <span className="font-mono text-[9px] text-ink-2">No models pulled</span>
        }
      </div>
    </div>
  )
}
