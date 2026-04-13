export const fmt = (n) => {
  if (n == null) return '—'
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return String(n)
}

export const fmtBytes = (b) => {
  if (!b) return '0 B'
  if (b >= 1e9) return (b / 1e9).toFixed(1) + ' GB'
  if (b >= 1e6) return (b / 1e6).toFixed(1) + ' MB'
  if (b >= 1e3) return (b / 1e3).toFixed(1) + ' KB'
  return b + ' B'
}

export const timeSince = (iso) => {
  if (!iso) return 'never'
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60)    return s + 's ago'
  if (s < 3600)  return Math.floor(s / 60) + 'm ago'
  if (s < 86400) return Math.floor(s / 3600) + 'h ago'
  return Math.floor(s / 86400) + 'd ago'
}

export const pct = (p, t) => (t > 0 ? ((p / t) * 100).toFixed(1) : '0.0')

export const clsx = (...args) =>
  args.flat().filter(Boolean).join(' ')

export const statusColor = (s) => ({
  healthy:  'text-jade',
  degraded: 'text-amber',
  offline:  'text-crimson',
  unknown:  'text-ink-2',
}[s] || 'text-ink-2')

export const statusDotClass = (s) => ({
  healthy:  'dot-healthy',
  degraded: 'dot-degraded',
  offline:  'dot-offline',
  unknown:  'dot-unknown',
}[s] || 'dot-unknown')

export const statusBadgeClass = (s) => ({
  healthy:  'bg-jade-dim border-jade text-jade',
  degraded: 'bg-amber-dim border-amber text-amber',
  offline:  'bg-crimson-dim border-crimson text-crimson',
  unknown:  'bg-bg-4 border-border text-ink-2',
}[s] || 'bg-bg-4 border-border text-ink-2')
