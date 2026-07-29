import { useState } from 'react'
import { api } from '../lib/api.js'
import { ShieldCheck } from 'lucide-react'

export default function Login({ onAuthed }) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setErr(null); setSubmitting(true)
    try {
      await api.login(username, password)
      onAuthed?.()
    } catch (e) {
      setErr(e.message || 'login failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <form onSubmit={submit} className="panel panel-pad w-full max-w-sm space-y-4" data-testid="login-form">
        <div className="flex items-center gap-2 text-accent-amber">
          <ShieldCheck size={18} />
          <span className="label-mono">Operator login</span>
        </div>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Opportunity Center</h1>
          <p className="text-xs text-ink-400 mt-1">ArbiCore X · read-only console</p>
        </div>
        <label className="block">
          <span className="label-mono mb-1 block">Username</span>
          <input
            data-testid="login-username"
            className="input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </label>
        <label className="block">
          <span className="label-mono mb-1 block">Password</span>
          <input
            data-testid="login-password"
            type="password"
            className="input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        {err && (
          <div data-testid="login-error" className="text-xs text-accent-red">{err}</div>
        )}
        <button
          data-testid="login-submit"
          type="submit"
          disabled={submitting}
          className="btn w-full justify-center border-accent-amber/40 text-accent-amber hover:border-accent-amber"
        >
          {submitting ? 'signing in…' : 'sign in'}
        </button>
      </form>
    </div>
  )
}
