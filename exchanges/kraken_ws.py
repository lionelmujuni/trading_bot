"""
Kraken Public WebSocket Client — 1-Minute Tick Aggregator
Connects to wss://ws.kraken.com, subscribes to the 'trade' channel for all
tracked pairs, aggregates raw trades into 1-minute OHLCV candles, and
broadcasts completed candles to the FastAPI WebSocket manager.

This module runs as a background asyncio task alongside the bot.
It does NOT write to the price_history table (which stays at 20-min candles).
"""
import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Callable, Dict, List, Optional

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

logger = logging.getLogger(__name__)

# Kraken public WebSocket URL
WS_URL = "wss://ws.kraken.com"

# Seconds per aggregation bucket
TICK_INTERVAL = 60


class _Candle:
    """In-progress 1-minute OHLCV candle."""

    def __init__(self, open_price: float, timestamp: int):
        self.ts = timestamp          # bucket start (floor to minute)
        self.open = open_price
        self.high = open_price
        self.low = open_price
        self.close = open_price
        self.volume = 0.0
        self.trade_count = 0

    def update(self, price: float, volume: float) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += volume
        self.trade_count += 1

    def to_dict(self, symbol: str) -> Dict:
        return {
            "type": "tick",
            "symbol": symbol,
            "time": self.ts,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": round(self.volume, 8),
            "trade_count": self.trade_count,
        }


class KrakenTickStreamer:
    """
    Subscribes to Kraken's public 'trade' WebSocket channel for a list of
    pairs and aggregates trades into 1-minute OHLCV candles.

    Usage:
        streamer = KrakenTickStreamer(
            pairs=["XBT/USD", "ETH/USD"],
            on_candle=my_callback,          # called with completed candle dict
        )
        await streamer.run()                # runs until cancelled
    """

    def __init__(
        self,
        pairs: List[str],
        on_candle: Callable[[Dict], None],
        reconnect_delay: float = 2.0,
        reconnect_max: float = 60.0,
    ):
        """
        Args:
            pairs: List of Kraken wsname pairs, e.g. ["XBT/USD", "ETH/USD"].
                   Obtain wsname from AssetPairs endpoint.
            on_candle: Async or sync callable(candle_dict) invoked when a
                       1-minute candle closes. Runs in the event loop.
            reconnect_delay: Initial reconnect back-off in seconds.
            reconnect_max: Maximum reconnect delay (exponential cap).
        """
        self.pairs = pairs
        self._on_candle = on_candle
        self._reconnect_delay = reconnect_delay
        self._reconnect_max = reconnect_max
        self._running = False

        # Active candles keyed by pair wsname
        self._candles: Dict[str, _Candle] = {}
        # Maps Kraken channelID (int) → wsname pair
        self._channel_map: Dict[int, str] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Run the WebSocket loop. Reconnects automatically on failure."""
        self._running = True
        delay = self._reconnect_delay
        while self._running:
            try:
                await self._connect_and_stream()
                delay = self._reconnect_delay   # reset on clean exit
            except asyncio.CancelledError:
                logger.info("KrakenTickStreamer cancelled.")
                self._running = False
                return
            except (ConnectionClosed, WebSocketException, OSError) as exc:
                logger.warning("KrakenTickStreamer disconnected: %s — retrying in %.0fs", exc, delay)
            except Exception as exc:
                logger.error("KrakenTickStreamer unexpected error: %s — retrying in %.0fs", exc, delay)

            if self._running:
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._reconnect_max)

    def stop(self) -> None:
        """Signal the streamer to stop after the current connection closes."""
        self._running = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _connect_and_stream(self) -> None:
        logger.info("KrakenTickStreamer connecting to %s", WS_URL)
        async with websockets.connect(
            WS_URL,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        ) as ws:
            await self._subscribe(ws)
            logger.info("KrakenTickStreamer subscribed to %d pairs", len(self.pairs))

            async for raw in ws:
                if not self._running:
                    break
                await self._handle_message(raw)

    async def _subscribe(self, ws) -> None:
        """Send subscription message for the 'trade' channel."""
        msg = {
            "event": "subscribe",
            "pair": self.pairs,
            "subscription": {"name": "trade"},
        }
        await ws.send(json.dumps(msg))

    async def _handle_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        # System/subscription events
        if isinstance(data, dict):
            event = data.get("event", "")
            if event == "subscriptionStatus" and data.get("status") == "subscribed":
                channel_id = data.get("channelID")
                pair = data.get("pair", "")
                if channel_id and pair:
                    self._channel_map[channel_id] = pair
            elif event in ("heartbeat", "systemStatus", "pong"):
                pass  # nothing to do
            elif event == "error":
                logger.error("Kraken WS error: %s", data.get("errorMessage"))
            return

        # Trade message: [channelID, [[price, volume, time, side, orderType, misc], ...], "trade", "pair"]
        if not isinstance(data, list) or len(data) < 4:
            return
        channel_id = data[0]
        trades = data[1]
        msg_type = data[2]
        pair = data[3]

        if msg_type != "trade":
            return

        pair_name = self._channel_map.get(channel_id, pair)
        for trade in trades:
            price = float(trade[0])
            volume = float(trade[1])
            trade_ts = float(trade[2])
            await self._process_trade(pair_name, price, volume, trade_ts)

    async def _process_trade(
        self, pair: str, price: float, volume: float, trade_ts: float
    ) -> None:
        """Bucket the trade into the current 1-minute candle, flushing if the minute rolled."""
        bucket_ts = int(trade_ts // TICK_INTERVAL) * TICK_INTERVAL

        if pair not in self._candles:
            self._candles[pair] = _Candle(price, bucket_ts)
            self._candles[pair].update(price, volume)
            return

        candle = self._candles[pair]

        if bucket_ts > candle.ts:
            # Minute rolled — emit completed candle then start a new one
            await self._emit(candle, pair)
            self._candles[pair] = _Candle(price, bucket_ts)

        self._candles[pair].update(price, volume)

    async def _emit(self, candle: _Candle, pair: str) -> None:
        payload = candle.to_dict(pair)
        try:
            if asyncio.iscoroutinefunction(self._on_candle):
                await self._on_candle(payload)
            else:
                self._on_candle(payload)
        except Exception as exc:
            logger.error("on_candle callback raised: %s", exc)

    # ------------------------------------------------------------------
    # Snapshot — current incomplete candle (for initial chart seed)
    # ------------------------------------------------------------------

    def get_current_candles(self) -> Dict[str, Dict]:
        """Return the in-progress candles for all pairs (may be partial minute)."""
        return {
            pair: candle.to_dict(pair)
            for pair, candle in self._candles.items()
        }


# ---------------------------------------------------------------------------
# Convenience: build pair list from tracked config symbols
# ---------------------------------------------------------------------------

def build_ws_pairs(exchange_client=None) -> List[str]:
    """
    Return a list of Kraken wsname pairs (e.g. "XBT/USD") from config.
    Falls back to a minimal default list if discovery fails.
    """
    import config as _config

    if _config.EXCHANGE != "kraken":
        return []

    if _config.TRADING_PAIRS:
        # If pairs are already in wsname format (contain '/') use as-is
        if all("/" in p for p in _config.TRADING_PAIRS):
            return list(_config.TRADING_PAIRS)

    # Try to fetch wsnames from the exchange
    if exchange_client is not None:
        try:
            result = exchange_client.get_trading_pairs()
            wsnames = [p["wsname"] for p in result.get("results", []) if p.get("wsname")]
            if wsnames:
                return wsnames
        except Exception as exc:
            logger.warning("Could not fetch trading pairs for WS: %s", exc)

    # Minimal safe default
    return ["XBT/USD", "ETH/USD", "SOL/USD", "ADA/USD", "XRP/USD"]
