import React, { useState } from 'react'
import { api } from '../api'
import { getToken } from '../auth'

export default function FileUpload({ onUploaded }) {
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function upload() {
    if (!file) return
    setBusy(true); setErr('')
    const fd = new FormData()
    fd.append('f', file)
    try {
      const res = await api('/v1/files/upload', { method: 'POST', body: fd }, getToken())
      const data = await res.json()
      onUploaded?.(data.id)
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="card">
      <h2>1) Upload image</h2>
      <div className="row">
        <input type="file" accept="image/*" onChange={e=>setFile(e.target.files?.[0] || null)} />
        <button className="primary" onClick={upload} disabled={!file || busy}>
          {busy ? 'Uploading...' : 'Upload'}
        </button>
      </div>
      {err && <p style={{color:'#fca5a5'}}>{err}</p>}
    </div>
  )
}
