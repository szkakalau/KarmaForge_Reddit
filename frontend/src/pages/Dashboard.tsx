import { useState } from 'react'
import { Send, Copy, Check, Sparkles } from 'lucide-react'
import { api } from '../api'
import type { TitleItem } from '../api'

export default function Dashboard() {
  const [input, setInput] = useState('')
  const [subreddit, setSubreddit] = useState('')
  const [loading, setLoading] = useState(false)
  const [titles, setTitles] = useState<TitleItem[]>([])
  const [genId, setGenId] = useState('')
  const [error, setError] = useState('')
  const [copied, setCopied] = useState<string | null>(null)

  async function generate() {
    if (!input.trim()) return
    setLoading(true)
    setError('')
    setTitles([])
    try {
      const res = await api.generateTitles(input, subreddit || undefined)
      setTitles(res.titles)
      setGenId(res.generation_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Generation failed')
    } finally {
      setLoading(false)
    }
  }

  function copyTitle(title: string) {
    navigator.clipboard.writeText(title)
    setCopied(title)
    setTimeout(() => setCopied(null), 2000)
  }

  return (
    <div className="max-w-4xl">
      <h1 className="text-[22px] font-semibold tracking-[-0.4px] mb-8">Generate</h1>

      {/* Generator Card */}
      <div className="bg-surface-1 border border-border rounded-lg p-6 mb-8">
        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="block text-[13px] font-semibold text-text-secondary mb-2">
              What are you promoting?
            </label>
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && generate()}
              placeholder="Describe your product or topic..."
              className="w-full bg-surface-2 border border-border rounded-md px-4 py-2.5 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent transition-colors"
            />
          </div>
          <div style={{ width: 200 }}>
            <label className="block text-[13px] font-semibold text-text-secondary mb-2">
              Subreddit
            </label>
            <input
              type="text"
              value={subreddit}
              onChange={e => setSubreddit(e.target.value)}
              placeholder="r/SaaS"
              className="w-full bg-surface-2 border border-border rounded-md px-4 py-2.5 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent transition-colors"
            />
          </div>
          <button
            onClick={generate}
            disabled={loading || !input.trim()}
            className="flex items-center gap-2 bg-accent text-base font-semibold px-5 py-2.5 rounded-md text-sm hover:bg-accent-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? (
              <span className="animate-spin w-4 h-4 border-2 border-base border-t-transparent rounded-full" />
            ) : (
              <Sparkles size={16} />
            )}
            Generate
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-error/10 border border-error/30 rounded-lg p-4 text-error text-sm mb-8">
          {error}
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="grid grid-cols-3 gap-4 mb-8">
          {[1, 2, 3].map(i => (
            <div key={i} className="bg-surface-1 border border-border rounded-lg p-5 animate-pulse">
              <div className="h-3 bg-surface-3 rounded w-24 mb-3" />
              <div className="h-4 bg-surface-3 rounded w-full mb-2" />
              <div className="h-4 bg-surface-3 rounded w-3/4" />
            </div>
          ))}
        </div>
      )}

      {/* Title cards */}
      {titles.length > 0 && (
        <>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-[16px] font-semibold">Generated Titles</h2>
            <span className="text-xs text-text-muted bg-surface-1 border border-border rounded-full px-3 py-1">
              {genId.slice(0, 10)}...
            </span>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {titles.map((t, i) => (
              <div key={i} className="bg-surface-1 border border-border rounded-lg p-5 group hover:border-border-hover transition-colors">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] text-text-muted uppercase tracking-wide">{t.hook_type}</span>
                  <span className="text-xs font-mono font-semibold text-accent">{Math.round(t.score)}%</span>
                </div>
                <p className="text-sm text-text-primary leading-relaxed mb-3">{t.title}</p>
                <button
                  onClick={() => copyTitle(t.title)}
                  className="flex items-center gap-1.5 text-xs text-text-muted hover:text-accent transition-colors"
                >
                  {copied === t.title ? <Check size={14} /> : <Copy size={14} />}
                  {copied === t.title ? 'Copied' : 'Copy'}
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Empty state */}
      {!loading && !error && titles.length === 0 && (
        <div className="text-center py-16">
          <div className="w-16 h-16 bg-surface-1 border border-border rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Send size={28} className="text-text-muted" />
          </div>
          <h2 className="text-lg font-semibold mb-2">Ready to grow on Reddit</h2>
          <p className="text-text-secondary max-w-sm mx-auto">
            Describe what you're promoting, pick a subreddit, and let KarmaForge craft titles that actually work on Reddit.
          </p>
        </div>
      )}
    </div>
  )
}
