import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Zap, AlertTriangle, ExternalLink, RefreshCw } from 'lucide-react'
import { api } from '../api'
import type { BillingStatus, QuotaInfo } from '../api'
import { useLang } from '../i18n/LanguageContext'

export default function Subscription() {
  const { t } = useLang()
  const navigate = useNavigate()
  const [billing, setBilling] = useState<BillingStatus | null>(null)
  const [quota, setQuota] = useState<QuotaInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  useEffect(() => {
    Promise.all([
      api.getBillingStatus().catch(() => null),
      api.getQuota().catch(() => null),
    ]).then(([b, q]) => {
      setBilling(b)
      setQuota(q)
      setLoading(false)
    })
  }, [])

  async function manageBilling() {
    setActionLoading(true)
    try {
      const res = await api.createPortal()
      window.location.href = res.url
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Portal unavailable')
      setActionLoading(false)
    }
  }

  async function upgrade() {
    setActionLoading(true)
    try {
      const res = await api.createCheckout()
      window.location.href = res.url
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Checkout unavailable')
      setActionLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="max-w-2xl">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-surface-2 rounded w-32" />
          <div className="h-40 bg-surface-1 border border-border rounded-lg" />
          <div className="h-32 bg-surface-1 border border-border rounded-lg" />
        </div>
      </div>
    )
  }

  const isPro = billing?.plan === 'pro'
  const isCanceled = billing?.cancel_at_period_end
  const periodEnd = billing?.current_period_end
    ? new Date(billing.current_period_end).toLocaleDateString()
    : null

  return (
    <div className="max-w-2xl">
      <h1 className="text-[22px] font-semibold tracking-[-0.4px] mb-8">
        {isPro ? 'Subscription' : 'Plan'}
      </h1>

      {error && (
        <div className="bg-error/10 border border-error/30 rounded-md p-3 text-error text-sm mb-6">{error}</div>
      )}

      {/* Current Plan Card */}
      <div className="bg-surface-1 border border-border rounded-lg p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isPro ? 'bg-accent' : 'bg-text-muted'}`} />
            <h2 className="text-[16px] font-semibold">
              {isPro ? 'Pro' : 'Free'} {t('nav.plan_suffix') || 'Plan'}
            </h2>
          </div>
          <span className={`text-[11px] font-mono px-2 py-0.5 rounded-full ${
            isCanceled ? 'bg-warning/15 text-warning' :
            isPro ? 'bg-accent/15 text-accent' :
            'bg-surface-3 text-text-muted'
          }`}>
            {isCanceled ? 'Canceling' : billing?.status === 'past_due' ? 'Past Due' : 'Active'}
          </span>
        </div>

        {isPro && periodEnd && (
          <div className="text-sm text-text-secondary mb-4">
            {isCanceled ? (
              <span className="flex items-center gap-1.5 text-warning">
                <AlertTriangle size={14} />
                Your Pro access ends on {periodEnd}. After that, you'll be moved to the Free plan.
              </span>
            ) : (
              <span>Next billing date: <span className="font-mono text-text-primary">{periodEnd}</span></span>
            )}
          </div>
        )}

        {isPro && !isCanceled && (
          <p className="text-sm text-text-secondary mb-4">
            You're on the Pro plan with 300 generations/month, unlimited AI revisions, and priority support.
          </p>
        )}

        {!isPro && (
          <p className="text-sm text-text-secondary mb-4">
            You're on the Free plan with 20 generations/month. Upgrade to Pro for 300/month.
          </p>
        )}
      </div>

      {/* Usage Card */}
      {quota && (
        <div className="bg-surface-1 border border-border rounded-lg p-6 mb-6">
          <h3 className="text-[13px] font-semibold text-text-secondary uppercase tracking-wide mb-4">Usage This Month</h3>
          <div className="grid grid-cols-2 gap-6">
            <div>
              <p className="font-mono text-[28px] font-bold text-text-primary">{quota.used}</p>
              <p className="text-xs text-text-muted">Generations used</p>
            </div>
            <div>
              <p className="font-mono text-[28px] font-bold text-accent">{quota.remaining}</p>
              <p className="text-xs text-text-muted">Remaining</p>
            </div>
          </div>
          <div className="w-full h-1 bg-surface-2 rounded-sm overflow-hidden mt-4">
            <div
              className="h-full rounded-sm bg-accent transition-all duration-400 ease-out"
              style={{ width: `${Math.min(100, (quota.used / quota.limit) * 100)}%` }}
            />
          </div>
          <p className="text-xs text-text-muted mt-2 font-mono">{quota.limit} total per month</p>
        </div>
      )}

      {/* Actions */}
      <div className="space-y-3">
        {isPro ? (
          <button
            onClick={manageBilling}
            disabled={actionLoading}
            className="flex items-center justify-center gap-2 w-full bg-surface-1 border border-border text-text-primary font-semibold py-3 rounded-md text-sm hover:bg-surface-2 transition-colors disabled:opacity-40"
          >
            {actionLoading ? (
              <RefreshCw size={14} className="animate-spin" />
            ) : (
              <ExternalLink size={14} />
            )}
            Manage Billing (Stripe Portal)
          </button>
        ) : (
          <button
            onClick={upgrade}
            disabled={actionLoading}
            className="flex items-center justify-center gap-2 w-full bg-accent text-base font-semibold py-3 rounded-md text-sm hover:bg-accent-hover transition-colors disabled:opacity-40"
          >
            {actionLoading ? (
              <RefreshCw size={14} className="animate-spin" />
            ) : (
              <Zap size={14} />
            )}
            Upgrade to Pro — $5/month
          </button>
        )}

        <button
          onClick={() => navigate('/app/pricing')}
          className="flex items-center justify-center gap-2 w-full bg-surface-2 text-text-secondary font-semibold py-3 rounded-md text-sm hover:bg-surface-3 transition-colors"
        >
          View Plans
        </button>
      </div>

      {isPro && (
        <p className="text-xs text-text-muted mt-4 text-center">
          Billing is managed securely through Stripe. Cancel anytime — your Pro access continues until the end of your billing period.
        </p>
      )}
    </div>
  )
}
