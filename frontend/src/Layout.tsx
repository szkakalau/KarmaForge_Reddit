import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { LayoutDashboard, History, BarChart3, LogOut } from 'lucide-react'

export default function Layout() {
  const navigate = useNavigate()
  const token = localStorage.getItem('kf_token')
  if (!token) { navigate('/login'); return null }

  return (
    <div className="flex h-screen">
      <nav className="w-[220px] bg-surface-1 border-r border-border flex flex-col flex-shrink-0 p-4">
        <div className="flex items-center gap-2 mb-8 px-1">
          <div className="w-3 h-3 rounded-full bg-accent" />
          <span className="font-semibold text-base text-text-primary">KarmaForge</span>
        </div>

        <NavLink to="/" end className={({ isActive }) =>
          `flex items-center gap-3 px-3 py-2 rounded-md text-[13px] transition-colors ${
            isActive ? 'bg-surface-2 text-text-primary font-semibold' : 'text-text-secondary hover:bg-surface-2 hover:text-text-primary'
          }`}>
          <LayoutDashboard size={16} /> Dashboard
        </NavLink>

        <NavLink to="/history" className={({ isActive }) =>
          `flex items-center gap-3 px-3 py-2 rounded-md text-[13px] transition-colors ${
            isActive ? 'bg-surface-2 text-text-primary font-semibold' : 'text-text-secondary hover:bg-surface-2 hover:text-text-primary'
          }`}>
          <History size={16} /> History
        </NavLink>

        <NavLink to="/analytics" className={({ isActive }) =>
          `flex items-center gap-3 px-3 py-2 rounded-md text-[13px] transition-colors ${
            isActive ? 'bg-surface-2 text-text-primary font-semibold' : 'text-text-secondary hover:bg-surface-2 hover:text-text-primary'
          }`}>
          <BarChart3 size={16} /> Analytics
        </NavLink>

        <div className="mt-auto">
          <button
            onClick={() => { localStorage.removeItem('kf_token'); navigate('/login') }}
            className="flex items-center gap-3 px-3 py-2 rounded-md text-[13px] text-text-muted hover:bg-surface-2 hover:text-error transition-colors w-full"
          >
            <LogOut size={16} /> Sign out
          </button>
        </div>
      </nav>
      <main className="flex-1 overflow-y-auto p-8 max-w-[1280px]">
        <Outlet />
      </main>
    </div>
  )
}
