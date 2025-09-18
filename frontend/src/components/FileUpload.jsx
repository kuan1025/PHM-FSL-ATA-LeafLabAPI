import React, { useState } from 'react'
import { api, apiJSON, API_VERSION } from '../api'

export default function FileUpload({ onUploaded }) {
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function upload() {
    if (!file) return
    setBusy(true); setErr('')
    try {
      // 1) presign
      const presign = await apiJSON(`/${API_VERSION}/files/presign-upload`, {
        method: 'POST',
        body: { filename: file.name || 'file', content_type: file.type || 'application/octet-stream' },
      })

      if (!presign?.url || !presign?.key) throw new Error('Failed to get presigned URL')

      // 2) direct PUT to S3 
      const putRes = await fetch(presign.url, {
        method: 'PUT',
        headers: { 'Content-Type': file.type || 'application/octet-stream' },
        body: file,
      })
      if (!putRes.ok) throw new Error(`Upload failed: ${putRes.status}`)

      // 3) commit to DB
      const rec = await apiJSON(`/${API_VERSION}/files/commit`, {
        method: 'POST',
        body: { key: presign.key, filename: file.name || 'file' },
      })

      onUploaded?.(rec.id)
    } catch (e) {
      setErr(e.message || String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card">
      <h2>1) Upload image</h2>
      <div className="row">
        <input type="file" accept="image/*" onChange={e=>setFile(e.target.files?.[0] || null)} />
        <button className="primary" onClick={upload} disabled={!file || busy}>
          {busy ? 'Uploading…' : 'Upload'}
        </button>
      </div>
      {err && <p style={{color:'#fca5a5'}}>{err}</p>}
    </div>
  )
}