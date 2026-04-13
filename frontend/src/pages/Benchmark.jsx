import { useState, useEffect, useRef } from 'react'
import { Play, Square, Trash2, ChevronDown, ChevronRight } from 'lucide-react'
import {
  Card, SectionTitle, FormGroup, Input, Textarea, Btn,
  Progress, Table, Th, Td, Tr, Empty
} from '../components/ui'
import { getModels, BASE, getApiKey } from '../lib/api'

// ── helpers ─────────────────────────────────────────────────────────────────

function pct(p, s) { return s > 0 ? ((p / s) * 100).toFixed(1) : '0.0' }
function fmtMs(v)  { return v != null ? v.toFixed(0) + 'ms' : '—' }

function percentile(sorted, p) {
  if (!sorted.length) return null
  const k = (sorted.length - 1) * p / 100
  const lo = Math.floor(k), hi = Math.ceil(k)
  return lo === hi ? sorted[lo] : sorted[lo] * (1 - (k - lo)) + sorted[hi] * (k - lo)
}

async function singleRun({ model, prompt, maxTok, temp, apiKey }) {
  const t0 = performance.now()
  let ttft = null, tokenCount = 0, errorMsg = null

  try {
    const res = await fetch(BASE + '/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: prompt }],
        stream: true,
        temperature: temp,
        max_tokens: maxTok,
      }),
      signal: AbortSignal.timeout(180_000),
    })

    if (!res.ok) {
      const e = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(e.detail || res.statusText)
    }

    const reader = res.body.getReader()
    const dec = new TextDecoder()
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ') || line === 'data: [DONE]') continue
        try {
          const chunk = JSON.parse(line.slice(6))
          const delta = chunk.choices?.[0]?.delta?.content || ''
          if (delta) {
            if (ttft === null) ttft = performance.now() - t0
            tokenCount++
          }
        } catch (_) {}
      }
    }
    reader.releaseLock()
  } catch (e) {
    errorMsg = e.message?.slice(0, 120)
  }

  const totalMs = performance.now() - t0
  return {
    latencyMs:    Math.round(totalMs),
    ttftMs:       ttft != null ? Math.round(ttft) : null,
    tokensPerSec: tokenCount > 0 ? parseFloat((tokenCount / (totalMs / 1000)).toFixed(1)) : 0,
    tokenCount,
    error:        errorMsg,
  }
}

// ── component ────────────────────────────────────────────────────────────────

export default function Benchmark({ toast }) {
  const [availModels, setAvailModels] = useState([])
  const [prompt,       setPrompt]     = useState('Explain what a neural network is in exactly 3 sentences.')
  const [modelsText,   setModelsText] = useState('')
  const [runsEach,     setRunsEach]   = useState('3')
  const [maxTok,       setMaxTok]     = useState('256')
  const [concurrency,  setConcurrency]= useState('1')
  const [temp,         setTemp]       = useState('0.0')
  const [running,      setRunning]    = useState(false)
  const [results,      setResults]    = useState({})   // model → {runs:[],errors:0}
  const [log,          setLog]        = useState([])
  const [progress,     setProgress]   = useState(0)    // 0–100
  const [expandedRow,  setExpandedRow]= useState(null)
  const stopRef = useRef(false)
  const logRef  = useRef(null)

  useEffect(() => {
    getModels().then(d => {
      const list = (d.data || []).map(m => m.id)
      setAvailModels(list)
      if (!modelsText && list.length) setModelsText(list.slice(0, 3).join('\n'))
    }).catch(() => {})
  }, [])

  const addLog = (msg, color = 'text-ink-1') => {
    setLog(l => [...l, { msg, color, id: Date.now() + Math.random() }])
    setTimeout(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight }, 30)
  }

  const runBench = async () => {
    const models = modelsText.split('\n').map(s => s.trim()).filter(Boolean)
    if (!models.length) return toast('Enter at least one model', 'err')
    if (!prompt.trim()) return toast('Enter a prompt', 'err')

    const runs  = Math.max(1, Math.min(20, parseInt(runsEach) || 3))
    const conc  = Math.max(1, Math.min(10, parseInt(concurrency) || 1))
    const mTok  = parseInt(maxTok) || 256
    const temperature = parseFloat(temp) || 0

    setRunning(true)
    stopRef.current = false
    setResults({})
    setLog([])
    setProgress(0)
    setExpandedRow(null)

    const apiKey = getApiKey()
    const total  = models.length * runs
    let completed = 0

    for (const model of models) {
      if (stopRef.current) break
      setResults(r => ({ ...r, [model]: { runs: [], errors: 0 } }))
      addLog(`▶ ${model}  (${runs} runs, concurrency=${conc})`, 'text-amber')

      for (let i = 0; i < runs; i += conc) {
        if (stopRef.current) break
        const batch = Array.from({ length: Math.min(conc, runs - i) }, () =>
          singleRun({ model, prompt: prompt.trim(), maxTok: mTok, temp: temperature, apiKey })
        )
        const batchResults = await Promise.all(batch)

        for (const r of batchResults) {
          completed++
          setProgress(Math.round((completed / total) * 100))
          setResults(prev => {
            const cur = prev[model] || { runs: [], errors: 0 }
            return {
              ...prev,
              [model]: {
                runs: [...cur.runs, r],
                errors: cur.errors + (r.error ? 1 : 0),
              },
            }
          })
          const label = r.error
            ? `  run ${completed}: ERROR — ${r.error}`
            : `  run ${i + batchResults.indexOf(r) + 1}: ${r.latencyMs}ms · ${r.tokensPerSec} t/s · ${r.tokenCount} tok`
          addLog(label, r.error ? 'text-crimson' : r.latencyMs < 2000 ? 'text-jade' : 'text-ink-1')
        }
      }
      addLog(`✓ ${model} complete`, 'text-teal')
    }

    addLog(stopRef.current ? '⏹ Stopped.' : '✓ Benchmark complete.', 'text-jade')
    setRunning(false)
    stopRef.current = false
  }

  const stop  = () => { stopRef.current = true }
  const clear = () => { setResults({}); setLog([]); setProgress(0); setExpandedRow(null) }

  // Compute summary stats per model
  const summaries = Object.entries(results).map(([model, d]) => {
    const ok   = d.runs.filter(r => !r.error)
    const lats = ok.map(r => r.latencyMs).sort((a, b) => a - b)
    const tpsList = ok.map(r => r.tokensPerSec).filter(x => x > 0)
    const avg  = lats.length ? Math.round(lats.reduce((a, b) => a + b, 0) / lats.length) : null
    const p95  = lats.length ? Math.round(percentile(lats, 95)) : null
    const p50  = lats.length ? Math.round(percentile(lats, 50)) : null
    const avgTps = tpsList.length ? parseFloat((tpsList.reduce((a, b) => a + b, 0) / tpsList.length).toFixed(1)) : null
    const avgTok = ok.length ? Math.round(ok.map(r => r.tokenCount).reduce((a, b) => a + b, 0) / ok.length) : null
    return { model, total: d.runs.length, ok: ok.length, errors: d.errors, avg, p50, p95, avgTps, avgTok, lats }
  })

  const avgs   = summaries.map(s => s.avg).filter(Boolean)
  const minAvg = avgs.length ? Math.min(...avgs) : null
  const maxAvg = avgs.length ? Math.max(...avgs) : null

  const latColor = (v) => {
    if (v == null || minAvg == null) return 'text-ink-1'
    if (v === minAvg) return 'text-jade'
    if (v === maxAvg) return 'text-crimson'
    return 'text-amber'
  }
  const tpsColor = (v) => {
    if (!v) return 'text-ink-2'
    const max = Math.max(...summaries.map(s => s.avgTps || 0))
    return v === max ? 'text-jade' : 'text-ink-1'
  }

  return (
    <div className="animate-fade-in">
      <div className="grid grid-cols-2 gap-3 mb-1">
        {/* Config */}
        <Card className="p-4">
          <div className="font-mono text-[9px] font-semibold tracking-widest text-ink-2 uppercase mb-3">
            Configuration
          </div>
          <div className="space-y-3">
            <FormGroup label="Prompt">
              <Textarea value={prompt} onChange={e => setPrompt(e.target.value)} rows={3} className="w-full" />
            </FormGroup>
            <FormGroup label="Models (one per line)">
              <Textarea value={modelsText} onChange={e => setModelsText(e.target.value)} rows={4}
                className="w-full" placeholder={availModels.slice(0,3).join('\n') || 'llama3.2\nmistral'} />
            </FormGroup>
            <div className="grid grid-cols-2 gap-2">
              <FormGroup label="Runs per model">
                <Input type="number" value={runsEach} onChange={e => setRunsEach(e.target.value)} min="1" max="20" />
              </FormGroup>
              <FormGroup label="Max tokens">
                <Input type="number" value={maxTok} onChange={e => setMaxTok(e.target.value)} min="1" max="2048" />
              </FormGroup>
              <FormGroup label="Concurrency">
                <Input type="number" value={concurrency} onChange={e => setConcurrency(e.target.value)} min="1" max="10" />
              </FormGroup>
              <FormGroup label="Temperature">
                <Input type="number" value={temp} onChange={e => setTemp(e.target.value)} step="0.1" min="0" max="2" />
              </FormGroup>
            </div>
            <div className="flex gap-2 items-center pt-1">
              {running
                ? <Btn variant="crimson" onClick={stop}><Square size={12} /> Stop</Btn>
                : <Btn variant="amber"   onClick={runBench}><Play size={12} /> Run benchmark</Btn>
              }
              <Btn variant="ghost" size="sm" onClick={clear}><Trash2 size={11} /> Clear</Btn>
              {running && (
                <span className="font-mono text-[10px] text-ink-2 ml-1">{progress}%</span>
              )}
            </div>
            {(running || progress > 0) && (
              <Progress value={progress} variant={running ? 'amber' : 'jade'} />
            )}
          </div>
        </Card>

        {/* Live log */}
        <Card className="p-4 flex flex-col">
          <div className="font-mono text-[9px] font-semibold tracking-widest text-ink-2 uppercase mb-3">
            Run log
          </div>
          <div
            ref={logRef}
            className="flex-1 overflow-y-auto font-mono text-[10px] leading-relaxed space-y-px min-h-[160px]"
          >
            {log.length === 0
              ? <span className="text-ink-2">No runs yet…</span>
              : log.map(l => (
                  <div key={l.id} className={`${l.color} animate-fade-in`}>{l.msg}</div>
                ))
            }
          </div>
        </Card>
      </div>

      {/* Results table */}
      <SectionTitle>Results</SectionTitle>
      {summaries.length === 0
        ? <Empty message="Run a benchmark to see results" />
        : (
          <Table>
            <thead>
              <tr>
                <Th>Model</Th>
                <Th>Runs (ok/total)</Th>
                <Th>Avg latency</Th>
                <Th>P50</Th>
                <Th>P95</Th>
                <Th>Avg tok/s</Th>
                <Th>Avg tokens</Th>
                <Th>Errors</Th>
                <Th>Dist.</Th>
              </tr>
            </thead>
            <tbody>
              {summaries.map(s => (
                <>
                  <Tr key={s.model} onClick={() => setExpandedRow(expandedRow === s.model ? null : s.model)}>
                    <Td className="text-ink-0 font-medium">
                      <div className="flex items-center gap-1">
                        {expandedRow === s.model ? <ChevronDown size={11} className="text-amber" /> : <ChevronRight size={11} className="text-ink-2" />}
                        {s.model}
                      </div>
                    </Td>
                    <Td>{s.ok}/{s.total}</Td>
                    <Td className={latColor(s.avg)}>{fmtMs(s.avg)}</Td>
                    <Td className="text-ink-2">{fmtMs(s.p50)}</Td>
                    <Td className="text-ink-2">{fmtMs(s.p95)}</Td>
                    <Td className={tpsColor(s.avgTps)}>{s.avgTps ?? '—'}</Td>
                    <Td className="text-ink-2">{s.avgTok ?? '—'}</Td>
                    <Td className={s.errors > 0 ? 'text-crimson' : 'text-ink-2'}>{s.errors}</Td>
                    <Td>
                      <LatDist lats={s.lats} />
                    </Td>
                  </Tr>

                  {expandedRow === s.model && (
                    <tr key={`${s.model}-detail`}>
                      <td colSpan={9} className="bg-bg-1 px-4 py-3 border-b border-border">
                        <div className="font-mono text-[9px] text-ink-2 uppercase tracking-widest mb-2">
                          Per-run detail — {s.model}
                        </div>
                        <table className="w-full border-collapse">
                          <thead>
                            <tr>
                              {['#','Latency','TTFT','Tok/s','Tokens','Status'].map(h => (
                                <th key={h} className="text-left px-2 py-1 font-mono text-[9px] text-ink-2 uppercase tracking-wider border-b border-border">{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {(results[s.model]?.runs || []).map((r, i) => (
                              <tr key={i} className="border-b border-border last:border-0">
                                <td className="px-2 py-1.5 font-mono text-[10px] text-ink-2">{i + 1}</td>
                                <td className="px-2 py-1.5 font-mono text-[10px] text-ink-1">{r.latencyMs}ms</td>
                                <td className="px-2 py-1.5 font-mono text-[10px] text-ink-2">{r.ttftMs != null ? r.ttftMs + 'ms' : '—'}</td>
                                <td className="px-2 py-1.5 font-mono text-[10px] text-teal">{r.tokensPerSec}</td>
                                <td className="px-2 py-1.5 font-mono text-[10px] text-ink-2">{r.tokenCount}</td>
                                <td className="px-2 py-1.5">
                                  {r.error
                                    ? <span className="font-mono text-[9px] text-crimson">{r.error.slice(0, 60)}</span>
                                    : <span className="font-mono text-[9px] text-jade">OK</span>
                                  }
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </Table>
        )
      }
    </div>
  )
}

// Mini latency distribution bar chart
function LatDist({ lats = [] }) {
  if (!lats.length) return <span className="text-ink-2 font-mono text-[10px]">—</span>
  const max = Math.max(...lats, 1)
  return (
    <div className="flex items-end gap-0.5 h-5">
      {lats.map((l, i) => {
        const h = Math.max(2, Math.round((l / max) * 20))
        const color = i === lats.indexOf(Math.min(...lats)) ? '#2fd87c'
                    : i === lats.indexOf(Math.max(...lats)) ? '#f05c5c'
                    : '#22d3c8'
        return (
          <div
            key={i}
            title={`${l}ms`}
            className="w-1.5 rounded-sm opacity-80 hover:opacity-100 transition-opacity"
            style={{ height: h, background: color }}
          />
        )
      })}
    </div>
  )
}
