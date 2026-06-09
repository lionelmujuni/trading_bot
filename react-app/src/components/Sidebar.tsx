import { Link, useLocation, useNavigate } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useBotStore } from '@/stores/botStore'
import { useAuthStore } from '@/stores/authStore'
import { LiveDot, Badge } from '@/components/ui/Badge'
import {
  LayoutDashboard, BarChart2, Layers, TrendingUp,
  Briefcase, Settings, Bot, LogOut
} from 'lucide-react'

const navItems = [
  { to: '/',            icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/markets',     icon: BarChart2,        label: 'Markets' },
  { to: '/strategies',  icon: Layers,           label: 'Strategies' },
  { to: '/analytics',   icon: TrendingUp,       label: 'Analytics' },
  { to: '/positions',   icon: Briefcase,        label: 'Positions' },
  { to: '/settings',    icon: Settings,         label: 'Settings' },
]

export function Sidebar() {
  const { pathname } = useLocation()
  const navigate     = useNavigate()
  const { running, mode, exchange } = useBotStore()
  const { user, logout } = useAuthStore()

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  /** Derive up-to-2-char initials from the user's name or email */
  const initials = user
    ? (user.name || user.email)
        .split(/[\s@]+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((s) => s[0].toUpperCase())
        .join('')
    : '?'

  return (
    <aside className="fixed left-0 top-0 h-full w-56 flex flex-col border-r border-slate-700/50 bg-slate-900 z-40">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 py-5 border-b border-slate-700/40">
        <Bot className="h-6 w-6 text-blue-400" />
        <span className="font-bold text-white text-sm tracking-wide">AlgoTrader</span>
      </div>

      {/* Bot status pill */}
      <div className="px-4 py-3 border-b border-slate-700/40">
        <div className="flex items-center gap-2 rounded-lg bg-slate-800 px-3 py-2">
          {running ? <LiveDot /> : <span className="h-2 w-2 rounded-full bg-slate-500" />}
          <span className="text-xs text-slate-300 font-medium">{running ? 'Bot Running' : 'Bot Stopped'}</span>
        </div>
        <div className="flex gap-1.5 mt-2 px-1">
          <Badge variant={mode === 'live' ? 'live' : 'paper'} className="text-[10px]">
            {mode?.toUpperCase()}
          </Badge>
          <Badge variant="info" className="text-[10px]">{exchange?.toUpperCase()}</Badge>
        </div>
      </div>

      {/* Nav links */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label }) => (
          <Link
            key={to}
            to={to}
            className={cn(
              'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
              pathname === to
                ? 'bg-blue-600/20 text-blue-300 font-medium'
                : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
            )}
          >
            <Icon className="h-4 w-4 flex-shrink-0" />
            {label}
          </Link>
        ))}
      </nav>

      {/* User footer */}
      <div className="px-3 py-3 border-t border-slate-700/40">
        <div className="flex items-center gap-2.5 rounded-lg px-2 py-2">
          {/* Avatar */}
          <div className="flex-shrink-0 h-8 w-8 rounded-full bg-blue-600 flex items-center justify-center text-xs font-bold text-white select-none">
            {initials}
          </div>
          {/* Name + email */}
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-slate-200 truncate">{user?.name ?? 'User'}</p>
            <p className="text-[10px] text-slate-500 truncate">{user?.email ?? ''}</p>
          </div>
          {/* Logout */}
          <button
            onClick={handleLogout}
            title="Sign out"
            className="flex-shrink-0 text-slate-500 hover:text-red-400 transition-colors"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  )
}
