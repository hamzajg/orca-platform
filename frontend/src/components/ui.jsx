import { clsx } from '../lib/utils'

// ── Card ──────────────────────────────────────────────────
export function Card({ children, className = '', onClick, variant = 'default' }) {
  const variants = {
    default: 'bg-[#121b2e] border-[rgba(100,180,255,0.12)]',
    metric: 'card-metric',
    glass: 'bg-[rgba(18,27,46,0.6)] backdrop-blur border-[rgba(100,180,255,0.12)]',
  }
  return (
    <div
      onClick={onClick}
      className={clsx(
        'border rounded-lg overflow-hidden',
        variants[variant] || variants.default,
        onClick && 'cursor-pointer hover:border-[rgba(0,212,255,0.25)] hover:bg-[#1a2640] transition-all duration-200',
        className
      )}
    >
      {children}
    </div>
  )
}

// ── KPI stat card ─────────────────────────────────────────
export function StatCard({ label, value, sub, accent = 'text-[#f0f4f8]', trend }) {
  return (
    <Card variant="metric" className="p-4 md:p-5">
      <div className="font-sans text-xs font-semibold tracking-[0.1em] text-[#7a8a9a] uppercase mb-2 md:mb-3 flex items-center gap-2">
        {label}
        {trend && (
          <span className={clsx('text-xs font-normal', {
            'text-[#10b981]': trend > 0,
            'text-[#f04d4d]': trend < 0,
          })}>
            {trend > 0 ? '↑' : '↓'} {Math.abs(trend)}%
          </span>
        )}
      </div>
      <div className={clsx('font-display text-2xl md:text-3xl font-bold tracking-tight', accent)}>
        {value ?? '—'}
      </div>
      {sub && (
        <div className="font-sans text-xs md:text-sm text-[#7a8a9a] mt-2 md:pt-3 border-t border-[rgba(100,180,255,0.08)]">
          {sub}
        </div>
      )}
    </Card>
  )
}

// ── Section title ─────────────────────────────────────────
export function SectionTitle({ children, action }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-0 my-4 md:my-5 first:mt-0">
      <div className="flex items-center gap-3">
        <span className="font-sans text-xs md:text-sm font-semibold tracking-[0.12em] text-[#7a8a9a] uppercase whitespace-nowrap">
          {children}
        </span>
        <div className="hidden sm:block h-px bg-[rgba(100,180,255,0.12)] flex-1 min-w-[80px]" />
      </div>
      {action && <div>{action}</div>}
    </div>
  )
}

// ── Badge ─────────────────────────────────────────────────
export function Badge({ children, variant = 'gray', size = 'md' }) {
  const cls = {
    green:  'bg-[rgba(16,185,129,0.12)] border-[#10b981] text-[#10b981]',
    amber:  'bg-[rgba(245,158,11,0.12)] border-[#f59e0b] text-[#f59e0b]',
    red:    'bg-[rgba(240,77,77,0.12)] border-[#f04d4d] text-[#f04d4d]',
    blue:   'bg-[rgba(0,212,255,0.12)] border-[#00d4ff] text-[#00d4ff]',
    purple: 'bg-[rgba(167,139,250,0.12)] border-[#a78bfa] text-[#a78bfa]',
    teal:   'bg-[rgba(34,211,200,0.12)] border-[#22d3c8] text-[#22d3c8]',
    gray:   'bg-[#1a2640] border-[rgba(100,180,255,0.20)] text-[#7a8a9a]',
  }[variant] || 'bg-[#1a2640] border-[rgba(100,180,255,0.20)] text-[#7a8a9a]'
  
  const sizes = {
    sm: 'text-[10px] px-1.5 py-0.5',
    md: 'text-[11px] px-2 py-1',
    lg: 'text-xs px-3 py-1.5',
  }
  
  return (
    <span className={clsx('inline-flex items-center gap-1.5 rounded border font-sans font-semibold tracking-wider', cls, sizes[size])}>
      {children}
    </span>
  )
}

// ── Status dot ────────────────────────────────────────────
export function StatusDot({ status, pulse = false }) {
  const classes = {
    healthy:  'bg-[#10b981]',
    degraded: 'bg-[#f59e0b]',
    offline:  'bg-[#f04d4d]',
    unknown:  'bg-[#5a6a7a]',
  }[status] || 'bg-[#5a6a7a]'
  
  return (
    <span className={clsx(
      'inline-block w-2 h-2 rounded-full flex-shrink-0',
      classes,
      pulse && 'status-pulse-healthy'
    )} />
  )
}

// ── Table primitives ──────────────────────────────────────
export function Table({ children, className = '' }) {
  return (
    <div className={clsx('border border-[rgba(100,180,255,0.12)] rounded-lg overflow-hidden overflow-x-auto', className)}>
      <table className="w-full border-collapse">{children}</table>
    </div>
  )
}
export function Th({ children, className = '' }) {
  return (
    <th className={clsx('px-3 md:px-4 py-2 md:py-3 text-left font-sans text-xs font-semibold tracking-wider text-[#7a8a9a] uppercase bg-[#1a2640] border-b border-[rgba(100,180,255,0.12)] whitespace-nowrap', className)}>
      {children}
    </th>
  )
}
export function Td({ children, className = '' }) {
  return (
    <td className={clsx('px-3 md:py-3 font-mono text-xs md:text-sm text-[#a8b8c8] border-b border-[rgba(100,180,255,0.08)]', className)}>
      {children}
    </td>
  )
}
export function Tr({ children, onClick, className = '' }) {
  return (
    <tr onClick={onClick} className={clsx('border-b border-[rgba(100,180,255,0.08)] last:border-0 hover:bg-[#1a2640] transition-colors', onClick && 'cursor-pointer', className)}>
      {children}
    </tr>
  )
}

// ── Input / Select / Textarea ─────────────────────────────
export function Input({ className = '', ...props }) {
  return <input {...props} className={clsx('inp-base text-sm', className)} />
}
export function Select({ className = '', children, ...props }) {
  return <select {...props} className={clsx('inp-base bg-[#121b2e] text-sm', className)}>{children}</select>
}
export function Textarea({ className = '', ...props }) {
  return <textarea {...props} className={clsx('inp-base resize-y leading-relaxed text-sm', className)} />
}

// ── Label ─────────────────────────────────────────────────
export function Label({ children }) {
  return <label className="font-sans text-xs font-medium text-[#a8b8c8]">{children}</label>
}

// ── FormGroup ─────────────────────────────────────────────
export function FormGroup({ label, children, className = '' }) {
  return (
    <div className={clsx('flex flex-col gap-2', className)}>
      {label && <Label>{label}</Label>}
      {children}
    </div>
  )
}

// ── Buttons ───────────────────────────────────────────────
export function Btn({ children, variant = 'ghost', className = '', size = 'md', ...props }) {
  const base = 'inline-flex items-center justify-center gap-2 font-sans font-semibold tracking-wide rounded border transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed'
  const sizes = { 
    sm: 'text-xs px-2.5 py-1.5 md:px-3 md:py-2', 
    md: 'text-sm px-3 py-2 md:px-4 md:py-2.5', 
    lg: 'text-base px-4 py-2.5 md:px-5 md:py-3' 
  }
  const variants = {
    primary: 'bg-[#00d4ff] border-transparent text-[#0c1220] hover:bg-[#33ddff]',
    secondary: 'bg-transparent border-[#00d4ff] text-[#00d4ff] hover:bg-[rgba(0,212,255,0.1)]',
    amber: 'bg-[rgba(0,212,255,0.1)] border-[#00d4ff] text-[#00d4ff] hover:bg-[rgba(0,212,255,0.2)]',
    jade: 'bg-[rgba(16,185,129,0.1)] border-[#10b981] text-[#10b981] hover:bg-[rgba(16,185,129,0.2)]',
    crimson: 'bg-[rgba(240,77,77,0.1)] border-[#f04d4d] text-[#f04d4d] hover:bg-[rgba(240,77,77,0.2)]',
    purple: 'bg-[rgba(167,139,250,0.1)] border-[#a78bfa] text-[#a78bfa] hover:bg-[rgba(167,139,250,0.2)]',
    ghost: 'bg-transparent border-[rgba(100,180,255,0.2)] text-[#a8b8c8] hover:border-[#00d4ff] hover:text-[#00d4ff]',
  }
  return (
    <button {...props} className={clsx(base, sizes[size] || sizes.md, variants[variant] || variants.ghost, className)}>
      {children}
    </button>
  )
}

// ── Progress bar ──────────────────────────────────────────
export function Progress({ value = 0, variant = 'blue', className = '' }) {
  const colors = { 
    blue: 'bg-[#00d4ff]', 
    purple: 'bg-[#a78bfa]',
    green: 'bg-[#10b981]', 
    amber: 'bg-[#f59e0b]',
    red: 'bg-[#f04d4d]', 
    teal: 'bg-[#22d3c8]',
  }
  return (
    <div className={clsx('h-1.5 bg-[#1a2640] rounded-full overflow-hidden', className)}>
      <div
        className={clsx('h-full rounded-full transition-all duration-500', colors[variant] || colors.blue)}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  )
}

// ── Hourly bar chart ──────────────────────────────────────
export function HourlyChart({ data = [], height = 60 }) {
  if (!data.length) return (
    <div className="flex items-center justify-center h-12 font-sans text-sm text-[#7a8a9a]">No data</div>
  )
  const maxReq = Math.max(...data.map(d => d.requests), 1)
  return (
    <div className="flex items-end gap-px" style={{ height }}>
      {data.map((d, i) => {
        const h = Math.max(2, (d.requests / maxReq) * height)
        const errRatio = d.errors / (d.requests || 1)
        const color = errRatio > 0.1 ? '#f04d4d' : errRatio > 0 ? '#f59e0b' : '#00d4ff'
        const tip = `${(d.hour || '').slice(11, 16)}: ${d.requests} req`
        return (
          <div key={i} title={tip} className="flex-1 rounded-t-sm hover:opacity-80 transition-opacity min-w-[2px]" style={{ height: h, background: color }} />
        )
      })}
    </div>
  )
}

// ── Bar chart (horizontal) ────────────────────────────────
export function BarChart({ data = [], labelKey, valueKey, color = 'metric-bar-requests', showValue = true }) {
  if (!data.length) return <div className="font-sans text-sm text-[#7a8a9a] py-4 text-center">No data</div>
  const max = Math.max(...data.map(d => d[valueKey] || 0), 1)
  return (
    <div className="space-y-2">
      {data.slice(0, 8).map((d, i) => (
        <div key={i} className="flex items-center gap-2 md:gap-3">
          <div className="font-mono text-xs text-[#a8b8c8] w-20 md:w-32 truncate flex-shrink-0" title={d[labelKey]}>{d[labelKey]}</div>
          <div className="flex-1 h-1.5 md:h-2 bg-[#1a2640] rounded-full overflow-hidden">
            <div className={clsx('h-full rounded-full transition-all duration-700', color)} style={{ width: `${((d[valueKey] || 0) / max) * 100}%` }} />
          </div>
          {showValue && <div className="font-mono text-xs text-[#7a8a9a] w-10 md:w-14 text-right flex-shrink-0">{d[valueKey]}</div>}
        </div>
      ))}
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────
export function Empty({ message = 'No data' }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 md:py-16 gap-3">
      <div className="text-3xl md:text-4xl opacity-20">◌</div>
      <div className="font-sans text-sm md:text-base text-[#7a8a9a]">{message}</div>
    </div>
  )
}

// ── Chip tag ──────────────────────────────────────────────
export function Chip({ children, variant = 'default' }) {
  const variants = {
    default: 'bg-[#1a2640] border-[rgba(100,180,255,0.2)] text-[#a8b8c8]',
    blue: 'bg-[rgba(0,212,255,0.1)] border-[rgba(0,212,255,0.3)] text-[#00d4ff]',
    green: 'bg-[rgba(16,185,129,0.1)] border-[rgba(16,185,129,0.3)] text-[#10b981]',
    purple: 'bg-[rgba(167,139,250,0.1)] border-[rgba(167,139,250,0.3)] text-[#a78bfa]',
  }
  return <span className={clsx('inline-block px-2 py-0.5 md:py-1 border rounded font-mono text-xs', variants[variant] || variants.default)}>{children}</span>
}

// ── Inline spinner ────────────────────────────────────────
export function Spinner({ size = 16, color = '#00d4ff' }) {
  return (
    <svg className="animate-spin" width={size} height={size} viewBox="0 0 24 24" fill="none" style={{ color }}>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeOpacity="0.2" />
      <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

// ── Metric trend ───────────────────────────────────────────
export function Trend({ value, suffix = '%', prefix = '' }) {
  const isPositive = value > 0
  const isNegative = value < 0
  return (
    <span className={clsx('font-mono text-xs font-medium', {
      'text-[#10b981]': isPositive,
      'text-[#f04d4d]': isNegative,
      'text-[#7a8a9a]': !isPositive && !isNegative,
    })}>
      {isPositive ? '+' : ''}{prefix}{value}{suffix}
    </span>
  )
}