import React, { useEffect, useRef, useState } from 'react'
import { api, apiJSON, API_VERSION } from '../api'

export default function FileManager({ onSelectFile }) {
  const [items, setItems] = useState([])
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [sort, setSort] = useState('created_at:desc')
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const [total, setTotal] = useState(0)
  const [downloadingId, setDownloadingId] = useState(null)

  const replaceInputRef = useRef(null)
  const [replaceId, setReplaceId] = useState(null)

  async function load() {
    setLoading(true); setErr('')
    const qs = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      sort,
      ...(q ? { q } : {}),
    })
    try {
      const data = await apiJSON(`/${API_VERSION}/files/my?` + qs.toString())
      setItems(data.items || [])
      setTotal(data.total || 0)
    } catch (e) { setErr(e.message) }
    finally { setLoading(false) }
  }

  useEffect(()=>{ load() }, [page, pageSize, sort])

  function pages() {
    const last = Math.max(1, Math.ceil(total / pageSize))
    return { last, hasPrev: page > 1, hasNext: page < last }
  }

  function askReplace(id) {
    setReplaceId(id)
    replaceInputRef.current?.click()
  }

  async function onPickReplace(e) {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f || !replaceId) return
    const fd = new FormData()
    fd.append('f', f)
    try {
      await api(`/${API_VERSION}/files/${replaceId}/content`, { method:'PUT', body: fd })
      await load()
    } catch (e) { alert(e.message) }
    finally { setReplaceId(null) }
  }

  // --- View in new tab (kept)
  async function view(id) {
    try {
      const meta = await apiJSON(`/${API_VERSION}/files/${id}`) // {url, mime, size_bytes, etag}
      if (!meta?.url) throw new Error('No presigned URL')
      const a = document.createElement('a')
      a.href = meta.url
      a.rel = 'noopener'
      a.target = '_blank'
      document.body.appendChild(a)
      a.click()
      a.remove()
    } catch (e) { alert(e.message) }
  }

  // --- Actual download (fetch blob -> save as <filename>)
  async function downloadFile(id, filename) {
    try {
      setDownloadingId(id)
      const meta = await apiJSON(`/${API_VERSION}/files/${id}`)
      if (!meta?.url) throw new Error('No presigned URL')
      const res = await fetch(meta.url)
      if (!res.ok) throw new Error(`Download failed: ${res.status} ${res.statusText}`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename || `file_${id}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {

      console.error(e)
      try { await view(id) } catch {}
      alert(e.message || 'Download failed')
    } finally {
      setDownloadingId(null)
    }
  }

  const { hasPrev, hasNext, last } = pages()

  return (
    <div className="card">
      <h2>1.5) My files</h2>
      <div className="row" style={{marginBottom:8}}>
        <input placeholder="Search…" value={q} onChange={e=>setQ(e.target.value)} />
        <button onClick={()=>{ setPage(1); load(); }} disabled={loading}>Search</button>

        <select value={sort} onChange={e=>setSort(e.target.value)}>
          <option value="created_at:desc">created_at:desc</option>
          <option value="created_at:asc">created_at:asc</option>
          <option value="filename:asc">filename:asc</option>
          <option value="filename:desc">filename:desc</option>
          <option value="size_bytes:desc">size_bytes:desc</option>
          <option value="size_bytes:asc">size_bytes:asc</option>
        </select>

        <label>Per page</label>
        <select
          value={pageSize}
          onChange={e=>{ setPageSize(Number(e.target.value) || 10); setPage(1); }}
        >
          <option value="5">5</option>
          <option value="10">10</option>
          <option value="20">20</option>
          <option value="50">50</option>
        </select>

        <button onClick={load} disabled={loading}>{loading ? 'Refreshing…' : 'Refresh'}</button>
        <span style={{marginLeft:'auto'}}><small className="muted">Total: {total}</small></span>
      </div>

      {err && <p style={{color:'#fca5a5'}}>{err}</p>}

      <ul style={{listStyle:'none', padding:0, margin:0}}>
        {items.map(it => (
          <li key={it.id} style={{padding:'8px 0', borderTop:'1px solid #1f2a44'}}>
            <div className="row" style={{justifyContent:'space-between'}}>
              <div>
                <b>#{it.id}</b> • {it.filename || '(no name)'} • {Math.round((it.size_bytes||0)/1024)} KB
                <div><small className="muted">{new Date(it.created_at).toLocaleString()}</small></div>
              </div>
              <div className="row" style={{gap:6}}>
                <button onClick={()=>onSelectFile?.(it.id)}>Select</button>
                <button onClick={()=>askReplace(it.id)}>Replace</button>
                <button onClick={()=>view(it.id)}>View</button>
                <button
                  onClick={()=>downloadFile(it.id, it.filename)}
                  disabled={downloadingId === it.id}
                  title="Download this file"
                >
                  {downloadingId === it.id ? 'Downloading…' : 'Download'}
                </button>
                <button onClick={()=>{
                  if (!confirm(`Delete file #${it.id}?`)) return
                  apiJSON(`/${API_VERSION}/files/${it.id}`, { method:'DELETE' })
                    .then(load).catch(e=>alert(e.message))
                }}>Delete</button>
              </div>
            </div>
          </li>
        ))}
      </ul>

      {!items.length && <small className="muted">No files.</small>}

      <div className="row" style={{marginTop:8}}>
        <button disabled={!hasPrev || loading} onClick={()=>setPage(p=>p-1)}>Prev</button>
        <span>Page {page} / {last}</span>
        <button disabled={!hasNext || loading} onClick={()=>setPage(p=>p+1)}>Next</button>
      </div>

      <input ref={replaceInputRef} type="file" style={{display:'none'}} accept="image/*" onChange={onPickReplace} />
    </div>
  )
}
