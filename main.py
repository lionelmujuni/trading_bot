"""
Main bot orchestrator - coordinates all components
"""
import signal
import sys
import time
from datetime import datetime
import schedule
import config
from logger import logger
from database import db
from cold_start import cold_start, BotState
from indicators import indicator_calc
from position_manager import position_manager
from strategy import strategy
from metrics import metrics_calc


class CryptoBot:
    """Main trading bot orchestrator"""
    
    def __init__(self):
        self.running = False
        self.setup_signal_handlers()
    
    def setup_signal_handlers(self):
        """Setup graceful shutdown on Ctrl+C"""
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
    
    def shutdown(self, signum, frame):
        """Graceful shutdown handler"""
        logger.print_separator()
        logger.info("Shutdown signal received. Saving state...", category="SYSTEM")
        self.running = False
        
        # Save final state
        cold_start.save_checkpoint()
        metrics_calc.save_metrics()
        
        logger.info("Shutdown complete. Goodbye!", category="SYSTEM")
        sys.exit(0)
    
    def startup(self):
        """Initialize bot on startup"""
        logger.print_header("MOMENTUM CRYPTO BOT - STARTING")
        
        # Validate configuration
        if not config.validate_config():
            logger.error("Configuration validation failed. Exiting.", category="SYSTEM")
            sys.exit(1)
        
        # Display configuration
        config.display_config()
        
        # Initialize database
        logger.info("Database initialized", category="SYSTEM")
        
        # Check if trading pairs need to be updated (e.g., switching from old config to all available)
        symbols_in_db = set()
        for symbol in config.TRADING_PAIRS:
            if db.get_price_count(symbol) > 0:
                symbols_in_db.add(symbol)
        
        # If READY/TRADING but we only have few pairs in DB, force re-bootstrap for all available
        if cold_start.state in [BotState.READY, BotState.TRADING]:
            if len(symbols_in_db) < 20:  # Threshold: likely using old 10-pair config
                logger.warning(
                    f"Detected only {len(symbols_in_db)} pairs in database. Re-bootstrapping all available pairs...",
                    category="SYSTEM"
                )
                cold_start.state = BotState.COLD_START
                cold_start.bootstrap_attempted = False
        
        # Check cold start state
        if cold_start.state == BotState.COLD_START:
            logger.info("Bot in COLD START mode", category="SYSTEM")
            
            # Try to bootstrap historical data from CryptoCompare
            if cold_start.bootstrap_historical_data():
                # Bootstrap successful - transition to ready
                if cold_start.is_ready_to_trade():
                    cold_start.transition_to_ready()
            else:
                # Bootstrap failed or incomplete - show progress
                cold_start.display_progress()
        elif cold_start.state == BotState.READY:
            logger.info("Bot READY - will begin trading on next evaluation cycle", category="SYSTEM")
        elif cold_start.state == BotState.TRADING:
            logger.info("Bot resuming TRADING mode", category="SYSTEM")
            metrics_calc.display_position_summary()
            metrics_calc.display_metrics()
    
    def evaluation_cycle(self):
        """Main 20-minute evaluation cycle"""
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
            logger.print_separator()
            logger.info(f"EVALUATION CYCLE - {current_time}", category="SYSTEM")
            logger.print_separator()
            
            # Step 1: Collect market data
            logger.info("Collecting market data...", category="DATA")
            cold_start.collect_market_data()
            
            # Step 2: Calculate indicators
            logger.info("Calculating indicators...", category="DATA")
            self.calculate_indicators()
            
            # Step 3: Check cold start status
            if cold_start.state == BotState.COLD_START:
                cold_start.display_progress()
                
                if cold_start.is_ready_to_trade():
                    cold_start.transition_to_ready()
                
                # Don't trade during cold start
                return
            
            # Step 4: Update and evaluate existing positions
            logger.info("Evaluating open positions...", category="POSITION")
            position_manager.evaluate_and_exit_positions()
            
            # Step 5: Evaluate entry signals
            if cold_start.state in [BotState.READY, BotState.TRADING]:
                logger.info("Evaluating entry signals...", category="SIGNAL")
                strategy.evaluate_all_symbols()
                
                # Transition to TRADING if we opened a position
                if cold_start.state == BotState.READY:
                    open_positions = position_manager.get_open_positions()
                    if open_positions:
                        cold_start.transition_to_trading()
            
            # Step 6: Update metrics
            metrics_calc.save_metrics()
            
            # Step 7: Display summary
            self.display_cycle_summary()
            
        except Exception as e:
            logger.error(f"Error in evaluation cycle: {e}", category="SYSTEM")
    
    def calculate_indicators(self):
        """Calculate indicators for all trading pairs"""
        timestamp = int(datetime.now().timestamp())
        
        for symbol in config.TRADING_PAIRS:
            try:
                price_count = db.get_price_count(symbol)
                
                # Need at least 26 candles for MACD (slowest indicator)
                if price_count < 26:
                    continue
                
                indicators = indicator_calc.calculate_all_indicators(symbol)
                
                if indicators:
                    db.insert_indicators(symbol, timestamp, indicators)
                    logger.debug(
                        f"Indicators for {symbol}: RSI={indicators.get('rsi_14', 'N/A'):.1f}",
                        category="DATA"
                    )
                    
            except Exception as e:
                logger.error(f"Failed to calculate indicators for {symbol}: {e}")
    
    def display_cycle_summary(self):
        """Display summary after evaluation cycle"""
        logger.print_separator()
        print("CYCLE SUMMARY")
        logger.print_separator()
        
        # Display positions
        open_positions = position_manager.get_open_positions()
        print(f"Open Positions: {len(open_positions)}")
        
        if open_positions:
            for symbol, pos in open_positions.items():
                pnl_pct = pos.get('unrealized_pnl_pct') or 0
                pnl_str = f"+{pnl_pct:.2%}" if pnl_pct >= 0 else f"{pnl_pct:.2%}"
                hours = pos.get('hours_held') or 0
                candles = int(hours * 3600 / config.INTERVAL_SECONDS)  # Convert to candles
                print(f"  {symbol}: {pnl_str} ({candles} candles, {hours:.1f}h)")
        
        # Display available capital
        available = position_manager.get_available_capital()
        print(f"\nAvailable Capital: ${available:,.2f}")
        
        # Display recent signals
        print(f"\nSignal Status:")
        for symbol in config.TRADING_PAIRS:
            if symbol not in open_positions:
                summary = strategy.get_signal_summary(symbol)
                if summary:
                    signals = summary.get('signals', {})
                    bullish = summary.get('bullish_count', 0)
                    print(f"  {symbol}: {bullish}/3 bullish indicators")
        
        logger.print_separator()
        next_eval = datetime.now().replace(second=0, microsecond=0)
        next_eval = next_eval.replace(minute=((next_eval.minute // 20) + 1) * 20 % 60)
        print(f"Next evaluation: {next_eval.strftime('%H:%M')} (in ~20 minutes)")
        logger.print_separator()
        print()
    
    def run(self):
        """Start the bot"""
        self.running = True
        self.startup()
        
        # Run initial evaluation immediately
        logger.info("Running initial evaluation...", category="SYSTEM")
        self.evaluation_cycle()
        
        # Schedule evaluations every 20 minutes
        schedule.every(20).minutes.do(self.evaluation_cycle)
        
        logger.info("Bot is now running. Press Ctrl+C to stop.", category="SYSTEM")
        print()
        
        # Main loop
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(30)  # Check every 30 seconds
            except KeyboardInterrupt:
                self.shutdown(None, None)
            except Exception as e:
                logger.error(f"Error in main loop: {e}", category="SYSTEM")
                time.sleep(60)


def main():
    """Main entry point"""
    bot = CryptoBot()
    bot.run()


if __name__ == "__main__":
    main()
