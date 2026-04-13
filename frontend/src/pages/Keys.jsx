import { useState, useEffect } from 'react'
import { Copy, Plus, X, ToggleLeft, ToggleRight, Trash2 } from 'lucide-react'
import { Card, SectionTitle, FormGroup, Input, Btn, Table, Th, Td, Tr, Badge, Empty } from '../components/ui'
import { getKeys, api } from '../lib/api'
import { timeSince } from '../lib/utils'

export default function Keys({ toast }) {
  const [keys, setKeys]         = useState([])
  const [name, setName]         = useState('')
  const [rpm, setRpm]           = useState('0')
  const [creating, setCreating] = useState(false)
  const [newKey, setNewKey]     = useState(null)

  const load = async () => {
    try { const d = await getKeys(); setKeys(d.keys || []) }
    catch (e) { toast(e.message, 'err') }
  }

  useEffect(() => { load() }, [])

  const create = async () => {
    if (!name.trim()) return toast('Enter a name', 'err')
    setCreating(true)
    try {
      const d = await api('/api/auth/keys', {
        method: 'POST',
        body: JSON.stringify({ name: name.trim(), rate_limit_rpm: parseInt(rpm) || 0 }),
      })
      setNewKey(d.key)
      setName('')
      toast('Key created — copy it now!', 'ok')
      load()
    } catch (e) { toast(e.message, 'err') }
    finally { setCreating(false) }
  }

  const revoke = async (n) => {
    try { await api(`/api/auth/keys/${n}/revoke`, { method: 'POST' }); toast(`Revoked: ${n}`, 'ok'); load() }
    catch (e) { toast(e.message, 'err') }
  }
  const enable = async (n) => {
    try { await api(`/api/auth/keys/${n}/enable`, { method: 'POST' }); toast(`Enabled: ${n}`, 'ok'); load() }
    catch (e) { toast(e.message, 'err') }
  }
  const del = async (n) => {
    if (!confirm(`Permanently delete key "${n}"?`)) return
    try { await api(`/api/auth/keys/${n}`, { method: 'DELETE' }); toast(`Deleted: ${n}`, 'ok'); load() }
    catch (e) { toast(e.message, 'err') }
  }

  return (
    <div className="animate-fade-in">
      <SectionTitle>Create key</SectionTitle>
      <Card className="p-4 mb-1">
        <div className="flex flex-wrap gap-3 items-end">
          <FormGroup label="Name">
            <Input value={name} onChange={e => setName(e.target.value)} onKeyDown={e => e.key==='Enter'&&create()} placeholder="prod-app, laptop-dev …" className="w-48" />
          </FormGroup>
          <FormGroup label="Rate limit (rpm)">
            <Input value={rpm} onChange={e => setRpm(e.target.value)} type="number" placeholder="0 = unlimited" className="w-32" />
          </FormGroup>
          <Btn variant="jade" onClick={create} disabled={creating} className="self-end">
            <Plus size={12} /> {creating ? 'Creating…' : 'Create'}
          </Btn>
        </div>

        {newKey && (
          <div className="mt-4 p-3 bg-bg-0 border border-jade/30 rounded">
            <div className="font-mono text-[9px] text-jade tracking-widest mb-2">
              KEY CREATED — COPY NOW, NOT SHOWN AGAIN
            </div>
            <div className="font-mono text-[12px] text-ink-0 break-all">{newKey}</div>
            <div className="flex gap-2 mt-2">
              <Btn size="sm" variant="ghost" onClick={() => { navigator.clipboard.writeText(newKey); toast('Copied!', 'ok') }}>
                <Copy size={11} /> Copy
              </Btn>
              <Btn size="sm" variant="ghost" onClick={() => setNewKey(null)}>
                <X size={11} /> Dismiss
              </Btn>
            </div>
          </div>
        )}
      </Card>

      <SectionTitle>Active keys</SectionTitle>
      {keys.length === 0
        ? <Empty message="No API keys" />
        : (
          <Table>
            <thead>
              <tr>
                <Th>Name</Th><Th>Hint</Th><Th>Status</Th><Th>RPM</Th>
                <Th>Requests</Th><Th>Last used</Th><Th>Created</Th><Th>Actions</Th>
              </tr>
            </thead>
            <tbody>
              {keys.map(k => (
                <Tr key={k.name}>
                  <Td className="text-ink-0 font-medium">{k.name}</Td>
                  <Td className="text-ink-2">{k.key_hint}…</Td>
                  <Td><Badge variant={k.enabled ? 'green' : 'red'}>{k.enabled ? 'ACTIVE' : 'REVOKED'}</Badge></Td>
                  <Td className="text-ink-2">{k.rate_limit_rpm > 0 ? k.rate_limit_rpm + ' rpm' : '∞'}</Td>
                  <Td>{k.request_count ?? 0}</Td>
                  <Td className="text-ink-2">{timeSince(k.last_used)}</Td>
                  <Td className="text-ink-2">{k.created_at ? new Date(k.created_at).toLocaleDateString() : '—'}</Td>
                  <Td>
                    <div className="flex gap-1.5">
                      {k.enabled
                        ? <Btn size="sm" variant="amber" onClick={() => revoke(k.name)}>Revoke</Btn>
                        : <Btn size="sm" variant="jade"  onClick={() => enable(k.name)}>Enable</Btn>
                      }
                      <Btn size="sm" variant="crimson" onClick={() => del(k.name)}>
                        <Trash2 size={10} />
                      </Btn>
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
