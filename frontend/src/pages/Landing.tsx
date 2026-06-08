import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { useLang } from '../i18n/LanguageContext'
import LangSwitch from '../components/LangSwitch'

export default function Landing() {
  const { t } = useLang()
  const token = localStorage.getItem('kf_token')

  return (
    <div className="min-h-screen">
      {/* Hero */}
      <section className="max-w-[960px] mx-auto pt-24 pb-20 px-8">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-accent" />
            <span className="font-semibold text-base text-text-primary font-mono tracking-wide uppercase text-xs">
              Reddpilot
            </span>
          </div>
          <LangSwitch />
        </div>

        <h1 className="text-[44px] font-bold tracking-[-1.2px] leading-[1.1] mb-6 max-w-[720px]">
          {t('landing.hero.title1')}
          <br />
          <span className="text-accent">{t('landing.hero.title2')}</span>
        </h1>

        <p className="text-text-secondary text-base leading-relaxed max-w-[520px] mb-10">
          {t('landing.hero.subtitle')}
        </p>

        <div className="flex items-center gap-4">
          {token ? (
            <Link
              to="/app"
              className="flex items-center gap-2 bg-accent text-base font-semibold px-6 py-3 rounded-md text-sm hover:bg-accent-hover transition-colors"
            >
              {t('landing.hero.dashboard')} <ArrowRight size={16} />
            </Link>
          ) : (
            <Link
              to="/login"
              className="flex items-center gap-2 bg-accent text-base font-semibold px-6 py-3 rounded-md text-sm hover:bg-accent-hover transition-colors"
            >
              {t('landing.hero.cta')} <ArrowRight size={16} />
            </Link>
          )}
          <Link
            to="/pricing"
            className="flex items-center gap-2 bg-surface-1 border border-border text-text-primary font-semibold px-6 py-3 rounded-md text-sm hover:bg-surface-2 transition-colors"
          >
            {t('landing.hero.pricing')}
          </Link>
        </div>
      </section>

      {/* How it works */}
      <section className="border-t border-border">
        <div className="max-w-[960px] mx-auto px-8 py-20">
          <h2 className="text-[11px] font-mono uppercase tracking-widest text-text-muted mb-12">
            {t('landing.how')}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
            {[1, 2, 3].map(i => (
              <div key={i}>
                <div className="w-8 h-8 flex items-center justify-center rounded bg-accent/10 mb-4">
                  <span className="text-accent font-mono font-bold text-sm">{i}</span>
                </div>
                <h3 className="text-sm font-semibold mb-2">{t(`landing.step${i}.title`)}</h3>
                <p className="text-text-secondary text-sm leading-relaxed">{t(`landing.step${i}.desc`)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Metrics */}
      <section className="border-t border-border">
        <div className="max-w-[960px] mx-auto px-8 py-20">
          <h2 className="text-[11px] font-mono uppercase tracking-widest text-text-muted mb-12">
            {t('landing.why')}
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
            {[1, 2, 3, 4].map(i => (
              <div key={i}>
                <p className={`font-mono text-[28px] font-bold mb-1 ${i === 2 ? 'text-accent' : 'text-text-primary'}`}>
                  {t(`landing.metric${i}.value`)}
                </p>
                <p className="text-text-secondary text-sm">{t(`landing.metric${i}.label`)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-border">
        <div className="max-w-[960px] mx-auto px-8 py-20 text-center">
          <h2 className="text-[22px] font-semibold mb-3">{t('landing.cta.title')}</h2>
          <p className="text-text-secondary text-sm mb-8 max-w-[400px] mx-auto">
            {t('landing.cta.subtitle')}
          </p>
          <Link
            to={token ? "/app" : "/login"}
            className="inline-flex items-center gap-2 bg-accent text-base font-semibold px-6 py-3 rounded-md text-sm hover:bg-accent-hover transition-colors"
          >
            {token ? t('landing.cta.dashboard') : t('landing.cta.button')} <ArrowRight size={16} />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border">
        <div className="max-w-[960px] mx-auto px-8 py-8 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-accent" />
            <span className="text-xs text-text-muted font-mono">{t('footer.version')}</span>
          </div>
          <div className="flex items-center gap-6">
            <Link to="/pricing" className="text-xs text-text-muted hover:text-text-secondary transition-colors">{t('footer.pricing')}</Link>
            <Link to="/login" className="text-xs text-text-muted hover:text-text-secondary transition-colors">{t('footer.login')}</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
