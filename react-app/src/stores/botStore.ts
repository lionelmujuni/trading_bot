import { create } from 'zustand'

export type BotState = 'COLD_START' | 'RUNNING' | 'STOPPED' | 'STARTING' | 'STOPPING'

interface ColdStartProgress {
  current: number
  required: number
  pct: number
  state: string
}

interface BotStore {
  running: boolean
  state: BotState
  mode: string       // 'paper' | 'live'
  exchange: string   // 'kraken' | 'robinhood'
  coldStart: ColdStartProgress
  lastUpdate: string | null
  setStatus: (payload: Partial<BotStore>) => void
}

export const useBotStore = create<BotStore>((set) => ({
  running: false,
  state: 'STOPPED',
  mode: 'paper',
  exchange: 'kraken',
  coldStart: { current: 0, required: 101, pct: 0, state: 'COLD_START' },
  lastUpdate: null,
  setStatus: (payload) => set({ ...payload, lastUpdate: new Date().toISOString() }),
}))
