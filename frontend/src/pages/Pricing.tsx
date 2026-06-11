import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, ArrowRight, Zap } from 'lucide-react'
import { api } from '../api'
import type { QuotaInfo } from '../api'
import { useLang } from '../i18n/LanguageContext'

interface PricingProps {
  quota?: QuotaInfo | null
}

export default function Pricing({ quota }: PricingProps) {
  const { t } = useLang()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const token = localStorage.getItem('kf_token')

  const isPro = quota?.tier === 'pro'

  async function upgrade() {
    if (!token) { navigate('/login?mode=register'); return }
    setLoading(true)
    setError('')
    try {
      const res = await api.createCheckout(
        `${window.location.origin}/?upgraded=true`,
        `${window.location.origin}/pricing?canceled=true`
      )
      window.location.href = res.url
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Checkout failed')
      setLoading(false)
    }
  }

  const features = [
    { key: 'generations', freeKey: 'pricing.free.generations', proKey: 'pricing.pro.generations' },
    { key: 'titles', freeKey: 'pricing.free.titles', proKey: 'pricing.pro.titles' },
    { key: 'history', freeKey: 'pricing.free.history', proKey: 'pricing.pro.history' },
    { key: 'matching', freeKey: 'pricing.free.matching', proKey: 'pricing.pro.matching' },
    { key: 'revise', freeKey: 'pricing.free.revise', proKey: 'pricing.pro.revise' },
    { key: 'export', freeKey: 'pricing.free.export', proKey: 'pricing.pro.export' },
    { key: 'support', freeKey: 'pricing.free.support', proKey: 'pricing.pro.support' },
  ]

  return (
    <div className="max-w-4xl">
      <h1 className="text-[22px] font-semibold tracking-[-0.4px] mb-2">{t('pricing.title')}</h1>
      <p className="text-text-secondary text-sm mb-8">{t('pricing.subtitle')}</p>

      {error && (
        <div className="bg-error/10 border border-error/30 rounded-md p-3 text-error text-sm mb-6">{error}</div>
      )}

      {isPro && (
        <div className="bg-accent/10 border border-accent/30 rounded-lg p-5 mb-8">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2 h-2 rounded-full bg-accent" />
            <span className="text-sm font-semibold text-accent">{t('pricing.current_pro')}</span>
          </div>
          <p className="text-text-secondary text-sm">{t('pricing.pro_unlocked')}</p>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-10">
        {/* Free */}
        <div className="bg-surface-1 border border-border rounded-lg p-6">
          <h2 className="text-[18px] font-semibold mb-1">{t('pricing.free')}</h2>
          <p className="text-text-secondary text-sm mb-4">{t('pricing.free_desc')}</p>
          <div className="mb-4">
            <span className="text-[28px] font-bold font-mono text-text-primary">{t('pricing.free_price')}</span>
            <span className="text-text-muted text-sm">{t('pricing.free_period')}</span>
          </div>
          {token && !isPro ? (
            <button disabled className="w-full bg-surface-2 text-text-secondary font-semibold py-2.5 rounded-md text-sm cursor-not-allowed mb-4">
              {t('pricing.free_current')}
            </button>
          ) : (
            <button
              onClick={() => token ? navigate('/app') : navigate('/login?mode=register')}
              className="w-full bg-surface-2 border border-border text-text-primary font-semibold py-2.5 rounded-md text-sm hover:bg-surface-3 transition-colors mb-4"
            >
              {token ? t('pricing.free_back') : t('pricing.free_signup')}
            </button>
          )}
          <ul className="space-y-2">
            {features.map(f => (
              <li key={f.key} className="flex items-center gap-2 text-sm text-text-secondary">
                <Check size={14} className="text-text-muted shrink-0" />
                <span className="font-mono text-xs text-text-muted mr-1">{t(f.freeKey)}</span>
                {t(`pricing.feature.${f.key}`)}
              </li>
            ))}
          </ul>
        </div>

        {/* Pro */}
        <div className="bg-surface-1 border-2 border-accent rounded-lg p-6 relative">
          <div className="absolute -top-3 left-6 bg-accent text-base text-xs font-bold px-3 py-1 rounded-full font-mono uppercase tracking-wide">
            {t('pricing.pro_recommended')}
          </div>
          <div className="flex items-center gap-2 mb-1">
            <h2 className="text-[18px] font-semibold">{t('pricing.pro')}</h2>
            <Zap size={16} className="text-accent" />
          </div>
          <p className="text-text-secondary text-sm mb-4">{t('pricing.pro_desc')}</p>
          <div className="mb-4">
            <span className="text-[28px] font-bold font-mono text-accent">{t('pricing.pro_price')}</span>
            <span className="text-text-muted text-sm">{t('pricing.pro_period')}</span>
          </div>
          {isPro ? (
            <button
              onClick={async () => {
                try { const res = await api.createPortal(); window.location.href = res.url } catch { /* ignore */ }
              }}
              className="w-full bg-surface-2 border border-border text-text-primary font-semibold py-2.5 rounded-md text-sm hover:bg-surface-3 transition-colors mb-4"
            >
              {t('pricing.pro_manage')}
            </button>
          ) : (
            <button
              onClick={upgrade}
              disabled={loading || !token}
              className="w-full bg-accent text-base font-semibold py-2.5 rounded-md text-sm hover:bg-accent-hover transition-colors disabled:opacity-40 flex items-center justify-center gap-2 mb-4"
            >
              {loading ? (
                <span className="animate-spin w-4 h-4 border-2 border-base border-t-transparent rounded-full" />
              ) : (
                <ArrowRight size={16} />
              )}
              {t('pricing.pro_upgrade')}
            </button>
          )}
          <ul className="space-y-2">
            {features.map(f => (
              <li key={f.key} className="flex items-center gap-2 text-sm text-text-secondary">
                <Check size={14} className="text-accent shrink-0" />
                <span className="font-mono text-xs text-accent mr-1">{t(f.proKey)}</span>
                {t(`pricing.feature.${f.key}`)}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <h2 className="text-[16px] font-semibold mb-4">{t('pricing.compare_title')}</h2>
      <div className="bg-surface-1 border border-border rounded-lg overflow-x-auto">
        <table className="w-full text-sm min-w-[400px]">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left p-4 text-text-secondary font-semibold text-xs uppercase tracking-wide">{t('pricing.compare.feature')}</th>
              <th className="text-center p-4 text-text-muted font-semibold text-xs uppercase tracking-wide w-24">{t('pricing.compare.free')}</th>
              <th className="text-center p-4 text-accent font-semibold text-xs uppercase tracking-wide w-24">{t('pricing.compare.pro')}</th>
            </tr>
          </thead>
          <tbody>
            {features.map((f, i) => (
              <tr key={f.key} className={i % 2 === 0 ? 'bg-surface-2/50' : ''}>
                <td className="p-4 text-text-secondary">{t(`pricing.feature.${f.key}`)}</td>
                <td className="p-4 text-center text-text-muted font-mono text-xs">{t(f.freeKey)}</td>
                <td className="p-4 text-center text-accent font-mono text-xs">{t(f.proKey)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
