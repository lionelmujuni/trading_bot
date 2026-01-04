"""
Robinhood Crypto API Client
Handles authentication, rate limiting, and API calls
"""
import base64
import datetime
import json
import time
import uuid
from typing import Any, Dict, Optional, List
import requests
from nacl.signing import SigningKey
import config


class RateLimiter:
    """Token bucket rate limiter"""
    def __init__(self, max_tokens: int, refill_rate: float):
        self.max_tokens = max_tokens
        self.tokens = max_tokens
        self.refill_rate = refill_rate  # tokens per second
        self.last_refill = time.time()
    
    def acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens, return True if successful"""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def _refill(self):
        """Refill tokens based on time elapsed"""
        now = time.time()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate
        
        self.tokens = min(self.max_tokens, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def wait_for_token(self, tokens: int = 1):
        """Wait until tokens are available"""
        while not self.acquire(tokens):
            time.sleep(0.1)


class RobinhoodClient:
    """Robinhood Crypto API Client"""
    
    def __init__(self, api_key: str = None, private_key_base64: str = None):
        self.api_key = api_key or config.API_KEY
        self.base_url = config.BASE_URL
        
        # Initialize private key
        private_key_seed = base64.b64decode(private_key_base64 or config.BASE64_PRIVATE_KEY)
        self.private_key = SigningKey(private_key_seed)
        
        # Initialize rate limiter
        self.rate_limiter = RateLimiter(
            max_tokens=config.RATE_LIMIT_CONFIG['max_requests_per_minute'],
            refill_rate=config.RATE_LIMIT_CONFIG['refill_rate']
        )
        
        # Request statistics
        self.request_count = 0
        self.error_count = 0
    
    @staticmethod
    def _get_current_timestamp() -> int:
        """Get current Unix timestamp"""
        return int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())
    
    @staticmethod
    def get_query_params(key: str, *args: Optional[str]) -> str:
        """Build query parameter string"""
        if not args:
            return ""
        
        params = []
        for arg in args:
            if arg:
                params.append(f"{key}={arg}")
        
        return "?" + "&".join(params)
    
    def get_authorization_header(
        self, method: str, path: str, body: str, timestamp: int
    ) -> Dict[str, str]:
        """Generate authorization headers with signature"""
        message_to_sign = f"{self.api_key}{timestamp}{path}{method}{body}"
        signed = self.private_key.sign(message_to_sign.encode("utf-8"))
        
        return {
            "x-api-key": self.api_key,
            "x-signature": base64.b64encode(signed.signature).decode("utf-8"),
            "x-timestamp": str(timestamp),
        }
    
    def make_api_request(
        self, 
        method: str, 
        path: str, 
        body: str = "", 
        retry_count: int = 3,
        retry_delay: float = 1.0
    ) -> Any:
        """Make authenticated API request with rate limiting and retries"""
        
        for attempt in range(retry_count):
            try:
                # Wait for rate limiter
                self.rate_limiter.wait_for_token()
                
                # Generate headers
                timestamp = self._get_current_timestamp()
                headers = self.get_authorization_header(method, path, body, timestamp)
                headers["Content-Type"] = "application/json; charset=utf-8"
                
                url = self.base_url + path
                
                # Make request
                response = None
                if method == "GET":
                    response = requests.get(url, headers=headers, timeout=10)
                elif method == "POST":
                    payload = json.loads(body) if body else {}
                    response = requests.post(url, headers=headers, json=payload, timeout=10)
                
                self.request_count += 1
                
                # Handle response
                if response.status_code == 200 or response.status_code == 201:
                    return response.json()
                elif response.status_code == 429:
                    # Rate limited - wait and retry
                    wait_time = retry_delay * (2 ** attempt)
                    time.sleep(wait_time)
                    continue
                elif response.status_code >= 400:
                    error_data = response.json() if response.content else {}
                    error_msg = error_data.get('errors', [{}])[0].get('detail', 'Unknown error')
                    raise Exception(f"API Error ({response.status_code}): {error_msg}")
                
            except requests.RequestException as e:
                self.error_count += 1
                if attempt < retry_count - 1:
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
                raise Exception(f"Request failed after {retry_count} attempts: {e}")
            except Exception as e:
                self.error_count += 1
                if attempt < retry_count - 1 and "429" in str(e):
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
                raise e
        
        raise Exception(f"Request failed after {retry_count} attempts")
    
    # ==================== Account Methods ====================
    
    def get_account(self) -> Dict:
        """Get account details"""
        path = "/api/v1/crypto/trading/accounts/"
        return self.make_api_request("GET", path)
    
    # ==================== Market Data Methods ====================
    
    def get_best_bid_ask(self, *symbols: Optional[str]) -> Dict:
        """
        Get best bid and ask prices for symbols
        If no symbols provided, returns all supported symbols
        """
        query_params = self.get_query_params("symbol", *symbols)
        path = f"/api/v1/crypto/marketdata/best_bid_ask/{query_params}"
        return self.make_api_request("GET", path)
    
    def get_estimated_price(self, symbol: str, side: str, quantity: str) -> Dict:
        """
        Get estimated price for an order
        
        Args:
            symbol: Trading pair (e.g., "BTC-USD")
            side: "bid" or "ask"
            quantity: Amount to trade (can be comma-separated for multiple)
        """
        path = f"/api/v1/crypto/marketdata/estimated_price/?symbol={symbol}&side={side}&quantity={quantity}"
        return self.make_api_request("GET", path)
    
    # ==================== Trading Methods ====================
    
    def get_trading_pairs(self, *symbols: Optional[str]) -> Dict:
        """
        Get trading pair information
        If no symbols provided, returns all supported pairs
        """
        query_params = self.get_query_params("symbol", *symbols)
        path = f"/api/v1/crypto/trading/trading_pairs/{query_params}"
        return self.make_api_request("GET", path)
    
    def get_holdings(self, *asset_codes: Optional[str]) -> Dict:
        """
        Get crypto holdings
        If no asset codes provided, returns all holdings
        """
        query_params = self.get_query_params("asset_code", *asset_codes)
        path = f"/api/v1/crypto/trading/holdings/{query_params}"
        return self.make_api_request("GET", path)
    
    def place_order(
        self,
        client_order_id: str,
        side: str,
        order_type: str,
        symbol: str,
        order_config: Dict[str, str],
    ) -> Dict:
        """
        Place a crypto order
        
        Args:
            client_order_id: UUID for idempotency
            side: "buy" or "sell"
            order_type: "market", "limit", "stop_loss", or "stop_limit"
            symbol: Trading pair (e.g., "BTC-USD")
            order_config: Configuration dict for the specific order type
                - market: {"asset_quantity": "0.001"}
                - limit: {"asset_quantity": "0.001", "limit_price": "50000"}
        """
        body = {
            "client_order_id": client_order_id,
            "side": side,
            "type": order_type,
            "symbol": symbol,
            f"{order_type}_order_config": order_config,
        }
        path = "/api/v1/crypto/trading/orders/"
        return self.make_api_request("POST", path, json.dumps(body))
    
    def cancel_order(self, order_id: str) -> Dict:
        """Cancel an open order"""
        path = f"/api/v1/crypto/trading/orders/{order_id}/cancel/"
        return self.make_api_request("POST", path)
    
    def get_order(self, order_id: str) -> Dict:
        """Get order details by ID"""
        path = f"/api/v1/crypto/trading/orders/{order_id}/"
        return self.make_api_request("GET", path)
    
    def get_orders(
        self,
        symbol: str = None,
        state: str = None,
        side: str = None,
        order_type: str = None
    ) -> Dict:
        """
        Get orders with optional filters
        
        Args:
            symbol: Filter by trading pair
            state: "open", "canceled", "partially_filled", "filled", "failed"
            side: "buy" or "sell"
            order_type: "limit", "market", "stop_limit", "stop_loss"
        """
        params = []
        if symbol:
            params.append(f"symbol={symbol}")
        if state:
            params.append(f"state={state}")
        if side:
            params.append(f"side={side}")
        if order_type:
            params.append(f"type={order_type}")
        
        query_string = "?" + "&".join(params) if params else ""
        path = f"/api/v1/crypto/trading/orders/{query_string}"
        return self.make_api_request("GET", path)
    
    # ==================== Helper Methods ====================
    
    def poll_order_status(
        self, 
        order_id: str, 
        timeout: int = 30,
        poll_interval: float = 2.0
    ) -> Dict:
        """
        Poll order status until it's filled or timeout
        
        Args:
            order_id: Robinhood order ID
            timeout: Maximum seconds to wait
            poll_interval: Seconds between polls
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            order = self.get_order(order_id)
            
            state = order.get('state', '').lower()
            if state in ['filled', 'canceled', 'failed']:
                return order
            
            time.sleep(poll_interval)
        
        # Timeout reached
        return self.get_order(order_id)
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current mid price for a symbol"""
        try:
            result = self.get_best_bid_ask(symbol)
            if result and 'results' in result and len(result['results']) > 0:
                data = result['results'][0]
                bid = float(data['bid_inclusive_of_sell_spread'])
                ask = float(data['ask_inclusive_of_buy_spread'])
                return (bid + ask) / 2
        except Exception as e:
            print(f"Error getting current price for {symbol}: {e}")
        return None
    
    def get_buying_power(self) -> Optional[float]:
        """Get available buying power"""
        try:
            account = self.get_account()
            if account and 'buying_power' in account:
                return float(account['buying_power'])
        except Exception as e:
            print(f"Error getting buying power: {e}")
        return None
    
    def validate_order_size(self, symbol: str, quantity: float) -> bool:
        """Check if order size meets minimum requirements"""
        try:
            pairs = self.get_trading_pairs(symbol)
            if pairs and 'results' in pairs and len(pairs['results']) > 0:
                pair_info = pairs['results'][0]
                min_size = float(pair_info['min_order_size'])
                max_size = float(pair_info['max_order_size'])
                return min_size <= quantity <= max_size
        except Exception as e:
            print(f"Error validating order size: {e}")
        return False
    
    def get_statistics(self) -> Dict:
        """Get client usage statistics"""
        return {
            "total_requests": self.request_count,
            "total_errors": self.error_count,
            "success_rate": (self.request_count - self.error_count) / max(self.request_count, 1),
            "available_tokens": int(self.rate_limiter.tokens)
        }


# Global client instance
client = RobinhoodClient()
