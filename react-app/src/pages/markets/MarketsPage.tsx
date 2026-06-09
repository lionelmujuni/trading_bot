import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PriceChart } from '@/components/charts/PriceChart'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { useMarketStore } from '@/stores/marketStore'
import { fmtUSD, fmt, cn } from '@/lib/utils'

export default function MarketsPage() {
  const [selectedSymbol, setSelectedSymbol] = useState('XBT/USD')

  const { data: markets = [] } = useQuery({
    queryKey: ['markets'],
    queryFn: () => fetch('/api/markets').then((r) => r.json()),
    refetchInterval: 10000,
  })

  const { data: candles = [] } = useQuery({
    queryKey: ['candles', selectedSymbol],
    queryFn: () => fetch(`/api/markets/${encodeURIComponent(selectedSymbol)}/candles?limit=300`).then((r) => r.json()),
    enabled: !!selectedSymbol,
  })

  const { data: indicators } = useQuery({
    queryKey: ['indicators', selectedSymbol],
    queryFn: () => fetch(`/api/markets/${encodeURIComponent(selectedSymbol)}/indicators`).then((r) => r.json()),
    refetchInterval: 30000,
    retry: false,
  })

  const livePrice = useMarketStore((s) => s.prices[selectedSymbol])
  const displayPrice = livePrice ?? markets.find((m: any) => m.symbol === selectedSymbol)?.price

  function getRegimeBadge(regime: string | undefined) {
    if (!regime) return null
    if (regime.toLowerCase().includes('trend')) return <Badge variant="success">{regime}</Badge>
    if (regime.toLowerCase().includes('rang')) return <Badge variant="info">{regime}</Badge>
    return <Badge variant="warning">{regime}</Badge>
  }

  return (
    <div className="p-6 space-y-5">
      <h1 className="text-xl font-bold text-white">Markets</h1>

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-5">
        {/* Symbol list */}
        <Card className="xl:col-span-1">
          <CardHeader><CardTitle>Pairs</CardTitle></CardHeader>
          <div className="divide-y divide-slate-800/60">
            {markets.map((m: any) => (
              <button
                key={m.symbol}
                onClick={() => setSelectedSymbol(m.symbol)}
                className={cn(
                  'w-full flex items-center justify-between px-4 py-3 text-sm transition-colors hover:bg-slate-800/40',
                  selectedSymbol === m.symbol ? 'bg-blue-600/10 text-blue-300' : 'text-slate-300'
                )}
              >
                <span className="font-medium">{m.symbol}</span>
                <span className="text-slate-400">{fmtUSD(m.price)}</span>
              </button>
            ))}
          </div>
        </Card>

        {/* Chart area */}
        <div className="xl:col-span-3 space-y-4">
          {/* Symbol header */}
          <Card>
            <CardContent className="py-4 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-white">{selectedSymbol}</h2>
                <p className="text-2xl font-bold text-white mt-1">{fmtUSD(displayPrice)}</p>
              </div>
              <div className="text-right space-y-1">
                {indicators && getRegimeBadge(indicators.regime)}
                {indicators && (
                  <div className="grid grid-cols-2 gap-x-6 gap-y-1 mt-2 text-xs text-slate-400">
                    <span>RSI: <span className={cn('font-medium', indicators.rsi > 70 ? 'text-red-400' : indicators.rsi < 30 ? 'text-emerald-400' : 'text-slate-300')}>{fmt(indicators.rsi, 1)}</span></span>
                    <span>MACD: <span className="font-medium text-slate-300">{fmt(indicators.macd, 4)}</span></span>
                    <span>BB Upper: <span className="font-medium text-slate-300">{fmtUSD(indicators.bb_upper)}</span></span>
                    <span>BB Lower: <span className="font-medium text-slate-300">{fmtUSD(indicators.bb_lower)}</span></span>
                    <span>EMA 12: <span className="font-medium text-slate-300">{fmtUSD(indicators.ema_short)}</span></span>
                    <span>EMA 26: <span className="font-medium text-slate-300">{fmtUSD(indicators.ema_long)}</span></span>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Price chart */}
          <Card>
            <CardHeader>
              <CardTitle>Price Chart</CardTitle>
              <div className="flex items-center gap-3 text-xs text-slate-500">
                <span className="flex items-center gap-1"><span className="inline-block h-0.5 w-4 bg-blue-400" /> EMA 12</span>
                <span className="flex items-center gap-1"><span className="inline-block h-0.5 w-4 bg-amber-400" /> EMA 26</span>
              </div>
            </CardHeader>
            <CardContent className="p-0 pb-2">
              <PriceChart
                symbol={selectedSymbol}
                historicalCandles={candles}
                className="w-full"
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
