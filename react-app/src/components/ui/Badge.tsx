import { cn } from '@/lib/utils'

type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'paper' | 'live'

interface BadgeProps {
  variant?: BadgeVariant
  className?: string
  children: React.ReactNode
}

const variants: Record<BadgeVariant, string> = {
  default: 'bg-slate-700 text-slate-200',
  success: 'bg-emerald-900/60 text-emerald-300 border border-emerald-700/40',
  warning: 'bg-amber-900/60 text-amber-300 border border-amber-700/40',
  danger:  'bg-red-900/60 text-red-300 border border-red-700/40',
  info:    'bg-blue-900/60 text-blue-300 border border-blue-700/40',
  paper:   'bg-purple-900/60 text-purple-300 border border-purple-700/40',
  live:    'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40',
}

export function Badge({ variant = 'default', className, children }: BadgeProps) {
  return (
    <span className={cn('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium', variants[variant], className)}>
      {children}
    </span>
  )
}

/** Pulsing green dot for "LIVE" or "RUNNING" status */
export function LiveDot({ className }: { className?: string }) {
  return (
    <span className={cn('relative flex h-2 w-2', className)}>
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
      <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
    </span>
  )
}
