"""
FastAPI Application Server
Bridges the Python trading bot and the React frontend.
Serves REST endpoints and a WebSocket at /ws for real-time events.

Run with:
    uvicorn api.api_server:app --host 0.0.0.0 --port 8000 --reload
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

from core import config
from core.database import Database
from api.auth_router import router as auth_router, decode_token, decrypt_credential, get_current_user
from api.strategy_registry import StrategyRegistry
from api.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared singletons
# ---------------------------------------------------------------------------

db = Database()
registry = StrategyRegistry(db=db)

# Bot subprocess handle
_bot_process: Optional[subprocess.Popen] = None
_bot_lock = threading.Lock()

# Background KrakenTickStreamer task (set during lifespan)
_tick_task: Optional[asyncio.Task] = None


# ---------------------------------------------------------------------------
# Lifespan — start/stop background tasks
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _tick_task

    # Phase 4: Load exchange credentials from DB for user_id=1 (single-user mode).
    # Credentials stored via the onboarding wizard take precedence over .env values.
    if config.CREDENTIAL_ENCRYPTION_KEY:
        try:
            for _exchange, _key_attr, _priv_attr in [
                ("kraken",    "KRAKEN_API_KEY",    "KRAKEN_PRIVATE_KEY"),
                ("robinhood", "API_KEY",            "BASE64_PRIVATE_KEY"),
            ]:
                _row = db.get_user_credentials_raw(1, _exchange)
                if _row:
                    config.__dict__[_key_attr]  # check attribute exists
                    setattr(config, _key_attr,  decrypt_credential(_row["api_key_encrypted"]))
                    setattr(config, _priv_attr, decrypt_credential(_row["private_key_encrypted"]))
                    logger.info("Loaded %s credentials from DB for user_id=1", _exchange)
        except Exception as _exc:
            logger.warning("Could not load credentials from DB: %s", _exc)

    # Start Kraken 1-min tick streamer only when exchange is Kraken
    if config.EXCHANGE == "kraken" and config.KRAKEN_API_KEY:
        from exchanges.kraken_ws import KrakenTickStreamer, build_ws_pairs
        from kraken_client import KrakenClient

        exchange = KrakenClient(db=db)
        ws_pairs = build_ws_pairs(exchange)

        async def on_candle(candle: Dict) -> None:
            await ws_manager.broadcast_tick(candle)

        streamer = KrakenTickStreamer(pairs=ws_pairs, on_candle=on_candle)
        _tick_task = asyncio.create_task(streamer.run())
        logger.info("KrakenTickStreamer started for %d pairs", len(ws_pairs))

    yield

    if _tick_task and not _tick_task.done():
        _tick_task.cancel()
        try:
            await _tick_task
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Trading Bot API",
    version="1.0.0",
    description="REST + WebSocket API bridging the Python trading bot and React dashboard.",
    lifespan=lifespan,
)

# JWT middleware — protects all /api/* routes.
# OPTIONS (CORS preflight) and /auth/* are always allowed through.
class _JWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        if request.method != "OPTIONS" and request.url.path.startswith("/api/"):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return JSONResponse({"detail": "Not authenticated"}, status_code=401)
            try:
                decode_token(auth_header[7:])
            except HTTPException:
                return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)
        return await call_next(request)

app.add_middleware(_JWTMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth router (public — /auth/* routes handle their own auth via Depends)
app.include_router(auth_router)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _bot_is_running() -> bool:
    with _bot_lock:
        return _bot_process is not None and _bot_process.poll() is None


def _cold_start_progress() -> Dict:
    try:
        with open(config.COLD_START_CONFIG.get("data_checkpoint_file", "cold_start_checkpoint.json")) as f:
            ckpt = json.load(f)
        required = config.COLD_START_CONFIG.get("min_candles_required", 101)
        # Find min candles across all tracked symbols
        symbol_counts = ckpt.get("symbol_candle_counts", {})
        if symbol_counts:
            current = min(symbol_counts.values())
        else:
            current = 0
        return {
            "current": current,
            "required": required,
            "pct": round(min(current / required * 100, 100), 1),
            "state": ckpt.get("state", "COLD_START"),
        }
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return {"current": 0, "required": 101, "pct": 0.0, "state": "COLD_START"}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class StrategyCreate(BaseModel):
    name: str
    description: str = ""
    code: str
    parameters: List[Dict[str, Any]] = []
    custom_metrics: List[Dict[str, Any]] = []


class StrategyUpdate(StrategyCreate):
    pass


class ConfigUpdate(BaseModel):
    total_capital: Optional[float] = None
    max_position_size_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    max_daily_loss_pct: Optional[float] = None
    trading_mode: Optional[str] = None
    trading_pairs: Optional[List[str]] = None
    exchange: Optional[str] = None


class ExchangeCredentials(BaseModel):
    exchange: str
    api_key: str
    private_key: str


# ---------------------------------------------------------------------------
# Status & portfolio endpoints
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def get_status():
    """Bot state, mode, exchange, and cold start progress."""
    progress = _cold_start_progress()
    return {
        "running": _bot_is_running(),
        "state": progress["state"],
        "mode": config.TRADING_MODE,
        "exchange": config.EXCHANGE,
        "cold_start": progress,
    }


@app.get("/api/portfolio")
async def get_portfolio():
    """Latest portfolio metrics snapshot."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM performance_metrics
            ORDER BY timestamp DESC LIMIT 1
        """)
        row = cursor.fetchone()
    if not row:
        return {"total_portfolio_value": 0, "realized_pnl": 0, "win_rate": 0, "max_drawdown": 0}
    return dict(row)


@app.get("/api/positions")
async def get_open_positions():
    """All currently open positions."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM positions WHERE status = 'OPEN'
            ORDER BY entry_timestamp DESC
        """)
        rows = cursor.fetchall()
    return [dict(r) for r in rows]


@app.get("/api/positions/history")
async def get_closed_positions(limit: int = 50, strategy: Optional[str] = None):
    """Closed positions, newest first. Filterable by strategy."""
    query = "SELECT * FROM positions WHERE status = 'CLOSED'"
    params: list = []
    if strategy:
        query += " AND entry_strategy = ?"
        params.append(strategy)
    query += " ORDER BY exit_timestamp DESC LIMIT ?"
    params.append(limit)

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
    return [dict(r) for r in rows]


@app.get("/api/signals")
async def get_signals(limit: int = 20):
    """Recent trading signals with confidence and indicator values."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM trading_signals
            ORDER BY timestamp DESC LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Market data endpoints
# ---------------------------------------------------------------------------

@app.get("/api/markets")
async def get_markets():
    """All tracked symbols with their latest price."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ph.symbol, ph.close as price, ph.best_bid, ph.best_ask, ph.timestamp
            FROM price_history ph
            INNER JOIN (
                SELECT symbol, MAX(timestamp) as max_ts
                FROM price_history GROUP BY symbol
            ) latest ON ph.symbol = latest.symbol AND ph.timestamp = latest.max_ts
            ORDER BY ph.symbol
        """)
        rows = cursor.fetchall()
    return [dict(r) for r in rows]


@app.get("/api/markets/{symbol}/candles")
async def get_candles(symbol: str, limit: int = 200):
    """Historical 20-minute OHLCV candles for a symbol (newest limit rows)."""
    rows = db.get_recent_prices(symbol, limit)
    return rows


@app.get("/api/markets/{symbol}/indicators")
async def get_indicators(symbol: str):
    """Latest indicator values for a symbol."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.*, ph.close as current_price
            FROM indicators i
            LEFT JOIN price_history ph ON ph.symbol = i.symbol AND ph.timestamp = i.timestamp
            WHERE i.symbol = ?
            ORDER BY i.timestamp DESC LIMIT 1
        """, (symbol,))
        row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"No indicators found for {symbol}")
    return dict(row)


# ---------------------------------------------------------------------------
# Strategy endpoints
# ---------------------------------------------------------------------------

BUILTIN_STRATEGIES = [
    {
        "id": "builtin_legacy",
        "name": "Legacy RSI/MACD/ROC",
        "description": "Confluence of RSI, MACD, and Rate-of-Change. Entry when ≥2/3 indicators agree.",
        "builtin": True,
        "risk_level": "medium",
        "parameters": [
            {"name": "rsi_buy_threshold", "type": "float", "default": 35, "description": "RSI level to trigger buy"},
            {"name": "rsi_sell_threshold", "type": "float", "default": 75, "description": "RSI level to trigger sell"},
            {"name": "roc_buy_pct", "type": "float", "default": 8.0, "description": "ROC% required for buy signal"},
        ],
    },
    {
        "id": "builtin_mean_reversion",
        "name": "Bollinger Bands Mean Reversion",
        "description": "Chan Ch.3 — Enter when price >2σ from mean. Exit when it converges.",
        "builtin": True,
        "risk_level": "low",
        "parameters": [
            {"name": "lookback", "type": "int", "default": 20, "description": "Bollinger lookback candles"},
            {"name": "entry_zscore", "type": "float", "default": 2.0, "description": "Z-score threshold to enter"},
            {"name": "exit_zscore", "type": "float", "default": 0.5, "description": "Z-score threshold to exit"},
        ],
    },
    {
        "id": "builtin_momentum",
        "name": "Dual MA Momentum",
        "description": "Chan Ch.6 — Golden cross / death cross on 9-candle and 36-candle MAs.",
        "builtin": True,
        "risk_level": "medium",
        "parameters": [
            {"name": "short_period", "type": "int", "default": 9, "description": "Short MA candles"},
            {"name": "long_period", "type": "int", "default": 36, "description": "Long MA candles"},
        ],
    },
    {
        "id": "builtin_breakout",
        "name": "Intraday Breakout",
        "description": "Chan Ch.7 — Large price move with above-average volume.",
        "builtin": True,
        "risk_level": "high",
        "parameters": [
            {"name": "vol_threshold", "type": "float", "default": 2.0, "description": "Z-score for breakout"},
            {"name": "volume_multiplier", "type": "float", "default": 1.5, "description": "Min volume vs average"},
        ],
    },
    {
        "id": "builtin_regime",
        "name": "Regime Detection",
        "description": "Chan Ch.8 — Dynamically weights strategies based on trending/ranging market regime.",
        "builtin": True,
        "risk_level": "medium",
        "parameters": [],
    },
]


@app.get("/api/strategies")
async def list_strategies():
    """Returns all built-in and user-defined strategies."""
    user_strategies = registry.list_strategies()
    return {
        "builtin": BUILTIN_STRATEGIES,
        "user": user_strategies,
    }


@app.post("/api/strategies", status_code=201)
async def create_strategy(body: StrategyCreate):
    """Save a new user strategy. Code is validated with RestrictedPython before saving."""
    try:
        strategy_id = registry.save_strategy(
            name=body.name,
            code=body.code,
            description=body.description,
            parameters=body.parameters,
            custom_metrics=body.custom_metrics,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"id": strategy_id, "name": body.name}


@app.put("/api/strategies/{strategy_id}")
async def update_strategy(strategy_id: int, body: StrategyUpdate):
    """Update an existing user strategy."""
    if registry.get_strategy(strategy_id) is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    try:
        registry.save_strategy(
            name=body.name,
            code=body.code,
            description=body.description,
            parameters=body.parameters,
            custom_metrics=body.custom_metrics,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"id": strategy_id}


@app.delete("/api/strategies/{strategy_id}", status_code=204)
async def delete_strategy(strategy_id: int):
    """Delete a user strategy."""
    if not registry.delete_strategy(strategy_id):
        raise HTTPException(status_code=404, detail="Strategy not found")


@app.post("/api/strategies/{strategy_id}/backtest")
async def backtest_strategy(strategy_id: int, symbol: Optional[str] = None, limit: int = 500):
    """
    Run a sandboxed backtest against historical price_history data.
    Returns equity_curve, trade list, and summary statistics.
    """
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: registry.run_backtest(strategy_id, symbol, limit)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result


@app.patch("/api/strategies/{strategy_id}/enabled")
async def toggle_strategy(strategy_id: int, enabled: bool):
    """Enable or disable a user strategy."""
    if registry.get_strategy(strategy_id) is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    registry.set_enabled(strategy_id, enabled)
    return {"id": strategy_id, "enabled": enabled}


# ---------------------------------------------------------------------------
# Bot control endpoints
# ---------------------------------------------------------------------------

@app.post("/api/bot/start")
async def start_bot():
    """Launch the bot as a subprocess."""
    global _bot_process
    with _bot_lock:
        if _bot_is_running():
            return {"running": True, "message": "Bot already running"}
        _bot_process = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    await ws_manager.broadcast_status("starting")
    return {"running": True, "pid": _bot_process.pid}


@app.post("/api/bot/stop")
async def stop_bot():
    """Send SIGTERM to the bot subprocess for graceful shutdown."""
    global _bot_process
    with _bot_lock:
        if not _bot_is_running():
            return {"running": False, "message": "Bot not running"}
        try:
            _bot_process.terminate()
        except OSError:
            pass
    await ws_manager.broadcast_status("stopped")
    return {"running": False}


# ---------------------------------------------------------------------------
# Configuration endpoint
# ---------------------------------------------------------------------------

@app.put("/api/config")
async def update_config(body: ConfigUpdate):
    """
    Update runtime configuration.
    Changes are written to the .env file so they survive restarts.
    Only provided (non-None) fields are updated.
    """
    env_map = {
        "total_capital": "TOTAL_CAPITAL",
        "max_position_size_pct": "MAX_POSITION_SIZE_PCT",
        "stop_loss_pct": "STOP_LOSS_PCT",
        "max_daily_loss_pct": "MAX_DAILY_LOSS_PCT",
        "trading_mode": "TRADING_MODE",
        "exchange": "EXCHANGE",
    }
    env_path = ".env"
    lines: List[str] = []

    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = f.readlines()

    updates = body.dict(exclude_none=True)
    for field, value in updates.items():
        if field == "trading_pairs":
            continue  # handled separately
        env_key = env_map.get(field)
        if env_key is None:
            continue
        # Convert pct floats (0.05 → "5.0")
        if "pct" in field and isinstance(value, float) and value <= 1.0:
            value = str(abs(value) * 100)
        written = False
        for i, line in enumerate(lines):
            if line.startswith(f"{env_key}="):
                lines[i] = f"{env_key}={value}\n"
                written = True
                break
        if not written:
            lines.append(f"{env_key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(lines)

    return {"updated": list(updates.keys()), "message": "Restart bot to apply changes."}


# ---------------------------------------------------------------------------
# Exchange credentials endpoint
# ---------------------------------------------------------------------------

@app.post("/api/exchange/test")
async def test_exchange(body: ExchangeCredentials):
    """
    Validate exchange API credentials by calling the balance endpoint.
    Credentials are written to .env on success.
    API keys never leave the server — only a success/fail response is returned.
    """
    if body.exchange == "kraken":
        from kraken_client import KrakenClient, KrakenAuthError

        # Temporarily build a client with provided keys (not from config)
        class _TempDB:
            def get_next_nonce(self):
                import time
                return int(time.time() * 1000)

        client = KrakenClient(
            api_key=body.api_key,
            private_key=body.private_key,
            db=_TempDB(),
        )
        try:
            account = client.get_account()
            usd = account.get("buying_power", 0)
        except KrakenAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Kraken API error: {exc}")

    elif body.exchange == "robinhood":
        from robinhood_client import RobinhoodClient

        client = RobinhoodClient(
            api_key=body.api_key,
            private_key_base64=body.private_key,
        )
        try:
            account = client.get_account()
            usd = float(account.get("buying_power", 0))
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Robinhood API error: {exc}")
    else:
        raise HTTPException(status_code=400, detail=f"Unknown exchange: {body.exchange}")

    # Write validated keys to .env
    _write_credentials_to_env(body.exchange, body.api_key, body.private_key)

    return {
        "success": True,
        "exchange": body.exchange,
        "buying_power_usd": round(float(usd), 2),
    }


def _write_credentials_to_env(exchange: str, api_key: str, private_key: str) -> None:
    """Write exchange credentials to .env file securely (server-side only)."""
    env_path = ".env"
    lines: List[str] = []
    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = f.readlines()

    if exchange == "kraken":
        keys_to_set = {
            "EXCHANGE": "kraken",
            "KRAKEN_API_KEY": api_key,
            "KRAKEN_PRIVATE_KEY": private_key,
        }
    else:
        keys_to_set = {
            "EXCHANGE": "robinhood",
            "API_KEY": api_key,
            "BASE64_PRIVATE_KEY": private_key,
        }

    for env_key, value in keys_to_set.items():
        written = False
        for i, line in enumerate(lines):
            if line.startswith(f"{env_key}="):
                lines[i] = f"{env_key}={value}\n"
                written = True
                break
        if not written:
            lines.append(f"{env_key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(lines)


# ---------------------------------------------------------------------------
# Analytics endpoint
# ---------------------------------------------------------------------------

@app.get("/api/analytics")
async def get_analytics():
    """Aggregate analytics: equity curve, per-strategy stats, regime matrix."""
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Equity curve (last 500 snapshots)
        cursor.execute("""
            SELECT timestamp, total_portfolio_value as equity,
                   realized_pnl, win_rate, max_drawdown
            FROM performance_metrics
            ORDER BY timestamp ASC
        """)
        equity_curve = [dict(r) for r in cursor.fetchall()]

        # Per-strategy breakdown
        cursor.execute("""
            SELECT
                entry_strategy as strategy,
                COUNT(*) as total_trades,
                SUM(CASE WHEN realized_pnl_pct > 0 THEN 1 ELSE 0 END) as wins,
                ROUND(AVG(realized_pnl_pct) * 100, 2) as avg_pnl_pct,
                ROUND(AVG(hours_held), 1) as avg_hold_hrs
            FROM positions
            WHERE status = 'CLOSED' AND realized_pnl_pct IS NOT NULL
            GROUP BY entry_strategy
        """)
        by_strategy = [dict(r) for r in cursor.fetchall()]
        for row in by_strategy:
            row["win_rate"] = round(row["wins"] / row["total_trades"] * 100, 1) if row["total_trades"] else 0

        # P&L distribution buckets
        cursor.execute("""
            SELECT realized_pnl_pct FROM positions
            WHERE status = 'CLOSED' AND realized_pnl_pct IS NOT NULL
        """)
        pnl_values = [row[0] * 100 for row in cursor.fetchall()]

    return {
        "equity_curve": equity_curve,
        "by_strategy": by_strategy,
        "pnl_distribution": pnl_values,
    }


# ---------------------------------------------------------------------------
# Robinhood keypair generation
# ---------------------------------------------------------------------------

@app.get("/api/setup/robinhood-keypair")
async def generate_robinhood_keypair(_: dict = Depends(get_current_user)):
    """
    Generate a fresh Ed25519 keypair for Robinhood API authentication.
    The caller receives the public key (to register on Robinhood's website)
    and the private key in Base64 (to store locally — shown only once).
    """
    import base64
    from nacl.signing import SigningKey

    signing_key = SigningKey.generate()
    private_key_b64 = base64.b64encode(bytes(signing_key)).decode()
    public_key_b64 = base64.b64encode(bytes(signing_key.verify_key)).decode()
    return {
        "public_key_base64": public_key_b64,
        "private_key_base64": private_key_b64,
    }


# ---------------------------------------------------------------------------
# Bot log endpoint
# ---------------------------------------------------------------------------

@app.get("/api/logs")
async def get_logs(limit: int = 50, category: Optional[str] = None):
    """Recent bot log entries."""
    query = "SELECT * FROM bot_log"
    params: list = []
    if category:
        query += " WHERE category = ?"
        params.append(category)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    Real-time event stream for the React dashboard.
    Pushes: tick (1-min candle), signal, trade, metrics, status.
    """
    await ws_manager.connect(ws)
    try:
        # Send current bot status immediately on connect
        progress = _cold_start_progress()
        await ws.send_text(json.dumps({
            "type": "status",
            "running": _bot_is_running(),
            "state": progress["state"],
            "cold_start": progress,
        }))
        # Keep connection alive by echoing pings
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(ws)
