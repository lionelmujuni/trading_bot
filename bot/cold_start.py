"""
Cold start manager - handles initial data collection phase (105 candles)
"""
import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List
from enum import Enum
from core import config
from core.database import db
from exchanges.robinhood_client import client
from core.logger import logger
from bot.data_bootstrap import data_bootstrap


class BotState(Enum):
    """Bot operational states"""
    COLD_START = "COLD_START"
    READY = "READY"
    TRADING = "TRADING"


class ColdStartManager:
    """Manages the cold start data collection phase"""
    
    def __init__(self):
        self.state = BotState.COLD_START
        self.start_time = datetime.now()
        self.checkpoint_file = config.COLD_START_CONFIG['data_checkpoint_file']
        self.min_candles_required = config.COLD_START_CONFIG['min_candles_required']
        self.trading_pairs = config.TRADING_PAIRS
        self.bootstrap_attempted = False
        
        # Load checkpoint if exists
        self.load_checkpoint()
    
    def load_checkpoint(self):
        """Load cold start progress from checkpoint file"""
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r') as f:
                    data = json.load(f)
                    self.start_time = datetime.fromisoformat(data['start_time'])
                    self.state = BotState[data['state']]
                    logger.info(f"Loaded cold start checkpoint from {data['start_time']}")
            except Exception as e:
                logger.error(f"Failed to load checkpoint: {e}")
    
    def save_checkpoint(self):
        """Save cold start progress to checkpoint file"""
        try:
            data = {
                'start_time': self.start_time.isoformat(),
                'state': self.state.name,
                'last_update': datetime.now().isoformat()
            }
            with open(self.checkpoint_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
    
    def get_candles_elapsed(self) -> int:
        """Get number of candles that should have elapsed since cold start began"""
        elapsed = datetime.now() - self.start_time
        return int(elapsed.total_seconds() / config.INTERVAL_SECONDS)
    
    def get_data_collection_status(self) -> Dict:
        """Get status of data collection for all pairs"""
        status = {}
        for symbol in self.trading_pairs:
            count = db.get_price_count(symbol)
            status[symbol] = {
                'candles_collected': count,
                'ready': count >= self.min_candles_required
            }
        return status
    
    def is_ready_to_trade(self) -> bool:
        """Check if enough data has been collected to start trading"""
        # Check actual data count (not elapsed time - bootstrap provides data instantly)
        for symbol in self.trading_pairs:
            count = db.get_price_count(symbol)
            if count < self.min_candles_required:
                return False
        
        return True
    
    def collect_market_data(self):
        """Collect current market data for all trading pairs (20-minute intervals)"""
        # Use current timestamp (no alignment needed for 20-min intervals)
        timestamp = int(datetime.now().timestamp())
        
        for symbol in self.trading_pairs:
            try:
                # Get best bid/ask
                result = client.get_best_bid_ask(symbol)
                
                if result and 'results' in result and len(result['results']) > 0:
                    data = result['results'][0]
                    
                    bid = float(data['bid_inclusive_of_sell_spread'])
                    ask = float(data['ask_inclusive_of_buy_spread'])
                    mid_price = (bid + ask) / 2
                    
                    # Insert price data with hourly-aligned timestamp
                    db.insert_price_data(
                        symbol=symbol,
                        timestamp=timestamp,
                        close=mid_price,
                        best_bid=bid,
                        best_ask=ask
                    )
                    
                    logger.debug(f"Collected data for {symbol}: ${mid_price:,.2f}")
                else:
                    logger.warning(f"No data returned for {symbol}")
                    
            except Exception as e:
                logger.error(f"Failed to collect data for {symbol}: {e}")
        
        # Save checkpoint after data collection
        self.save_checkpoint()
    
    def bootstrap_historical_data(self) -> bool:
        """Bootstrap historical data from CryptoCompare (auto-fetches ALL available cryptos)"""
        if self.bootstrap_attempted:
            return False
        
        self.bootstrap_attempted = True
        
        try:
            logger.info("Attempting to bootstrap historical data from CryptoCompare...", category="SYSTEM")
            
            # Bootstrap ALL available cryptos from Robinhood (no symbols = auto-fetch)
            results = data_bootstrap.bootstrap_all_symbols(
                symbols=None  # Let bootstrap fetch all available cryptos
            )
            
            # Update our trading pairs to match what was bootstrapped
            if results:
                self.trading_pairs = list(results.keys())
                logger.info(f"Trading pairs updated to: {', '.join(self.trading_pairs)}", category="SYSTEM")
            
            # Check if we got enough data
            success = all(count >= self.min_candles_required for count in results.values())
            
            if success:
                logger.info("Bootstrap successful! Ready to trade immediately.", category="SYSTEM")
                return True
            else:
                failed = [s for s, c in results.items() if c < self.min_candles_required]
                logger.warning(
                    f"Bootstrap incomplete for: {', '.join(failed)}. Will collect data organically.",
                    category="SYSTEM"
                )
                return False
                
        except Exception as e:
            logger.error(f"Bootstrap failed: {e}. Will collect data organically.", category="SYSTEM")
            return False
    
    def display_progress(self):
        """Display cold start progress to console"""
        candles_elapsed = self.get_candles_elapsed()
        candles_remaining = max(0, self.min_candles_required - candles_elapsed)
        progress_pct = min(100, (candles_elapsed / self.min_candles_required) * 100)
        
        # Calculate estimated ready time
        ready_time = self.start_time + timedelta(seconds=self.min_candles_required * config.INTERVAL_SECONDS)
        
        # Create progress bar
        bar_length = 40
        filled = int(bar_length * progress_pct / 100)
        bar = '█' * filled + '░' * (bar_length - filled)
        
        logger.print_separator()
        print("MOMENTUM CRYPTO BOT - COLD START")
        logger.print_separator()
        print(f"Start Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"Trading Pairs: {', '.join(self.trading_pairs)}")
        print(f"Capital Allocation: ${config.CAPITAL_PER_PAIR:,.2f} per pair")
        print()
        print(f"STATUS: COLD START - Collecting data...")
        print(f"Estimated Ready Time: {ready_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print()
        print(f"Data Collection Progress:")
        print(f"[{bar}] {candles_elapsed}/{self.min_candles_required} candles ({progress_pct:.0f}%)")
        print()
        
        # Display per-symbol status
        status = self.get_data_collection_status()
        for symbol, info in status.items():
            count = info['candles_collected']
            ready_str = "✓" if info['ready'] else ""
            
            # Get latest price if available
            prices = db.get_recent_prices(symbol, candles=1)
            price_str = f"${prices[-1]['close']:,.2f}" if prices else "N/A"
            
            # Check indicator availability
            indicator_status = []
            if count >= 14:
                indicator_status.append("RSI")
            if count >= 26:
                indicator_status.append("MACD")
            indicators_str = ", ".join(indicator_status) if indicator_status else "None"
            
            print(f"{symbol:.<10} {count:>2} candles | Latest: {price_str:>10} | Indicators: {indicators_str:<12} {ready_str}")
        
        print()
        print(f"Indicators Available:")
        print(f"  - RSI:  Candle 14+ ({'✓' if candles_elapsed >= 14 else 'waiting...'})")
        print(f"  - MACD: Candle 26+ ({'✓' if candles_elapsed >= 26 else 'waiting...'})")
        print()
        
        if candles_remaining > 0:
            time_remaining = candles_remaining * config.INTERVAL_SECONDS
            hours_remaining = time_remaining / 3600
            print(f"Candles Remaining: {candles_remaining} (~{hours_remaining:.1f} hours)")
            print(f"Next Update: {(datetime.now() + timedelta(seconds=config.INTERVAL_SECONDS)).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        else:
            print("✓ ALL SYSTEMS READY - Trading will begin next cycle")
        
        logger.print_separator()
        print()
    
    def transition_to_ready(self):
        """Transition from COLD_START to READY state"""
        if self.state == BotState.COLD_START and self.is_ready_to_trade():
            self.state = BotState.READY
            self.save_checkpoint()
            
            logger.print_separator()
            logger.info("COLD START COMPLETE - READY TO TRADE", category="SYSTEM")
            logger.print_separator()
            
            # Display summary
            status = self.get_data_collection_status()
            print("\nData Collection Summary:")
            for symbol, info in status.items():
                print(f"  {symbol}: {info['candles_collected']} candles of data collected")
            print()
            
            return True
        return False
    
    def transition_to_trading(self):
        """Transition from READY to TRADING state"""
        if self.state == BotState.READY:
            self.state = BotState.TRADING
            self.save_checkpoint()
            logger.info("LIVE TRADING ACTIVE", category="SYSTEM")
            return True
        return False
    
    def reset(self):
        """Reset cold start (for testing purposes)"""
        self.state = BotState.COLD_START
        self.start_time = datetime.now()
        self.save_checkpoint()
        logger.warning("Cold start reset", category="SYSTEM")


# Global cold start manager instance
cold_start = ColdStartManager()
