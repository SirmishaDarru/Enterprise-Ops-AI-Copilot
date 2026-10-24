import { FormEvent, useEffect, useState } from 'react'
import Knowledge from './Knowledge'
import Investigation from './Investigation'
import Workflows from './Workflows'
import Evaluation from './Evaluation'

type User = { id: string; email: string; role: string }
type Metric = { id: string; observed_at: string; request_count: number; error_count: number; error_rate_percent: number; latency_p95_ms: number; source: string }
type Service = { id: string; name: string; description: string; depends_on: string[] }
type Card = { id: string; name: string; description: string; latest: Metric | null; active_incidents: number; source: string }
type Incident = { id: string; service_id: string; service_name: string; title: string; status: string; severity: string; created_at: string; synthetic: boolean }
type TimelineEvent = { id: string; occurred_at: string; type: string; message: string }
type Detail = Incident & { timeline: TimelineEvent[]; alerts: { id: string; sample_id: string; occurred_at: string; observed_percent: number }[] }
type Log = { id: string; occurred_at: string; level: string; message: string; source: string }
type Rule = { id: string; service_id: string; name: string; threshold_percent: number; enabled: boolean }
type Page<T> = { items: T[]; next_cursor: string | null }
type ApiError = { error?: { message?: string } }

async function api<T>(path: string, token?: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init?.headers },
  })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { message = ((await response.json()) as ApiError).error?.message || message } catch { /* non-JSON response */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

const when = (value: string) => new Date(value).toLocaleString()
const params = (values: Record<string, string>) => new URLSearchParams(values).toString()

function ErrorRateChart({ points }: { points: Metric[] }) {
  if (!points.length) return <p className="empty">No metric samples yet.</p>
  const xy = points.map((m, i) => `${24 + i * 540 / Math.max(points.length - 1, 1)},${170 - m.error_rate_percent * 1.45}`).join(' ')
  return <figure className="chart"><svg viewBox="0 0 590 195" role="img" aria-label="Synthetic error rate percent over sample windows">
    <line x1="24" y1="170" x2="564" y2="170" stroke="#526582" /><line x1="24" y1="25" x2="24" y2="170" stroke="#526582" />
    <text x="2" y="30">100%</text><text x="6" y="166">0%</text><polyline points={xy} fill="none" stroke="#60dac2" strokeWidth="4" strokeLinejoin="round" />
    {points.map((m, i) => <circle key={m.id} cx={24 + i * 540 / Math.max(points.length - 1, 1)} cy={170 - m.error_rate_percent * 1.45} r="3" fill="#60dac2" />)}
  </svg><figcaption>Error rate per collected sample · {when(points[0].observed_at)} to {when(points[points.length - 1].observed_at)}</figcaption></figure>
}

export default function App() {
  const [token, setToken] = useState<string | null>(() => sessionStorage.getItem('ops_token'))
  const [user, setUser] = useState<User | null>(null)
  const [email, setEmail] = useState('viewer@local.example')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(Boolean(token))
  const [view, setView] = useState<'overview' | 'incidents' | 'knowledge' | 'investigations' | 'workflows' | 'evaluation'>('overview')
  const [cards, setCards] = useState<Card[]>([])
  const [services, setServices] = useState<Service[]>([])
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [incidentCursor, setIncidentCursor] = useState<string | null>(null)
  const [incidentStatus, setIncidentStatus] = useState('')
  const [incidentSearch, setIncidentSearch] = useState('')
  const [incidentInput, setIncidentInput] = useState('')
  const [rules, setRules] = useState<Rule[]>([])
  const [serviceId, setServiceId] = useState('')
  const [metrics, setMetrics] = useState<Metric[]>([])
  const [logs, setLogs] = useState<Log[]>([])
  const [logCursor, setLogCursor] = useState<string | null>(null)
  const [logInput, setLogInput] = useState('')
  const [logSearch, setLogSearch] = useState('')
  const [logLevel, setLogLevel] = useState('')
  const [selectedIncident, setSelectedIncident] = useState('')
  const [detail, setDetail] = useState<Detail | null>(null)
  const [timelineInput, setTimelineInput] = useState('')
  const [timelineSearch, setTimelineSearch] = useState('')
  const [timelineEvents, setTimelineEvents] = useState<TimelineEvent[]>([])
  const [timelineCursor, setTimelineCursor] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const [liveFailure, setLiveFailure] = useState<boolean | null>(null)
  const [liveBusy, setLiveBusy] = useState(false)

  useEffect(() => {
    if (!token) { setUser(null); setBusy(false); return }
    let active = true
    api<User>('/auth/me', token).then(data => { if (active) setUser(data) }).catch(err => {
      if (active) { sessionStorage.removeItem('ops_token'); setToken(null); setError(err.message) }
    }).finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [token])

  async function refreshOverview(auth = token!) {
    setBusy(true); setError('')
    try {
      const [dashboard, serviceList, incidentPage, ruleList] = await Promise.all([
        api<{ services: Card[] }>('/dashboard', auth), api<{ items: Service[] }>('/services', auth),
        api<Page<Incident>>('/incidents?limit=30', auth), api<{ items: Rule[] }>('/alerts/rules', auth),
      ])
      setCards(dashboard.services); setServices(serviceList.items); setIncidents(incidentPage.items)
      setIncidentCursor(incidentPage.next_cursor); setRules(ruleList.items)
      setServiceId(current => current || serviceList.items[0]?.id || '')
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  useEffect(() => { if (token && user) void refreshOverview(token) }, [token, user])
  useEffect(() => {
    if (!token || user?.role !== 'admin') { setLiveFailure(null); return }
    api<{ failure_enabled: boolean }>('/live-demo/status', token)
      .then(result => setLiveFailure(result.failure_enabled)).catch(() => setLiveFailure(null))
  }, [token, user])

  useEffect(() => {
    if (!token || !serviceId) { setMetrics([]); setLogs([]); return }
    let active = true
    const query = params({ service_id: serviceId, limit: '30', ...(logSearch ? { q: logSearch } : {}), ...(logLevel ? { level: logLevel } : {}) })
    Promise.all([api<{ items: Metric[] }>(`/telemetry/metrics?service_id=${serviceId}`, token), api<Page<Log>>(`/telemetry/logs?${query}`, token)])
      .then(([samples, events]) => { if (active) { setMetrics(samples.items); setLogs(events.items); setLogCursor(events.next_cursor) } })
      .catch(err => { if (active) setError(err.message) })
    return () => { active = false }
  }, [token, serviceId, logSearch, logLevel])

  useEffect(() => {
    if (!token || !selectedIncident) { setDetail(null); return }
    let active = true
    api<Detail>(`/incidents/${selectedIncident}`, token).then(data => { if (active) setDetail(data) })
      .catch(err => { if (active) setError(err.message) })
    return () => { active = false }
  }, [token, selectedIncident])

  useEffect(() => {
    if (!token || !selectedIncident) { setTimelineEvents([]); return }
    let active = true
    const qs = params({ limit: '30', ...(timelineSearch ? { q: timelineSearch } : {}) })
    api<Page<TimelineEvent>>(`/incidents/${selectedIncident}/events?${qs}`, token)
      .then(result => { if (active) { setTimelineEvents(result.items); setTimelineCursor(result.next_cursor) } })
      .catch(err => { if (active) setError(err.message) })
    return () => { active = false }
  }, [token, selectedIncident, timelineSearch])

  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const form = new URLSearchParams({ username: email, password })
      const result = await api<{ access_token: string }>('/auth/token', undefined, {
        method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: form,
      })
      sessionStorage.setItem('ops_token', result.access_token); setToken(result.access_token); setPassword('')
    } catch (err) { setError((err as Error).message); setBusy(false) }
  }

  function logout() { sessionStorage.removeItem('ops_token'); setToken(null); setUser(null); setCards([]); setError(''); setNotice('') }

  async function loadLiveRunbook() {
    setError('')
    try {
      await api('/knowledge/live-demo/runbook', token!, { method: 'POST' })
      setNotice('Live checkout runbook ready. Open Knowledge to inspect its source.')
    } catch (err) { setError((err as Error).message) }
  }

  async function setLiveMode(enabled: boolean) {
    setLiveBusy(true); setError(''); setNotice('')
    try {
      const result = await api<{ failure_enabled: boolean }>('/live-demo/failure', token!, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }),
      })
      setLiveFailure(result.failure_enabled)
      setNotice(enabled ? 'Checkout is returning HTTP 503. Wait about 10 seconds, then refresh to see collected samples and the incident.'
                        : 'Checkout is healthy again. Refresh after about 10 seconds; resolve the incident separately when reviewed.')
    } catch (err) { setError((err as Error).message) } finally { setLiveBusy(false) }
  }

  async function replay() {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await api<{ incident_ids: string[] }>('/demo/replay', token!, { method: 'POST' })
      await refreshOverview()
      setNotice('Synthetic failure replayed. Repeating it will not duplicate the alert samples.')
      if (result.incident_ids[0]) { setSelectedIncident(result.incident_ids[0]); setDetail(await api<Detail>(`/incidents/${result.incident_ids[0]}`, token!)); setView('incidents') }
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  async function searchIncidents(event: FormEvent) {
    event.preventDefault(); setIncidentSearch(incidentInput)
    await loadIncidents(incidentStatus, incidentInput)
  }

  async function loadIncidents(status: string, query: string, cursor?: string) {
    try {
      const qs = params({ limit: '30', ...(status ? { status } : {}), ...(query ? { q: query } : {}), ...(cursor ? { cursor } : {}) })
      const result = await api<Page<Incident>>(`/incidents?${qs}`, token!)
      setIncidents(old => cursor ? [...old, ...result.items] : result.items)
      setIncidentCursor(result.next_cursor)
    } catch (err) { setError((err as Error).message) }
  }

  async function moreLogs() {
    if (!logCursor) return
    try {
      const qs = params({ service_id: serviceId, limit: '30', cursor: logCursor, ...(logSearch ? { q: logSearch } : {}), ...(logLevel ? { level: logLevel } : {}) })
      const result = await api<Page<Log>>(`/telemetry/logs?${qs}`, token!)
      setLogs(old => [...old, ...result.items]); setLogCursor(result.next_cursor)
    } catch (err) { setError((err as Error).message) }
  }

  async function moreTimeline() {
    if (!timelineCursor) return
    try {
      const qs = params({ limit: '30', cursor: timelineCursor, ...(timelineSearch ? { q: timelineSearch } : {}) })
      const result = await api<Page<TimelineEvent>>(`/incidents/${selectedIncident}/events?${qs}`, token!)
      setTimelineEvents(old => [...old, ...result.items]); setTimelineCursor(result.next_cursor)
    } catch (err) { setError((err as Error).message) }
  }

  async function setStatus(status: 'investigating' | 'resolved') {
    try {
      await api(`/incidents/${selectedIncident}/status`, token!, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) })
      setDetail(await api<Detail>(`/incidents/${selectedIncident}`, token!)); await refreshOverview()
      const events = await api<Page<TimelineEvent>>(`/incidents/${selectedIncident}/events?limit=30`, token!)
      setTimelineEvents(events.items); setTimelineCursor(events.next_cursor)
      setNotice(`Incident moved to ${status}.`)
      setTimelineSearch(''); setTimelineInput('')
    } catch (err) { setError((err as Error).message) }
  }

  async function saveRule(rule: Rule, threshold: number) {
    try {
      await api(`/alerts/rules/${rule.id}`, token!, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ threshold_percent: threshold, enabled: rule.enabled }) })
      setRules(old => old.map(item => item.id === rule.id ? { ...item, threshold_percent: threshold } : item))
      setNotice('Threshold saved. Evaluate the rule to apply it to existing samples.')
    } catch (err) { setError((err as Error).message) }
  }

  async function evaluateRule(rule: Rule) {
    try {
      const result = await api<{ incident_ids: string[] }>(`/alerts/rules/${rule.id}/evaluate`, token!, { method: 'POST' })
      await refreshOverview()
      setNotice(`Evaluated existing samples. ${result.incident_ids.length} incident matched.`)
    } catch (err) { setError((err as Error).message) }
  }

  if (!token) return <main className="login-layout"><header className="brand"><div className="mark">OC</div><div><h1>Operations Copilot</h1><p>Engineering operations · local demo</p></div></header>
    {error && <p role="alert" className="error">{error}</p>}
    <section className="panel login-panel"><h2>Sign in</h2><p>Explore a local checkout service and a separate synthetic fixture.</p>
      <form onSubmit={login}><label>Email<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} /></label>
        <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>
        <button type="submit" disabled={busy}>Sign in</button></form><small>Use a seeded local account and its password.</small></section></main>

  return <div className="app"><aside className="sidebar"><div className="brand"><div className="mark">OC</div><div><strong>Ops Copilot</strong><small>Local demo</small></div></div>
    <nav aria-label="Main navigation"><button aria-current={view === 'overview' ? 'page' : undefined} className={view === 'overview' ? 'active' : ''} onClick={() => setView('overview')}>Overview</button><button aria-current={view === 'incidents' ? 'page' : undefined} className={view === 'incidents' ? 'active' : ''} onClick={() => setView('incidents')}>Incidents</button><button aria-current={view === 'knowledge' ? 'page' : undefined} className={view === 'knowledge' ? 'active' : ''} onClick={() => setView('knowledge')}>Knowledge</button><button aria-current={view === 'investigations' ? 'page' : undefined} className={view === 'investigations' ? 'active' : ''} onClick={() => setView('investigations')}>Investigations</button><button aria-current={view === 'workflows' ? 'page' : undefined} className={view === 'workflows' ? 'active' : ''} onClick={() => setView('workflows')}>Workflows</button><button aria-current={view === 'evaluation' ? 'page' : undefined} className={view === 'evaluation' ? 'active' : ''} onClick={() => setView('evaluation')}>Evaluation</button></nav>
    <div className="account"><small>{user?.email || 'Loading account…'}</small><p>{user?.role || ''}</p><button className="secondary" onClick={logout}>Sign out</button></div></aside>
    <main className="content"><div className="topline"><div><p className="eyebrow">DEMO OPERATIONS DATA</p><h1>{view === 'overview' ? 'Service health' : view === 'incidents' ? 'Incidents' : view === 'knowledge' ? 'Knowledge' : view === 'investigations' ? 'Investigations' : view === 'workflows' ? 'Workflows' : 'Evaluation'}</h1></div><button className="secondary" onClick={() => void refreshOverview()} disabled={busy}>Refresh</button></div>
      {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status" className="notice">{notice}</p>}{busy && <p role="status">Loading…</p>}
      {view === 'evaluation' && <Evaluation token={token} role={user?.role || ''} />}
      {view === 'workflows' && <Workflows token={token} userId={user?.id || ''} role={user?.role || ''} incidents={incidents} />}
      {view === 'investigations' && <Investigation token={token} role={user?.role || ''} incidents={incidents} />}
      {view === 'knowledge' && <Knowledge token={token} role={user?.role || ''} services={services} />}
      {view === 'overview' && <>
        <div className="intro"><p>The live checkout demo records actual local HTTP responses; the older replay fixture is deterministic and synthetic. Neither is production telemetry. A deployment marker is correlation, not proof of cause.</p>
          {user?.role === 'admin' && <button onClick={() => void replay()} disabled={busy}>Replay synthetic failure</button>}</div>
        {user?.role === 'admin' && <section className="panel"><h2>Live checkout service</h2><p>Steady traffic is sent to a separate local HTTP service. Enable a controlled 503 failure, wait about 10 seconds, then refresh. The collector records observed batches, error logs and an alert. Clearing the failure does not automatically resolve the incident.</p><p role="status">{liveFailure === null ? 'Live service unavailable or still starting.' : liveFailure ? 'Failure mode: ON' : 'Failure mode: OFF'}</p><div className="actions"><button className="secondary" disabled={liveFailure === null} onClick={() => void loadLiveRunbook()}>Load live runbook</button><button disabled={liveBusy || liveFailure === null || liveFailure} onClick={() => void setLiveMode(true)}>Trigger checkout failure</button><button className="secondary" disabled={liveBusy || liveFailure === null || !liveFailure} onClick={() => void setLiveMode(false)}>Restore checkout</button></div></section>}
        {!cards.length && !busy && <div className="panel empty">No services yet. {user?.role === 'admin' ? 'Replay the synthetic failure to create the fixture.' : 'Ask a local admin to load the demo fixture.'}</div>}
        <div className="cards">{cards.map(card => <button key={card.id} aria-pressed={serviceId === card.id} className={`service-card ${serviceId === card.id ? 'selected' : ''}`} onClick={() => setServiceId(card.id)}><span className="card-top"><strong>{card.name}</strong><em>{card.active_incidents ? `${card.active_incidents} active incident` : 'No active incidents'}</em></span><span className="subtext">{card.description}</span><span className="stats"><span><b>{card.latest?.error_rate_percent ?? '—'}%</b>Error rate</span><span><b>{card.latest?.latency_p95_ms ?? '—'} ms</b>P95 latency</span><span><b>{card.latest?.request_count ?? '—'}</b>Requests/min</span></span><small>{card.source === 'live_demo' ? 'Observed local HTTP batch' : 'Synthetic sample'}: {card.latest ? when(card.latest.observed_at) : 'none'}</small></button>)}</div>
        {serviceId && <><section className="panel"><div className="section-heading"><h2>Error rate</h2><span className="pill">{cards.find(card => card.id === serviceId)?.source === 'live_demo' ? 'Observed local HTTP demo' : 'Synthetic fixture'}</span></div><ErrorRateChart points={metrics} />
          {services.find(s => s.id === serviceId)?.depends_on.length ? <p className="subtext">Depends on: {services.find(s => s.id === services.find(v => v.id === serviceId)?.depends_on[0])?.name || 'service'}</p> : null}</section>
          <section className="panel"><h2>Search logs</h2><form className="filterbar" onSubmit={e => { e.preventDefault(); setLogSearch(logInput) }}><label>Message<input value={logInput} onChange={e => setLogInput(e.target.value)} placeholder="connection pool" /></label><label>Level<select value={logLevel} onChange={e => setLogLevel(e.target.value)}><option value="">All</option><option>ERROR</option><option>WARN</option><option>INFO</option></select></label><button type="submit">Search</button></form>
            {!logs.length && <p className="empty">No matching logs.</p>}<ul className="event-list">{logs.map(log => <li key={log.id}><time>{when(log.occurred_at)}</time><span className={`level ${log.level.toLowerCase()}`}>{log.level}</span><span>{log.message}</span></li>)}</ul>{logCursor && <button className="secondary" onClick={() => void moreLogs()}>More logs</button>}</section>
          {rules.filter(r => r.service_id === serviceId).map(rule => <RulePanel key={rule.id} rule={rule} canEdit={user?.role === 'admin'} canEvaluate={Boolean(user && ['admin', 'approver', 'responder'].includes(user.role))} onSave={saveRule} onEvaluate={evaluateRule} />)}</>}
      </>}
      {view === 'incidents' && <><form className="filterbar" onSubmit={e => void searchIncidents(e)}><label>Search title<input value={incidentInput} onChange={e => setIncidentInput(e.target.value)} placeholder="error rate" /></label><label>Status<select value={incidentStatus} onChange={e => { setIncidentStatus(e.target.value); void loadIncidents(e.target.value, incidentSearch) }}><option value="">All</option><option value="open">Open</option><option value="investigating">Investigating</option><option value="resolved">Resolved</option></select></label><button type="submit">Search</button></form>
        <div className="incident-layout"><section className="panel"><h2>Incident list</h2>{!incidents.length && !busy && <p className="empty">No incidents match. An admin can replay the synthetic failure from Overview.</p>}<ul className="incident-list">{incidents.map(incident => <li key={incident.id}><button aria-pressed={selectedIncident === incident.id} className={selectedIncident === incident.id ? 'selected' : ''} onClick={() => setSelectedIncident(incident.id)}><span className="card-top"><strong>{incident.title}</strong><em>{incident.status}</em></span><small>{incident.service_name} · {when(incident.created_at)} · {incident.synthetic ? 'synthetic fixture' : 'observed local HTTP demo'}</small></button></li>)}</ul>{incidentCursor && <button className="secondary" onClick={() => void loadIncidents(incidentStatus, incidentSearch, incidentCursor)}>More incidents</button>}</section>
          <section className="panel detail"><h2>Incident detail</h2>{!selectedIncident && <p className="empty">Select an incident to inspect its alerts and timeline.</p>}{selectedIncident && !detail && <p>Loading incident…</p>}{detail && <><span className="pill">{detail.status}</span><h3>{detail.title}</h3><p>{detail.service_name} · {detail.severity} · {detail.synthetic ? 'synthetic fixture' : 'observed local HTTP demo'}</p>
            {user && ['responder', 'approver', 'admin'].includes(user.role) && <div className="actions">{detail.status === 'open' && <button onClick={() => void setStatus('investigating')}>Start investigating</button>}{detail.status !== 'resolved' && <button className="secondary" onClick={() => void setStatus('resolved')}>Resolve incident</button>}</div>}
            <h4>Threshold alerts</h4>{!detail.alerts.length && <p className="empty">No alerts.</p>}<ul className="timeline">{detail.alerts.map(alert => <li key={alert.id}><strong>{alert.observed_percent}% error rate</strong><small>{when(alert.occurred_at)} · sample {alert.sample_id.slice(0, 8)}</small></li>)}</ul>
            <h4>Timeline</h4><form className="filterbar" onSubmit={e => { e.preventDefault(); setTimelineSearch(timelineInput) }}><label>Search timeline<input value={timelineInput} onChange={e => setTimelineInput(e.target.value)} placeholder="threshold" /></label><button type="submit">Search</button></form>
            {!timelineEvents.length && <p className="empty">No matching timeline events.</p>}<ul className="timeline">{timelineEvents.map(event => <li key={event.id}><strong>{event.message}</strong><small>{when(event.occurred_at)} · {event.type}</small></li>)}</ul>{timelineCursor && <button className="secondary" onClick={() => void moreTimeline()}>More events</button>}
            <button className="secondary" onClick={() => { setServiceId(detail.service_id); setView('overview') }}>Inspect supporting telemetry</button></>}</section></div></>}
    </main></div>
}

function RulePanel({ rule, canEdit, canEvaluate, onSave, onEvaluate }: { rule: Rule; canEdit: boolean; canEvaluate: boolean; onSave: (rule: Rule, threshold: number) => Promise<void>; onEvaluate: (rule: Rule) => Promise<void> }) {
  const [threshold, setThreshold] = useState(rule.threshold_percent)
  useEffect(() => setThreshold(rule.threshold_percent), [rule.threshold_percent])
  return <section className="panel"><div className="section-heading"><h2>{rule.name}</h2><span className="pill">{rule.enabled ? 'Enabled' : 'Disabled'}</span></div><p>Alert when a collected sample reaches {rule.threshold_percent}% errors. Repeated breaches join the same active incident.</p>
    {canEdit && <form className="filterbar" onSubmit={e => { e.preventDefault(); void onSave(rule, threshold) }}><label>Threshold (%)<input type="number" min="1" max="100" value={threshold} onChange={e => setThreshold(Number(e.target.value))} /></label><button type="submit">Save threshold</button></form>}{canEvaluate && <button className="secondary" onClick={() => void onEvaluate(rule)}>Evaluate existing samples</button>}</section>
}
