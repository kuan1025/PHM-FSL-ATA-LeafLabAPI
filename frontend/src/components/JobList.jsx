import React, { useEffect, useState } from 'react'
import { apiJSON } from '../api'
import { getToken } from '../auth'

export default function JobList({ onSelect }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  async function load() {
    setLoading(true); setErr('')
    try {
      const data = await apiJSON('/v1/jobs?page=1&page_size=25&sort=created_at:desc', {}, getToken())
      setItems(data.items || [])
    } catch(e) { setErr(e.message) }
    finally { setLoading(false) }
  }

  useEffect(()=>{ load() }, [])

  return (
    <div className="card">
      <h2>3) Jobs</h2>
      <div className="row" style={{marginBottom:8}}>
        <button onClick={load} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</button>
      </div>
      {err && <p style={{color:'#fca5a5'}}>{err}</p>}
      <ul style={{listStyle:'none', padding:0, margin:0}}>
        {items.map(j => (
          <li key={j.id} style={{padding:'8px 0', borderTop:'1px solid #1f2a44'}}>
            <div className="row" style={{justifyContent:'space-between'}}>
              <div>
                <b>#{j.id}</b> • {j.status} • <small className="muted">{new Date(j.created_at).toLocaleString()}</small>
              </div>
              <div>
                <button onClick={()=>onSelect?.(j.id)}>Open</button>
              </div>
            </div>
          </li>
        ))}
      </ul>
      {!items.length && <small className="muted">No jobs yet.</small>}
    </div>
  )
}
