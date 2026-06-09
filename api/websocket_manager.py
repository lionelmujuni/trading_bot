"""
WebSocket Manager
Broadcasts real-time events to all connected React clients via FastAPI WebSockets.

Events pushed:
  - tick     : completed 1-minute OHLCV candle from KrakenTickStreamer
  - signal   : new BUY/SELL signal detected by the bot
  - trade    : position opened or closed
  - metrics  : portfolio metrics snapshot (end of each 20-min cycle)
  - status   : bot state change (COLD_START / READY / TRADING / STOPPED)
"""
import asyncio
import json
import logging
from typing import Any, Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages a set of active WebSocket connections and broadcasts JSON messages.
    Thread-safe via asyncio: all broadcasts must be awaited from the event loop.
    """

    def __init__(self):
        self._connections: Set[WebSocket] = set()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.info("WebSocket client connected. Total: %d", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.info("WebSocket client disconnected. Total: %d", len(self._connections))

    # ------------------------------------------------------------------
    # Broadcast helpers
    # ------------------------------------------------------------------

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        """Send a JSON payload to all connected clients. Dead connections are pruned."""
        if not self._connections:
            return

        message = json.dumps(payload, default=str)
        dead: Set[WebSocket] = set()

        for ws in list(self._connections):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)

        for ws in dead:
            self.disconnect(ws)

    async def broadcast_tick(self, candle: Dict) -> None:
        """Push a completed 1-minute candle to all clients."""
        await self.broadcast(candle)   # candle dict already has type='tick'

    async def broadcast_signal(self, signal: Dict) -> None:
        """Push a new trading signal."""
        await self.broadcast({"type": "signal", **signal})

    async def broadcast_trade(self, trade: Dict) -> None:
        """Push a trade event (position opened or closed)."""
        await self.broadcast({"type": "trade", **trade})

    async def broadcast_metrics(self, metrics: Dict) -> None:
        """Push a portfolio metrics snapshot."""
        await self.broadcast({"type": "metrics", **metrics})

    async def broadcast_status(self, status: str, detail: Dict = None) -> None:
        """Push a bot status change event."""
        payload = {"type": "status", "status": status}
        if detail:
            payload.update(detail)
        await self.broadcast(payload)

    # ------------------------------------------------------------------
    # Sync shim — safe to call from synchronous bot code via run_coroutine_threadsafe
    # ------------------------------------------------------------------

    def emit_from_thread(self, loop: asyncio.AbstractEventLoop, payload: Dict) -> None:
        """
        Schedule a broadcast from a non-async context (e.g., the 20-min bot cycle
        running in a thread). Returns immediately without waiting.
        """
        asyncio.run_coroutine_threadsafe(self.broadcast(payload), loop)


# Singleton instance — imported by both api_server.py and the bot modules
manager = WebSocketManager()
