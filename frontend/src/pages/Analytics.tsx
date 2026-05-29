import { useEffect, useState } from 'react'
import { TrendingUp, Clock, Target, Zap } from 'lucide-react'
import { api } from '../api'
import type { HistoryItem } from '../api'

interface AnalyticsData {
  total_posts: number
  total_upvotes: number
  avg_upvotes: number
  survival_rate: number
  best_subreddit: string | null
  milestones_hit: number[]
  recent_posts: { subreddit: string; title: string; upvotes: number; performance: string }[]
}

interface TimingWindow {
  day: string
  window: string
  score: number
  reason: string
}

export default function Analytics() {
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [timing, setTiming] = useState<TimingWindow[]>([])
  const [timingSub, setTimingSub] = useState('SaaS')
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.get('/track/analytics').catch(() => null),
      api.get('/track/history?limit=10').catch(() => []),
    ]).then(([a, h]) => {
      setData(a as AnalyticsData)
      setHistory(h as HistoryItem[])
      setLoading(false)
    })
  }, [])

  useEffect(() => {
    api.get(`/track/timing?subreddit=${timingSub}`)
      .then(d => setTiming((d as { best_times: TimingWindow[] }).best_times))
      .catch(() => {})
  }, [timingSub])

  if (loading) {
    return (
      <div className="max-w-5xl">
        <h1 className="text-[22px] font-semibold mb-8">Analytics</h1>
        <div className="grid grid-cols-4 gap-4 mb-8">
          {[1,2,3,4].map(i => (
            <div key={i} className="h-24 bg-surface-1 border border-border rounded-lg animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-5xl">
      <h1 className="text-[22px] font-semibold tracking-[-0.4px] mb-8">Analytics</h1>

      {/* Metric cards */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <MetricCard icon={<TrendingUp size={20} />} label="Total Posts" value={data?.total_posts ?? 0} />
        <MetricCard icon={<Zap size={20} />} label="Avg Upvotes" value={data?.avg_upvotes ?? 0} mono />
        <MetricCard icon={<Target size={20} />} label="Survival Rate" value={`${data?.survival_rate ?? 0}%`} accent />
        <MetricCard icon={<TrendingUp size={20} />} label="Best Subreddit" value={data?.best_subreddit ?? '—'} />
      </div>

      {/* Milestones */}
      {data && data.milestones_hit.length > 0 && (
        <div className="bg-surface-1 border border-border rounded-lg p-5 mb-8">
          <h2 className="text-sm font-semibold text-text-secondary mb-3">Milestones Achieved</h2>
          <div className="flex gap-3 flex-wrap">
            {data.milestones_hit.map(m => (
              <span key={m} className="px-4 py-1.5 bg-accent/10 text-accent border border-accent/30 rounded-full text-sm font-semibold font-mono">
                {m}+ upvotes
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Timing Optimization */}
      <div className="bg-surface-1 border border-border rounded-lg p-5 mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-text-secondary flex items-center gap-2">
            <Clock size={16} /> Best Posting Times
          </h2>
          <select
            value={timingSub}
            onChange={e => setTimingSub(e.target.value)}
            className="bg-surface-2 border border-border rounded-md px-3 py-1.5 text-xs text-text-primary outline-none"
          >
            {['SaaS', 'ExperiencedDevs', 'webdev', 'SideProject'].map(s => (
              <option key={s} value={s}>r/{s}</option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          {timing.map((t, i) => (
            <div key={i} className="flex items-center justify-between py-2 border-b border-border last:border-0">
              <div>
                <span className="text-sm font-semibold text-text-primary">{t.day}</span>
                <span className="text-text-muted text-xs ml-2">{t.window}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-text-muted max-w-xs truncate">{t.reason}</span>
                <span className="text-sm font-mono font-semibold text-accent">{t.score}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Quick History */}
      <div className="border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface-2 text-text-muted text-xs font-semibold uppercase">
              <th className="text-left p-3 pl-4">Recent Posts</th>
              <th className="text-left p-3">Subreddit</th>
              <th className="text-right p-3 font-mono">Upvotes</th>
              <th className="text-right p-3 pr-4">Status</th>
            </tr>
          </thead>
          <tbody>
            {history.slice(0, 5).map((item, i) => (
              <tr key={i} className="border-t border-border">
                <td className="p-3 pl-4 text-text-primary truncate max-w-xs">{item.title}</td>
                <td className="p-3 text-text-muted">{item.subreddit}</td>
                <td className="p-3 text-right font-mono">{item.upvotes}</td>
                <td className="p-3 pr-4 text-right">
                  <span className={`text-xs font-semibold ${
                    item.performance === 'viral' || item.performance === 'super_viral' ? 'text-accent' :
                    item.performance === 'failed' ? 'text-error' : 'text-text-muted'
                  }`}>{item.performance}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function MetricCard({ icon, label, value, mono, accent }: {
  icon: React.ReactNode; label: string; value: string | number;
  mono?: boolean; accent?: boolean;
}) {
  return (
    <div className="bg-surface-1 border border-border rounded-lg p-5">
      <div className="flex items-center gap-2 text-text-muted mb-2">{icon}<span className="text-xs font-semibold uppercase tracking-wide">{label}</span></div>
      <div className={`text-[28px] font-bold tracking-[-0.5px] ${
        accent ? 'text-accent' : 'text-text-primary'
      } ${mono ? 'font-mono' : ''}`}>
        {value}
      </div>
    </div>
  )
}
