import { useEffect, useState } from 'react'
import { api } from '../api'
import type { HistoryItem } from '../api'

const perfColors: Record<string, string> = {
  viral: 'bg-success',
  hot: 'bg-success/70',
  solid: 'bg-info',
  average: 'bg-warning',
  low: 'bg-error',
  unknown: 'bg-border',
}

export default function History() {
  const [items, setItems] = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getHistory().then(setItems).catch(console.error).finally(() => setLoading(false))
  }, [])

  return (
    <div className="max-w-5xl">
      <h1 className="text-[22px] font-semibold tracking-[-0.4px] mb-8">Post History</h1>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-12 bg-surface-1 border border-border rounded-lg animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16">
          <h2 className="text-lg font-semibold mb-2">No posts tracked yet</h2>
          <p className="text-text-secondary">
            Generate and publish posts, then track their performance here.
          </p>
        </div>
      ) : (
        <div className="border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-2 text-text-muted text-xs font-semibold uppercase tracking-wide">
                <th className="text-left p-3 pl-4">Status</th>
                <th className="text-left p-3">Title</th>
                <th className="text-left p-3">Subreddit</th>
                <th className="text-right p-3 font-mono">Upvotes</th>
                <th className="text-right p-3 font-mono">Comments</th>
                <th className="text-right p-3 pr-4">Date</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, i) => (
                <tr key={i} className="border-t border-border hover:bg-surface-1/50 transition-colors">
                  <td className="p-3 pl-4">
                    <span className={`inline-flex items-center gap-2 text-xs font-semibold`}>
                      <span className={`w-2 h-2 rounded-full ${perfColors[item.performance] || 'bg-border'}`} />
                      <span className="text-text-secondary">{item.performance}</span>
                    </span>
                  </td>
                  <td className="p-3 text-text-primary max-w-xs truncate">{item.title}</td>
                  <td className="p-3 text-text-muted">{item.subreddit}</td>
                  <td className="p-3 text-right font-mono text-text-primary tabular-nums">{item.upvotes}</td>
                  <td className="p-3 text-right font-mono text-text-primary tabular-nums">{item.num_comments}</td>
                  <td className="p-3 pr-4 text-right text-text-muted text-xs">
                    {item.tracked_at ? new Date(item.tracked_at).toLocaleDateString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
