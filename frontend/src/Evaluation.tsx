import { useState } from 'react'

type Check = { id: string; category: string; passed: boolean; detail: string | object; latency_ms: number | null }
type Report = { dataset: { id: string; sha256: string; documents: number; queries: number }; run: { mode: string; provider: string; live_model_called: boolean }; checks: Check[]; metrics: { passed: number; total: number; retrieval: { status: string; reason?: string }; latency_ms: { median_ms: number | null }; usage: { input_tokens: number | null; cost_usd: string | null } }; human_review: { status: string }; limitations: string[] }
type ErrorBody = { error?: { message?: string } }

export default function Evaluation({ token, role }: { token: string; role: string }) {
  const [report, setReport] = useState<Report | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function run() {
    setBusy(true); setError('')
    try {
      const response = await fetch('/api/v1/evaluation/offline', { headers: { Authorization: `Bearer ${token}` } })
      if (!response.ok) {
        let message = `Evaluation failed (${response.status})`
        try { message = ((await response.json()) as ErrorBody).error?.message || message } catch { /* non-JSON */ }
        throw new Error(message)
      }
      setReport(await response.json() as Report)
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  return <div className="evaluation-stack"><p className="intro">Deterministic checks for citations, ambiguity, injection attempts, failure handling, and plan integrity. The PostgreSQL retrieval evaluation runs separately from a terminal.</p>
    {role === 'admin' ? <button disabled={busy} onClick={() => void run()}>{busy ? 'Running checks…' : 'Run offline evaluation'}</button> : <p className="panel">An admin can run the offline evaluation. The README includes the PostgreSQL command.</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {report && <><section className="panel"><h2>{report.metrics.passed}/{report.metrics.total} checks passed</h2><p>Dataset: {report.dataset.id} · {report.dataset.documents} documents · {report.dataset.queries} labelled queries</p><small>SHA-256: {report.dataset.sha256}</small><p>Provider: {report.run.provider} · mode: {report.run.mode} · live model called: {String(report.run.live_model_called)}</p><p>Retrieval: {report.metrics.retrieval.status} · {report.metrics.retrieval.reason || ''}</p><p>Human review: {report.human_review.status} · token cost: {report.metrics.usage.cost_usd ?? 'unavailable'}</p></section>
      <section className="panel"><h2>Checks</h2><ul className="knowledge-results">{report.checks.map(item => <li key={item.id}><strong>{item.passed ? 'PASS' : 'FAIL'} · {item.id}</strong><small>{item.category} · {item.latency_ms ?? '—'} ms</small><p>{typeof item.detail === 'string' ? item.detail : JSON.stringify(item.detail)}</p></li>)}</ul></section>
      <section className="panel"><h2>Limits</h2><ul>{report.limitations.map(item => <li key={item}>{item}</li>)}</ul><p>Run the PostgreSQL mode from <code>backend</code> with <code>py -3.12 -m uv run --frozen python -m app.evaluation.run --mode postgres --output ../evaluation-postgres.json</code> after migration.</p></section></>}
  </div>
}
