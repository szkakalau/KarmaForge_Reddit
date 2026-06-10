import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Send, Copy, Check, Sparkles, FileText, AlertTriangle, RefreshCw, Wand2, ArrowUpRight } from 'lucide-react'
import { api } from '../api'
import type { QuotaInfo } from '../api'
import type { TitleItem, FullGenerationResponse } from '../api'
import { useLang } from '../i18n/LanguageContext'
import Onboarding from '../components/Onboarding'
import { trackLead, RD_EVENTS } from '../redditPixel'

export default function Dashboard() {
  const { t } = useLang()
  const navigate = useNavigate()
  const [showOnboarding, setShowOnboarding] = useState(
    !localStorage.getItem('kf_onboarded')
  )
  const [input, setInput] = useState('')
  const [subreddit, setSubreddit] = useState('')
  const [loading, setLoading] = useState(false)
  const [titles, setTitles] = useState<TitleItem[]>([])
  const [genId, setGenId] = useState('')
  const [error, setError] = useState('')
  const [copied, setCopied] = useState<string | null>(null)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [body, setBody] = useState('')
  const [selectedPatternId, setSelectedPatternId] = useState('')
  const [editedBody, setEditedBody] = useState('')
  const [selfCheck, setSelfCheck] = useState<FullGenerationResponse['self_check']>(null)
  const [generatingFull, setGeneratingFull] = useState(false)
  const [revising, setRevising] = useState(false)
  const [revisionCount, setRevisionCount] = useState(0)

  // Quota state
  const [quota, setQuota] = useState<QuotaInfo | null>(null)

  useEffect(() => {
    api.getQuota().then(setQuota).catch(() => {})
  }, [loading, generatingFull])

  function _handleApiError(e: unknown) {
    const msg = e instanceof Error ? e.message : 'Unknown error'
    if (msg.includes('402') || msg.includes('quota_exceeded')) {
      return t('dash.upgrade_banner_title', { limit: 20 })
    }
    return msg
  }

  async function generate() {
    if (!input.trim()) return
    setLoading(true)
    setError('')
    setTitles([])
    try {
      const res = await api.generateTitles(input, subreddit || undefined)
      setTitles(res.titles)
      setGenId(res.generation_id)
      if (!localStorage.getItem(RD_EVENTS.LEAD_FIRED)) {
        trackLead()
        localStorage.setItem(RD_EVENTS.LEAD_FIRED, '1')
      }
    } catch (e) {
      setError(_handleApiError(e))
    } finally {
      setLoading(false)
    }
  }

  function copyTitle(title: string) {
    navigator.clipboard.writeText(title)
    setCopied(title)
    setTimeout(() => setCopied(null), 2000)
  }

  async function generateFull() {
    if (!input.trim()) return
    setGeneratingFull(true)
    setError('')
    setBody('')
    setEditedBody('')
    setSelfCheck(null)
    setRevisionCount(0)
    try {
      const res = await api.generateFull(input, subreddit || undefined, 3, selectedIndex)
      setBody(res.body || '')
      setEditedBody(res.body || '')
      setSelectedPatternId(res.selected_pattern_id || '')
      setSelfCheck(res.self_check)
    } catch (e) {
      setError(_handleApiError(e))
    } finally {
      setGeneratingFull(false)
    }
  }

  async function recheck() {
    if (!selectedPatternId || !editedBody) return
    setError('')
    try {
      const result = await api.recheck(
        titles[selectedIndex]?.title || '', editedBody, selectedPatternId, subreddit
      )
      setSelfCheck(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Recheck failed')
    }
  }

  async function revise() {
    if (!selfCheck?.suggestions?.length || !editedBody) return
    setRevising(true)
    setError('')
    try {
      const res = await api.revise(
        titles[selectedIndex]?.title || '', editedBody, selfCheck.suggestions, subreddit
      )
      setEditedBody(res.revised_body)
      setBody(res.revised_body)
      setRevisionCount(c => c + 1)
      // Auto recheck after revision
      if (selectedPatternId) {
        const check = await api.recheck(
          titles[selectedIndex]?.title || '', res.revised_body, selectedPatternId, subreddit
        )
        setSelfCheck(check)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Revise failed')
    } finally {
      setRevising(false)
    }
  }

  return (
    <div className="max-w-4xl">
      {showOnboarding && (
        <Onboarding onComplete={() => {
          localStorage.setItem('kf_onboarded', '1')
          setShowOnboarding(false)
        }} />
      )}
      <h1 className="text-[22px] font-semibold tracking-[-0.4px] mb-4">{t('dash.title')}</h1>

      {/* Quota Progress Bar */}
      {quota && (
        <div className="mb-6">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs text-text-muted font-mono uppercase tracking-wide">
              {t('dash.quota_label')}
            </span>
            <span className="text-xs font-mono text-text-secondary">
              <span className={quota.remaining <= 5 && quota.remaining > 0 ? 'text-warning font-semibold' : 'text-text-primary font-semibold'}>
                {quota.remaining}
              </span>
              <span className="text-text-muted"> / {quota.limit} {t('dash.quota_remaining')}</span>
            </span>
          </div>
          <div className="w-full h-1 bg-surface-2 rounded-sm overflow-hidden">
            <div
              className={`h-full rounded-sm transition-all duration-400 ease-out ${
                quota.remaining === 0 ? 'bg-error' :
                quota.remaining <= 5 ? 'bg-warning' : 'bg-accent'
              }`}
              style={{ width: `${Math.min(100, (quota.used / quota.limit) * 100)}%` }}
              role="progressbar"
              aria-valuenow={quota.used}
              aria-valuemin={0}
              aria-valuemax={quota.limit}
            />
          </div>
        </div>
      )}

      {/* Generator Card */}
      <div className="bg-surface-1 border border-border rounded-lg p-6 mb-8">
        <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
          <div className="flex-1">
            <label className="block text-[13px] font-semibold text-text-secondary mb-2">
              {t('dash.what_promoting')}
            </label>
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && generate()}
              placeholder={t('dash.placeholder')}
              className="w-full bg-surface-2 border border-border rounded-md px-4 py-2.5 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent transition-colors"
            />
          </div>
          <div className="w-full sm:w-[200px]">
            <label className="block text-[13px] font-semibold text-text-secondary mb-2">
              {t('dash.subreddit')}
            </label>
            <input
              type="text"
              value={subreddit}
              onChange={e => setSubreddit(e.target.value)}
              placeholder={t('dash.subreddit_placeholder')}
              className="w-full bg-surface-2 border border-border rounded-md px-4 py-2.5 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent transition-colors"
            />
          </div>
          <button
            onClick={generate}
            disabled={loading || !input.trim()}
            className="flex items-center justify-center gap-2 bg-accent text-base font-semibold px-5 py-2.5 rounded-md text-sm hover:bg-accent-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? (
              <span className="animate-spin w-4 h-4 border-2 border-base border-t-transparent rounded-full" />
            ) : (
              <Sparkles size={16} />
            )}
            {t('dash.generate')}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-error/10 border border-error/30 rounded-lg p-4 text-error text-sm mb-6">
          {error}
        </div>
      )}

      {/* Upgrade Banner — shows when quota is low or exhausted */}
      {quota && quota.remaining === 0 && !error && (
        <div className="bg-accent/8 border-l-2 border-accent rounded-r-lg p-4 mb-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-text-primary mb-1">
                {t('dash.upgrade_banner_title', { limit: quota?.limit ?? 20 })}
              </p>
              <p className="text-xs text-text-secondary">
                {t('dash.upgrade_banner_desc')}
              </p>
            </div>
            <button
              onClick={() => navigate('/app/pricing')}
              className="flex items-center gap-1.5 bg-accent text-base font-semibold px-4 py-2 rounded-md text-xs hover:bg-accent-hover transition-colors shrink-0 sm:ml-4 w-full sm:w-auto justify-center"
            >
              {t('dash.upgrade_button')} <ArrowUpRight size={14} />
            </button>
          </div>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
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
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {titles.map((title, i) => (
              <div
                key={i}
                onClick={() => setSelectedIndex(i)}
                className={`bg-surface-1 border rounded-lg p-5 cursor-pointer transition-colors ${
                  i === selectedIndex
                    ? 'border-accent ring-1 ring-accent/20'
                    : 'border-border hover:border-border-hover'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] text-text-muted uppercase tracking-wide">{title.hook_type}</span>
                  <span className="text-xs font-mono font-semibold text-accent">{Math.round(title.score)}%</span>
                </div>
                <p className="text-sm text-text-primary leading-relaxed mb-3">{title.title}</p>
                <button
                  onClick={() => copyTitle(title.title)}
                  className="flex items-center gap-1.5 text-xs text-text-muted hover:text-accent transition-colors"
                >
                  {copied === title.title ? <Check size={14} /> : <Copy size={14} />}
                  {copied === title.title ? t('dash.copied') : t('dash.copy')}
                </button>
              </div>
            ))}
          </div>

          {/* Full post generation button */}
          <div className="mt-6 flex flex-wrap items-center gap-4">
            <button
              onClick={generateFull}
              disabled={generatingFull}
              className="flex items-center gap-2 bg-surface-1 border border-accent text-accent font-semibold px-5 py-2.5 rounded-md text-sm hover:bg-accent hover:text-base transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {generatingFull ? (
                <span className="animate-spin w-4 h-4 border-2 border-current border-t-transparent rounded-full" />
              ) : (
                <FileText size={16} />
              )}
              {t('dash.generate_full')}
            </button>
            <span className="text-xs text-text-muted truncate max-w-[200px] sm:max-w-[300px]">
              Using: {titles[selectedIndex]?.title?.slice(0, 60)}...
            </span>
          </div>

          {/* Body result — editable */}
          {body && (
            <div className="mt-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-[16px] font-semibold">Post Body</h2>
                <div className="flex items-center gap-2">
                  {revisionCount > 0 && (
                    <span className="text-xs text-text-muted bg-surface-2 px-2 py-0.5 rounded">
                      Revision {revisionCount}
                    </span>
                  )}
                  <button
                    onClick={() => copyTitle(editedBody || body)}
                    className="flex items-center gap-1.5 text-xs text-text-muted hover:text-accent transition-colors bg-surface-2 px-2 py-1 rounded"
                  >
                    {copied === (editedBody || body) ? <Check size={14} /> : <Copy size={14} />}
                    {copied === (editedBody || body) ? 'Copied' : 'Copy'}
                  </button>
                </div>
              </div>
              <textarea
                value={editedBody}
                onChange={e => setEditedBody(e.target.value)}
                rows={12}
                className="w-full bg-surface-1 border border-border rounded-lg p-5 text-sm text-text-primary leading-relaxed resize-y outline-none focus:border-accent transition-colors"
                placeholder="Edit the body text, then re-check quality..."
              />
            </div>
          )}

          {/* Self-check */}
          {selfCheck && (
            <div className="mt-4 bg-surface-1 border border-border rounded-lg p-5">
              <div className="flex items-center gap-2 mb-3">
                <div className={`w-2 h-2 rounded-full ${selfCheck.passed ? 'bg-green-500' : 'bg-orange-500'}`} />
                <span className="text-sm font-semibold">
                  {selfCheck.passed ? 'Quality Check Passed' : 'Quality Check: Issues Found'}
                </span>
              </div>
              {selfCheck.dimensions && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
                  {Object.entries(selfCheck.dimensions).map(([dim, info]: [string, any]) => (
                    <div key={dim} className="flex justify-between items-center bg-surface-2 rounded px-3 py-2">
                      <span className="text-xs text-text-secondary">{dim}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-semibold">{info.得分 ?? info.score ?? '-'}</span>
                        <span className={`text-[11px] px-1.5 py-0.5 rounded ${
                          (info.状态 ?? info.status) === '正常' || (info.状态 ?? info.status) === 'ok' ? 'bg-green-500/10 text-green-600' :
                          (info.状态 ?? info.status) === '警告' || (info.状态 ?? info.status) === 'warn' ? 'bg-orange-500/10 text-orange-600' :
                          'bg-red-500/10 text-red-600'
                        }`}>{info.状态 ?? info.status ?? '-'}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {selfCheck.suggestions && selfCheck.suggestions.length > 0 && (
                <div className="bg-surface-2 rounded p-3 mb-4">
                  <p className="text-xs text-text-secondary mb-2 flex items-center gap-1">
                    <AlertTriangle size={12} /> Suggestions:
                  </p>
                  <ul className="list-disc list-inside text-xs text-text-secondary space-y-1">
                    {selfCheck.suggestions.map((s: string, i: number) => <li key={i}>{s}</li>)}
                  </ul>
                </div>
              )}
              {/* Action buttons */}
              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={recheck}
                  disabled={!editedBody}
                  className="flex items-center gap-1.5 bg-surface-2 border border-border text-text-secondary text-xs font-medium px-3 py-1.5 rounded hover:border-accent hover:text-accent transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <RefreshCw size={13} />
                  Re-check
                </button>
                <button
                  onClick={revise}
                  disabled={revising || !selfCheck.suggestions?.length || !editedBody}
                  className="flex items-center gap-1.5 bg-accent text-base text-xs font-semibold px-3 py-1.5 rounded hover:bg-accent-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {revising ? (
                    <span className="animate-spin w-3 h-3 border-2 border-base border-t-transparent rounded-full" />
                  ) : (
                    <Wand2 size={13} />
                  )}
                  {revising ? 'Revising...' : 'AI Revise'}
                </button>
                <span className="text-[11px] text-text-muted">
                  Edit body → Re-check, or let AI fix suggestions automatically
                </span>
              </div>
            </div>
          )}
        </>
      )}

      {/* Empty state */}
      {!loading && !error && titles.length === 0 && (
        <div className="text-center py-16">
          <div className="w-16 h-16 bg-surface-1 border border-border rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Send size={28} className="text-text-muted" />
          </div>
          <h2 className="text-lg font-semibold mb-2">{t('dash.empty_title')}</h2>
          <p className="text-text-secondary max-w-sm mx-auto">
            {t('dash.empty_desc')}
          </p>
        </div>
      )}
    </div>
  )
}
