import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

export default function Login() {
  const navigate = useNavigate()
  if (localStorage.getItem('kf_token')) { navigate('/'); return null }
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isRegister, setIsRegister] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit() {
    setLoading(true)
    setError('')
    try {
      const fn = isRegister ? api.register : api.login
      const res = await fn(email, password)
      localStorage.setItem('kf_token', res.token)
      navigate('/')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Auth failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-full max-w-sm bg-surface-1 border border-border rounded-lg p-8">
        <div className="flex items-center gap-2 mb-8 justify-center">
          <div className="w-3 h-3 rounded-full bg-accent" />
          <span className="font-semibold text-lg text-text-primary">KarmaForge</span>
        </div>

        <h1 className="text-xl font-semibold text-center mb-6">
          {isRegister ? 'Create account' : 'Welcome back'}
        </h1>

        {error && (
          <div className="bg-error/10 border border-error/30 rounded-md p-3 text-error text-sm mb-4">
            {error}
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-[13px] font-semibold text-text-secondary mb-1.5">Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && submit()}
              className="w-full bg-surface-2 border border-border rounded-md px-4 py-2.5 text-sm outline-none focus:border-accent transition-colors"
            />
          </div>
          <div>
            <label className="block text-[13px] font-semibold text-text-secondary mb-1.5">Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && submit()}
              className="w-full bg-surface-2 border border-border rounded-md px-4 py-2.5 text-sm outline-none focus:border-accent transition-colors"
            />
          </div>
          <button
            onClick={submit}
            disabled={loading}
            className="w-full bg-accent text-base font-semibold py-2.5 rounded-md text-sm hover:bg-accent-hover transition-colors disabled:opacity-40"
          >
            {loading ? '...' : isRegister ? 'Create account' : 'Sign in'}
          </button>
        </div>

        <p className="text-center text-text-muted text-xs mt-6">
          {isRegister ? 'Already have an account?' : "Don't have an account?"}{' '}
          <button onClick={() => setIsRegister(!isRegister)} className="text-accent hover:underline font-medium">
            {isRegister ? 'Sign in' : 'Register'}
          </button>
        </p>
      </div>
    </div>
  )
}
