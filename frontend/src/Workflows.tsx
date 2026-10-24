import { useCallback, useEffect, useState } from 'react'

type Incident = { id: string; title: string; service_name: string }
type Workflow = { id: string; incident_id: string; requester_id: string; action: string; state: string; phase: string; attempts: number; error_code: string | null; cancel_requested: boolean; created_at: string; diagnostics?: { metrics: { sample_id: string; at: string; errors: number; requests: number; p95_ms: number }[]; logs: { log_id: string; at: string; level: string; message: string }[] }; result?: { effect_id: string; simulated: boolean; message: string }; approval?: { id: string; plan: { action: string; service_id: string; incident_id: string; max_simulated_effects: number; description: string }; plan_hash: string; decision: string; approver_id: string | null } | null; events?: { id: string; type: string; detail: string; at: string }[] }
type ErrorBody = { error?: { message?: string } }

async function req<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1/workflows${path}`, {
    ...init, headers: { Authorization: `Bearer ${token}`, ...init?.headers },
  })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { message = ((await response.json()) as ErrorBody).error?.message || message } catch { /* non-JSON */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export default function Workflows({ token, userId, role, incidents }: { token: string; userId: string; role: string; incidents: Incident[] }) {
  const [incidentId, setIncidentId] = useState('')
  const [mine, setMine] = useState<Workflow[]>([])
  const [pending, setPending] = useState<Workflow[]>([])
  const [selected, setSelected] = useState<Workflow | null>(null)
  const [key, setKey] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const canRun = ['responder', 'approver', 'admin'].includes(role)
  const canApprove = ['approver', 'admin'].includes(role)

  useEffect(() => { if (!incidentId && incidents[0]) setIncidentId(incidents[0].id) }, [incidentId, incidents])
  const refresh = useCallback(async () => {
    const [own, queue] = await Promise.all([
      req<{ items: Workflow[] }>('', token),
      canApprove ? req<{ items: Workflow[] }>('/pending', token) : Promise.resolve({ items: [] }),
    ])
    setMine(own.items); setPending(queue.items)
  }, [token, canApprove])
  useEffect(() => { void refresh().catch(err => setError(err.message)) }, [refresh])
  useEffect(() => {
    const timer = window.setInterval(() => {
      void refresh().catch(() => { /* keep last visible state until a direct action */ })
      if (selected) void req<Workflow>(`/${selected.id}`, token).then(setSelected).catch(() => { /* direct open reports errors */ })
    }, 4000)
    return () => window.clearInterval(timer)
  }, [refresh, selected?.id, token])

  async function open(id: string) {
    setError(''); setNotice('')
    try { setSelected(await req<Workflow>(`/${id}`, token)) }
    catch (err) { setError((err as Error).message) }
  }
  async function create() {
    if (!incidentId) return
    const requestKey = key || crypto.randomUUID()
    setKey(requestKey); setBusy(true); setError(''); setNotice('')
    try {
      const result = await req<Workflow>(`/incidents/${incidentId}`, token, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': requestKey },
        body: JSON.stringify({ action: 'simulate_pool_refresh' }),
      })
      setSelected(result); setKey(null); await refresh()
      setNotice('Read-only diagnostics queued. Start the separate worker if it is not running.')
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  async function action(path: string, body?: object) {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await req<Workflow>(path, token, { method: 'POST',
        ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) })
      setSelected(result); await refresh()
      setNotice(result.state === 'queued' ? 'Approved. The worker will resume the exact plan.' : `Workflow ${result.state}.`)
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  const approval = selected?.approval
  return <div className="workflow-stack"><p className="intro">A separate worker gathers read-only diagnostics, pauses for a different approver, and records one simulated database outcome. No service is changed.</p>
    {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status" className="notice">{notice}</p>}
    <section className="panel"><h2>Create diagnostic workflow</h2>{!incidents.length ? <p className="empty">Replay the synthetic incident on Overview first.</p> : <div className="filterbar"><label>Incident<select value={incidentId} onChange={e => { setIncidentId(e.target.value); setKey(null) }}>{incidents.map(item => <option key={item.id} value={item.id}>{item.title} · {item.service_name}</option>)}</select></label>
      {canRun && <button disabled={busy || !incidentId} onClick={() => void create()}>Queue diagnostics</button>}</div>}
      <p className="subtext">The worker runs separately from the API. A responder can request; an approver or admin with service access must approve. You cannot approve your own request.</p></section>
    <div className="workflow-columns"><section className="panel"><h2>My workflows</h2>{!mine.length && <p className="empty">No workflows yet.</p>}<ul className="knowledge-results">{mine.map(item => <li key={item.id}><strong>{item.state}</strong><small>{new Date(item.created_at).toLocaleString()} · attempt {item.attempts}</small><button className="secondary" onClick={() => void open(item.id)}>Inspect</button></li>)}</ul></section>
      {canApprove && <section className="panel"><h2>Waiting for my approval</h2>{!pending.length && <p className="empty">No pending plans for your services.</p>}<ul className="knowledge-results">{pending.map(item => <li key={item.id}><strong>{item.action}</strong><small>Workflow {item.id.slice(0, 8)} · requester {item.requester_id.slice(0, 8)}</small><button className="secondary" onClick={() => void open(item.id)}>Review exact plan</button></li>)}</ul></section>}</div>
    {selected && <section className="panel"><div className="section-heading"><h2>Workflow detail</h2><span className="pill">{selected.state}</span></div><p>Phase: {selected.phase} · attempts: {selected.attempts} · ID: {selected.id}</p>
      {selected.error_code && <p role="status" className="error">{selected.error_code.replaceAll('_', ' ')}</p>}
      {selected.cancel_requested && <p className="notice">Cancellation requested. The worker will apply it before the simulated outcome.</p>}
      {selected.requester_id === userId && ['queued', 'running', 'awaiting_approval'].includes(selected.state) && <button className="secondary" disabled={busy} onClick={() => void action(`/${selected.id}/cancel`)}>Cancel</button>}
      {selected.diagnostics && <><h3>Read-only diagnostic snapshot</h3><p>{selected.diagnostics.metrics.length} metric windows · {selected.diagnostics.logs.length} recent logs</p><ul className="timeline">{selected.diagnostics.metrics.map(metric => <li key={metric.sample_id}><strong>{metric.errors}/{metric.requests} errors · p95 {metric.p95_ms} ms</strong><small>{new Date(metric.at).toLocaleString()}</small></li>)}</ul><ul className="timeline">{selected.diagnostics.logs.map(log => <li key={log.log_id}><strong>{log.level}: {log.message}</strong><small>{new Date(log.at).toLocaleString()}</small></li>)}</ul></>}
      {approval && <div className="approval-plan"><h3>Exact approval plan</h3><p><strong>{approval.plan.action}</strong> · {approval.decision}</p><p>{approval.plan.description}</p><p>Service: {approval.plan.service_id}<br />Incident: {approval.plan.incident_id}<br />Maximum simulated effects: {approval.plan.max_simulated_effects}</p><small>Plan hash: {approval.plan_hash}</small>
        {selected.state === 'awaiting_approval' && canApprove && selected.requester_id !== userId && <div className="actions"><button disabled={busy} onClick={() => void action(`/${selected.id}/decision`, { approval_id: approval.id, plan_hash: approval.plan_hash, decision: 'approved' })}>Approve exact plan</button><button className="secondary" disabled={busy} onClick={() => void action(`/${selected.id}/decision`, { approval_id: approval.id, plan_hash: approval.plan_hash, decision: 'rejected' })}>Reject</button></div>}</div>}
      {selected.result && <div className="notice"><strong>Simulated result</strong><p>{selected.result.message}</p><small>Effect ID: {selected.result.effect_id}</small></div>}
      <h3>Timeline</h3><ul className="timeline">{selected.events?.map(item => <li key={item.id}><strong>{item.type}: {item.detail}</strong><small>{new Date(item.at).toLocaleString()}</small></li>)}</ul></section>}
  </div>
}
