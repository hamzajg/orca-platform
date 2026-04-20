import { useState, useEffect, useCallback, useRef } from 'react'
import { RefreshCw, Wifi, WifiOff, Menu, X } from 'lucide-react'
import { setApiKey, getHealth, getNodes } from './lib/api'
import { timeSince } from './lib/utils'

import Overview    from './pages/Overview'
import Nodes       from './pages/Nodes'
import Models      from './pages/Models'
import Metrics     from './pages/Metrics'
import Keys        from './pages/Keys'
import RequestLog  from './pages/RequestLog'
import Playground  from './pages/Playground'
import Benchmark   from './pages/Benchmark'

function Toast({ message, type, visible }) {
  if (!message) return null
  const borderColor = type === 'ok' ? 'border-l-[#10b981]' : 'border-l-[#f04d4d]'
  const icon = type === 'ok' ? '✓' : '✕'
  return (
    <div className={`
      fixed bottom-4 right-4 left-4 md:left-auto z-50 border border-[rgba(100,180,255,0.12)] border-l-2 ${borderColor}
      bg-[#121b2e] rounded-lg px-4 py-3 font-sans text-sm text-[#f0f4f8]
      shadow-xl transition-all duration-200
      ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2 pointer-events-none'}
    `}>
      <span className={type === 'ok' ? 'text-[#10b981]' : 'text-[#f04d4d]'}>{icon}</span> {message}
    </div>
  )
}

const TABS = [
  { id: 'overview',   label: 'Overview'    },
  { id: 'nodes',      label: 'Nodes'       },
  { id: 'models',     label: 'Models'      },
  { id: 'metrics',    label: 'Metrics'     },
  { id: 'keys',       label: 'Keys'        },
  { id: 'log',        label: 'Log' },
  { id: 'playground', label: 'Playground'  },
  { id: 'benchmark',  label: 'Benchmark'   },
]

export default function App() {
  const [tab,          setTab]         = useState('overview')
  const [apiKeyInput,  setApiKeyInput] = useState('')
  const [connected,    setConnected]   = useState(false)
  const [connecting,   setConnecting]  = useState(false)
  const [nodeCount,    setNodeCount]   = useState(null)
  const [lastRefresh,  setLastRefresh] = useState(null)
  const [toast,        setToastState]  = useState({ message: '', type: 'ok', visible: false })
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const toastTimer = useRef(null)

  const showToast = useCallback((message, type = 'ok') => {
    setToastState({ message, type, visible: true })
    clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => setToastState(s => ({ ...s, visible: false })), 3000)
  }, [])

  useEffect(() => {
    const stored = sessionStorage.getItem('ollama_api_key')
    if (stored) {
      setApiKeyInput(stored)
      doConnect(stored)
    }
  }, [])

  const doConnect = async (key) => {
    const k = key ?? apiKeyInput.trim()
    if (!k) return showToast('Enter an API key', 'err')
    setConnecting(true)
    setApiKey(k)
    try {
      const [health, nodes] = await Promise.all([getHealth(), getNodes()])
      sessionStorage.setItem('ollama_api_key', k)
      setConnected(true)
      setNodeCount({ healthy: health.nodes?.healthy ?? 0, total: health.nodes?.total ?? 0 })
      setLastRefresh(new Date())
      showToast('Connected to orchestrator', 'ok')
    } catch (e) {
      setConnected(false)
      setApiKey('')
      showToast(e.message || 'Connection failed', 'err')
    } finally { setConnecting(false) }
  }

  const refresh = async () => {
    if (!connected) return
    try {
      const [health, nodes] = await Promise.all([getHealth(), getNodes()])
      setNodeCount({ healthy: health.nodes?.healthy ?? 0, total: health.nodes?.total ?? 0 })
      setLastRefresh(new Date())
    } catch (e) { showToast(e.message, 'err') }
  }

  const PAGE_PROPS = { toast: showToast }

  const handleTabClick = (tabId) => {
    setTab(tabId)
    setMobileMenuOpen(false)
  }

  return (
    <div className="flex flex-col h-screen bg-[#0c1220] text-[#f0f4f8]">
      <div className="bg-grid" />

      {/* Topbar */}
      <header className="topbar-accent nav-glass relative flex items-center justify-between h-14 px-3 md:px-5 flex-shrink-0 z-20">

        {/* Logo & Menu Toggle */}
        <div className="flex items-center gap-2">
          <button 
            className="md:hidden p-2 text-[#a8b8c8] hover:text-[#00d4ff]"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <div className="font-display text-sm font-semibold tracking-[0.06em] text-[#00d4ff] whitespace-nowrap flex items-center gap-2">
            <span className="w-2 h-2 bg-[#00d4ff] rounded-sm rotate-45" />
            <span className="hidden sm:inline">ORCA<span className="text-[#7a8a9a] font-normal">/</span>PLATFORM</span>
          </div>
        </div>

        {/* Status - Desktop only */}
        <div className="hidden md:flex items-center gap-3">
          <div className="flex items-center gap-2 font-sans text-sm">
            <StatusDot status={connected ? 'healthy' : connecting ? 'degraded' : 'unknown'} pulse={connected} />
            <span className="text-[#a8b8c8]">
              {connected ? 'Connected' : connecting ? 'Connecting...' : 'Disconnected'}
            </span>
          </div>
          {connected && nodeCount && (
            <div className="flex items-center gap-1 font-mono text-xs text-[#7a8a9a]">
              <span className="text-[#10b981] font-medium">{nodeCount.healthy}</span>
              <span>/</span>
              <span>{nodeCount.total}</span>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {/* Last refresh - Desktop */}
          {lastRefresh && connected && (
            <span className="hidden lg:block font-mono text-xs text-[#5a6a7a]">
              {timeSince(lastRefresh.toISOString())}
            </span>
          )}

          {/* Refresh */}
          {connected && (
            <button
              onClick={refresh}
              className="btn-ghost p-2"
            >
              <RefreshCw size={16} />
            </button>
          )}

          {/* API Key */}
          <div className="flex items-center gap-1.5">
            <input
              type="password"
              value={apiKeyInput}
              onChange={e => setApiKeyInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && doConnect()}
              placeholder="API key..."
              className="inp-base w-24 sm:w-32 md:w-36 text-xs sm:text-sm"
              autoComplete="off"
            />
            <button
              onClick={() => doConnect()}
              disabled={connecting}
              className="btn-primary text-xs px-3 py-2"
            >
              {connecting ? '...' : 'Connect'}
            </button>
          </div>
        </div>
      </header>

      {/* Tabs - Desktop */}
      <nav className="hidden md:flex nav-glass px-5 flex-shrink-0 z-10 border-t border-[rgba(100,180,255,0.06)]">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`
              px-3 lg:px-4 py-3 font-sans text-sm font-medium
              border-b-2 transition-all cursor-pointer whitespace-nowrap
              ${tab === t.id
                ? 'text-[#00d4ff] border-[#00d4ff] bg-[rgba(0,212,255,0.05)]'
                : 'text-[#7a8a9a] border-transparent hover:text-[#a8b8c8] hover:bg-[rgba(100,180,255,0.04)]'}
            `}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {/* Mobile Menu Overlay */}
      {mobileMenuOpen && (
        <div className="md:hidden nav-glass fixed inset-0 top-14 z-10 overflow-y-auto">
          <div className="p-2">
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => handleTabClick(t.id)}
                className={`
                  w-full text-left px-4 py-3 font-sans text-base
                  border-b border-[rgba(100,180,255,0.08)] transition-all cursor-pointer
                  ${tab === t.id
                    ? 'text-[#00d4ff] bg-[rgba(0,212,255,0.1)]'
                    : 'text-[#a8b8c8]'}
                `}
              >
                {t.label}
              </button>
            ))}
          </div>
          {/* Mobile Status */}
          <div className="p-4 mt-4 border-t border-[rgba(100,180,255,0.12)]">
            <div className="flex items-center gap-2 mb-2">
              <StatusDot status={connected ? 'healthy' : connecting ? 'degraded' : 'unknown'} pulse={connected} />
              <span className="font-sans text-sm text-[#a8b8c8]">
                {connected ? 'Connected' : connecting ? 'Connecting...' : 'Disconnected'}
              </span>
            </div>
            {connected && nodeCount && (
              <div className="font-mono text-xs text-[#7a8a9a]">
                {nodeCount.healthy}/{nodeCount.total} nodes
              </div>
            )}
          </div>
        </div>
      )}

      {/* Content */}
      <main className="flex-1 overflow-y-auto p-3 md:p-5 z-10">
        {!connected && (
          <div className="flex flex-col items-center justify-center h-64 gap-4">
            <WifiOff size={48} className="text-[#5a6a7a]" />
            <p className="font-sans text-base text-[#7a8a9a] text-center px-4">
              Enter your API key to connect to the orchestrator
            </p>
          </div>
        )}

        {connected && (
          <div className="animate-fade-in">
            {tab === 'overview'   && <Overview   {...PAGE_PROPS} />}
            {tab === 'nodes'      && <Nodes       {...PAGE_PROPS} />}
            {tab === 'models'     && <Models      {...PAGE_PROPS} />}
            {tab === 'metrics'    && <Metrics     {...PAGE_PROPS} />}
            {tab === 'keys'       && <Keys        {...PAGE_PROPS} />}
            {tab === 'log'        && <RequestLog  {...PAGE_PROPS} />}
            {tab === 'playground' && <Playground  {...PAGE_PROPS} />}
            {tab === 'benchmark'  && <Benchmark   {...PAGE_PROPS} />}
          </div>
        )}
      </main>

      <Toast message={toast.message} type={toast.type} visible={toast.visible} />
    </div>
  )
}

function StatusDot({ status, pulse = false }) {
  const classes = {
    healthy:  'bg-[#10b981]',
    degraded: 'bg-[#f59e0b]',
    offline:  'bg-[#f04d4d]',
    unknown:  'bg-[#5a6a7a]',
  }[status] || 'bg-[#5a6a7a]'
  return (
    <span className={`
      inline-block w-2 h-2 rounded-full flex-shrink-0
      ${classes}
      ${pulse ? 'status-pulse-healthy' : ''}
    `} />
  )
}