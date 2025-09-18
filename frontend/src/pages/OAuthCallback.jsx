import React, { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { apiJSON, API_VERSION } from '../api'
import { setTokens } from '../auth'

export default function OAuthCallback() {
  const [search] = useSearchParams()
  const nav = useNavigate()
  const [msg, setMsg] = useState('Exchanging code for tokens…')

  useEffect(() => {
    const err = search.get('error')
    const desc = search.get('error_description')
    const code = search.get('code')
    const state = search.get('state')
    const redirectHint = search.get('r') || '/dashboard'

    if (err) { setMsg(`OAuth error: ${err}${desc ? ' - ' + decodeURIComponent(desc) : ''}`); return }
    if (!code) { setMsg('Missing authorization code.'); return }

    (async () => {
      try {
        const data = await apiJSON(`/${API_VERSION}/cognito/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state || '')}`)
        const tokens = data?.tokens || data || {}
        const { id_token, access_token, refresh_token, expires_in } = tokens
        if (!id_token || !access_token) throw new Error('Token exchange failed.')
        setTokens({ id_token, access_token, refresh_token, expires_in })
        const dest = data?.redirect_to || redirectHint
        setMsg('Login success. Redirecting…')
        nav(dest, { replace: true })
      } catch (e) {
        setMsg(e.message || 'Token exchange failed.')
      }
    })()
  }, [search, nav])

  return (
    <div className="app">
      <h1>LeafLab • OAuth Callback</h1>
      <div className="card">
        <p>{msg}</p>
      </div>
    </div>
  )
}