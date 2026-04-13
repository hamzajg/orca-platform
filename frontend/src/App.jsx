import { useState, useEffect, useCallback, useRef } from 'react'
import { RefreshCw, Wifi, WifiOff, Key, ChevronDown } from 'lucide-react'
import { setApiKey, getApiKey, getHealth, getNodes } from './lib/api'
import { timeSince } from './lib/utils'

// Pages
import Overview    from './pages/Overview'
import Nodes       from './pages/Nodes'
import Models      from './pages/Models'
import Metrics     from './pages/Metrics'
import Keys        from './pages/Keys'
import RequestLog  from './pages/RequestLog'
import Playground  from './pages/Playground'
import Benchmark   from './pages/Benchmark'

// ── Toast ─────────────────────────────────────────────────────────────────────
function Toast({ message, type, visible }) {
  if (!message) return null
  const border = type === 'ok' ? 'border-l-jade' : 'border-l-crimson'
  return (
    <div
      className={`
        fixed bottom-5 right-5 z-50 border border-border-2 border-l-2 ${border}
        bg-bg-3 rounded-md px-4 py-2.5 font-mono text-[11px] text-ink-0
        shadow-xl transition-all duration-200
        ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2 pointer-events-none'}
      `}
    >
      {message}
    </div>
  )
}

// ── Tabs config ───────────────────────────────────────────────────────────────
const TABS = [
  { id: 'overview',   label: 'Overview'    },
  { id: 'nodes',      label: 'Nodes'       },
  { id: 'models',     label: 'Models'      },
  { id: 'metrics',    label: 'Metrics'     },
  { id: 'keys',       label: 'Keys'        },
  { id: 'log',        label: 'Request Log' },
  { id: 'playground', label: 'Playground'  },
  { id: 'benchmark',  label: 'Benchmark'   },
]

// ── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  const [tab,          setTab]         = useState('overview')
  const [apiKeyInput,  setApiKeyInput] = useState('')
  const [connected,    setConnected]   = useState(false)
  const [connecting,   setConnecting]  = useState(false)
  const [nodeCount,    setNodeCount]   = useState(null)  // {healthy, total}
  const [lastRefresh,  setLastRefresh] = useState(null)
  const [toast,        setToastState]  = useState({ message: '', type: 'ok', visible: false })
  const toastTimer = useRef(null)

  // Toast helper — stable ref so pages can call it without stale closure
  const showToast = useCallback((message, type = 'ok') => {
    setToastState({ message, type, visible: true })
    clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() =>
      setToastState(s => ({ ...s, visible: false })), 3200)
  }, [])

  // Auto-restore from sessionStorage
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
      showToast('Connected', 'ok')
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

  return (
    <div className="flex flex-col h-screen bg-bg-0 text-ink-0">

      {/* ── Topbar ── */}
      <header className="topbar-accent relative flex items-center gap-4 h-12 px-5 bg-bg-1 border-b border-border flex-shrink-0">

        {/* Logo */}
        <div className="font-mono text-[12px] font-semibold tracking-[0.08em] text-amber whitespace-nowrap">
          ORCA<span className="text-ink-2 font-normal">/</span>PLATFORM
          <span className="text-ink-2 font-normal text-[10px] ml-2">v0.6</span>
        </div>

        {/* Status pills */}
        <div className="flex items-center gap-3 ml-1">
          <div className="flex items-center gap-1.5 font-mono text-[10px]">
            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
              connected
                ? 'bg-jade shadow-[0_0_6px_theme(colors.jade.DEFAULT)] animate-pulse-dot'
                : connecting
                  ? 'bg-amber shadow-[0_0_6px_theme(colors.amber.DEFAULT)] animate-pulse-dot'
                  : 'bg-ink-2'
            }`} />
            <span className="text-ink-1">
              {connected ? 'connected' : connecting ? 'connecting…' : 'disconnected'}
            </span>
          </div>

          {connected && nodeCount && (
            <div className="font-mono text-[10px] text-ink-2">
              <span className="text-jade">{nodeCount.healthy}</span>
              <span>/{nodeCount.total} nodes</span>
            </div>
          )}
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Last refresh */}
        {lastRefresh && (
          <span className="font-mono text-[10px] text-ink-2 hidden sm:block">
            {timeSince(lastRefresh.toISOString())}
          </span>
        )}

        {/* Refresh */}
        {connected && (
          <button
            onClick={refresh}
            className="font-mono text-[10px] text-ink-1 hover:text-teal border border-border-2 hover:border-teal rounded px-2.5 py-1 transition-colors cursor-pointer"
          >
            <RefreshCw size={11} className="inline mr-1" />
            Refresh
          </button>
        )}

        {/* API Key input */}
        <div className="flex items-center gap-2">
          <label className="font-mono text-[9px] text-ink-2 tracking-widest hidden sm:block">API KEY</label>
          <input
            type="password"
            value={apiKeyInput}
            onChange={e => setApiKeyInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && doConnect()}
            placeholder="paste your key…"
            className="bg-bg-0 border border-border-2 focus:border-amber rounded px-2.5 py-1
                       font-mono text-[11px] text-ink-0 outline-none w-48 placeholder:text-ink-3
                       transition-colors"
            autoComplete="off"
          />
          <button
            onClick={() => doConnect()}
            disabled={connecting}
            className="font-mono text-[10px] font-semibold tracking-widest
                       bg-amber-dim border border-amber text-amber rounded px-3 py-1
                       hover:bg-[#8a5210] disabled:opacity-40 transition-colors cursor-pointer"
          >
            {connecting ? '…' : 'CONNECT'}
          </button>
        </div>
      </header>

      {/* ── Tabs ── */}
      <nav className="flex bg-bg-1 border-b border-border px-5 flex-shrink-0">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`
              px-4 py-2.5 font-mono text-[10px] font-medium tracking-[0.08em]
              border-b-2 transition-colors cursor-pointer whitespace-nowrap
              ${tab === t.id
                ? 'text-amber border-amber'
                : 'text-ink-2 border-transparent hover:text-ink-1'}
            `}
          >
            {t.label.toUpperCase()}
          </button>
        ))}
      </nav>

      {/* ── Content ── */}
      <main className="flex-1 overflow-y-auto p-5">
        {!connected && (
          <div className="flex flex-col items-center justify-center h-48 gap-3 text-ink-2">
            <WifiOff size={32} className="opacity-30" />
            <p className="font-mono text-[11px]">Enter your API key and click CONNECT</p>
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

      {/* ── Toast ── */}
      <Toast message={toast.message} type={toast.type} visible={toast.visible} />
    </div>
  )
}
