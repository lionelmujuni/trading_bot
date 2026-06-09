import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface SettingsStore {
  // Onboarding
  onboardingComplete: boolean
  setOnboardingComplete: (v: boolean) => void

  // Exchange settings (display only — actual keys never stored in browser)
  exchange: string
  setExchange: (e: string) => void

  // Risk parameters (mirrors config.py values fetched from API)
  tradingMode: 'paper' | 'live'
  setTradingMode: (m: 'paper' | 'live') => void
}

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set) => ({
      onboardingComplete: false,
      setOnboardingComplete: (v) => set({ onboardingComplete: v }),
      exchange: 'kraken',
      setExchange: (exchange) => set({ exchange }),
      tradingMode: 'paper',
      setTradingMode: (tradingMode) => set({ tradingMode }),
    }),
    { name: 'trading-bot-settings' }
  )
)
