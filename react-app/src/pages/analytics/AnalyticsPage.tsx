import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { createChart, ColorType, type IChartApi, AreaSeries } from 'lightweight-charts'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { fmt, fmtPct, fmtUSD, cn } from '@/lib/utils'

function EquityChart({ equityCurve }: { equityCurve: any[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current || !equityCurve.length) return
    if (chartRef.current) chartRef.current.remove()

    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
      rightPriceScale: { borderColor: '#334155' },
      timeScale: { borderColor: '#334155' },
      width: containerRef.current.clientWidth,
      height: 220,
    })
    chartRef.current = chart

    const series = chart.addSeries(AreaSeries, {
      lineColor: '#3b82f6',
      topColor: 'rgba(59,130,246,0.3)',
      bottomColor: 'rgba(59,130,246,0.01)',
      lineWidth: 2,
    })

    const data = equityCurve
      .map((p: any) => ({ time: Math.floor(new Date(p.timestamp).getTime() / 1000) as any, value: p.equity }))
      .sort((a: any, b: any) => a.time - b.time)
    series.setData(data)
    chart.timeScale().fitContent()

    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth })
    })
    ro.observe(containerRef.current)
    return () => { ro.disconnect(); chart.remove() }
  }, [equityCurve])

  return <div ref={containerRef} className="w-full" />
}

export default function AnalyticsPage() {
  const { data } = useQuery({
    queryKey: ['analytics'],
    queryFn: () => fetch('/api/analytics').then((r) => r.json()),
    refetchInterval: 30000,
  })

  const equityCurve = data?.equity_curve ?? []
  const byStrategy = data?.by_strategy ?? []
  const pnlDist = data?.pnl_distribution ?? []

  // Bucket P&L distribution
  const buckets = Array.from({ length: 20 }, (_, i) => ({ range: `${(i - 10) * 2}%`, count: 0 }))
  pnlDist.forEach((v: number) => {
    const idx = Math.min(Math.max(Math.floor(v / 2) + 10, 0), 19)
    buckets[idx].count++
  })
  const maxCount = Math.max(...buckets.map((b) => b.count), 1)

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold text-white">Analytics</h1>

      {/* Equity curve */}
      <Card>
        <CardHeader><CardTitle>Equity Curve</CardTitle></CardHeader>
        <CardContent className="p-0 pb-2">
          {equityCurve.length ? <EquityChart equityCurve={equityCurve} /> : (
            <div className="h-48 flex items-center justify-center text-slate-600 text-sm">No data yet</div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* Per-strategy table */}
        <Card>
          <CardHeader><CardTitle>Performance by Strategy</CardTitle></CardHeader>
          <CardContent className="p-0">
            {byStrategy.length === 0 ? (
              <div className="py-8 text-center text-slate-600 text-sm">No closed trades yet</div>
            ) : (
              <table className="w-full text-sm">
                <thead><tr className="border-b border-slate-700/50">
                  {['Strategy', 'Trades', 'Win Rate', 'Avg P&L', 'Avg Hold'].map((h) => (
                    <th key={h} className="text-left px-4 py-2.5 text-xs text-slate-500 font-medium">{h}</th>
                  ))}
                </tr></thead>
                <tbody className="divide-y divide-slate-800">
                  {byStrategy.map((s: any) => (
                    <tr key={s.strategy} className="hover:bg-slate-800/30">
                      <td className="px-4 py-2.5 text-xs text-slate-300">{s.strategy}</td>
                      <td className="px-4 py-2.5 text-xs text-slate-400">{s.total_trades}</td>
                      <td className={cn('px-4 py-2.5 text-xs font-medium', s.win_rate >= 50 ? 'text-emerald-400' : 'text-red-400')}>{s.win_rate}%</td>
                      <td className={cn('px-4 py-2.5 text-xs font-medium', s.avg_pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400')}>{fmtPct(s.avg_pnl_pct)}</td>
                      <td className="px-4 py-2.5 text-xs text-slate-400">{s.avg_hold_hrs}h</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>

        {/* P&L distribution */}
        <Card>
          <CardHeader><CardTitle>P&L Distribution</CardTitle></CardHeader>
          <CardContent>
            <div className="flex items-end gap-1 h-40">
              {buckets.map((b, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div
                    className={cn('w-full rounded-sm transition-all', i >= 10 ? 'bg-emerald-500/60' : 'bg-red-500/60')}
                    style={{ height: `${(b.count / maxCount) * 100}%`, minHeight: b.count > 0 ? 4 : 0 }}
                  />
                </div>
              ))}
            </div>
            <div className="flex justify-between text-[10px] text-slate-600 mt-1">
              <span>-20%</span><span>0%</span><span>+20%</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
