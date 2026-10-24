import { FormEvent, useCallback, useEffect, useState } from 'react'

type Service = { id: string; name: string }
type Doc = { id: string; title: string; kind: string; filename: string; version: number; allowed_roles: string[]; service_id: string }
type Hit = { source_id: string; title: string; snippet: string; filename: string; page_number: number | null; ordinal: number; version: number }
type Source = { id: string; title: string; filename: string; page_number: number | null; ordinal: number; version: number; content: string }
type ErrorBody = { error?: { message?: string } }

async function req<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1/knowledge${path}`, { ...init, headers: { Authorization: `Bearer ${token}`, ...init?.headers } })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { message = ((await response.json()) as ErrorBody).error?.message || message } catch { /* response not JSON */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export default function Knowledge({ token, role, services }: { token: string; role: string; services: Service[] }) {
  const [docs, setDocs] = useState<Doc[]>([])
  const [query, setQuery] = useState('connection pool exhausted')
  const [hits, setHits] = useState<Hit[]>([])
  const [source, setSource] = useState<Source | null>(null)
  const [model, setModel] = useState('')
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState('runbook')
  const [serviceId, setServiceId] = useState('')
  const [roles, setRoles] = useState<string[]>(['viewer', 'responder', 'approver', 'admin'])
  const [file, setFile] = useState<File | null>(null)
  const [editing, setEditing] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const refresh = useCallback(async () => setDocs((await req<{ items: Doc[] }>('/documents', token)).items), [token])
  useEffect(() => { void refresh().catch(err => setError(err.message)) }, [refresh])
  useEffect(() => { if (!serviceId && services[0]) setServiceId(services[0].id) }, [services, serviceId])

  async function search(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setSource(null)
    try {
      const data = await req<{ items: Hit[]; embedding_model: string }>(`/search?${new URLSearchParams({ q: query })}`, token)
      setHits(data.items); setModel(data.embedding_model)
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  async function inspect(id: string) {
    try { setSource(await req<Source>(`/sources/${id}`, token)) }
    catch (err) { setError((err as Error).message) }
  }
  async function upload(event: FormEvent) {
    event.preventDefault()
    if (!file) { setError('Choose a file.'); return }
    setBusy(true); setError(''); setNotice('')
    const form = new FormData()
    form.set('title', title); form.set('kind', kind); form.set('allowed_roles', roles.join(','))
    if (!editing) form.set('service_id', serviceId)
    form.set('file', file)
    try {
      await req(`/documents${editing ? `/${editing}` : ''}`, token, { method: editing ? 'PUT' : 'POST', body: form })
      await refresh(); setTitle(''); setFile(null); setEditing(''); setHits([]); setSource(null)
      const input = document.getElementById('knowledge-file') as HTMLInputElement | null
      if (input) input.value = ''
      setNotice('Document indexed. Search again to see current passages.')
    } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  async function action(path: string, method: string, message: string) {
    setBusy(true); setError(''); setNotice('')
    try { await req(path, token, { method }); await refresh(); setHits([]); setSource(null); setNotice(message) }
    catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }
  function edit(doc: Doc) {
    setEditing(doc.id); setTitle(doc.title); setKind(doc.kind); setServiceId(doc.service_id); setRoles(doc.allowed_roles)
    setNotice('Choose a replacement file to replace the indexed passages.')
  }
  return <div className="knowledge-stack"><p className="intro">Search approved runbooks, service notes, and postmortems. Access follows service membership and document role.</p>
    {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status" className="notice">{notice}</p>}
    <section className="panel"><h2>Search knowledge</h2><form className="filterbar" onSubmit={e => void search(e)}><label>Question or terms<input required minLength={2} maxLength={300} value={query} onChange={e => setQuery(e.target.value)} /></label><button disabled={busy}>Search</button></form>
      {model && <p className="subtext">Embedding: {model}{model.startsWith('mock') ? ' · deterministic test mode' : ''}</p>}
      {!hits.length && model && <p className="empty">No accessible passages matched.</p>}
      <ul className="knowledge-results">{hits.map(hit => <li key={hit.source_id}><strong>{hit.title}</strong><small>{hit.filename} · {hit.page_number ? `page ${hit.page_number}` : `passage ${hit.ordinal + 1}`} · version {hit.version}</small><p>{hit.snippet}</p><button className="secondary" onClick={() => void inspect(hit.source_id)}>Inspect source</button></li>)}</ul>
      {source && <div className="source-inspector"><h3>{source.title}</h3><small>{source.filename} · {source.page_number ? `page ${source.page_number}` : `passage ${source.ordinal + 1}`} · version {source.version}</small><p>{source.content}</p><small>Source ID: {source.id}</small></div>}
    </section>
    <section className="panel"><h2>Accessible documents</h2>{!docs.length && <p className="empty">No accessible documents. An admin can load synthetic examples or upload files.</p>}
      <ul className="knowledge-results">{docs.map(doc => <li key={doc.id}><strong>{doc.title}</strong><small>{doc.kind} · {doc.filename} · version {doc.version} · roles: {doc.allowed_roles.join(', ')}</small>
        {role === 'admin' && <div className="actions"><button className="secondary" onClick={() => edit(doc)}>Replace</button><button className="secondary" disabled={busy} onClick={() => void action(`/documents/${doc.id}/reindex`, 'POST', 'Reindexed current text.')}>Reindex</button><button className="secondary" disabled={busy} onClick={() => { if (window.confirm(`Delete ${doc.title}?`)) void action(`/documents/${doc.id}`, 'DELETE', 'Document deleted.') }}>Delete</button></div>}</li>)}</ul></section>
    {role === 'admin' && <section className="panel"><h2>{editing ? 'Replace document' : 'Add document'}</h2><p>UTF-8 text, Markdown, or text-based PDF up to 2 MiB. The local model downloads on first use.</p>
      <button className="secondary" disabled={busy} onClick={() => void action('/demo', 'POST', 'Demo runbooks loaded. Search “connection pool exhausted”.')}>Load demo runbooks</button>
      <form className="knowledge-form" onSubmit={e => void upload(e)}><label>Title<input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} /></label><label>Kind<select value={kind} onChange={e => setKind(e.target.value)}><option value="runbook">Runbook</option><option value="service_doc">Service document</option><option value="postmortem">Postmortem</option></select></label>
        {!editing && <label>Service<select required value={serviceId} onChange={e => setServiceId(e.target.value)}>{services.map(service => <option key={service.id} value={service.id}>{service.name}</option>)}</select></label>}
        <fieldset><legend>Roles allowed to read</legend>{['viewer', 'responder', 'approver', 'admin'].map(name => <label key={name}><input type="checkbox" checked={roles.includes(name)} onChange={e => setRoles(old => e.target.checked ? [...old, name] : old.filter(item => item !== name))} />{name}</label>)}</fieldset>
        <label>File<input id="knowledge-file" type="file" accept=".txt,.md,.pdf" required onChange={e => setFile(e.target.files?.[0] || null)} /></label><div className="actions"><button disabled={busy || !serviceId || !roles.length}>{editing ? 'Replace and index' : 'Upload and index'}</button>{editing && <button type="button" className="secondary" onClick={() => { setEditing(''); setTitle(''); setFile(null) }}>Cancel</button>}</div></form></section>}
  </div>
}
