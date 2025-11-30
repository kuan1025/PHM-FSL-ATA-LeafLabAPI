import React, { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { apiForm, API_BASE, API_VERSION } from '../api'
import { setTokens } from '../auth'

export default function Login() {
  const [username, setU] = useState('Kuan')
  const [password, setP] = useState('Password123!')
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const nav = useNavigate()
  const loc = useLocation()

  async function onSubmit(e) {
    e.preventDefault()
    setErr('')
    setLoading(true)
    try {
     
      const data = await apiForm(`/${API_VERSION}/cognito/login`, { username, password })
      const { id_token, access_token, refresh_token, expires_in } = data?.tokens || data || {}
      if (!id_token || !access_token) throw new Error('Login failed: missing token')
      setTokens({ id_token, access_token, refresh_token, expires_in })
      const params = new URLSearchParams(loc.search)
      const redirectTo = params.get('r') || '/dashboard'
      nav(redirectTo, { replace: true })
    } catch (e) {
      setErr(e.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  function loginWithGoogle() {
   
    const params = new URLSearchParams(window.location.search)
    const r = params.get('r') || '/dashboard'
    window.location.href = `${API_BASE}/${API_VERSION}/cognito/login/google?r=${encodeURIComponent(r)}`
  }

  return (
    <div className="app">
      <h1>LeafLab • Login</h1>
      <div className="card">
        <form onSubmit={onSubmit}>
          <div className="row">
            <label>Username</label>
            <input value={username} onChange={e => setU(e.target.value)} />
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <label>Password</label>
            <input type="password" value={password} onChange={e => setP(e.target.value)} />
          </div>
          <div className="row" style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <button className="primary" disabled={loading}>
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
            <button type="button" onClick={loginWithGoogle}>
              Sign in with Google
            </button>
          </div>
          {err && <p style={{ color: '#fca5a5', marginTop: 8 }}>{err}</p>}
        </form>
      </div>
    </div>
  )
}