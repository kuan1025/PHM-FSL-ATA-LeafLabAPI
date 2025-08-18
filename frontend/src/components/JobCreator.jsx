import React, { useState } from 'react'
import { apiJSON, API_VERSION } from '../api'
import { getToken } from '../auth'

export default function JobCreator({ fileId, onCreated }) {
  const [method, setMethod] = useState('sam')
  const [preproc, setPreproc] = useState(false)
  const [wb, setWb] = useState('none')
  const [gamma, setGamma] = useState(1.0)
  const [repeat, setRepeat] = useState(8)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  function preset(name) {
    if (name === 'sam') { setMethod('sam'); setPreproc(false); setWb('none'); setGamma(1.0) }
    if (name === 'sam+pre') { setMethod('sam'); setPreproc(true); setWb('grayworld'); setGamma(1.12) }
    if (name === 'gc') { setMethod('grabcut'); setPreproc(false); setWb('none'); setGamma(1.0) }
    if (name === 'gc+pre') { setMethod('grabcut'); setPreproc(true); setWb('grayworld'); setGamma(1.12) }
  }

  async function createJob() {
    if (!fileId) { setErr('Please upload an image first.'); return }
    setBusy(true); setErr('')

    const validGamma = isNaN(Number(gamma)) ? 1.0 : Number(gamma);
    const validRepeat = isNaN(Number(repeat)) ? 8 : Number(repeat);

    const body = {
      method,
      white_balance: preproc ? wb : 'none',
      gamma: preproc ? validGamma : 1.0,
      repeat: validRepeat
    }
    try {
      const data = await apiJSON(`/${API_VERSION}/jobs?file_id=${fileId}`, { method: 'POST', body }, getToken())
      onCreated?.(data.id)
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="card">
      <h2>2) Create job</h2>
      <div className="row">
        <button onClick={() => preset('sam')}>SAM</button>
        <button onClick={() => preset('sam+pre')}>SAM + preprocessing</button>
        <button onClick={() => preset('gc')}>GrabCut</button>
        <button onClick={() => preset('gc+pre')}>GrabCut + preprocessing</button>
      </div>
      <hr />
      <div className="row">
        <label>Method</label>
        <select value={method} onChange={e => setMethod(e.target.value)}>
          <option value="sam">sam</option>
          <option value="grabcut">grabcut</option>
        </select>
        <label><input type="checkbox" checked={preproc} onChange={e => setPreproc(e.target.checked)} /> apply preprocessing</label>
      </div>
      <div className="row">
        <label>WB</label>
        <select value={wb} onChange={e => setWb(e.target.value)} disabled={!preproc || method === 'sam'}>
          <option value="none">none</option>
          <option value="grayworld">grayworld</option>
        </select>
        <label>Gamma</label>
        <input type="number" step="0.01" value={gamma} onChange={e => setGamma(e.target.value)} disabled={!preproc || method === 'sam'} />
        <label>Repeat</label>
        <input type="number" min="1" max="64" value={repeat} onChange={e => setRepeat(e.target.value)} />
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button className="primary" disabled={!fileId || busy} onClick={createJob}>
          {busy ? 'Creating...' : 'Create'}
        </button>
      </div>
      <small className="muted">
        Note: For SAM, preprocessing is ignored by backend; kept here only as a preset indicator.
      </small>
      {err && <p style={{ color: '#fca5a5' }}>{err}</p>}
    </div>
  )
}
