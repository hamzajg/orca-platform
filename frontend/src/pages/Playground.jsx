import { useState, useEffect, useRef } from 'react'
import { Send, Square, Trash2, ChevronDown } from 'lucide-react'
import { Card, SectionTitle, FormGroup, Input, Select, Textarea, Btn, Spinner } from '../components/ui'
import { getModels, apiFetch, streamSSE, BASE } from '../lib/api'
import { getApiKey } from '../lib/api'

export default function Playground({ toast }) {
  const [models, setModels]     = useState([])
  const [model, setModel]       = useState('')
  const [system, setSystem]     = useState('')
  const [prompt, setPrompt]     = useState('')
  const [temp, setTemp]         = useState('0.7')
  const [maxTok, setMaxTok]     = useState('512')
  const [topP, setTopP]         = useState('1')
  const [seed, setSeed]         = useState('')
  const [stream, setStream]     = useState(true)
  const [history, setHistory]   = useState([])  // [{role,content}]
  const [output, setOutput]     = useState('')
  const [sending, setSending]   = useState(false)
  const [stats, setStats]       = useState(null)
  const stopRef                 = useRef(false)
  const outputRef               = useRef(null)

  useEffect(() => {
    getModels().then(d => {
      const list = d.data || []
      setModels(list)
      if (list.length) setModel(list[0].id)
    }).catch(() => {})
  }, [])

  const send = async () => {
    if (!model)  return toast('Select a model', 'err')
    if (!prompt.trim()) return toast('Enter a message', 'err')
    setSending(true)
    stopRef.current = false
    setOutput('')
    setStats(null)

    const messages = []
    if (system.trim()) messages.push({ role: 'system', content: system.trim() })
    messages.push(...history)
    messages.push({ role: 'user', content: prompt.trim() })

    const body = { model, messages, stream, temperature: parseFloat(temp)||0.7, max_tokens: parseInt(maxTok)||512, top_p: parseFloat(topP)||1 }
    if (seed.trim()) body.seed = parseInt(seed)
    const userPrompt = prompt.trim()
    setPrompt('')

    const t0 = performance.now()
    let ttft = null, fullText = '', tokenCount = 0

    try {
      const res = await fetch(BASE + '/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': getApiKey() },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const e = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(e.detail)
      }

      if (stream) {
        await streamSSE(res, (chunk) => {
          const delta = chunk.choices?.[0]?.delta?.content || ''
          if (delta) {
            if (ttft === null) ttft = performance.now() - t0
            fullText += delta
            tokenCount++
            setOutput(fullText)
            if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight
          }
        }, () => stopRef.current)
      } else {
        const data = await res.json()
        ttft = performance.now() - t0
        fullText = data.choices?.[0]?.message?.content || ''
        tokenCount = data.usage?.completion_tokens || 0
        setOutput(fullText)
      }

      const totalMs = performance.now() - t0
      setStats({
        ttft: ttft != null ? ttft.toFixed(0) : null,
        latency: totalMs.toFixed(0),
        tps: tokenCount > 0 ? (tokenCount / (totalMs / 1000)).toFixed(1) : null,
        tokens: tokenCount,
      })
      setHistory(h => [...h, { role: 'user', content: userPrompt }, { role: 'assistant', content: fullText }])

    } catch (e) {
      if (!stopRef.current) {
        setOutput(`Error: ${e.message}`)
        toast(e.message, 'err')
      }
    } finally { setSending(false) }
  }

  const stop = () => { stopRef.current = true; setSending(false) }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!sending) send() }
  }

  return (
    <div className="animate-fade-in h-full">
      <div className="grid gap-3" style={{ gridTemplateColumns: '300px 1fr', height: 'calc(100vh - 120px)' }}>

        {/* Sidebar */}
        <div className="flex flex-col gap-3 overflow-y-auto pr-1">
          <Card className="p-4">
            <div className="font-mono text-[9px] font-semibold tracking-widest text-ink-2 uppercase mb-2">Model</div>
            <Select value={model} onChange={e => setModel(e.target.value)} className="w-full">
              <option value="">— select —</option>
              {models.map(m => <option key={m.id} value={m.id}>{m.id}</option>)}
            </Select>
          </Card>

          <Card className="p-4">
            <div className="font-mono text-[9px] font-semibold tracking-widest text-ink-2 uppercase mb-2">System prompt</div>
            <Textarea value={system} onChange={e => setSystem(e.target.value)} rows={3} placeholder="You are a helpful assistant." className="w-full" />
          </Card>

          <Card className="p-4">
            <div className="font-mono text-[9px] font-semibold tracking-widest text-ink-2 uppercase mb-3">Parameters</div>
            <div className="grid grid-cols-2 gap-2">
              <FormGroup label="Temperature">
                <Input type="number" value={temp} onChange={e => setTemp(e.target.value)} step="0.1" min="0" max="2" />
              </FormGroup>
              <FormGroup label="Max tokens">
                <Input type="number" value={maxTok} onChange={e => setMaxTok(e.target.value)} min="1" />
              </FormGroup>
              <FormGroup label="Top-p">
                <Input type="number" value={topP} onChange={e => setTopP(e.target.value)} step="0.05" min="0" max="1" />
              </FormGroup>
              <FormGroup label="Seed">
                <Input type="number" value={seed} onChange={e => setSeed(e.target.value)} placeholder="random" />
              </FormGroup>
            </div>
            <label className="flex items-center gap-2 cursor-pointer mt-3 font-mono text-[10px] text-ink-1">
              <input type="checkbox" checked={stream} onChange={e => setStream(e.target.checked)} className="accent-amber" />
              Stream tokens
            </label>
          </Card>

          <Card className="p-4">
            <div className="flex justify-between items-center mb-2">
              <div className="font-mono text-[9px] font-semibold tracking-widest text-ink-2 uppercase">Chat history</div>
              <Btn size="sm" variant="ghost" onClick={() => { setHistory([]); setOutput(''); setStats(null) }}>
                <Trash2 size={10} /> Clear
              </Btn>
            </div>
            {history.length === 0
              ? <div className="font-mono text-[9px] text-ink-2">No messages yet</div>
              : history.map((m, i) => (
                <div key={i} className="font-mono text-[9px] mb-1 leading-relaxed">
                  <span className={m.role === 'user' ? 'text-amber' : 'text-teal'}>{m.role}: </span>
                  <span className="text-ink-2">{m.content.slice(0, 70)}{m.content.length > 70 ? '…' : ''}</span>
                </div>
              ))
            }
          </Card>
        </div>

        {/* Main area */}
        <div className="flex flex-col gap-3 min-h-0">
          {/* Prompt input */}
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              <FormGroup label="User message">
                <Textarea
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  onKeyDown={handleKey}
                  rows={3}
                  placeholder="Type your message… (Enter to send, Shift+Enter for newline)"
                  className="w-full"
                />
              </FormGroup>
            </div>
            {sending
              ? <Btn variant="crimson" onClick={stop} className="self-end px-4 py-2">
                  <Square size={12} /> Stop
                </Btn>
              : <Btn variant="amber" onClick={send} className="self-end px-4 py-2">
                  <Send size={12} /> Send
                </Btn>
            }
          </div>

          {/* Stats bar */}
          {stats && (
            <div className="flex gap-6 flex-wrap bg-bg-2 border border-border rounded-md px-4 py-3 animate-fade-in">
              {[
                { label: 'TTFT',       value: stats.ttft    ? stats.ttft + 'ms'    : '—', color: 'text-amber' },
                { label: 'Latency',    value: stats.latency ? stats.latency + 'ms' : '—', color: 'text-teal' },
                { label: 'Tokens/sec', value: stats.tps     ? stats.tps + ' t/s'   : '—', color: 'text-jade' },
                { label: 'Tokens',     value: stats.tokens  ?? '—', color: 'text-ink-0' },
              ].map(s => (
                <div key={s.label}>
                  <div className="font-mono text-[9px] text-ink-2 tracking-widest">{s.label}</div>
                  <div className={`font-mono text-[15px] font-semibold ${s.color}`}>{s.value}</div>
                </div>
              ))}
            </div>
          )}

          {/* Output */}
          <div
            ref={outputRef}
            className="flex-1 bg-bg-0 border border-border rounded-md p-4 font-mono text-[12px] text-ink-0 overflow-y-auto whitespace-pre-wrap leading-relaxed min-h-[120px]"
          >
            {output
              ? <>{output}{sending && stream && <span className="stream-cursor" />}</>
              : <span className="text-ink-2">Output will appear here…</span>
            }
          </div>
        </div>
      </div>
    </div>
  )
}
