"""
Data bootstrap module - fetches market cap from Robinhood, historical data from CryptoCompare
"""
import os
import time
from datetime import datetime
from typing import Dict, List, Optional
import requests
from logger import logger
from database import db
import config
from robinhood_client import client


class DataBootstrap:
    """Bootstrap: Get top 10 by market cap from Robinhood, historical data from CryptoCompare"""
    
    def __init__(self):
        self.base_url = "https://min-api.cryptocompare.com"
        self.api_key = os.getenv("CRYPTOCOMPARE_API_KEY", "")
        self.rate_limit_delay = 1.0  # CryptoCompare rate limiting
        self.symbol_map = {}  # Maps Robinhood symbols (BTC-USD) to CryptoCompare symbols (BTC)
    
    def check_cryptocompare_data(self, symbol: str) -> bool:
        """
        Check if a symbol has data available on CryptoCompare
        
        Args:
            symbol: Robinhood symbol (e.g., "BTC-USD")
        
        Returns:
            True if data is available, False otherwise
        """
        base_symbol = symbol.split("-")[0]
        
        try:
            url = f"{self.base_url}/data/v2/histominute"
            params = {
                "fsym": base_symbol,
                "tsym": "USD",
                "limit": 1,
                "aggregate": 20
            }
            
            if self.api_key:
                params["api_key"] = self.api_key
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("Response") == "Error":
                    return False
                
                hist_data = data.get("Data", {}).get("Data", [])
                
                if hist_data and len(hist_data) > 0:
                    # Check if data is not all zeros
                    last_candle = hist_data[-1]
                    if last_candle.get("close", 0) > 0:
                        return True
            
            return False
            
        except Exception:
            return False
    
    def get_all_available_cryptos(self) -> List[str]:
        """
        Get ALL cryptocurrencies available on both Robinhood and CryptoCompare
        
        Strategy:
        1. Get all available trading pairs from Robinhood
        2. For each pair, test if CryptoCompare has data
        3. Return all symbols that have data on both platforms
        
        Returns:
            List of symbol pairs like ["BTC-USD", "ETH-USD", ...]
        """
        try:
            # Step 1: Get all available trading pairs from Robinhood
            logger.info("Fetching available trading pairs from Robinhood...", category="DATA")
            robinhood_pairs = client.get_trading_pairs()
            
            if not robinhood_pairs or 'results' not in robinhood_pairs:
                logger.error("Failed to fetch trading pairs from Robinhood", category="DATA")
                return []
            
            # Extract symbols (e.g., "BTC-USD", "ETH-USD")
            robinhood_symbols = []
            for pair in robinhood_pairs['results']:
                symbol = pair.get('symbol', '')
                if symbol and symbol.endswith('-USD'):
                    robinhood_symbols.append(symbol)
            
            logger.info(f"Found {len(robinhood_symbols)} trading pairs on Robinhood", category="DATA")
            logger.info("Testing CryptoCompare data availability for each pair...", category="DATA")
            
            # Step 2: Test each symbol on CryptoCompare
            available_symbols = []
            
            for i, symbol in enumerate(robinhood_symbols, 1):
                base_symbol = symbol.split("-")[0]
                
                if self.check_cryptocompare_data(symbol):
                    available_symbols.append(symbol)
                    self.symbol_map[symbol] = base_symbol
                    logger.info(f"✓ {symbol} - Data available", category="DATA")
                else:
                    logger.debug(f"✗ {symbol} - No data", category="DATA")
                
                # Rate limiting between checks
                time.sleep(0.5)
                
                # Progress indicator
                if i % 10 == 0:
                    logger.info(f"  Progress: {i}/{len(robinhood_symbols)} checked...", category="DATA")
            
            logger.info(f"Found {len(available_symbols)} cryptos with data on both platforms", category="DATA")
            
            return available_symbols
            
        except Exception as e:
            logger.error(f"Failed to fetch available cryptos: {e}", category="DATA")
            return []
    
    def fetch_historical_data(self, symbol: str, candles: int = 101) -> Optional[List[Dict]]:
        """
        Fetch historical 20-minute interval data from CryptoCompare
        
        Args:
            symbol: Robinhood symbol (e.g., "BTC-USD")
            candles: Number of 20-minute candles to fetch (default 101 = ~33.7 hours)
        
        Returns:
            List of price data dicts with timestamps
        """
        # Get base symbol (BTC from BTC-USD)
        base_symbol = self.symbol_map.get(symbol)
        if not base_symbol:
            base_symbol = symbol.split("-")[0]
            self.symbol_map[symbol] = base_symbol
        
        try:
            # CryptoCompare histominute endpoint - aggregate=20 for 20-minute candles
            # Note: CryptoCompare limit counts backwards from now, so we need extra to get full count
            url = f"{self.base_url}/data/v2/histominute"
            params = {
                "fsym": base_symbol,
                "tsym": "USD",
                "limit": candles + 10,  # Request extra to ensure we get at least the minimum
                "aggregate": 20  # 20-minute intervals
            }
            
            if self.api_key:
                params["api_key"] = self.api_key
            
            logger.debug(f"Fetching {candles} 20-minute candles for {symbol} from CryptoCompare...", category="DATA")
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 429:
                logger.warning(f"CryptoCompare rate limit hit, retrying in 30s...", category="DATA")
                time.sleep(30)
                response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                logger.error(
                    f"CryptoCompare error for {symbol}: {response.status_code} - {response.text}",
                    category="DATA"
                )
                return None
            
            data = response.json()
            
            # Check response status
            if data.get("Response") == "Error":
                logger.error(f"API error for {symbol}: {data.get('Message')}", category="DATA")
                return None
            
            # Extract historical data - CryptoCompare v2 structure
            hist_data = data.get("Data", {}).get("Data", [])
            
            if not hist_data:
                logger.warning(f"No price data returned for {symbol}", category="DATA")
                return None
            
            # Convert to our format
            price_data = []
            
            for item in hist_data:
                # CryptoCompare format: {time, open, high, low, close, volumefrom, volumeto}
                timestamp = int(item.get("time", 0))
                
                if timestamp == 0:
                    continue
                
                price_data.append({
                    'symbol': symbol,
                    'timestamp': timestamp,
                    'close': float(item.get('close', 0)),
                    'open': float(item.get('open', 0)),
                    'high': float(item.get('high', 0)),
                    'low': float(item.get('low', 0)),
                    'volume': float(item.get('volumeto', 0)),  # Volume in USD
                    'best_bid': None,
                    'best_ask': None
                })
            
            if not price_data:
                logger.warning(f"Could not parse price data for {symbol}", category="DATA")
                return None
            
            logger.info(
                f"Fetched {len(price_data)} 20-minute candles for {symbol}",
                category="DATA"
            )
            
            # Rate limit protection
            time.sleep(self.rate_limit_delay)
            
            return price_data
            
        except Exception as e:
            logger.error(f"Failed to fetch CryptoCompare data for {symbol}: {e}", category="DATA")
            return None
    
    def bootstrap_all_symbols(self, symbols: List[str] = None) -> Dict[str, int]:
        """
        Bootstrap historical 20-minute interval data for all symbols
        
        Workflow:
        1. If no symbols provided: Get ALL available cryptos from Robinhood + CryptoCompare
        2. Fetch 20-minute historical candles from CryptoCompare for each symbol
        3. Store in database
        
        Args:
            symbols: Optional list of symbols to bootstrap. If None, fetches ALL available from Robinhood
        
        Returns:
            Dict with symbol -> count of records inserted
        """
        results = {}
        min_candles = config.COLD_START_CONFIG.get('min_candles_required', 105)
        
        # Get ALL available cryptos from Robinhood if no symbols provided
        if not symbols:
            logger.info("No symbols provided, fetching ALL available cryptos from Robinhood...", category="SYSTEM")
            symbols = self.get_all_available_cryptos()
            
            if not symbols:
                logger.error("Failed to fetch top cryptos, aborting bootstrap", category="SYSTEM")
                return {}
            
            # Update config with new trading pairs
            config.TRADING_PAIRS = symbols
            logger.info(f"Updated TRADING_PAIRS to: {symbols}", category="SYSTEM")
        
        logger.print_separator()
        logger.info("BOOTSTRAPPING 20-MINUTE DATA FROM CRYPTOCOMPARE", category="SYSTEM")
        logger.print_separator()
        
        for symbol in symbols:
            try:
                # Check if we already have data
                existing_count = db.get_price_count(symbol)
                
                if existing_count >= min_candles:
                    logger.info(f"{symbol}: Already have {existing_count} candles of data", category="DATA")
                    results[symbol] = existing_count
                    continue
                
                # Fetch 20-minute candles from CryptoCompare
                price_data = self.fetch_historical_data(symbol, candles=min_candles)
                
                if not price_data:
                    results[symbol] = 0
                    logger.warning(f"{symbol}: No data fetched, skipping", category="DATA")
                    continue
                
                # Insert into database
                inserted = 0
                for data in price_data:
                    try:
                        db.insert_price_data(
                            symbol=data['symbol'],
                            timestamp=data['timestamp'],
                            close=data['close'],
                            open_price=data['open'],
                            high=data['high'],
                            low=data['low'],
                            volume=data['volume'],
                            best_bid=data['best_bid'],
                            best_ask=data['best_ask']
                        )
                        inserted += 1
                    except Exception as e:
                        # Skip duplicates
                        if "UNIQUE constraint" not in str(e):
                            logger.debug(f"Error inserting data: {e}")
                
                results[symbol] = inserted
                logger.info(f"{symbol}: Inserted {inserted} 20-minute candles", category="DATA")
                
            except Exception as e:
                logger.error(f"Failed to bootstrap {symbol}: {e}", category="DATA")
                results[symbol] = 0
        
        logger.print_separator()
        total_inserted = sum(results.values())
        logger.info(f"Bootstrap complete: {total_inserted} total records inserted", category="SYSTEM")
        logger.info(f"Ready to begin 20-minute interval trading", category="SYSTEM")
        logger.print_separator()
        print()
        
        return results
    
    def ensure_continuous_timeline(self, symbol: str):
        """
        Ensure we have a continuous timeline without gaps
        Fill any gaps with interpolated data if needed
        """
        min_candles = config.COLD_START_CONFIG.get('min_candles_required', 105)
        prices = db.get_recent_prices(symbol, candles=min_candles + 10)
        
        if len(prices) < 2:
            return
        
        # Check for gaps > 1.5 candles (30 minutes for 20-min intervals)
        gap_threshold = int(config.INTERVAL_SECONDS * 1.5)  # 1800 seconds (30 min)
        
        for i in range(1, len(prices)):
            time_diff = prices[i]['timestamp'] - prices[i-1]['timestamp']
            
            # If gap is more than 1.5 candles, we have missing data
            if time_diff > gap_threshold:
                candles_gap = int(time_diff / config.INTERVAL_SECONDS)
                logger.warning(
                    f"{symbol}: Found {candles_gap}-candle gap in timeline at {datetime.fromtimestamp(prices[i]['timestamp'])}",
                    category="DATA"
                )


# Global bootstrap instance
data_bootstrap = DataBootstrap()
