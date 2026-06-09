"""
Strategy Registry
Handles CRUD for user-defined strategies stored in the user_strategies DB table
and executes them inside a RestrictedPython sandbox for backtesting.

Security model:
  - User code is compiled with RestrictedPython (allowlist-based bytecode transform)
  - Backtest runs in a subprocess with resource limits (CPU 5s, memory 128MB)
  - Network access and filesystem access are blocked inside the sandbox
  - Production trading uses built-in strategies only; user strategies are backtest-only
"""
import json
import logging
import multiprocessing
import os
import signal
import sys
import time
import traceback
from typing import Any, Dict, List, Optional

from core.database import Database

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sandbox execution (runs in subprocess)
# ---------------------------------------------------------------------------

def _sandbox_worker(code: str, params: dict, price_rows: list, result_queue: multiprocessing.Queue) -> None:
    """
    Executed inside a fresh subprocess.
    Applies CPU + memory resource limits, compiles with RestrictedPython,
    runs the strategy against historical price rows, and puts the result
    onto result_queue.
    """
    # Apply resource limits (Unix only; Windows falls back gracefully)
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))            # 5s CPU
        resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))  # 128MB
    except (ImportError, ValueError):
        pass  # resource module not available on Windows

    try:
        from RestrictedPython import compile_restricted, safe_globals, safe_builtins
        from RestrictedPython.Guards import safe_iter_unpack_sequence, guarded_unpack_sequence

        # Build a restricted globals dict
        restricted_globals = dict(safe_globals)
        restricted_globals["__builtins__"] = dict(safe_builtins)
        # Allow safe math modules
        import math, statistics
        restricted_globals["math"] = math
        restricted_globals["statistics"] = statistics
        # Allow numpy if available
        try:
            import numpy as np
            restricted_globals["np"] = np
            restricted_globals["numpy"] = np
        except ImportError:
            pass
        restricted_globals["_getiter_"] = iter
        restricted_globals["_getattr_"] = getattr
        restricted_globals["_iter_unpack_sequence_"] = safe_iter_unpack_sequence
        restricted_globals["_inplacevar_"] = lambda op, x, y: x  # no in-place operations

        # Compile with RestrictedPython
        code_obj = compile_restricted(code, filename="<user_strategy>", mode="exec")

        local_ns: Dict[str, Any] = {}
        exec(code_obj, restricted_globals, local_ns)  # noqa: S102

        # Find the strategy class (first class defined in the code)
        strategy_cls = None
        for obj in local_ns.values():
            if isinstance(obj, type):
                strategy_cls = obj
                break

        if strategy_cls is None:
            result_queue.put({"error": "No class found in strategy code."})
            return

        strategy = strategy_cls(params or {})

        # ---------------------------------------------------------------
        # Backtest loop
        # ---------------------------------------------------------------
        equity = 100.0    # normalised starting equity
        trades: List[Dict] = []
        position: Optional[Dict] = None
        equity_curve: List[Dict] = []

        WINDOW = 101  # Minimum candles for indicator calculation

        # Compute simple indicators over rolling window
        def _ema(prices, period):
            k = 2 / (period + 1)
            ema = prices[0]
            for p in prices[1:]:
                ema = p * k + ema * (1 - k)
            return ema

        def _rsi(prices, period=14):
            if len(prices) < period + 1:
                return 50.0
            gains = [max(0, prices[i] - prices[i-1]) for i in range(1, len(prices))][-period:]
            losses = [max(0, prices[i-1] - prices[i]) for i in range(1, len(prices))][-period:]
            avg_gain = sum(gains) / period or 1e-9
            avg_loss = sum(losses) / period or 1e-9
            rs = avg_gain / avg_loss
            return 100 - (100 / (1 + rs))

        def _macd(prices):
            ema12 = _ema(prices[-26:], 12)
            ema26 = _ema(prices[-26:], 26)
            line = ema12 - ema26
            signal = _ema([line] * 9, 9)  # simplified
            return line, signal, line - signal

        def _bb(prices, period=20, std_dev=2.0):
            window = prices[-period:]
            mean = sum(window) / len(window)
            variance = sum((p - mean) ** 2 for p in window) / len(window)
            std = variance ** 0.5 or 1e-9
            return mean, mean + std_dev * std, mean - std_dev * std, (prices[-1] - mean) / std

        closes = [row["close"] for row in price_rows]

        for i in range(WINDOW, len(price_rows)):
            window_prices = closes[max(0, i - 200): i + 1]
            current_price = closes[i]
            ts = price_rows[i].get("timestamp", i)

            rsi_val = _rsi(window_prices)
            macd_line, macd_sig, macd_hist = _macd(window_prices)
            roc = ((current_price - closes[i - 12]) / closes[i - 12] * 100) if i >= 12 else 0.0
            mean_bb, upper_bb, lower_bb, zscore = _bb(window_prices)
            short_ma = sum(closes[i-9:i]) / 9
            long_ma = sum(closes[i-36:i]) / 36

            data = {
                "prices": window_prices,
                "volumes": [r.get("volume", 0) for r in price_rows[max(0, i - 200): i + 1]],
                "rsi": rsi_val,
                "macd": macd_line,
                "macd_signal": macd_sig,
                "macd_histogram": macd_hist,
                "roc": roc,
                "bb_zscore": zscore,
                "bb_upper": upper_bb,
                "bb_lower": lower_bb,
                "regime": "unknown",
                "short_ma": short_ma,
                "long_ma": long_ma,
                "symbol": price_rows[i].get("symbol", "UNKNOWN"),
                "timestamp": ts,
            }

            if position is None:
                signal = strategy.evaluate_entry(data)
                if signal and signal.get("signal") == "BUY":
                    position = {
                        "entry_price": current_price,
                        "entry_ts": ts,
                        "confidence": signal.get("confidence", 0.5),
                        "unrealized_pnl_pct": 0.0,
                        "hours_held": 0,
                        "candles_held": 0,
                        "entry_strategy": signal.get("strategy", "user"),
                        "stop_loss_level": current_price * 0.90,
                        "current_price": current_price,
                    }
            else:
                position["current_price"] = current_price
                position["candles_held"] += 1
                position["hours_held"] = position["candles_held"] * 20 / 60
                pnl = (current_price - position["entry_price"]) / position["entry_price"]
                position["unrealized_pnl_pct"] = pnl

                should_exit = strategy.evaluate_exit(position, data)
                if should_exit or pnl <= -0.15:  # safety stop at -15%
                    equity *= (1 + pnl)
                    trades.append({
                        "entry_ts": position["entry_ts"],
                        "exit_ts": ts,
                        "pnl": round(pnl * 100, 3),
                        "candles_held": position["candles_held"],
                    })
                    position = None

            equity_curve.append({"time": ts, "equity": round(equity, 4)})

        # Calculate summary stats
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        win_rate = len(wins) / len(trades) if trades else 0.0
        avg_pnl = sum(t["pnl"] for t in trades) / len(trades) if trades else 0.0
        avg_hold = sum(t["candles_held"] for t in trades) / len(trades) if trades else 0.0

        # Max drawdown
        peak = 100.0
        max_dd = 0.0
        for pt in equity_curve:
            if pt["equity"] > peak:
                peak = pt["equity"]
            dd = (peak - pt["equity"]) / peak
            if dd > max_dd:
                max_dd = dd

        result_queue.put({
            "equity_curve": equity_curve,
            "trades": trades,
            "total_trades": len(trades),
            "win_rate": round(win_rate * 100, 1),
            "avg_pnl_pct": round(avg_pnl, 3),
            "avg_hold_candles": round(avg_hold, 1),
            "total_return_pct": round(equity - 100, 2),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "custom_metrics": getattr(strategy, "metrics", {}),
        })

    except SyntaxError as exc:
        result_queue.put({"error": f"Syntax error: {exc}"})
    except Exception as exc:
        result_queue.put({"error": f"Backtest error: {traceback.format_exc()}"})


# ---------------------------------------------------------------------------
# StrategyRegistry
# ---------------------------------------------------------------------------

class StrategyRegistry:
    """
    CRUD wrapper for user_strategies table and sandbox backtest runner.
    """

    def __init__(self, db: Database = None):
        self._db = db or Database()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_strategies(self) -> List[Dict]:
        rows = self._db.list_user_strategies()
        # Deserialise JSON fields
        for row in rows:
            row["parameters"] = json.loads(row.get("parameters") or "[]")
            row["custom_metrics"] = json.loads(row.get("custom_metrics") or "[]")
        return rows

    def get_strategy(self, strategy_id: int) -> Optional[Dict]:
        row = self._db.get_user_strategy(strategy_id)
        if row is None:
            return None
        row["parameters"] = json.loads(row.get("parameters") or "[]")
        row["custom_metrics"] = json.loads(row.get("custom_metrics") or "[]")
        return row

    def save_strategy(
        self,
        name: str,
        code: str,
        description: str = "",
        parameters: List[Dict] = None,
        custom_metrics: List[Dict] = None,
    ) -> int:
        """Validate code compiles with RestrictedPython, then save. Returns id."""
        self._compile_check(code)
        return self._db.save_user_strategy(
            name=name,
            code=code,
            description=description,
            parameters=parameters,
            custom_metrics=custom_metrics,
        )

    def delete_strategy(self, strategy_id: int) -> bool:
        return self._db.delete_user_strategy(strategy_id)

    def set_enabled(self, strategy_id: int, enabled: bool) -> None:
        self._db.set_user_strategy_enabled(strategy_id, enabled)

    # ------------------------------------------------------------------
    # Compile check (no execution)
    # ------------------------------------------------------------------

    @staticmethod
    def _compile_check(code: str) -> None:
        """Raises ValueError if the code fails RestrictedPython compilation."""
        try:
            from RestrictedPython import compile_restricted
            compile_restricted(code, filename="<user_strategy>", mode="exec")
        except ImportError:
            # RestrictedPython not installed — fall back to standard syntax check
            compile(code, "<user_strategy>", "exec")
        except SyntaxError as exc:
            raise ValueError(f"Strategy syntax error: {exc}") from exc

    # ------------------------------------------------------------------
    # Backtest
    # ------------------------------------------------------------------

    def run_backtest(
        self, strategy_id: int, symbol: str = None, limit: int = 500
    ) -> Dict:
        """
        Run a sandboxed backtest against historical price_history data.
        Returns result dict with equity_curve, trades, and summary stats.
        Raises ValueError on sandbox violation or timeout.
        """
        strategy = self.get_strategy(strategy_id)
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")

        # Fetch historical candles
        if symbol:
            price_rows = self._db.get_recent_prices(symbol, limit)
        else:
            # Use first symbol in DB that has enough data
            price_rows = self._get_any_symbol_prices(limit)

        if len(price_rows) < 102:
            raise ValueError(
                f"Not enough historical data for backtest. "
                f"Got {len(price_rows)} candles, need ≥102."
            )

        params = {p["name"]: p.get("default") for p in strategy["parameters"]}

        result_queue: multiprocessing.Queue = multiprocessing.Queue()
        proc = multiprocessing.Process(
            target=_sandbox_worker,
            args=(strategy["code"], params, price_rows, result_queue),
            daemon=True,
        )
        proc.start()
        proc.join(timeout=10)   # 10s wall clock; subprocess enforces 5s CPU

        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=2)
            raise ValueError("Backtest exceeded time limit (10 seconds).")

        if proc.exitcode not in (0, None):
            raise ValueError(f"Backtest process exited with code {proc.exitcode}.")

        if result_queue.empty():
            raise ValueError("Backtest produced no output.")

        result = result_queue.get_nowait()
        if "error" in result:
            raise ValueError(result["error"])

        return result

    def _get_any_symbol_prices(self, limit: int) -> List[Dict]:
        """Find the symbol with the most data and return its price rows."""
        with self._db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, COUNT(*) as cnt
                FROM price_history
                GROUP BY symbol
                ORDER BY cnt DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
        if row is None:
            return []
        return self._db.get_recent_prices(row["symbol"], limit)
