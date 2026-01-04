#!/usr/bin/env python3
"""
Command-line interface for the crypto trading bot
"""
import sys
import argparse
from datetime import datetime
import config
from logger import logger
from database import db
from cold_start import cold_start
from position_manager import position_manager
from metrics import metrics_calc
from robinhood_client import client


def cmd_start():
    """Start the trading bot"""
    print("Starting Crypto Trading Bot...")
    from main import main
    main()


def cmd_status():
    """Display current bot status"""
    logger.print_header("BOT STATUS")
    
    # Cold start status
    print(f"Bot State: {cold_start.state.name}")
    if cold_start.state.name == "COLD_START":
        hours = cold_start.get_hours_elapsed()
        required = cold_start.min_hours_required
        print(f"Cold Start Progress: {hours}/{required} hours")
    
    print()
    
    # Positions
    metrics_calc.display_position_summary()
    
    # Metrics
    metrics_calc.display_metrics()
    
    # API stats
    stats = client.get_statistics()
    print("API Statistics:")
    print(f"  Total Requests: {stats['total_requests']}")
    print(f"  Success Rate: {stats['success_rate']:.1%}")
    print(f"  Available Tokens: {stats['available_tokens']}")
    print()


def cmd_history(limit=10):
    """Display trade history"""
    logger.print_header(f"TRADE HISTORY (Last {limit})")
    
    closed_positions = db.get_closed_positions(limit=limit)
    
    if not closed_positions:
        print("No closed positions yet.\n")
        return
    
    for pos in closed_positions:
        symbol = pos['symbol']
        entry_time = datetime.fromisoformat(pos['entry_time'])
        exit_time = datetime.fromisoformat(pos['exit_time']) if pos.get('exit_time') else None
        pnl_pct = pos.get('realized_pnl_pct', 0)
        pnl_usd = pos.get('realized_pnl_usd', 0)
        reason = pos.get('exit_reason', 'N/A')
        
        pnl_sign = "+" if pnl_pct >= 0 else ""
        
        print(f"{entry_time.strftime('%Y-%m-%d %H:%M')} | {symbol:.<12} {pnl_sign}{pnl_pct:>6.2%} (${pnl_usd:>+8,.2f}) | {reason}")
    
    print()


def cmd_signals():
    """Display current signal status for all pairs"""
    logger.print_header("SIGNAL STATUS")
    
    from strategy import strategy
    
    for symbol in config.TRADING_PAIRS:
        summary = strategy.get_signal_summary(symbol)
        
        if summary:
            signals = summary.get('signals', {})
            indicators = summary.get('indicators', {})
            
            print(f"\n{symbol}:")
            print(f"  RSI: {indicators.get('rsi', 'N/A'):.1f} -> {signals.get('rsi', 'N/A')}")
            print(f"  MACD: {indicators.get('macd', 'N/A'):.2f} -> {signals.get('macd', 'N/A')}")
            print(f"  ROC: {indicators.get('roc', 'N/A'):.1f}% -> {signals.get('roc', 'N/A')}")
            print(f"  Confluence: {summary.get('bullish_count', 0)}/3 bullish")
        else:
            print(f"\n{symbol}: No data available")
    
    print()


def cmd_reset_db():
    """Reset database (WARNING: deletes all data)"""
    response = input("WARNING: This will delete ALL data. Type 'YES' to confirm: ")
    
    if response != "YES":
        print("Reset cancelled.")
        return
    
    print("Resetting database...")
    
    import os
    db_path = config.DATABASE_CONFIG['db_path']
    if os.path.exists(db_path):
        os.remove(db_path)
    
    # Reinitialize
    from database import Database
    db = Database()
    
    # Reset cold start
    cold_start.reset()
    
    print("Database reset complete.")


def cmd_test_api():
    """Test API connection"""
    logger.print_header("API CONNECTION TEST")
    
    try:
        print("Testing account connection...")
        account = client.get_account()
        print(f"✓ Account: {account.get('account_number', 'N/A')}")
        print(f"  Buying Power: ${float(account.get('buying_power', 0)):,.2f}")
        print()
        
        print("Testing market data...")
        for symbol in config.TRADING_PAIRS[:10]:  # Test first 10 symbols 
            price = client.get_current_price(symbol)
            if price:
                print(f"✓ {symbol}: ${price:,.2f}")
            else:
                print(f"✗ {symbol}: Failed")
        print()
        
        print("API connection successful!")
        
    except Exception as e:
        print(f"✗ API connection failed: {e}")


def cmd_close_position(ticker=None, close_all=False):
    """Close position(s) manually"""
    logger.print_header("CLOSE POSITION")
    
    # Handle mutually exclusive arguments
    if ticker and close_all:
        print("Error: Cannot specify both ticker and --all flag")
        return
    
    # Handle --all flag
    if close_all:
        positions = db.get_open_positions()
        
        if not positions:
            print("No open positions to close.\n")
            return
        
        # Display summary
        print(f"Found {len(positions)} open position(s):\n")
        total_pnl_usd = 0
        for pos in positions:
            short_symbol = pos['symbol'].replace('-USD', '')
            pnl_pct = pos.get('unrealized_pnl_pct') or 0
            pnl_usd = pos.get('unrealized_pnl_usd') or 0
            total_pnl_usd += pnl_usd
            print(f"  {short_symbol}: {pnl_pct:+.2%} (${pnl_usd:+,.2f})")
        
        print(f"\nTotal Unrealized P&L: ${total_pnl_usd:+,.2f}")
        print()
        
        # Confirmation
        confirm = input(f"Close all {len(positions)} position(s)? (yes/no): ")
        
        if confirm.lower() != 'yes':
            print("Operation cancelled.\n")
            return
        
        # Close each position
        success_count = 0
        for pos in positions:
            short_symbol = pos['symbol'].replace('-USD', '')
            print(f"\nClosing {short_symbol}...")
            
            success = position_manager.close_position(pos, "MANUAL_CLOSE")
            
            if success:
                print(f"✓ {short_symbol} closed successfully")
                success_count += 1
            else:
                print(f"✗ Failed to close {short_symbol}")
        
        print(f"\nClosed {success_count}/{len(positions)} position(s)\n")
        return
    
    # Handle specific ticker
    if ticker:
        # Convert short ticker to full symbol format
        full_symbol = f"{ticker.upper()}-USD"
        
        position = db.get_position_by_symbol(full_symbol)
        
        if not position:
            print(f"No open position found for {ticker.upper()}\n")
            return
        
        # Display position details
        pnl_pct = position['unrealized_pnl_pct']
        pnl_usd = position['unrealized_pnl_usd']
        entry_price = position['entry_price']
        current_price = position['current_price']
        quantity = position['quantity']
        hours_held = position.get('hours_held', 0)
        
        print(f"Position: {ticker.upper()}")
        print(f"  Entry Price: ${entry_price:,.2f}")
        print(f"  Current Price: ${current_price:,.2f}")
        print(f"  Quantity: {quantity:.6f}")
        print(f"  Hours Held: {hours_held:.1f}")
        print(f"  Unrealized P&L: {pnl_pct:+.2%} (${pnl_usd:+,.2f})")
        print()
        
        # Confirmation
        confirm = input(f"Close {ticker.upper()} position? (yes/no): ")
        
        if confirm.lower() != 'yes':
            print("Operation cancelled.\n")
            return
        
        # Close position
        print(f"\nClosing {ticker.upper()}...")
        success = position_manager.close_position(position, "MANUAL_CLOSE")
        
        if success:
            print(f"✓ Position {ticker.upper()} closed successfully\n")
        else:
            print(f"✗ Failed to close position {ticker.upper()}\n")
        
        return
    
    # No arguments - list open positions
    positions = db.get_open_positions()
    
    if not positions:
        print("No open positions.\n")
        return
    
    print(f"Open Positions ({len(positions)}): \n")
    for pos in positions:
        short_symbol = pos['symbol'].replace('-USD', '')
        pnl_pct = pos.get('unrealized_pnl_pct') or 0
        pnl_usd = pos.get('unrealized_pnl_usd') or 0
        hours_held = pos.get('hours_held', 0)
        print(f"  {short_symbol:<8} {pnl_pct:>+7.2%} (${pnl_usd:>+9,.2f})  |  {hours_held:.1f}h held")
    
    print("\nUsage: python cli.py close <TICKER>  or  python cli.py close --all\n")


def main():
    parser = argparse.ArgumentParser(
        description="Crypto Trading Bot CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Commands
    subparsers.add_parser('start', help='Start the trading bot')
    subparsers.add_parser('status', help='Display current status')
    
    history_parser = subparsers.add_parser('history', help='Display trade history')
    history_parser.add_argument('--limit', type=int, default=10, help='Number of trades to show')
    
    subparsers.add_parser('signals', help='Display current signal status')
    subparsers.add_parser('reset', help='Reset database (WARNING: deletes all data)')
    subparsers.add_parser('test-api', help='Test API connection')
    
    close_parser = subparsers.add_parser('close', help='Close position by ticker or list open positions')
    close_parser.add_argument('ticker', nargs='?', help='Ticker symbol (e.g., BTC, ETH)')
    close_parser.add_argument('--all', action='store_true', dest='close_all', help='Close all open positions')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Execute command
    commands = {
        'start': cmd_start,
        'status': cmd_status,
        'history': lambda: cmd_history(args.limit if hasattr(args, 'limit') else 10),
        'signals': cmd_signals,
        'reset': cmd_reset_db,
        'test-api': cmd_test_api,
        'close': lambda: cmd_close_position(
            ticker=args.ticker if hasattr(args, 'ticker') else None,
            close_all=args.close_all if hasattr(args, 'close_all') else False
        )
    }
    
    command_func = commands.get(args.command)
    if command_func:
        command_func()
    else:
        print(f"Unknown command: {args.command}")
        parser.print_help()


if __name__ == "__main__":
    main()
