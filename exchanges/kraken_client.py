"""
Kraken Spot API Client
Matches the RobinhoodClient interface so the bot can swap exchanges via config.
Authentication: HMAC-SHA512 with a DB-backed nonce counter (never resets).
"""
import base64
import hashlib
import hmac
import json
import time
import urllib.parse
from typing import Any, Dict, List, Optional

import requests

from core import config
from core.database import Database


# ---------------------------------------------------------------------------
# Typed exceptions mirroring common Kraken error codes
# ---------------------------------------------------------------------------

class KrakenAPIError(Exception):
    """Base class for Kraken API errors."""


class KrakenAuthError(KrakenAPIError):
    """EAPI:Invalid key or EAPI:Invalid signature."""


class KrakenRateLimitError(KrakenAPIError):
    """EAPI:Rate limit exceeded."""


class KrakenInsufficientFundsError(KrakenAPIError):
    """EOrder:Insufficient funds."""


class KrakenOrderMinError(KrakenAPIError):
    """EOrder:Order minimum not met."""


# ---------------------------------------------------------------------------
# Rate limiter (token bucket, mirrors Kraken's 15-second cost window)
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Token bucket calibrated to Kraken's private endpoint cost model."""

    def __init__(self, capacity: float = 20.0, refill_rate: float = 20.0 / 15):
        self._capacity = capacity
        self._tokens = capacity
        self._refill_rate = refill_rate   # tokens per second
        self._last = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._refill_rate)
        self._last = now

    def wait(self, cost: float = 0.1) -> None:
        while True:
            self._refill()
            if self._tokens >= cost:
                self._tokens -= cost
                return
            time.sleep(0.05)


# ---------------------------------------------------------------------------
# KrakenClient
# ---------------------------------------------------------------------------

class KrakenClient:
    """
    Kraken REST API client.
    Public interface matches RobinhoodClient so main.py can use either via
    the get_exchange_client() factory in config.py.
    """

    BASE_URL = "https://api.kraken.com"

    # Endpoint cost table (tokens consumed per call)
    _COSTS: Dict[str, float] = {
        "/0/private/Balance": 0.1,
        "/0/private/TradeBalance": 0.1,
        "/0/private/AddOrder": 0.1,
        "/0/private/CancelOrder": 0.1,
        "/0/private/OpenOrders": 1.0,
        "/0/private/QueryOrders": 1.0,
        "/0/private/TradesHistory": 2.0,
        "/0/private/GetWebSocketsToken": 0.1,
    }

    def __init__(
        self,
        api_key: str = None,
        private_key: str = None,
        db: "Database" = None,
    ):
        self.api_key = api_key or config.KRAKEN_API_KEY
        self._private_key_b64 = private_key or config.KRAKEN_PRIVATE_KEY
        self._db = db or Database()
        self._rate_limiter = _RateLimiter()
        self.request_count = 0
        self.error_count = 0

    # ------------------------------------------------------------------
    # Signature helpers
    # ------------------------------------------------------------------

    def _sign(self, endpoint: str, postdata: str, nonce: int) -> str:
        """
        Kraken HMAC-SHA512 signature.
        signature = HMAC-SHA512(base64_decoded_secret,
                                endpoint_path + SHA256(nonce + postdata))
        Returns base64-encoded signature string.
        """
        sha = hashlib.sha256((str(nonce) + postdata).encode()).digest()
        secret = base64.b64decode(self._private_key_b64)
        mac = hmac.new(secret, endpoint.encode() + sha, hashlib.sha512)
        return base64.b64encode(mac.digest()).decode()

    # ------------------------------------------------------------------
    # Core request methods
    # ------------------------------------------------------------------

    def _public_get(self, endpoint: str, params: Dict = None) -> Dict:
        url = self.BASE_URL + endpoint
        resp = requests.get(url, params=params or {}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self._check_errors(data)
        self.request_count += 1
        return data["result"]

    def _private_post(
        self,
        endpoint: str,
        data: Dict = None,
        retry: int = 3,
    ) -> Dict:
        data = data or {}
        cost = self._COSTS.get(endpoint, 0.1)

        for attempt in range(retry):
            self._rate_limiter.wait(cost)
            nonce = self._db.get_next_nonce()
            data["nonce"] = str(nonce)
            postdata = urllib.parse.urlencode(data)
            signature = self._sign(endpoint, postdata, nonce)

            headers = {
                "API-Key": self.api_key,
                "API-Sign": signature,
                "Content-Type": "application/x-www-form-urlencoded",
            }

            try:
                resp = requests.post(
                    self.BASE_URL + endpoint,
                    data=postdata,
                    headers=headers,
                    timeout=10,
                )

                # Honour Retry-After on 429
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", 2 ** attempt))
                    time.sleep(retry_after)
                    continue

                resp.raise_for_status()
                body = resp.json()
                self.request_count += 1

                self._check_errors(body)

                # Adjust rate limiter tokens from response header
                remaining = resp.headers.get("X-RateLimit-Remaining")
                if remaining is not None:
                    self._rate_limiter._tokens = min(
                        self._rate_limiter._capacity, float(remaining)
                    )

                return body["result"]

            except (KrakenRateLimitError, requests.exceptions.RequestException) as exc:
                self.error_count += 1
                if attempt < retry - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise exc

        raise KrakenAPIError(f"Request to {endpoint} failed after {retry} attempts")

    @staticmethod
    def _check_errors(body: Dict) -> None:
        """Inspect Kraken error array and raise typed exceptions."""
        errors: List[str] = body.get("error", [])
        if not errors:
            return
        msg = errors[0]
        if "Invalid key" in msg or "Invalid signature" in msg:
            raise KrakenAuthError(msg)
        if "Rate limit exceeded" in msg:
            raise KrakenRateLimitError(msg)
        if "Insufficient funds" in msg:
            raise KrakenInsufficientFundsError(msg)
        if "Order minimum not met" in msg:
            raise KrakenOrderMinError(msg)
        raise KrakenAPIError(msg)

    # ------------------------------------------------------------------
    # Account methods  (mirror RobinhoodClient interface)
    # ------------------------------------------------------------------

    def get_account(self) -> Dict:
        """
        Returns a dict with keys:
          - 'buying_power': available USD balance
          - 'account_number': not applicable for Kraken; returns api_key prefix
          - 'balances': full asset → balance map from /0/private/Balance
        """
        balances = self._private_post("/0/private/Balance")
        trade = self._private_post("/0/private/TradeBalance", {"asset": "ZUSD"})

        usd_balance = float(balances.get("ZUSD", balances.get("USD", 0)))
        return {
            "buying_power": usd_balance,
            "account_number": self.api_key[:8] + "...",
            "balances": balances,
            "trade_balance": trade,
        }

    # ------------------------------------------------------------------
    # Market data methods
    # ------------------------------------------------------------------

    def get_current_price(self, symbol: str) -> float:
        """
        Get the last traded price for a pair.
        symbol: Kraken altname, e.g. 'XBTUSD' or 'ETHUSD'.
        """
        result = self._public_get("/0/public/Ticker", {"pair": symbol})
        pair_data = next(iter(result.values()))
        # 'c' field: [last_trade_price, lot_volume]
        return float(pair_data["c"][0])

    def get_best_bid_ask(self, *symbols: str) -> Dict:
        """
        Returns bid/ask data for one or more symbols.
        Mirrors RobinhoodClient.get_best_bid_ask interface.
        """
        pair_str = ",".join(symbols)
        result = self._public_get("/0/public/Ticker", {"pair": pair_str})
        output = {}
        for pair_key, data in result.items():
            output[pair_key] = {
                "bid_inclusive_of_sell_spread": data["b"][0],
                "ask_inclusive_of_buy_spread": data["a"][0],
                "price": data["c"][0],
            }
        return {"results": output}

    def get_trading_pairs(self, *symbols: str) -> Dict:
        """
        Returns all tradable pairs (or filtered by symbols).
        Mirrors RobinhoodClient.get_trading_pairs interface.
        Result includes: altname, wsname, base, quote, ordermin, costmin
        """
        params = {}
        if symbols:
            params["pair"] = ",".join(symbols)
        result = self._public_get("/0/public/AssetPairs", params)
        # Normalise to a list of pair dicts similar to Robinhood's format
        pairs = []
        for internal_name, info in result.items():
            pairs.append({
                "symbol": info.get("altname", internal_name),
                "wsname": info.get("wsname", ""),
                "base": info.get("base", ""),
                "quote": info.get("quote", ""),
                "ordermin": float(info.get("ordermin", 0)),
                "costmin": float(info.get("costmin", 0)),
                "pair_decimals": info.get("pair_decimals", 8),
                "internal_name": internal_name,
            })
        return {"results": pairs}

    def get_ohlc(self, symbol: str, interval: int = 1, since: int = None) -> List[Dict]:
        """
        Fetch OHLC candles from Kraken.
        interval: minutes (1, 5, 15, 30, 60, 240, 1440, 10080, 21600)
        Returns list of dicts: time, open, high, low, close, volume
        """
        params = {"pair": symbol, "interval": interval}
        if since:
            params["since"] = since
        result = self._public_get("/0/public/OHLC", params)
        candles_raw = next(iter(v for k, v in result.items() if k != "last"), [])
        return [
            {
                "time": int(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[6]),
            }
            for c in candles_raw
        ]

    # ------------------------------------------------------------------
    # Order methods
    # ------------------------------------------------------------------

    def place_order(
        self,
        client_order_id: str,
        side: str,
        order_type: str,
        symbol: str,
        order_config: Dict[str, str],
        validate: bool = False,
    ) -> Dict:
        """
        Place an order on Kraken.
        Mirrors RobinhoodClient.place_order signature.

        Args:
            client_order_id: Used as Kraken userref (integer prefix derived from UUID)
            side: 'buy' or 'sell'
            order_type: 'market', 'limit', 'stop-loss', 'take-profit'
            symbol: Kraken altname, e.g. 'XBTUSD'
            order_config:
                market: {'asset_quantity': '0.001'}
                limit:  {'asset_quantity': '0.001', 'limit_price': '50000'}
        """
        # Convert Robinhood-style order_config to Kraken params
        volume = order_config.get("asset_quantity", order_config.get("volume", ""))
        price = order_config.get("limit_price", order_config.get("price"))

        # In paper mode always validate
        if config.TRADING_MODE == "paper":
            validate = True

        payload: Dict[str, Any] = {
            "pair": symbol,
            "type": side,
            "ordertype": order_type,
            "volume": str(volume),
            "validate": validate,
            "userref": int(client_order_id.replace("-", "")[:9], 16) % (2 ** 31),
        }
        if price:
            payload["price"] = str(price)

        result = self._private_post("/0/private/AddOrder", payload)
        txids = result.get("txid", [])
        return {
            "id": txids[0] if txids else client_order_id,
            "client_order_id": client_order_id,
            "state": "filled" if not validate else "validated",
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "volume": volume,
            "kraken_txids": txids,
            "descr": result.get("descr", {}),
        }

    def cancel_order(self, order_id: str) -> Dict:
        """Cancel an open order by Kraken txid."""
        result = self._private_post("/0/private/CancelOrder", {"txid": order_id})
        return {"count": result.get("count", 0), "order_id": order_id}

    def get_order(self, order_id: str) -> Dict:
        """Get order details by txid."""
        result = self._private_post(
            "/0/private/QueryOrders", {"txids": order_id, "trades": True}
        )
        order = result.get(order_id, {})
        status_map = {"open": "open", "closed": "filled", "canceled": "cancelled", "expired": "cancelled"}
        return {
            "id": order_id,
            "state": status_map.get(order.get("status", ""), order.get("status", "")),
            "average_price": order.get("price", "0"),
            "filled_quantity": order.get("vol_exec", "0"),
            "raw": order,
        }

    def get_orders(
        self,
        created_at_start: str = None,
        created_at_end: str = None,
        side: str = None,
        order_type: str = None,
        symbol: str = None,
        status: str = None,
        limit: int = 50,
    ) -> Dict:
        """Get open orders. Mirrors RobinhoodClient.get_orders."""
        result = self._private_post("/0/private/OpenOrders", {"trades": True})
        orders_raw = result.get("open", {})
        orders = []
        for txid, o in orders_raw.items():
            order_symbol = o.get("descr", {}).get("pair", "")
            if symbol and order_symbol != symbol:
                continue
            orders.append({
                "id": txid,
                "symbol": order_symbol,
                "side": o.get("descr", {}).get("type", ""),
                "type": o.get("descr", {}).get("ordertype", ""),
                "volume": o.get("vol", "0"),
                "filled_quantity": o.get("vol_exec", "0"),
                "state": "open",
                "raw": o,
            })
        return {"results": orders[:limit]}

    def poll_order_status(self, order_id: str, timeout: float = 30.0, interval: float = 2.0) -> Dict:
        """
        Poll until order is filled or cancelled (up to timeout seconds).
        Mirrors RobinhoodClient.poll_order_status.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            order = self.get_order(order_id)
            if order["state"] in ("filled", "cancelled"):
                return order
            time.sleep(interval)
        return self.get_order(order_id)  # Return whatever state we're in

    # ------------------------------------------------------------------
    # WebSocket token
    # ------------------------------------------------------------------

    def get_websockets_token(self) -> str:
        """Obtain a short-lived token for the private Kraken WebSocket feed."""
        result = self._private_post("/0/private/GetWebSocketsToken")
        return result.get("token", "")

    # ------------------------------------------------------------------
    # Compatibility shims for methods called elsewhere in the bot
    # ------------------------------------------------------------------

    def get_holdings(self, *asset_codes: str) -> Dict:
        """Return current crypto holdings from Balance endpoint."""
        balances = self._private_post("/0/private/Balance")
        results = []
        for asset, qty in balances.items():
            if asset.startswith("Z") or asset == "USD":
                continue  # skip fiat
            if asset_codes and asset not in asset_codes:
                continue
            results.append({
                "asset_code": asset,
                "quantity": float(qty),
                "cost_basis": None,
            })
        return {"results": results}

    def get_estimated_price(self, symbol: str, side: str, quantity: str) -> Dict:
        """Estimate order price using current ticker."""
        result = self._public_get("/0/public/Ticker", {"pair": symbol})
        pair_data = next(iter(result.values()))
        # bid side → use bid price, ask side → use ask price
        if side == "bid":
            price = float(pair_data["b"][0])
        else:
            price = float(pair_data["a"][0])
        estimated_total = price * float(quantity)
        return {
            "price": str(price),
            "quantity": quantity,
            "estimated_total": str(estimated_total),
        }
