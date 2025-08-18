import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { setToken } from '../auth'

export default function Login() {
    const [username, setU] = useState('kuan')
    const [password, setP] = useState('password')
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState('')
    const nav = useNavigate()

    async function onSubmit(e) {
        e.preventDefault();
        setErr(''); setLoading(true);
        try {
            const body = new URLSearchParams({ username, password });
            const data = await api('/auth/login', {
                method: 'POST',
                body: body,
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
            });
            const json_data = await data.json();

            setToken(json_data.access_token);
            nav('/');
        } catch (e) {
            setErr(e.message || 'Login failed');
        } finally {
            setLoading(false);
        }
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
                    <div className="row" style={{ marginTop: 12 }}>
                        <button className="primary" disabled={loading}>{loading ? 'Signing in...' : 'Sign in'}</button>
                    </div>
                    {err && <p style={{ color: '#fca5a5', marginTop: 8 }}>{err}</p>}
                </form>
            </div>
        </div>
    )
}
