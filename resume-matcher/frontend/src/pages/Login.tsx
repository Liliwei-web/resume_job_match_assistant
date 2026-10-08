import { useState, type FormEvent } from 'react'
import { api, errorMessage } from '../api'
import type { User } from '../types'

export default function Login({ onLoggedIn }: { onLoggedIn: (user: User) => void }) {
  const [username, setUsername] = useState('demo1')
  const [password, setPassword] = useState('demo1234')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const user = await api.post<User>('/api/auth/login', { username, password })
      onLoggedIn(user)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-shell">
      <div className="card login-card">
        <h2>简历与岗位匹配助手</h2>
        <p className="muted">使用预置测试账号登录，无需注册。</p>
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="username">账号</label>
            <input id="username" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </div>
          <div className="field">
            <label htmlFor="password">密码</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          {error && <div className="error-box">{error}</div>}
          <div className="row">
            <button className="primary" type="submit" disabled={busy}>
              {busy ? '登录中…' : '登录'}
            </button>
          </div>
        </form>
        <p className="muted" style={{ marginTop: 16 }}>
          测试账号：<span className="mono">demo1 / demo1234</span>、<span className="mono">demo2 / demo1234</span>
        </p>
      </div>
    </div>
  )
}
