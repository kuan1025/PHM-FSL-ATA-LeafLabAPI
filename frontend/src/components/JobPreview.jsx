import React, { useEffect, useState } from 'react'
import { api, apiJSON, API_BASE_URL } from '../api'
import { getToken } from '../auth'

export default function JobPreview({ jobId }) {
  const [job, setJob] = useState(null)
  const [imgUrl, setImgUrl] = useState('')
  const [err, setErr] = useState('')
  const [running, setRunning] = useState(false)

  async function loadJob() {
    setErr('')
    try {
      const data = await apiJSON(`/v1/jobs/${jobId}`, {}, getToken())
      setJob(data)
      if (data.status === 'done' && data.result_id) {
        // fetch image as blob (so we can pass Authorization header)
        const res = await api(`/v1/jobs/results/${data.result_id}/preview`, {}, getToken())
        const blob = await res.blob()
        setImgUrl(URL.createObjectURL(blob))
      } else {
        setImgUrl('')
      }
    } catch (e) { setErr(e.message) }
  }

  async function start() {
    setRunning(true); setErr('')
    try {
      await apiJSON(`/v1/jobs/${jobId}/start`, { method: 'POST' }, getToken())
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
      {!job && <small className="muted">Loading...</small>}
      {job && (
        <>
          <div className="row" style={{justifyContent:'space-between'}}>
            <div>
              <b>Job #{job.id}</b> — {job.status}
              {job.params && <div><small className="muted">params: {JSON.stringify(job.params)}</small></div>}
            </div>
            <div>
              {job.status !== 'done' && <button className="primary" onClick={start} disabled={running}>{running ? 'Running...' : 'Start'}</button>}
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
