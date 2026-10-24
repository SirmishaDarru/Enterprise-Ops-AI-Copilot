import { useEffect, useState } from 'react'

type Incident = { id: string; title: string; service_name: string; status: string }
type Evidence = { id: string; kind: string; detail: string; occurred_at: string | null; source_url: string | null }
type Claim = { statement: string; evidence_ids: string[] }
type Hypothesis = Claim & { confidence: string; uncertainty: string }
type Recommendation = { action: string; reason: string; evidence_ids: string[]; requires_approval: boolean }
type Report = { summary: string; summary_evidence_ids: string[]; observations: Claim[]; hypotheses: Hypothesis[]; recommendations: Recommendation[]; gaps: string[] }
type Run = { id: string; incident_id: string; status: string; provider: string; model: string; error_code: string | null; input_tokens: number | null; output_tokens: number | null; cost_usd: string | null; latency_ms: number; created_at: string; report?: Report | null; evidence?: Evidence[] }
type ErrorBody = { error?: { message?: string } }

async function req<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { ...init, headers: { Authorization: `Bearer ${token}`, ...init?.headers } })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { message = ((await response.json()) as ErrorBody).error?.message || message } catch { /* non-JSON */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export default function Investigation({ token, role, incidents }: { token: string; role: string; incidents: Incident[] }) {
  const [incidentId, setIncidentId] = useState('')
  const [runs, setRuns] = useState<Run[]>([])
  const [run, setRun] = useState<Run | null>(null)
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(null)
  const [sourceText, setSourceText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { if (!incidentId && incidents[0]) setIncidentId(incidents[0].id) }, [incidentId, incidents])
  useEffect(() => {
    if (!incidentId) return
    let active = true
    setRun(null); setSelectedEvidence(null); setError('')
    req<{ items: Run[] }>(`/investigations/incidents/${incidentId}`, token)
      .then(data => { if (active) setRuns(data.items) })
      .catch(err => { if (active) setError(err.message) })
    return () => { active = false }
  }, [incidentId, token])

  async function open(id: string) {
    setError(''); setSelectedEvidence(null)
    try { setRun(await req<Run>(`/investigations/${id}`, token)) }
    catch (err) { setRun(null); setError((err as Error).message) }
  }
  async function generate() {
    setBusy(true); setError(''); setSelectedEvidence(null)
    try {
      const result = await req<Run>(`/investigations/incidents/${incidentId}`, token, { method: 'POST' })
      setRun(result)
      setRuns(old => [result, ...old])
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  async function cite(id: string) {
    const item = run?.evidence?.find(e => e.id === id)
    if (!item) { setError('Evidence item no longer available.'); return }
    setSelectedEvidence(item); setSourceText(''); setError('')
    if (item.source_url) {
      try { const result = await req<{ content: string }>(item.source_url.replace('/api/v1', ''), token); setSourceText(result.content) }
      catch (err) { setError((err as Error).message) }
    }
  }
  const citations = (ids: string[]) => <span className="citations">{ids.map(id => <button key={id} type="button" className="secondary" onClick={() => void cite(id)}>{id.split(':')[0]} · {id.split(':')[1].slice(0, 8)}</button>)}</span>
  return <div className="investigation-stack"><p className="intro">Reports separate observed evidence from unverified hypotheses. The local demo provider is deterministic. No diagnostic or operational action is executed.</p>
    {error && <p role="alert" className="error">{error}</p>}
    <section className="panel"><h2>Investigate an incident</h2>{!incidents.length ? <p className="empty">Replay the synthetic failure on Overview to create an incident.</p> : <div className="filterbar"><label>Incident<select value={incidentId} onChange={e => setIncidentId(e.target.value)}>{incidents.map(item => <option key={item.id} value={item.id}>{item.title} · {item.service_name} · {item.status}</option>)}</select></label>
      {['responder', 'approver', 'admin'].includes(role) && <button disabled={busy || !incidentId} onClick={() => void generate()}>{busy ? 'Investigating…' : 'Generate report'}</button>}</div>}
      <p className="subtext">Up to 10 reports per account per hour. Reports are visible only to their creator and require current service access.</p>
      <h3>My reports</h3>{!runs.length && <p className="empty">No reports for this incident yet.</p>}
      <ul className="knowledge-results">{runs.map(item => <li key={item.id}><strong>{item.status} · {item.provider}</strong><small>{new Date(item.created_at).toLocaleString()} · {item.latency_ms} ms · {item.model}</small><button className="secondary" onClick={() => void open(item.id)}>Open report</button></li>)}</ul></section>
    {run && <section className="panel"><div className="section-heading"><h2>Investigation report</h2><span className="pill">{run.status}</span></div>
      <p className="subtext">Provider: {run.provider} / {run.model} · {run.latency_ms} ms · input/output tokens: {run.input_tokens ?? 'unknown'} / {run.output_tokens ?? 'unknown'} · estimated cost: {run.cost_usd === null ? 'unavailable' : `$${run.cost_usd}`}</p>
      {run.provider === 'mock' && <p className="notice">Deterministic synthetic demonstration, not a live model analysis.</p>}
      {run.error_code && <p role="status" className="error">{run.error_code.replaceAll('_', ' ')}. Review the evidence and configuration before trying again.</p>}
      {run.report && <><h3>Summary</h3><p>{run.report.summary}</p>{citations(run.report.summary_evidence_ids)}
        <h3>Observations</h3>{run.report.observations.map((item, i) => <div className="report-item" key={i}><p>{item.statement}</p>{citations(item.evidence_ids)}</div>)}
        <h3>Hypotheses · unverified</h3>{run.report.hypotheses.length ? run.report.hypotheses.map((item, i) => <div className="report-item" key={i}><p><strong>{item.confidence} confidence:</strong> {item.statement}</p><p>Uncertainty: {item.uncertainty}</p>{citations(item.evidence_ids)}</div>) : <p>No supported hypothesis.</p>}
        <h3>Recommended read-only checks</h3>{run.report.recommendations.map((item, i) => <div className="report-item" key={i}><p>{item.action}</p><p>{item.reason}</p>{citations(item.evidence_ids)}</div>)}
        <h3>Evidence gaps</h3><ul>{run.report.gaps.map((gap, i) => <li key={i}>{gap}</li>)}</ul></>}
      {run.evidence && <><h3>Evidence inspector</h3><p className="subtext">Select a citation above to see the collected item. Document passages are checked again against current permissions.</p>
        {selectedEvidence ? <div className="source-inspector"><strong>{selectedEvidence.kind}</strong><small>{selectedEvidence.id}{selectedEvidence.occurred_at ? ` · ${new Date(selectedEvidence.occurred_at).toLocaleString()}` : ''}</small><p>{selectedEvidence.detail}</p>{sourceText && <><h4>Current source passage</h4><p>{sourceText}</p></>}</div> : <p className="empty">Select a citation.</p>}</>}
    </section>}
  </div>
}
