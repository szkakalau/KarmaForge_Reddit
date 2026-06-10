import { useState, useEffect } from 'react'
import { Users, BarChart3, DollarSign, Activity, Mail, Calendar, Zap } from 'lucide-react'
import { api } from '../api'

interface AdminStats {
  total_users: number
  free_users: number
  pro_users: number
  total_generations: number
  estimated_cost: number
}

interface UserRow {
  id: string
  email: string
  display_name: string | null
  tier: string
  generation_count: number
  feedback_count: number
  has_subscription: boolean
  created_at: string | null
}

export default function Admin() {
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [users, setUsers] = useState<UserRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.get('/admin/stats').catch(() => null),
      api.get('/admin/users').catch(() => null),
    ]).then(([s, u]) => {
      if (s) setStats(s as AdminStats)
      if (u) setUsers(u as UserRow[])
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="max-w-5xl">
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
    <div className="max-w-5xl">
      <h1 className="text-[22px] font-semibold tracking-[-0.4px] mb-8">Admin</h1>

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
                <span className="font-mono text-[28px] font-bold text-accent">{stats.pro_users}</span>
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

          {/* User table */}
          {users.length > 0 && (
            <div className="bg-surface-1 border border-border rounded-lg overflow-hidden">
              <div className="px-5 py-3 border-b border-border">
                <h2 className="text-sm font-semibold">Users ({users.length})</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left p-3 text-text-muted font-semibold text-[11px] uppercase tracking-wide">Email</th>
                      <th className="text-left p-3 text-text-muted font-semibold text-[11px] uppercase tracking-wide">Name</th>
                      <th className="text-center p-3 text-text-muted font-semibold text-[11px] uppercase tracking-wide">Tier</th>
                      <th className="text-center p-3 text-text-muted font-semibold text-[11px] uppercase tracking-wide">Gens</th>
                      <th className="text-center p-3 text-text-muted font-semibold text-[11px] uppercase tracking-wide">Tracked</th>
                      <th className="text-right p-3 text-text-muted font-semibold text-[11px] uppercase tracking-wide">Joined</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u, i) => (
                      <tr key={u.id} className={i % 2 === 0 ? 'bg-surface-2/50' : ''}>
                        <td className="p-3">
                          <div className="flex items-center gap-2">
                            <Mail size={12} className="text-text-muted shrink-0" />
                            <span className="font-mono text-xs text-text-primary truncate max-w-[200px]">{u.email}</span>
                          </div>
                        </td>
                        <td className="p-3 text-xs text-text-secondary">
                          {u.display_name || '—'}
                        </td>
                        <td className="p-3 text-center">
                          <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full ${
                            u.tier === 'pro' ? 'bg-accent/15 text-accent' : 'bg-surface-3 text-text-muted'
                          }`}>
                            {u.tier === 'pro' && <Zap size={10} />}
                            {u.tier === 'pro' ? 'Pro' : 'Free'}
                            {u.has_subscription && !u.tier.includes('pro') && ' (sub)'}
                          </span>
                        </td>
                        <td className="p-3 text-center font-mono text-xs text-text-secondary">{u.generation_count}</td>
                        <td className="p-3 text-center font-mono text-xs text-text-secondary">{u.feedback_count}</td>
                        <td className="p-3 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <Calendar size={11} className="text-text-muted" />
                            <span className="text-xs text-text-muted font-mono">
                              {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
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
