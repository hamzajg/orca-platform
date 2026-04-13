import { clsx } from '../lib/utils'

// ── Card ──────────────────────────────────────────────────
export function Card({ children, className = '', onClick }) {
  return (
    <div
      onClick={onClick}
      className={clsx(
        'relative bg-bg-2 border border-border rounded-md overflow-hidden',
        'before:absolute before:inset-x-0 before:top-0 before:h-px',
        'before:bg-gradient-to-r before:from-border-2 before:to-transparent',
        onClick && 'cursor-pointer hover:border-border-2 transition-colors',
        className
      )}
    >
      {children}
    </div>
  )
}

// ── KPI stat card ─────────────────────────────────────────
export function StatCard({ label, value, sub, accent = 'text-ink-0' }) {
  return (
    <Card className="p-4">
      <div className="font-mono text-[9px] font-semibold tracking-[0.12em] text-ink-2 uppercase mb-2">
        {label}
      </div>
      <div className={clsx('font-mono text-2xl font-semibold leading-none', accent)}>
        {value ?? '—'}
      </div>
      {sub && (
        <div className="font-mono text-[10px] text-ink-2 mt-1.5">{sub}</div>
      )}
    </Card>
  )
}

// ── Section title ─────────────────────────────────────────
export function SectionTitle({ children }) {
  return (
    <div className="flex items-center gap-3 my-4 first:mt-0">
      <span className="font-mono text-[9px] font-semibold tracking-[0.14em] text-ink-2 uppercase whitespace-nowrap">
        {children}
      </span>
      <div className="flex-1 h-px bg-border" />
    </div>
  )
}

// ── Badge ─────────────────────────────────────────────────
export function Badge({ children, variant = 'gray' }) {
  const cls = {
    green:  'bg-jade-dim border-jade text-jade',
    amber:  'bg-amber-dim border-amber text-amber',
    red:    'bg-crimson-dim border-crimson text-crimson',
    blue:   'bg-sky-dim border-sky text-sky',
    teal:   'bg-teal-dim border-teal text-teal',
    gray:   'bg-bg-4 border-border-2 text-ink-2',
  }[variant] || 'bg-bg-4 border-border-2 text-ink-2'
  return (
    <span className={clsx('inline-flex items-center gap-1 px-1.5 py-0.5 rounded border font-mono text-[9px] font-semibold tracking-wider', cls)}>
      {children}
    </span>
  )
}

// ── Status dot ────────────────────────────────────────────
export function StatusDot({ status }) {
  return <span className={clsx('inline-block w-1.5 h-1.5 rounded-full flex-shrink-0', {
    healthy:  'dot-healthy',
    degraded: 'dot-degraded',
    offline:  'dot-offline',
    unknown:  'dot-unknown',
  }[status] || 'dot-unknown')} />
}

// ── Table primitives ──────────────────────────────────────
export function Table({ children }) {
  return (
    <div className="border border-border rounded-md overflow-hidden overflow-x-auto">
      <table className="w-full border-collapse">{children}</table>
    </div>
  )
}
export function Th({ children, className = '' }) {
  return (
    <th className={clsx('px-3 py-2 text-left font-mono text-[9px] font-semibold tracking-widest text-ink-2 uppercase bg-bg-3 border-b border-border whitespace-nowrap', className)}>
      {children}
    </th>
  )
}
export function Td({ children, className = '' }) {
  return (
    <td className={clsx('px-3 py-2 font-mono text-[11px] text-ink-1 border-b border-border last:border-0', className)}>
      {children}
    </td>
  )
}
export function Tr({ children, onClick, className = '' }) {
  return (
    <tr onClick={onClick} className={clsx('border-b border-border last:border-0 hover:bg-bg-3 transition-colors', onClick && 'cursor-pointer', className)}>
      {children}
    </tr>
  )
}

// ── Input / Select / Textarea ─────────────────────────────
export function Input({ className = '', ...props }) {
  return (
    <input
      {...props}
      className={clsx('inp-base', className)}
    />
  )
}
export function Select({ className = '', children, ...props }) {
  return (
    <select
      {...props}
      className={clsx('inp-base bg-bg-0', className)}
    >
      {children}
    </select>
  )
}
export function Textarea({ className = '', ...props }) {
  return (
    <textarea
      {...props}
      className={clsx('inp-base resize-y leading-relaxed', className)}
    />
  )
}

// ── Label ─────────────────────────────────────────────────
export function Label({ children }) {
  return (
    <label className="font-mono text-[9px] tracking-[0.08em] text-ink-2 uppercase">
      {children}
    </label>
  )
}

// ── FormGroup ─────────────────────────────────────────────
export function FormGroup({ label, children, className = '' }) {
  return (
    <div className={clsx('flex flex-col gap-1', className)}>
      <Label>{label}</Label>
      {children}
    </div>
  )
}

// ── Buttons ───────────────────────────────────────────────
export function Btn({ children, variant = 'ghost', className = '', size = 'md', ...props }) {
  const base = 'inline-flex items-center justify-center gap-1.5 font-mono font-semibold tracking-widest rounded border transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed'
  const sizes = { sm: 'text-[9px] px-2 py-1', md: 'text-[10px] px-3 py-1.5', lg: 'text-[11px] px-4 py-2' }
  const variants = {
    amber:  'bg-amber-dim border-amber text-amber hover:bg-[#8a5210]',
    jade:   'bg-jade-dim border-jade text-jade hover:bg-[#1a6338]',
    crimson:'bg-crimson-dim border-crimson text-crimson hover:bg-[#7a1e1e]',
    ghost:  'bg-transparent border-border-2 text-ink-1 hover:border-teal hover:text-teal',
    teal:   'bg-teal-dim border-teal text-teal hover:bg-[#0f4a46]',
  }
  return (
    <button
      {...props}
      className={clsx(base, sizes[size] || sizes.md, variants[variant] || variants.ghost, className)}
    >
      {children}
    </button>
  )
}

// ── Progress bar ──────────────────────────────────────────
export function Progress({ value = 0, variant = 'amber', className = '' }) {
  const colors = { amber: 'bg-amber', jade: 'bg-jade', crimson: 'bg-crimson', teal: 'bg-teal' }
  return (
    <div className={clsx('h-1 bg-bg-4 rounded-full overflow-hidden', className)}>
      <div
        className={clsx('h-full rounded-full transition-all duration-300', colors[variant] || 'bg-amber')}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  )
}

// ── Hourly bar chart ──────────────────────────────────────
export function HourlyChart({ data = [], height = 52 }) {
  if (!data.length) return (
    <div className="flex items-center justify-center h-12 font-mono text-[10px] text-ink-2">
      No hourly data
    </div>
  )
  const maxReq = Math.max(...data.map(d => d.requests), 1)
  return (
    <div className="flex items-end gap-0.5" style={{ height }}>
      {data.map((d, i) => {
        const h = Math.max(2, (d.requests / maxReq) * height)
        const errRatio = d.errors / (d.requests || 1)
        const color = errRatio > 0.1 ? '#f05c5c' : errRatio > 0 ? '#f0a030' : '#22d3c8'
        const tip = `${(d.hour || '').slice(11, 16)}: ${d.requests} req`
        return (
          <div
            key={i}
            title={tip}
            className="flex-1 rounded-t-sm opacity-70 hover:opacity-100 transition-opacity min-w-[3px]"
            style={{ height: h, background: color }}
          />
        )
      })}
    </div>
  )
}

// ── Bar chart (horizontal) ────────────────────────────────
export function BarChart({ data = [], labelKey, valueKey, color = 'bg-amber' }) {
  if (!data.length) return (
    <div className="font-mono text-[10px] text-ink-2 py-3 text-center">No data</div>
  )
  const max = Math.max(...data.map(d => d[valueKey] || 0), 1)
  return (
    <div className="space-y-2">
      {data.slice(0, 8).map((d, i) => (
        <div key={i} className="flex items-center gap-2">
          <div className="font-mono text-[10px] text-ink-1 w-32 truncate flex-shrink-0" title={d[labelKey]}>
            {d[labelKey]}
          </div>
          <div className="flex-1 h-1.5 bg-bg-4 rounded-full overflow-hidden">
            <div
              className={clsx('h-full rounded-full transition-all duration-500', color)}
              style={{ width: `${((d[valueKey] || 0) / max) * 100}%` }}
            />
          </div>
          <div className="font-mono text-[10px] text-ink-2 w-14 text-right flex-shrink-0">
            {d[valueKey]}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────
export function Empty({ message = 'No data' }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 gap-2">
      <div className="text-2xl opacity-20">◌</div>
      <div className="font-mono text-[10px] text-ink-2">{message}</div>
    </div>
  )
}

// ── Chip tag ──────────────────────────────────────────────
export function Chip({ children }) {
  return (
    <span className="inline-block px-1.5 py-0.5 bg-bg-3 border border-border-2 rounded font-mono text-[9px] text-ink-1">
      {children}
    </span>
  )
}

// ── Inline spinner ────────────────────────────────────────
export function Spinner({ size = 14 }) {
  return (
    <svg className="animate-spin text-amber" width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeOpacity="0.25" />
      <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}
