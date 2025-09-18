import React, { useEffect, useState } from 'react'
import { apiJSON, API_VERSION } from '../api'

export default function JobList({ onSelect }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [sort, setSort] = useState('created_at:desc')
  const [status, setStatus] = useState('')
  const [method, setMethod] = useState('')
  const [hasResult, setHasResult] = useState('')
  const [fileId, setFileId] = useState('')
  const [total, setTotal] = useState(0)

  async function load() {
    setLoading(true); setErr('')
    const qs = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      sort,
      ...(status ? { status } : {}),
      ...(method ? { method } : {}),
      ...(hasResult ? { has_result: hasResult } : {}),
      ...(fileId ? { file_id: fileId } : {}),
    })
    try {
      const data = await apiJSON(`/${API_VERSION}/jobs?` + qs.toString())
      setItems(data.items || [])
      setTotal(data.total || 0)
    } catch(e) { setErr(e.message) }
    finally { setLoading(false) }
  }

  useEffect(()=>{ load() }, [page, pageSize, sort, status, method, hasResult, fileId])

  function pages() {
    const last = Math.max(1, Math.ceil(total / pageSize))
    return { last, hasPrev: page > 1, hasNext: page < last }
  }
  const { hasPrev, hasNext, last } = pages()

  async function del(id) {
    if (!confirm(`Delete job #${id}?`)) return
    try {
      await apiJSON(`/${API_VERSION}/jobs/${id}`, { method:'DELETE' })
      await load()
    } catch (e) { alert(e.message) }
  }

  async function requeue(id) {
    try {
      await apiJSON(`/${API_VERSION}/jobs/${id}/requeue`, { method:'PUT' })
      await load()
    } catch (e) { alert(e.message) }
  }

  function resetFilters() {
    setStatus('')
    setMethod('')
    setHasResult('')
    setFileId('')
    setPage(1)
  }

  return (
    <div className="card">
      <h2>3) Jobs</h2>
      <div className="row" style={{marginBottom:8}}>
        <label>Status</label>
        <select value={status} onChange={e=>{ setStatus(e.target.value); setPage(1); }}>
          <option value="">(all)</option>
          <option value="queued">queued</option>
          <option value="running">running</option>
          <option value="done">done</option>
          <option value="error">error</option>
        </select>

        <label>Method</label>
        <select value={method} onChange={e=>{ setMethod(e.target.value); setPage(1); }}>
          <option value="">(all)</option>
          <option value="sam">sam</option>
          <option value="grabcut">grabcut</option>
        </select>

        <label>Has result</label>
        <select value={hasResult} onChange={e=>{ setHasResult(e.target.value); setPage(1); }}>
          <option value="">(all)</option>
          <option value="true">true</option>
          <option value="false">false</option>
        </select>

        <label>File ID</label>
        <input type="number" value={fileId} onChange={e=>{ setFileId(e.target.value); setPage(1); }} style={{width:100}} min="0" />

        <label>Sort</label>
        <select value={sort} onChange={e=>setSort(e.target.value)}>
          <option value="created_at:desc">created_at:desc</option>
          <option value="created_at:asc">created_at:asc</option>
          <option value="id:desc">id:desc</option>
          <option value="id:asc">id:asc</option>
          <option value="status:asc">status:asc</option>
          <option value="status:desc">status:desc</option>
          <option value="started_at:desc">started_at:desc</option>
          <option value="started_at:asc">started_at:asc</option>
          <option value="finished_at:desc">finished_at:desc</option>
          <option value="finished_at:asc">finished_at:asc</option>
        </select>

        <label>Per page</label>
        <select value={pageSize} onChange={e=>{ setPageSize(Number(e.target.value) || 10); setPage(1); }}>
          <option value="5">5</option>
          <option value="10">10</option>
          <option value="20">20</option>
          <option value="50">50</option>
        </select>

        <button onClick={resetFilters}>Reset</button>
        <button onClick={load} disabled={loading}>{loading ? 'Refreshing…' : 'Refresh'}</button>
        <span style={{marginLeft:'auto'}}><small className="muted">Total: {total}</small></span>
      </div>

      {err && <p style={{color:'#fca5a5'}}>{err}</p>}

      <ul style={{listStyle:'none', padding:0, margin:0}}>
        {items.map(j => (
          <li key={j.id} style={{padding:'8px 0', borderTop:'1px solid #1f2a44'}}>
            <div className="row" style={{justifyContent:'space-between'}}>
              <div>
                <b>#{j.id}</b> • {j.status} • <small className="muted">{new Date(j.created_at).toLocaleString()}</small>
              </div>
              <div className="row">
                <button onClick={()=>onSelect?.(j.id)}>Open</button>
                <button onClick={()=>requeue(j.id)}>Requeue</button>
                <button onClick={()=>del(j.id)}>Delete</button>
              </div>
            </div>
          </li>
        ))}
      </ul>

      {!items.length && <small className="muted">No jobs yet.</small>}

      <div className="row" style={{marginTop:8}}>
        <button disabled={!hasPrev || loading} onClick={()=>setPage(p=>p-1)}>Prev</button>
        <span>Page {page} / {last}</span>
        <button disabled={!hasNext || loading} onClick={()=>setPage(p=>p+1)}>Next</button>
      </div>
    </div>
  )
}