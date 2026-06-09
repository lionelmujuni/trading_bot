import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { fmt, fmtUSD, fmtPct, cn } from '@/lib/utils'
import { Download } from 'lucide-react'

function exportCSV(positions: any[], filename: string) {
  const headers = ['id', 'symbol', 'side', 'quantity', 'entry_price', 'exit_price', 'realized_pnl', 'realized_pnl_pct', 'entry_strategy', 'entry_timestamp', 'exit_timestamp']
  const rows = positions.map((p) => headers.map((h) => p[h] ?? '').join(','))
  const csv = [headers.join(','), ...rows].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

export default function PositionsPage() {
  const [tab, setTab] = useState<'open' | 'closed'>('open')

  const { data: openPositions = [] } = useQuery({
    queryKey: ['positions'],
    queryFn: () => fetch('/api/positions').then((r) => r.json()),
    refetchInterval: 10000,
  })

  const { data: closedPositions = [] } = useQuery({
    queryKey: ['positions-history'],
    queryFn: () => fetch('/api/positions/history?limit=100').then((r) => r.json()),
    refetchInterval: 30000,
  })

  const positions = tab === 'open' ? openPositions : closedPositions

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white">Positions</h1>
        <Button variant="outline" size="sm" onClick={() => exportCSV(positions, `${tab}-positions.csv`)}>
          <Download className="h-3.5 w-3.5" /> Export CSV
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-700/50">
        {(['open', 'closed'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              'px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px capitalize',
              tab === t ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-500 hover:text-slate-300'
            )}
          >
            {t} {t === 'open' ? `(${openPositions.length})` : `(${closedPositions.length})`}
          </button>
        ))}
      </div>

      <Card>
        <CardContent className="p-0">
          {positions.length === 0 ? (
            <div className="py-12 text-center text-slate-600 text-sm">No {tab} positions</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-slate-700/40">
                  {(tab === 'open'
                    ? ['Symbol', 'Side', 'Qty', 'Entry', 'Current', 'Unrealized P&L', 'Strategy', 'Opened']
                    : ['Symbol', 'Side', 'Qty', 'Entry', 'Exit', 'Realized P&L', 'Strategy', 'Duration']
                  ).map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs text-slate-500 font-medium">{h}</th>
                  ))}
                </tr></thead>
                <tbody className="divide-y divide-slate-800/60">
                  {positions.map((p: any) => {
                    const pnlPct = tab === 'open'
                      ? (p.unrealized_pnl_pct ?? 0) * 100
                      : (p.realized_pnl_pct ?? 0) * 100
                    const durationHrs = p.hours_held ? `${fmt(p.hours_held, 1)}h` : '—'
                    return (
                      <tr key={p.id} className="hover:bg-slate-800/20">
                        <td className="px-4 py-3 font-medium text-white">{p.symbol}</td>
                        <td className="px-4 py-3"><Badge variant={p.side === 'buy' ? 'success' : 'danger'}>{p.side?.toUpperCase()}</Badge></td>
                        <td className="px-4 py-3 text-slate-300">{fmt(p.quantity, 6)}</td>
                        <td className="px-4 py-3 text-slate-300">{fmtUSD(p.entry_price)}</td>
                        <td className="px-4 py-3 text-slate-300">{fmtUSD(tab === 'open' ? p.current_price : p.exit_price)}</td>
                        <td className={cn('px-4 py-3 font-medium', pnlPct >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                          {fmtPct(pnlPct)}
                        </td>
                        <td className="px-4 py-3 text-slate-500 text-xs truncate max-w-32">{p.entry_strategy}</td>
                        <td className="px-4 py-3 text-slate-500 text-xs">{tab === 'open' ? new Date(p.entry_timestamp).toLocaleDateString() : durationHrs}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
