import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { LayoutDashboard, History, BarChart3, LogOut, ArrowUpRight, Zap } from 'lucide-react'
import { api } from './api'
import type { QuotaInfo } from './api'
import { useLang } from './i18n/LanguageContext'
import LangSwitch from './components/LangSwitch'

export default function Layout() {
  const { t } = useLang()
  const navigate = useNavigate()
  const token = localStorage.getItem('kf_token')
  const [quota, setQuota] = useState<QuotaInfo | null>(null)

  useEffect(() => {
    if (!token) { navigate('/login'); return }
    api.getQuota().then(setQuota).catch(() => setQuota(null))
  }, [token, navigate])

  if (!token) return null

  const isPro = quota?.tier === 'pro'

  return (
    <div className="flex h-screen">
      <nav className="w-[220px] bg-surface-1 border-r border-border flex flex-col flex-shrink-0 p-4">
        <div className="flex items-center gap-2 mb-8 px-1">
          <div className="w-3 h-3 rounded-full bg-accent" />
          <span className="font-semibold text-base text-text-primary">Reddpilot</span>
        </div>

        <NavLink to="/app" end className={({ isActive }) =>
          `flex items-center gap-3 px-3 py-2 rounded-md text-[13px] transition-colors ${
            isActive ? 'bg-surface-2 text-text-primary font-semibold' : 'text-text-secondary hover:bg-surface-2 hover:text-text-primary'
          }`}>
          <LayoutDashboard size={16} /> {t('nav.dashboard')}
        </NavLink>

        <NavLink to="/app/history" className={({ isActive }) =>
          `flex items-center gap-3 px-3 py-2 rounded-md text-[13px] transition-colors ${
            isActive ? 'bg-surface-2 text-text-primary font-semibold' : 'text-text-secondary hover:bg-surface-2 hover:text-text-primary'
          }`}>
          <History size={16} /> {t('nav.history')}
        </NavLink>

        <NavLink to="/app/analytics" className={({ isActive }) =>
          `flex items-center gap-3 px-3 py-2 rounded-md text-[13px] transition-colors ${
            isActive ? 'bg-surface-2 text-text-primary font-semibold' : 'text-text-secondary hover:bg-surface-2 hover:text-text-primary'
          }`}>
          <BarChart3 size={16} /> {t('nav.analytics')}
        </NavLink>

        {isPro ? (
          <>
            <NavLink to="/app/subscription" className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-md text-[13px] transition-colors mt-1 ${
                isActive ? 'bg-surface-2 text-text-primary font-semibold' : 'text-text-secondary hover:bg-surface-2 hover:text-text-primary'
              }`}>
              <Zap size={16} /> 管理订阅
            </NavLink>
          </>
        ) : (
          <NavLink to="/app/pricing" className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2 rounded-md text-[13px] transition-colors mt-1 ${
              isActive ? 'bg-accent/10 text-accent font-semibold' : 'text-accent hover:bg-accent/10'
            }`}>
            <ArrowUpRight size={16} /> {t('nav.upgrade')}
          </NavLink>
        )}

        <div className="mt-auto">
          <LangSwitch />
          <div className="px-3 mt-3 mb-3">
            <span className={`inline-block text-[11px] font-mono px-2 py-0.5 rounded-full ${
              isPro ? 'bg-accent/15 text-accent' : 'bg-surface-3 text-text-muted'
            }`}>
              {isPro ? t('nav.pro_plan') : t('nav.free_plan')}
            </span>
          </div>
          <button
            onClick={() => { localStorage.removeItem('kf_token'); navigate('/') }}
            className="flex items-center gap-3 px-3 py-2 rounded-md text-[13px] text-text-muted hover:bg-surface-2 hover:text-error transition-colors w-full"
          >
            <LogOut size={16} /> {t('nav.signout')}
          </button>
        </div>
      </nav>
      <main className="flex-1 overflow-y-auto p-8 max-w-[1280px]">
        <Outlet context={{ quota }} />
      </main>
    </div>
  )
}
