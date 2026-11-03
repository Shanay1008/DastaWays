import { ChangeEvent, FormEvent, useEffect, useState } from 'react'
import { ArrowRight, CheckCircle2, FileCheck2, FileUp, ShieldCheck, Trash2 } from 'lucide-react'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api'
type Scheme = { id: string; name: string; label: string; description: string }
type Session = { session_id: string; access_token: string }
type Profile = { applicant_name: string; education_level: string; course: string; academic_year: string; marks_percentage: string }
type Document = { id: string; filename: string; page_count: number; status: string; text_characters: number }
type Requirement = { id: string; title: string; status: string; explanation: string; evidence_documents: string[] }
type Report = { overall_status: string; disclaimer: string; requirements: Requirement[]; next_steps: string[] }
const blankProfile: Profile = { applicant_name: '', education_level: '', course: '', academic_year: '', marks_percentage: '' }

export default function App() {
  const [scheme, setScheme] = useState<Scheme | null>(null)
  const [apiStatus, setApiStatus] = useState<'checking' | 'ready' | 'error'>('checking')
  const [session, setSession] = useState<Session | null>(null)
  const [profile, setProfile] = useState<Profile>(blankProfile)
  const [documents, setDocuments] = useState<Document[]>([])
  const [report, setReport] = useState<Report | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  async function request(path: string, init: RequestInit = {}) {
    const headers = new Headers(init.headers)
    if (session) headers.set('Authorization', `Bearer ${session.access_token}`)
    const response = await fetch(`${API}${path}`, { ...init, headers })
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new Error(body?.detail ?? `Request failed (${response.status})`)
    }
    return response.status === 204 ? null : response.json()
  }

  async function loadWorkspace(active: Session) {
    const headers = { Authorization: `Bearer ${active.access_token}` }
    const [docsResponse, profileResponse, reportResponse] = await Promise.all([
      fetch(`${API}/sessions/${active.session_id}/documents`, { headers }),
      fetch(`${API}/sessions/${active.session_id}/profile`, { headers }),
      fetch(`${API}/sessions/${active.session_id}/report`, { headers }),
    ])
    if (docsResponse.ok) setDocuments(await docsResponse.json())
    if (profileResponse.ok) {
      const saved = await profileResponse.json()
      if (saved) setProfile({ ...blankProfile, ...saved, marks_percentage: saved.marks_percentage?.toString() ?? '' })
    }
    if (reportResponse.ok) setReport(await reportResponse.json())
  }

  useEffect(() => {
    Promise.all([fetch(`${API}/health`), fetch(`${API}/schemes`)]).then(async ([health, schemes]) => {
      if (!health.ok || !schemes.ok) throw new Error('API unavailable')
      const items: Scheme[] = await schemes.json()
      setScheme(items[0] ?? null)
      setApiStatus('ready')
      const id = sessionStorage.getItem('dastaways:session-id')
      const token = id && sessionStorage.getItem(`dastaways:${id}`)
      if (id && token) {
        const active = { session_id: id, access_token: token }
        setSession(active)
        const owned = await fetch(`${API}/sessions/${id}`, { headers: { Authorization: `Bearer ${token}` } })
        if (owned.ok) await loadWorkspace(active)
        else { sessionStorage.removeItem('dastaways:session-id'); setSession(null) }
      }
    }).catch(() => setApiStatus('error'))
  }, [])

  async function begin() {
    setBusy(true); setMessage('')
    try {
      const created: Session = await request('/sessions', { method: 'POST' })
      sessionStorage.setItem(`dastaways:${created.session_id}`, created.access_token)
      sessionStorage.setItem('dastaways:session-id', created.session_id)
      setSession(created)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not create a workspace') }
    finally { setBusy(false) }
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage('')
    try {
      await request(`/sessions/${session!.session_id}/profile`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...profile, marks_percentage: profile.marks_percentage ? Number(profile.marks_percentage) : null }) })
      setReport(null); setMessage('Applicant information saved.')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not save profile') }
    finally { setBusy(false) }
  }

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    for (const file of files) {
      setBusy(true); setMessage('')
      try {
        const form = new FormData(); form.append('file', file)
        await request(`/sessions/${session!.session_id}/documents`, { method: 'POST', body: form })
        setMessage(`${file.name} processed.`)
      } catch (error) { setMessage(error instanceof Error ? error.message : `Could not process ${file.name}`) }
      finally { setBusy(false) }
    }
    const docs: Document[] = await request(`/sessions/${session!.session_id}/documents`)
    setDocuments(docs); setReport(null)
  }

  async function assess() {
    setBusy(true); setMessage('')
    try { setReport(await request(`/sessions/${session!.session_id}/assess`, { method: 'POST' })) }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Assessment failed') }
    finally { setBusy(false) }
  }

  async function deleteDocument(id: string) {
    try { await request(`/sessions/${session!.session_id}/documents/${id}`, { method: 'DELETE' }); setDocuments(documents.filter(d => d.id !== id)); setReport(null); setMessage('Document deleted.') }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Could not delete document') }
  }

  async function deleteWorkspace() {
    if (!window.confirm('Delete this workspace and all of its uploaded document text?')) return
    try {
      await request(`/sessions/${session!.session_id}`, { method: 'DELETE' })
      sessionStorage.removeItem(`dastaways:${session!.session_id}`)
      sessionStorage.removeItem('dastaways:session-id')
      setSession(null); setProfile(blankProfile); setDocuments([]); setReport(null); setMessage('Workspace and its data deleted.')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not delete workspace') }
  }

  return <main className="page">
    <nav className="nav"><a className="brand" href="#"><span className="brand-mark">D</span>DastaWays</a><span className="nav-note"><ShieldCheck size={16}/> Private workspace</span></nav>
    {!session ? <section className="hero">
      <div className="eyebrow"><span className="dot"/> APPLICATION READINESS, MADE CLEAR</div>
      <h1>From paperwork<br/><em>to possibilities.</em></h1>
      <p className="intro">Understand what an application asks for, see what evidence you have, and know what to do next.</p>
      <div className="scheme-card"><div className="scheme-icon"><FileCheck2 size={22}/></div><div className="scheme-copy"><span className="pill">{scheme?.label ?? 'DEMO WORKFLOW'}</span><h2>{scheme?.name ?? 'Sample Scholarship'}</h2><p>{scheme?.description ?? 'Connect to the API to load the sample workflow.'}</p></div></div>
      <button className="cta" onClick={begin} disabled={busy || apiStatus !== 'ready' || !scheme}>{busy ? 'Creating workspace…' : 'Start a private workspace'}<ArrowRight size={18}/></button>
      {apiStatus === 'error' && <p className="api-error">The API is unavailable. Start the backend on port 8000, then refresh.</p>}{message && <p className="api-error">{message}</p>}
      <p className="disclaimer">Readiness guidance is advisory and is not an official eligibility decision or approval.</p>
    </section> : <section className="workspace">
      <div className="workspace-heading"><div><div className="eyebrow"><span className="dot"/> SYNTHETIC DEMO · PRIVATE WORKSPACE</div><h1 className="workspace-title">Your application<br/><em>readiness workspace.</em></h1></div><div className="session-actions"><span className="session-chip">Session {session.session_id.slice(0, 8)}</span><button className="delete-workspace" onClick={deleteWorkspace}>Delete workspace</button></div></div>
      <p className="intro">{scheme?.name}. Add basic details and sample PDFs to see a transparent demo assessment.</p>
      {message && <div className="notice">{message}</div>}
      <div className="work-grid"><div className="main-column">
        <section className="panel"><div className="panel-heading"><span className="step">01</span><div><h2>Applicant information</h2><p>Demo fields only. Do not enter sensitive ID or bank details.</p></div></div>
          <form className="profile-form" onSubmit={saveProfile}>
            <label>Applicant name<input required maxLength={120} value={profile.applicant_name} onChange={e => setProfile({...profile, applicant_name:e.target.value})} placeholder="e.g. Asha Kumar"/></label>
            <label>Education level<input required maxLength={80} value={profile.education_level} onChange={e => setProfile({...profile, education_level:e.target.value})} placeholder="e.g. Undergraduate"/></label>
            <label>Course<input required maxLength={160} value={profile.course} onChange={e => setProfile({...profile, course:e.target.value})} placeholder="e.g. BSc Biology"/></label>
            <label>Academic year<input required maxLength={40} value={profile.academic_year} onChange={e => setProfile({...profile, academic_year:e.target.value})} placeholder="e.g. 2026–27"/></label>
            <label>Marks percentage <span className="optional">optional</span><input type="number" min="0" max="100" step="0.01" value={profile.marks_percentage} onChange={e => setProfile({...profile, marks_percentage:e.target.value})} placeholder="0–100"/></label>
            <button className="secondary-button" disabled={busy}>{busy ? 'Saving…' : 'Save applicant information'}</button>
          </form>
        </section>
        <section className="panel"><div className="panel-heading"><span className="step">02</span><div><h2>Supporting PDFs</h2><p>Text-based PDFs only · Up to 10 MB each · Stored in this local demo database</p></div></div>
          <label className="upload-box"><FileUp size={21}/><span><strong>Choose PDF files</strong><small>Transcript or enrollment evidence for the demo</small></span><input type="file" accept="application/pdf,.pdf" multiple onChange={upload} disabled={busy}/></label>
          {documents.length > 0 && <div className="document-list">{documents.map(doc => <div className="document-row" key={doc.id}><FileCheck2 size={18}/><span><strong>{doc.filename}</strong><small>{doc.page_count} pages · {doc.text_characters} characters extracted · {doc.status}</small></span><button className="icon-button" title="Delete document" onClick={() => deleteDocument(doc.id)}><Trash2 size={16}/></button></div>)}</div>}
          {documents.length === 0 && <p className="empty">No documents uploaded yet.</p>}
        </section>
        <button className="cta assess-button" onClick={assess} disabled={busy}>{busy ? 'Assessing…' : 'Generate readiness report'}<ArrowRight size={18}/></button>
        {report && <section className="panel report-panel"><div className="report-top"><div><span className="pill">DEMO ASSESSMENT</span><h2>{report.overall_status.replaceAll('_',' ')}</h2></div><CheckCircle2 size={26}/></div><p className="report-disclaimer">{report.disclaimer}</p>
          <div className="requirements">{report.requirements.map(item => <details className="requirement" key={item.id}><summary><span className={`status status-${item.status.toLowerCase()}`}>{item.status.replaceAll('_',' ')}</span><strong>{item.title}</strong><span className="expand">+</span></summary><p>{item.explanation}</p>{item.evidence_documents.length > 0 && <small>Possible evidence: {item.evidence_documents.join(', ')}</small>}</details>)}</div>
          <h3>Suggested next steps</h3><ol className="next-steps">{report.next_steps.map(step => <li key={step}>{step}</li>)}</ol>
        </section>}
      </div><aside className="side-note"><ShieldCheck size={20}/><h3>How to read this</h3><p>Profile fields are marked as provided. PDF keyword matches are only possible evidence and remain uncertain until a person checks them.</p><p>This synthetic workflow has no official policy source, eligibility rules, or approval decision.</p><div className="privacy-note">Your session token is held in this browser tab. Delete uploaded PDFs or the entire session when finished.</div></aside></div>
    </section>}
    <footer><span>DASTAWAYS · PHASE 2</span><span>Demo workflow · No real identity documents requested</span></footer>
  </main>
}
