import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge, LiveDot } from '@/components/ui/Badge'
import { useBotStore } from '@/stores/botStore'
import { usePortfolioStore } from '@/stores/portfolioStore'
import { fmt, fmtUSD, fmtPct, timeAgo } from '@/lib/utils'
import { cn } from '@/lib/utils'
import {
  DollarSign, TrendingUp, TrendingDown, BarChart2,
  Play, Square, AlertCircle, Activity
} from 'lucide-react'

// ── API helpers ───────────────────────────────────────────────────────────────

const fetchPortfolio = () => fetch('/api/portfolio').then((r) => r.json())
const fetchPositions = () => fetch('/api/positions').then((r) => r.json())
const fetchSignals   = () => fetch('/api/signals?limit=10').then((r) => r.json())
const fetchLogs      = () => fetch('/api/logs?limit=20').then((r) => r.json())

// ── Sub-components ────────────────────────────────────────────────────────────

function MetricCard({
  label, value, sub, icon: Icon, trend,
}: {
  label: string; value: string; sub?: string
  icon: React.ElementType; trend?: 'up' | 'down' | 'neutral'
}) {
  return (
    <Card>
      <CardContent className="flex items-start gap-4 py-5">
        <div className="rounded-lg bg-slate-700/50 p-2.5">
          <Icon className="h-5 w-5 text-slate-300" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">{label}</p>
          <p className="text-xl font-bold text-white leading-none">{value}</p>
          {sub && (
            <p className={cn('text-xs mt-1', trend === 'up' ? 'text-emerald-400' : trend === 'down' ? 'text-red-400' : 'text-slate-500')}>
              {sub}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function ColdStartBar({ pct, current, required }: { pct: number; current: number; required: number }) {
  return (
    <Card className="border-amber-700/40 bg-amber-900/10">
      <CardContent className="py-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-amber-300 flex items-center gap-2">
            <Activity className="h-4 w-4" />
            Cold Start — Collecting historical data
          </span>
          <span className="text-xs text-amber-400">{current} / {required} candles</span>
        </div>
        <div className="h-2 rounded-full bg-slate-700 overflow-hidden">
          <div
            className="h-full rounded-full bg-amber-500 transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="text-xs text-slate-500 mt-1.5">Bot will start trading once {required} candles are collected for each pair.</p>
      </CardContent>
    </Card>
  )
}

function PositionsTable({ positions }: { positions: any[] }) {
  if (!positions.length) return (
    <div className="text-center py-8 text-slate-500 text-sm">No open positions</div>
  )
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-700/50">
            {['Symbol', 'Side', 'Qty', 'Entry', 'Current', 'P&L', 'Strategy', ''].map((h) => (
              <th key={h} className="text-left px-3 py-2 text-xs text-slate-500 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {positions.map((p) => {
            const pnlPct = p.unrealized_pnl_pct ?? 0
            return (
              <tr key={p.id} className="hover:bg-slate-800/30 transition-colors">
                <td className="px-3 py-2.5 font-medium text-white">{p.symbol}</td>
                <td className="px-3 py-2.5">
                  <Badge variant={p.side === 'buy' ? 'success' : 'danger'}>{p.side.toUpperCase()}</Badge>
                </td>
                <td className="px-3 py-2.5 text-slate-300">{fmt(p.quantity, 4)}</td>
                <td className="px-3 py-2.5 text-slate-300">{fmtUSD(p.entry_price)}</td>
                <td className="px-3 py-2.5 text-slate-300">{fmtUSD(p.current_price)}</td>
                <td className={cn('px-3 py-2.5 font-medium', pnlPct >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                  {fmtPct(pnlPct * 100)}
                </td>
                <td className="px-3 py-2.5 text-slate-500 text-xs">{p.entry_strategy}</td>
                <td className="px-3 py-2.5">
                  {/* Manual close — requires additional endpoint; shown as placeholder */}
                  <Button variant="ghost" size="sm" className="h-6 text-xs text-slate-500 hover:text-red-400">Close</Button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function SignalFeed({ signals }: { signals: any[] }) {
  if (!signals.length) return <div className="text-center py-8 text-slate-500 text-sm">No signals yet</div>
  return (
    <div className="space-y-2">
      {signals.map((s, i) => (
        <div key={i} className="flex items-start gap-3 p-2.5 rounded-lg bg-slate-800/40">
          <Badge variant={s.signal_type === 'BUY' ? 'success' : s.signal_type === 'SELL' ? 'danger' : 'info'} className="text-[10px] mt-0.5 flex-shrink-0">
            {s.signal_type}
          </Badge>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-slate-200">{s.symbol}</p>
            <p className="text-xs text-slate-500 truncate">{s.strategy_name} · conf {fmt(s.confidence * 100, 0)}%</p>
          </div>
          <span className="text-[10px] text-slate-600 flex-shrink-0">{timeAgo(s.timestamp)}</span>
        </div>
      ))}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const qc = useQueryClient()
  const { running, state: botState, coldStart } = useBotStore()
  const storeMetrics = usePortfolioStore((s) => s.metrics)

  const { data: portfolio } = useQuery({ queryKey: ['portfolio'], queryFn: fetchPortfolio, refetchInterval: 15000 })
  const { data: positions = [] } = useQuery({ queryKey: ['positions'], queryFn: fetchPositions, refetchInterval: 10000 })
  const { data: signals = [] } = useQuery({ queryKey: ['signals'], queryFn: fetchSignals, refetchInterval: 15000 })
  const { data: logs = [] } = useQuery({ queryKey: ['logs'], queryFn: fetchLogs, refetchInterval: 20000 })

  // Prefer live WS metrics, fall back to polled
  const metrics = storeMetrics ?? portfolio ?? {}

  const startBot = useMutation({
    mutationFn: () => fetch('/api/bot/start', { method: 'POST' }).then((r) => r.json()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portfolio'] }),
  })
  const stopBot = useMutation({
    mutationFn: () => fetch('/api/bot/stop', { method: 'POST' }).then((r) => r.json()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portfolio'] }),
  })

  const pnl = metrics.realized_pnl ?? 0
  const portVal = metrics.total_portfolio_value ?? 0

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-slate-500">Real-time trading overview</p>
        </div>
        <div className="flex items-center gap-3">
          {running && <div className="flex items-center gap-2 text-sm text-emerald-400"><LiveDot /> Running</div>}
          {running ? (
            <Button variant="outline" size="sm" loading={stopBot.isPending} onClick={() => stopBot.mutate()}>
              <Square className="h-3.5 w-3.5" /> Stop Bot
            </Button>
          ) : (
            <Button size="sm" loading={startBot.isPending} onClick={() => startBot.mutate()}>
              <Play className="h-3.5 w-3.5" /> Start Bot
            </Button>
          )}
        </div>
      </div>

      {/* Cold start progress */}
      {botState === 'COLD_START' && (
        <ColdStartBar pct={coldStart.pct} current={coldStart.current} required={coldStart.required} />
      )}

      {/* Metric cards */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <MetricCard label="Portfolio Value" value={fmtUSD(portVal)} icon={DollarSign} />
        <MetricCard
          label="Total P&L"
          value={fmtUSD(pnl)}
          sub={pnl >= 0 ? 'All time' : 'All time'}
          trend={pnl >= 0 ? 'up' : 'down'}
          icon={pnl >= 0 ? TrendingUp : TrendingDown}
        />
        <MetricCard
          label="Win Rate"
          value={`${fmt(metrics.win_rate ?? 0, 1)}%`}
          sub={`${metrics.total_trades ?? 0} trades`}
          icon={BarChart2}
        />
        <MetricCard
          label="Max Drawdown"
          value={fmtPct((metrics.max_drawdown ?? 0) * 100)}
          trend="down"
          icon={AlertCircle}
        />
      </div>

      {/* Open positions + Signal feed */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <div className="xl:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Open Positions</CardTitle>
              <Badge variant="info">{positions.length}</Badge>
            </CardHeader>
            <CardContent className="p-0">
              <PositionsTable positions={positions} />
            </CardContent>
          </Card>
        </div>

        <div>
          <Card>
            <CardHeader>
              <CardTitle>Live Signal Feed</CardTitle>
            </CardHeader>
            <CardContent>
              <SignalFeed signals={signals} />
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Activity log */}
      <Card>
        <CardHeader>
          <CardTitle>Activity Log</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y divide-slate-800/60 max-h-64 overflow-y-auto">
            {logs.length === 0 && (
              <p className="text-center py-6 text-slate-500 text-sm">No log entries yet</p>
            )}
            {logs.map((log: any, i: number) => (
              <div key={i} className="flex items-start gap-3 px-4 py-2.5 hover:bg-slate-800/20">
                <span className={cn(
                  'text-[10px] font-bold px-1.5 py-0.5 rounded uppercase flex-shrink-0 mt-0.5',
                  log.level === 'ERROR' ? 'bg-red-900/60 text-red-300' :
                  log.level === 'WARNING' ? 'bg-amber-900/60 text-amber-300' :
                  'bg-slate-700 text-slate-400'
                )}>{log.level ?? 'INFO'}</span>
                <p className="text-xs text-slate-400 flex-1">{log.message}</p>
                <span className="text-[10px] text-slate-600 flex-shrink-0">{timeAgo(log.timestamp)}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
