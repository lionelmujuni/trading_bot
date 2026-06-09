import { create } from 'zustand'

export interface Candle {
  time: number   // unix seconds
  open: number
  high: number
  low: number
  close: number
  volume: number
  trade_count?: number
}

interface MarketStore {
  activeSymbol: string
  candles: Record<string, Candle[]>         // 20-min historical (from REST)
  liveCandles: Record<string, Candle[]>     // 1-min live ticks (from WS)
  prices: Record<string, number>
  setActiveSymbol: (symbol: string) => void
  setCandles: (symbol: string, candles: Candle[]) => void
  upsertLiveCandle: (candle: Candle & { symbol: string }) => void
  setPrice: (symbol: string, price: number) => void
}

export const useMarketStore = create<MarketStore>((set) => ({
  activeSymbol: 'XBT/USD',
  candles: {},
  liveCandles: {},
  prices: {},
  setActiveSymbol: (symbol) => set({ activeSymbol: symbol }),
  setCandles: (symbol, candles) =>
    set((s) => ({ candles: { ...s.candles, [symbol]: candles } })),
  upsertLiveCandle: (candle) =>
    set((s) => {
      const existing = s.liveCandles[candle.symbol] ?? []
      const last = existing[existing.length - 1]
      let next: Candle[]
      if (last && last.time === candle.time) {
        // update current minute candle
        next = [...existing.slice(0, -1), candle]
      } else {
        // new minute — keep last 500 candles
        next = [...existing, candle].slice(-500)
      }
      return { liveCandles: { ...s.liveCandles, [candle.symbol]: next } }
    }),
  setPrice: (symbol, price) =>
    set((s) => ({ prices: { ...s.prices, [symbol]: price } })),
}))
