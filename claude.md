# Trading Bot — Agent Documentation (claude.md)

> This file is the authoritative reference for AI coding agents working on this codebase.
> It covers architecture, all modules, database schema, strategy interfaces, API setup,
> sandbox rules, and contribution patterns.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [File Reference](#file-reference)
3. [Database Schema](#database-schema)
4. [Strategies](#strategies)
5. [Exchange API Setup](#exchange-api-setup)
6. [Configuration Reference](#configuration-reference)
7. [Adding a Custom Strategy](#adding-a-custom-strategy)
8. [RestrictedPython Sandbox Rules](#restrictedpython-sandbox-rules)
9. [CLI Commands](#cli-commands)
10. [React App Structure](#react-app-structure)
11. [FastAPI Endpoints](#fastapi-endpoints)

---

## Architecture Overview

The bot runs a **20-minute evaluation cycle** orchestrated by `CryptoBot` in `main.py`.
A separate **1-minute tick WebSocket** (`kraken_ws.py`) feeds real-time price data to the
React dashboard without affecting the bot's evaluation frequency.

```
┌─────────────────────────────────────────────────────────────┐
│                     CryptoBot (main.py)                     │
│                  20-minute evaluation cycle                 │
│                                                             │
│  1. collect_market_data()   ←── ExchangeClient              │
│  2. calculate_indicators()  ←── indicators.py               │
│  3. evaluate_and_exit()     ←── exit_manager.py             │
│  4. evaluate_entry()        ←── strategy.py / strategies_advanced.py │
│  5. save_metrics()          ←── metrics.py                  │
│  6. broadcast cycle end     ──► websocket_manager.py        │
└─────────────────────────────────────────────────────────────┘

┌──────────────┐    ┌────────────────┐    ┌─────────────────┐
│ kraken_ws.py │    │ api_server.py  │    │  React App      │
│ 1-min ticks  │───►│ FastAPI :8000  │◄──►│  :5173          │
│ (Kraken WS)  │    │                │    │                 │
└──────────────┘    └────────────────┘    └─────────────────┘
                           │
                    SQLite Database
                    (crypto_bot.db)
```

### Bot States (cold_start.py)

| State | Meaning |
|-------|---------|
| `COLD_START` | Collecting historical data. Need ≥101 candles per pair (~33.7 hrs). |
| `READY` | Data collected. Waiting for first entry signal. |
| `TRADING` | Actively evaluating and trading. |

### Indicator Availability

- RSI: requires ≥14 candles
- MACD: requires ≥26 candles
- Full strategy evaluation: requires ≥101 candles

---

## File Reference

| File | Purpose |
|------|---------|
| `main.py` | `CryptoBot` orchestrator. Runs the 20-min cycle loop. Entry point. |
| `strategy.py` | Legacy RSI/MACD/ROC confluence strategy. |
| `strategies_advanced.py` | 4 advanced strategies (Bollinger, Dual MA, Breakout, Regime). |
| `exit_manager.py` | Priority-ordered exit condition evaluation. |
| `position_manager.py` | Open/close positions. Paper & live trading. |
| `indicators.py` | RSI, MACD, ROC calculation + helper signal methods. |
| `database.py` | SQLite ORM. All DB reads/writes go through here. |
| `config.py` | All configuration constants + exchange factory function. |
| `robinhood_client.py` | Robinhood API client (Ed25519 auth). |
| `kraken_client.py` | Kraken API client (HMAC-SHA512 auth, DB nonce counter). |
| `kraken_ws.py` | Kraken public WebSocket. Aggregates 1-min OHLCV ticks. |
| `api_server.py` | FastAPI app. Bridges bot + React via REST + WebSocket. |
| `strategy_registry.py` | CRUD for user strategies. RestrictedPython sandbox runner. |
| `websocket_manager.py` | Broadcasts ticks + events to connected React clients. |
| `cold_start.py` | Manages bot state transitions + checkpoint persistence. |
| `metrics.py` | Calculates and saves portfolio performance metrics. |
| `mean_reversion_analytics.py` | Ornstein-Uhlenbeck half-life calculation for mean reversion. |
| `logger.py` | Structured logger that writes to `bot_log` table. |
| `data_bootstrap.py` | Bootstraps historical candles from CryptoCompare at startup. |
| `cli.py` | Command-line interface for manual bot control. |

---

## Database Schema

Database: `crypto_bot.db` (SQLite)

### Table 1: `price_history`
20-minute OHLCV candles + bid/ask data.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `symbol` | TEXT | e.g., `BTC-USD` |
| `timestamp` | INTEGER | Unix timestamp |
| `datetime` | TEXT | ISO 8601 |
| `open` | REAL | |
| `high` | REAL | |
| `low` | REAL | |
| `close` | REAL NOT NULL | |
| `volume` | REAL | |
| `best_bid` | REAL | |
| `best_ask` | REAL | |
| `spread` | REAL | ask - bid |
| UNIQUE | `(symbol, timestamp)` | |

### Table 2: `indicators`
Calculated indicator values per candle.

| Column | Type | Notes |
|--------|------|-------|
| `symbol` | TEXT | |
| `timestamp` | INTEGER | |
| `rsi_14` | REAL | RSI(14) |
| `macd` | REAL | MACD line |
| `macd_signal` | REAL | Signal line |
| `macd_histogram` | REAL | MACD - Signal |
| `roc_12` | REAL | Rate of Change(12) |
| `ema_12` | REAL | |
| `ema_26` | REAL | |

### Table 3: `trading_signals`
BUY/SELL signals with confidence scores.

| Column | Type | Notes |
|--------|------|-------|
| `signal_type` | TEXT | `BUY` or `SELL` |
| `confidence` | REAL | 0.0–1.0 |
| `rsi_value` | REAL | RSI at signal time |
| `macd_value` | REAL | |
| `roc_value` | REAL | |
| `reason` | TEXT | Human-readable explanation |

### Table 4: `positions`
Open and closed positions.

| Column | Type | Notes |
|--------|------|-------|
| `position_id` | TEXT UNIQUE | UUID |
| `symbol` | TEXT | |
| `entry_price` | REAL | |
| `quantity` | REAL | |
| `entry_value_usd` | REAL | |
| `entry_strategy` | TEXT | `legacy`, `mean_reversion`, `momentum`, `breakout` |
| `current_price` | REAL | Updated each cycle |
| `unrealized_pnl_usd` | REAL | |
| `unrealized_pnl_pct` | REAL | |
| `stop_loss_level` | REAL | Absolute price level |
| `special_tp_level` | REAL | Absolute price level |
| `status` | TEXT | `OPEN` or `CLOSED` |
| `exit_reason` | TEXT | Why position was closed |
| `realized_pnl_usd` | REAL | Set on close |
| `realized_pnl_pct` | REAL | Set on close |

### Table 5: `orders`

Order records with execution status.

| Column | Notes |
|--------|-------|
| `order_id` | Exchange-assigned ID |
| `client_order_id` | UUID generated client-side |
| `position_id` | FK → positions |
| `side` | `buy` or `sell` |
| `order_type` | `market`, `limit`, etc. |
| `status` | `pending`, `filled`, `cancelled` |

### Table 6: `executions`

Filled trade executions with price and fee.

### Table 7: `holdings`

Snapshot of crypto holdings at each cycle.

### Table 8: `performance_metrics`

Historical portfolio metrics per cycle.

| Column | Notes |
|--------|-------|
| `total_portfolio_value` | Cash + crypto value |
| `realized_pnl` | Cumulative realized P&L |
| `unrealized_pnl` | Current open position P&L |
| `win_rate` | Winning / total trades |
| `max_drawdown` | Max peak-to-trough |

### Table 9: `bot_log`

All log messages with category and level.

### Table 10: `nonce_counter` *(new)*

Stores monotonically increasing Kraken API nonce. Single row.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Always 1 |
| `value` | INTEGER | Atomically incremented |

Never reset this value. It must always increase across restarts.

### Table 11: `user_strategies` *(new)*

User-defined strategy code managed through the React Strategy Builder.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `name` | TEXT UNIQUE | Display name |
| `description` | TEXT | |
| `code` | TEXT | Python source (RestrictedPython-safe) |
| `parameters` | TEXT | JSON: `[{name, type, default, description}]` |
| `custom_metrics` | TEXT | JSON: `[{name, aggregation}]` |
| `enabled` | INTEGER | Boolean (0/1) |
| `created_at` | TEXT | ISO 8601 |
| `updated_at` | TEXT | ISO 8601 |

---

## Strategies

### Strategy Interface

All strategies must implement two functions:

```python
def evaluate_entry(data: dict) -> dict | None:
    """
    Returns a signal dict if entry conditions are met, otherwise None.
    Signal dict: {"signal": "BUY", "confidence": 0.8, "reason": "...", "strategy": "my_strategy"}
    """

def evaluate_exit(position: dict, data: dict) -> bool:
    """
    Returns True if the position should be closed.
    position keys: entry_price, current_price, unrealized_pnl_pct, hours_held, entry_strategy, ...
    """
```

### `data` Dictionary Keys Available to Strategies

| Key | Type | Description |
|-----|------|-------------|
| `prices` | `list[float]` | Close prices, newest last, ≥101 candles |
| `volumes` | `list[float]` | Volume per candle |
| `rsi` | `float` | Current RSI(14) |
| `macd` | `float` | MACD line |
| `macd_signal` | `float` | MACD signal line |
| `macd_histogram` | `float` | MACD - signal |
| `roc` | `float` | ROC(12) as percentage |
| `bb_zscore` | `float` | Bollinger Band z-score: (price - mean) / std |
| `bb_upper` | `float` | Upper band (mean + 2σ) |
| `bb_lower` | `float` | Lower band (mean - 2σ) |
| `regime` | `str` | `"trending"`, `"ranging"`, or `"unknown"` |
| `short_ma` | `float` | Short moving average (9 candles) |
| `long_ma` | `float` | Long moving average (36 candles) |
| `symbol` | `str` | e.g. `"BTC-USD"` |
| `timestamp` | `int` | Current Unix timestamp |

### Built-in Strategies

#### 1. Legacy RSI/MACD/ROC Confluence (`strategy.py`)

Ernest P. Chan-inspired confluence system.

- **Entry**: ≥2 of 3 indicators bullish + 0 bearish + ≥66% confidence
- **RSI**: BUY < 35, SELL > 75, Favorable: 55–75
- **MACD**: BUY on bullish crossover, SELL on bearish crossover
- **ROC**: BUY > +8%, SELL < -8%

#### 2. Bollinger Bands Mean Reversion (`strategies_advanced.py`, Chan Ch.3)

- Lookback: 20 candles (~6.7 hrs)
- Entry: `|bb_zscore| > 2.0`
- Exit: `|bb_zscore| < 0.5` OR 3× half-life timeout (via Ornstein-Uhlenbeck)
- Strategy stop loss: −15% (wider tolerance for convergence)
- Time exit: 144 candles (48 hrs)

#### 3. Dual MA Momentum (`strategies_advanced.py`, Chan Ch.6)

- Short MA: 9 candles (3 hrs), Long MA: 36 candles (12 hrs)
- Entry: Golden cross (`short_ma > long_ma`)
- Exit: Death cross (`short_ma < long_ma`)
- Strategy stop loss: −8% (tighter for trend following)
- Time exit: 54 candles (18 hrs)

#### 4. Intraday Breakout (`strategies_advanced.py`, Chan Ch.7)

- Entry: `|bb_zscore| > 2.0` AND `volume > 1.5× avg_volume`
- Detects high-volume price breakouts
- Strategy stop loss: −10%
- Time exit: 72 candles (24 hrs)

#### 5. Regime Detection (`strategies_advanced.py`, Chan Ch.8)

- Classifies market as `trending`, `ranging`, or `unknown` using normalized slope + volatility
- Adjusts strategy weights dynamically:
  - Trending → momentum 50%, breakout 30%, mean reversion 20%
  - Ranging → mean reversion 60%, momentum 20%, breakout 20%

### Exit Priority Chain (`exit_manager.py`)

Exits are evaluated in priority order. First match wins.

| Priority | Condition | Details |
|----------|-----------|---------|
| 0 | Strategy-specific exit | Mean rev: `bb_zscore < 0.5`. Momentum: death cross. |
| 1 | Hard stop loss | `current_price ≤ stop_loss_level` |
| 2 | Special +25% TP | Price ≥ +25% AND RSI 55–75 AND MACD maintaining strength |
| 3 | Indicator TP | RSI overbought reversal + MACD bearish cross + ≥5% profit |
| 4 | Time-based exit | Held > time_threshold AND stagnant (< stagnant_pct movement) |

---

## Exchange API Setup

### Kraken

**Key creation steps:**
1. Log in → Settings → API → Generate Key
2. Required permissions:
   - ✅ Query Funds
   - ✅ Query Open/Closed Orders & Trades
   - ✅ Modify Orders
   - ❌ Withdraw Funds (only if automating withdrawals)
3. Copy `API Key` and `Private Key` — **secret shown only once**
4. Set environment variables:
   ```
   EXCHANGE=kraken
   KRAKEN_API_KEY=your_key_here
   KRAKEN_PRIVATE_KEY=your_base64_secret_here
   ```

**Authentication (HMAC-SHA512):**
```python
# For every private request:
nonce = db.get_next_nonce()           # DB counter — always increasing
postdata = f"nonce={nonce}&{params}"
sha = hashlib.sha256(postdata.encode()).digest()
secret = base64.b64decode(private_key)
message = endpoint.encode() + sha
signature = base64.b64encode(hmac.new(secret, message, hashlib.sha512).digest())
headers = {"API-Key": api_key, "API-Sign": signature.decode()}
```

**Nonce rule:** The `nonce_counter` DB table ensures nonces survive restarts and remain strictly
increasing. Never use `time.time()` as a nonce source — a restart mid-second would reuse values.

**Key error codes:**
- `EAPI:Invalid key` — wrong key or permissions
- `EAPI:Invalid signature` — check HMAC construction
- `EAPI:Rate limit exceeded` — back off, check `X-RateLimit-Remaining`
- `EOrder:Insufficient funds` — not enough balance
- `EOrder:Order minimum not met` — volume below `ordermin` from AssetPairs

**Rate limits:** 15-second window. Each private call has a cost (Balance=0.1, AddOrder=0.1,
OpenOrders=1.0, TradesHistory=2.0). Monitor `X-RateLimit-Remaining` header.

**WebSocket public:** `wss://ws.kraken.com` — subscribe to `trade` channel for 1-min ticks.
**WebSocket private:** `wss://ws-auth.kraken.com` — requires token from `/0/private/GetWebSocketsToken`.

### Robinhood

**Authentication (Ed25519):**
```python
private_key_seed = base64.b64decode(BASE64_PRIVATE_KEY)
private_key = SigningKey(private_key_seed)  # from PyNaCl
message = f"{api_key}{timestamp}{path}{method}{body}"
signature = base64.b64encode(private_key.sign(message.encode()).signature)
headers = {"x-api-key": api_key, "x-signature": signature, "x-timestamp": str(timestamp)}
```

**Environment variables:**
```
EXCHANGE=robinhood
API_KEY=your_key_here
BASE64_PRIVATE_KEY=your_base64_private_key
```

---

## Configuration Reference

### `config.py` Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `EXCHANGE` | `"kraken"` | `"kraken"` or `"robinhood"` |
| `TOTAL_CAPITAL` | `5000.00` | Total portfolio size in USD |
| `MAX_POSITION_SIZE_PCT` | `0.05` | Max 5% of capital per trade = $250 |
| `TRADING_MODE` | `"paper"` | `"paper"` or `"live"` |
| `INTERVAL_SECONDS` | `1200` | 20-minute candles |
| `STOP_LOSS_PCT` | `-0.10` | Hard stop at −10% |
| `MAX_DAILY_LOSS_PCT` | `0.05` | Halt trading if daily loss > 5% |

### `EXIT_CONFIG`

| Key | Default | Description |
|-----|---------|-------------|
| `stop_loss_pct` | `-0.10` | Hard stop loss |
| `special_tp_pct` | `0.25` | +25% take profit with indicator confirmation |
| `time_exit_candles.mean_reversion` | `144` | 48 hrs |
| `time_exit_candles.momentum` | `54` | 18 hrs |
| `time_exit_candles.breakout` | `72` | 24 hrs |
| `regime_time_multipliers.ranging` | `1.5` | Extra time in ranging markets |
| `regime_time_multipliers.trending` | `0.75` | Less time in trending markets |
| `half_life_exit_multiplier` | `3.0` | Exit after 3× Ornstein-Uhlenbeck half-life |

### `STRATEGY_STOP_LOSS`

| Strategy | Stop | Rationale |
|----------|------|-----------|
| `mean_reversion` | `-0.15` | Wider — positions often dip before reverting |
| `momentum` | `-0.08` | Tighter — trends can reverse sharply |
| `breakout` | `-0.10` | Standard |
| `legacy` | `-0.10` | Standard |

### `MULTI_STRATEGY_CONFIG`

| Section | Key | Default |
|---------|-----|---------|
| `bollinger_bands` | `lookback` | 20 |
| | `std_dev` | 2.0 |
| | `entry_zscore` | 2.0 |
| | `exit_zscore` | 0.5 |
| `dual_ma` | `short_period` | 9 |
| | `long_period` | 36 |
| `kelly_criterion` | `enabled` | True |
| | `safety_factor` | 0.5 (half-Kelly) |
| | `min_trades` | 20 |

---

## Adding a Custom Strategy

### Step 1: Write the strategy class

```python
class MyStrategy:
    def __init__(self, params: dict = None):
        self.params = params or {}
        # Declare custom metrics — these appear in the Analytics page
        self.metrics = {
            "signal_count": 0,
            "avg_zscore_entry": 0.0,
        }

    def evaluate_entry(self, data: dict) -> dict | None:
        """
        data keys: prices, volumes, rsi, macd, macd_signal, macd_histogram,
                   roc, bb_zscore, bb_upper, bb_lower, regime, short_ma, long_ma,
                   symbol, timestamp
        """
        # Example: enter when RSI oversold AND MACD bullish
        if data["rsi"] < 35 and data["macd"] > data["macd_signal"]:
            self.metrics["signal_count"] += 1
            return {
                "signal": "BUY",
                "confidence": 0.75,
                "reason": f"RSI={data['rsi']:.1f} oversold + MACD bullish",
                "strategy": "my_strategy",
            }
        return None

    def evaluate_exit(self, position: dict, data: dict) -> bool:
        """
        position keys: entry_price, current_price, unrealized_pnl_pct,
                       hours_held, candles_held, entry_strategy, stop_loss_level
        """
        # Example: exit when RSI overbought
        return data["rsi"] > 70
```

### Step 2: Register in `strategies_advanced.py`

```python
from my_strategy import MyStrategy

STRATEGY_REGISTRY = {
    "my_strategy": MyStrategy,
    # ... existing strategies ...
}
```

### Step 3: Add to `EXIT_CONFIG` (optional)

```python
EXIT_CONFIG["time_exit_candles"]["my_strategy"] = 96   # 32 hours
STRATEGY_STOP_LOSS["my_strategy"] = -0.12
```

### Step 4: Declare custom metrics (optional)

If your strategy has a `metrics` dict, add declarations to `user_strategies` table:
```json
[
  {"name": "signal_count", "aggregation": "sum"},
  {"name": "avg_zscore_entry", "aggregation": "avg"}
]
```
These will auto-render in the Analytics page under "Custom Strategy Metrics".

---

## RestrictedPython Sandbox Rules

User strategies submitted through the React Strategy Builder are executed inside a
**RestrictedPython** sandbox for backtesting. Production trading uses built-in strategies only.

### Allowed

- All Python builtins except those blocked below
- `import math`
- `import statistics`
- `import numpy as np` (read-only array operations)
- `list`, `dict`, `set`, `tuple`, `range`, `enumerate`, `zip`, `sorted`, `min`, `max`, `sum`, `abs`, `round`, `len`
- `if`, `for`, `while`, `def`, `class`, `return`, `yield`
- f-strings, list comprehensions, dict comprehensions

### Blocked

- `import os`, `import sys`, `import subprocess` — filesystem/process access
- `import socket`, `import requests`, `import urllib` — network access
- `open()`, `exec()`, `eval()`, `compile()` — dynamic execution
- `__import__()`, `getattr()`, `setattr()`, `delattr()` — reflection
- `globals()`, `locals()` — scope inspection

### Resource Limits (subprocess)

- CPU time: 5 seconds maximum
- Memory: 128 MB maximum
- Returns `403` if sandbox detects a violation

---

## CLI Commands

```bash
python cli.py start              # Start bot
python cli.py status             # Show positions + metrics
python cli.py history [--limit N] # Show last N closed trades
python cli.py signals            # Show RSI/MACD/ROC signals per pair
python cli.py close TICKER       # Manually close a position
python cli.py close --all        # Close all positions
python cli.py test-api           # Test exchange connection
python cli.py reset              # Wipe database (requires typing YES)
```

---

## React App Structure

```
react-app/src/
├── pages/
│   ├── Onboarding.tsx      # 6-step wizard (exchange → keys → capital → pairs → strategy → launch)
│   ├── Dashboard.tsx       # Live positions + signal feed + metrics
│   ├── Markets.tsx         # TradingView chart + indicators
│   ├── Strategies.tsx      # Monaco editor + backtest
│   ├── Analytics.tsx       # Equity curve + per-strategy breakdown
│   ├── Positions.tsx       # Open + closed positions table
│   └── Settings.tsx        # Config + API key management
├── stores/
│   ├── botStore.ts         # Status, mode, exchange
│   ├── portfolioStore.ts   # Metrics, positions
│   ├── strategyStore.ts    # Strategy list, backtest results
│   ├── marketStore.ts      # Selected symbol, candle data
│   └── settingsStore.ts    # Config values
├── hooks/
│   ├── useRealtimeSocket.ts # WebSocket connection to /ws
│   └── useApi.ts           # TanStack Query hooks
└── components/
    ├── Chart/              # TradingView Lightweight Charts wrapper
    ├── StrategyEditor/     # Monaco Editor wrapper
    └── ui/                 # shadcn/ui components
```

---

## FastAPI Endpoints

Full reference in `api_server.py`. Key endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/status` | Bot state, mode, exchange, cold start progress |
| GET | `/api/portfolio` | Value, P&L, win rate, drawdown |
| GET | `/api/positions` | Open positions |
| GET | `/api/positions/history` | Closed positions |
| GET | `/api/signals` | Recent signals |
| GET | `/api/markets/{symbol}/candles` | 20-min OHLCV |
| GET | `/api/markets/{symbol}/indicators` | Latest indicator values |
| GET | `/api/markets` | All pairs + prices |
| GET | `/api/strategies` | Strategy list |
| POST | `/api/strategies` | Save user strategy |
| POST | `/api/strategies/{id}/backtest` | Run sandboxed backtest |
| POST | `/api/bot/start` | Start bot |
| POST | `/api/bot/stop` | Stop bot |
| PUT | `/api/config` | Update config |
| POST | `/api/exchange/test` | Test API credentials |
| WS | `/ws` | Real-time ticks, signals, trades, metrics |

---

*Last updated: auto-generated. Keep in sync when adding strategies, endpoints, or DB tables.*
