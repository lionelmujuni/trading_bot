import { create } from 'zustand'

export interface Position {
  id: number
  symbol: string
  side: string
  quantity: number
  entry_price: number
  current_price?: number
  unrealized_pnl?: number
  realized_pnl?: number
  realized_pnl_pct?: number
  entry_strategy: string
  entry_timestamp: string
  exit_timestamp?: string
  status: 'OPEN' | 'CLOSED'
}

export interface PortfolioMetrics {
  total_portfolio_value: number
  realized_pnl: number
  unrealized_pnl: number
  win_rate: number
  max_drawdown: number
  total_trades: number
  timestamp?: string
}

interface PortfolioStore {
  metrics: PortfolioMetrics | null
  positions: Position[]
  recentSignals: any[]
  setMetrics: (m: PortfolioMetrics) => void
  setPositions: (p: Position[]) => void
  addSignal: (s: any) => void
  addTrade: (t: any) => void
}

export const usePortfolioStore = create<PortfolioStore>((set) => ({
  metrics: null,
  positions: [],
  recentSignals: [],
  setMetrics: (metrics) => set({ metrics }),
  setPositions: (positions) => set({ positions }),
  addSignal: (signal) =>
    set((s) => ({ recentSignals: [signal, ...s.recentSignals].slice(0, 20) })),
  addTrade: (trade) =>
    set((s) => ({
      positions: s.positions.map((p) =>
        p.id === trade.position_id ? { ...p, ...trade } : p
      ),
    })),
}))
