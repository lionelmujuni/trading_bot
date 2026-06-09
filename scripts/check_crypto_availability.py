"""
Script to check how many Robinhood cryptos have data available on CryptoCompare
"""
import os
import time
import requests
from dotenv import load_dotenv
from exchanges.robinhood_client import client

# Load environment variables
load_dotenv()

CRYPTOCOMPARE_BASE_URL = "https://min-api.cryptocompare.com"
CRYPTOCOMPARE_API_KEY = os.getenv("CRYPTOCOMPARE_API_KEY", "")


def check_cryptocompare_availability(symbol: str) -> dict:
    """
    Check if a symbol has data on CryptoCompare
    
    Args:
        symbol: Robinhood symbol like "BTC-USD"
    
    Returns:
        Dict with availability info
    """
    base_symbol = symbol.split("-")[0]
    
    try:
        # Try to fetch 1 candle of 20-minute data
        url = f"{CRYPTOCOMPARE_BASE_URL}/data/v2/histominute"
        params = {
            "fsym": base_symbol,
            "tsym": "USD",
            "limit": 1,
            "aggregate": 20
        }
        
        if CRYPTOCOMPARE_API_KEY:
            params["api_key"] = CRYPTOCOMPARE_API_KEY
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get("Response") == "Error":
                return {
                    "available": False,
                    "reason": data.get("Message", "Unknown error")
                }
            
            hist_data = data.get("Data", {}).get("Data", [])
            
            if hist_data and len(hist_data) > 0:
                # Check if data is not all zeros
                last_candle = hist_data[-1]
                if last_candle.get("close", 0) > 0:
                    return {
                        "available": True,
                        "candles": len(hist_data),
                        "latest_price": last_candle.get("close")
                    }
                else:
                    return {
                        "available": False,
                        "reason": "No price data (zeros)"
                    }
            else:
                return {
                    "available": False,
                    "reason": "No historical data returned"
                }
        else:
            return {
                "available": False,
                "reason": f"HTTP {response.status_code}"
            }
            
    except Exception as e:
        return {
            "available": False,
            "reason": f"Error: {str(e)}"
        }


def main():
    print("=" * 80)
    print("ROBINHOOD <-> CRYPTOCOMPARE AVAILABILITY CHECK")
    print("=" * 80)
    print()
    
    # Step 1: Get all Robinhood trading pairs
    print("Fetching all trading pairs from Robinhood...")
    try:
        robinhood_pairs = client.get_trading_pairs()
        
        if not robinhood_pairs or 'results' not in robinhood_pairs:
            print("❌ Failed to fetch trading pairs from Robinhood")
            return
        
        # Extract symbols
        symbols = []
        for pair in robinhood_pairs['results']:
            symbol = pair.get('symbol', '')
            if symbol and symbol.endswith('-USD'):
                symbols.append(symbol)
        
        print(f"✓ Found {len(symbols)} trading pairs on Robinhood\n")
        
    except Exception as e:
        print(f"❌ Error fetching Robinhood pairs: {e}")
        return
    
    # Step 2: Check each symbol on CryptoCompare
    print("Checking CryptoCompare availability...\n")
    print(f"{'Symbol':<15} {'Status':<12} {'Info':<50}")
    print("-" * 80)
    
    available = []
    unavailable = []
    
    for i, symbol in enumerate(symbols, 1):
        result = check_cryptocompare_availability(symbol)
        
        if result["available"]:
            status = "✓ Available"
            info = f"Price: ${result['latest_price']:,.2f}"
            available.append(symbol)
            print(f"{symbol:<15} {status:<12} {info:<50}")
        else:
            status = "✗ Missing"
            info = result.get("reason", "Unknown")
            unavailable.append(symbol)
            print(f"{symbol:<15} {status:<12} {info:<50}")
        
        # Rate limiting - wait between requests
        time.sleep(0.5)
        
        # Progress indicator
        if i % 10 == 0:
            print(f"  ... checked {i}/{len(symbols)} ...")
    
    # Step 3: Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total Robinhood pairs:        {len(symbols)}")
    print(f"Available on CryptoCompare:   {len(available)} ({len(available)/len(symbols)*100:.1f}%)")
    print(f"Missing on CryptoCompare:     {len(unavailable)} ({len(unavailable)/len(symbols)*100:.1f}%)")
    print()
    
    if unavailable:
        print("Missing symbols:")
        for symbol in unavailable:
            print(f"  - {symbol}")
        print()
    
    print("Available symbols:")
    for symbol in available:
        print(f"  - {symbol}")


if __name__ == "__main__":
    main()
