import React, { useEffect, useState } from 'react'
import { api, apiJSON, API_VERSION } from '../api'

export default function JobPreview({ jobId }) {
  const [job, setJob] = useState(null)
  const [imgUrl, setImgUrl] = useState('')
  const [err, setErr] = useState('')
  const [running, setRunning] = useState(false)

  async function loadJob() {
    setErr('')
    try {
      const data = await apiJSON(`/${API_VERSION}/jobs/${jobId}`)
      setJob(data)
      if (data.status === 'done' && data.result_id) {
        const meta = await apiJSON(`/${API_VERSION}/jobs/results/${data.result_id}/preview`) // {url, mime, size, etag}
        setImgUrl(meta?.url || '')
      } else {
        setImgUrl('')
      }
    } catch (e) { setErr(e.message) }
  }

  async function start() {
    setRunning(true); setErr('')
    try {
      await apiJSON(`/${API_VERSION}/jobs/${jobId}/start`, { method: 'POST' })
      await loadJob()
    } catch (e) { setErr(e.message) }
    finally { setRunning(false) }
  }

  useEffect(()=>{ if (jobId) loadJob() }, [jobId])

  if (!jobId) return null

  return (
    <div className="card">
      <h2>4) Job detail</h2>
      {err && <p style={{color:'#fca5a5'}}>{err}</p>}
      {!job && <small className="muted">Loading…</small>}
      {job && (
        <>
          <div className="row" style={{justifyContent:'space-between'}}>
            <div>
              <b>Job #{job.id}</b> — {job.status}
              {job.params && <div><small className="muted">params: {JSON.stringify(job.params)}</small></div>}
            </div>
            <div>
              {job.status !== 'done' && <button className="primary" onClick={start} disabled={running}>{running ? 'Running…' : 'Start'}</button>}
              <button onClick={loadJob} style={{marginLeft:8}}>Refresh</button>
            </div>
          </div>
          <div style={{marginTop:12}}>
            {imgUrl ? <img className="preview" src={imgUrl} alt="preview" /> : <small className="muted">No preview yet.</small>}
          </div>
        </>
      )}
    </div>
  )
}