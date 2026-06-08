import { useState, useEffect } from 'react'
import { Users, BarChart3, DollarSign, Activity } from 'lucide-react'
import { api } from '../api'

interface AdminStats {
  total_users: number
  free_users: number
  pro_users: number
  total_generations: number
  estimated_cost: number
}

export default function Admin() {
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    // Admin stats from available endpoints
    Promise.all([
      api.get('/admin/stats').catch(() => null),
    ]).then(([s]) => {
      if (s) setStats(s as AdminStats)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="max-w-4xl">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-surface-2 rounded w-32" />
          <div className="grid grid-cols-4 gap-4">
            {[1,2,3,4].map(i => <div key={i} className="h-24 bg-surface-1 border border-border rounded-lg" />)}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-4xl">
      <h1 className="text-[22px] font-semibold tracking-[-0.4px] mb-8">Admin</h1>

      {error && (
        <div className="bg-error/10 border border-error/30 rounded-md p-3 text-error text-sm mb-6">{error}</div>
      )}

      {stats ? (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <div className="bg-surface-1 border border-border rounded-lg p-5">
              <Users size={20} className="text-text-muted mb-3" />
              <p className="font-mono text-[28px] font-bold text-text-primary">{stats.total_users}</p>
              <p className="text-xs text-text-muted">Total Users</p>
            </div>
            <div className="bg-surface-1 border border-border rounded-lg p-5">
              <Activity size={20} className="text-text-muted mb-3" />
              <p className="font-mono text-[28px] font-bold text-text-primary">{stats.total_generations}</p>
              <p className="text-xs text-text-muted">Total Generations</p>
            </div>
            <div className="bg-surface-1 border border-border rounded-lg p-5">
              <BarChart3 size={20} className="text-text-muted mb-3" />
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-[28px] font-bold text-text-primary">{stats.pro_users}</span>
                <span className="text-xs text-text-muted">Pro</span>
                <span className="font-mono text-[28px] font-bold text-text-muted">/</span>
                <span className="font-mono text-[28px] font-bold text-text-muted">{stats.free_users}</span>
                <span className="text-xs text-text-muted">Free</span>
              </div>
              <p className="text-xs text-text-muted mt-2">Pro / Free Split</p>
            </div>
            <div className="bg-surface-1 border border-border rounded-lg p-5">
              <DollarSign size={20} className="text-text-muted mb-3" />
              <p className="font-mono text-[28px] font-bold text-accent">${stats.estimated_cost.toFixed(2)}</p>
              <p className="text-xs text-text-muted">Est. API Cost</p>
            </div>
          </div>
        </>
      ) : (
        <div className="bg-surface-1 border border-border rounded-lg p-8 text-center">
          <p className="text-text-secondary text-sm">
            Admin stats unavailable. Make sure the backend <code className="font-mono text-xs bg-surface-2 px-1 rounded">GET /api/admin/stats</code> endpoint is running.
          </p>
        </div>
      )}
    </div>
  )
}
