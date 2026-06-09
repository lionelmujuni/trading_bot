import { useEffect, useRef, useCallback } from 'react'
import { useBotStore } from '@/stores/botStore'
import { useMarketStore } from '@/stores/marketStore'
import { usePortfolioStore } from '@/stores/portfolioStore'

const WS_URL = '/ws'
const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000

/**
 * Singleton WebSocket connection to /ws.
 * Dispatches incoming messages to the appropriate Zustand stores:
 *   tick     → marketStore.upsertLiveCandle
 *   signal   → portfolioStore.addSignal
 *   trade    → portfolioStore.addTrade
 *   metrics  → portfolioStore.setMetrics
 *   status   → botStore.setStatus
 *   ping     → (ignored)
 */
export function useRealtimeSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const attemptRef = useRef(0)

  const setBotStatus = useBotStore((s) => s.setStatus)
  const upsertLiveCandle = useMarketStore((s) => s.upsertLiveCandle)
  const setPrice = useMarketStore((s) => s.setPrice)
  const { setMetrics, addSignal, addTrade } = usePortfolioStore()

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    // Build absolute WS URL from the current page origin
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}${WS_URL}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      attemptRef.current = 0
    }

    ws.onmessage = (event: MessageEvent) => {
      let msg: any
      try {
        msg = JSON.parse(event.data as string)
      } catch {
        return
      }

      switch (msg.type) {
        case 'tick': {
          const { symbol, time, open, high, low, close, volume, trade_count } = msg
          upsertLiveCandle({ symbol, time, open, high, low, close, volume, trade_count })
          setPrice(symbol, close)
          break
        }
        case 'signal':
          addSignal(msg)
          break
        case 'trade':
          addTrade(msg)
          break
        case 'metrics':
          setMetrics(msg)
          break
        case 'status':
          setBotStatus({
            running: msg.running,
            state: msg.state,
            coldStart: msg.cold_start,
          })
          break
        case 'ping':
          break
        default:
          break
      }
    }

    ws.onclose = () => {
      attemptRef.current += 1
      const delay = Math.min(
        RECONNECT_BASE_MS * 2 ** (attemptRef.current - 1),
        RECONNECT_MAX_MS
      )
      retryRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [setBotStatus, upsertLiveCandle, setPrice, setMetrics, addSignal, addTrade])

  useEffect(() => {
    connect()
    return () => {
      if (retryRef.current) clearTimeout(retryRef.current)
      wsRef.current?.close()
    }
  }, [connect])
}
