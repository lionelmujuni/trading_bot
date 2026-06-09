import { useEffect, useRef } from 'react'
import {
  createChart, type IChartApi, type ISeriesApi,
  type CandlestickData, type LineData, ColorType,
  CandlestickSeries, LineSeries,
} from 'lightweight-charts'
import { useMarketStore, type Candle } from '@/stores/marketStore'

interface PriceChartProps {
  symbol: string
  historicalCandles: Candle[]   // 20-min REST candles (seeded once)
  className?: string
}

export function PriceChart({ symbol, historicalCandles, className }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const ema12Ref = useRef<ISeriesApi<'Line'> | null>(null)
  const ema26Ref = useRef<ISeriesApi<'Line'> | null>(null)

  const liveCandles = useMarketStore((s) => s.liveCandles[symbol] ?? [])

  // ── Build chart once ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0f172a' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: '#334155' },
      timeScale: { borderColor: '#334155', timeVisible: true },
      width: containerRef.current.clientWidth,
      height: 360,
    })
    chartRef.current = chart

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    })
    candleSeriesRef.current = candleSeries

    const ema12 = chart.addSeries(LineSeries, { color: '#60a5fa', lineWidth: 1, priceLineVisible: false })
    const ema26 = chart.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 1, priceLineVisible: false })
    ema12Ref.current = ema12
    ema26Ref.current = ema26

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
    }
  }, [])

  // ── Seed historical candles (20-min) ────────────────────────────────────────
  useEffect(() => {
    if (!candleSeriesRef.current || !historicalCandles.length) return
    const data: CandlestickData[] = historicalCandles.map((c) => ({
      time: c.time as any,
      open: c.open, high: c.high, low: c.low, close: c.close,
    }))
    candleSeriesRef.current.setData(data)

    // Compute EMAs from historical close prices
    const closes = historicalCandles.map((c) => c.close)
    const times = historicalCandles.map((c) => c.time as any)
    ema12Ref.current?.setData(computeEMA(closes, times, 12))
    ema26Ref.current?.setData(computeEMA(closes, times, 26))

    chartRef.current?.timeScale().fitContent()
  }, [historicalCandles])

  // ── Apply live 1-min ticks via series.update() ───────────────────────────────
  useEffect(() => {
    if (!candleSeriesRef.current || !liveCandles.length) return
    const last = liveCandles[liveCandles.length - 1]
    candleSeriesRef.current.update({
      time: last.time as any,
      open: last.open,
      high: last.high,
      low: last.low,
      close: last.close,
    })
  }, [liveCandles])

  return <div ref={containerRef} className={className} />
}

// ── EMA helper ────────────────────────────────────────────────────────────────

function computeEMA(closes: number[], times: number[], period: number): LineData[] {
  const k = 2 / (period + 1)
  const result: LineData[] = []
  let ema = closes[0]
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) continue
    if (i === period - 1) {
      ema = closes.slice(0, period).reduce((a, b) => a + b) / period
    } else {
      ema = closes[i] * k + ema * (1 - k)
    }
    result.push({ time: times[i] as any, value: ema })
  }
  return result
}
