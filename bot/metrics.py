"""
Performance metrics calculator
"""
from typing import Dict, List, Optional
from datetime import datetime
from core import config
from core.database import db
from bot.position_manager import position_manager


class MetricsCalculator:
    """Calculate trading performance metrics"""
    
    def calculate_current_metrics(self) -> Dict:
        """Calculate current performance metrics"""
        # Get open positions
        open_positions = position_manager.get_open_positions()
        
        # Get closed positions
        closed_positions = db.get_closed_positions(limit=1000)
        
        # Calculate total values (handle None values)
        total_crypto_value = sum((p.get('current_value_usd') or 0) for p in open_positions.values())
        unrealized_pnl = sum((p.get('unrealized_pnl_usd') or 0) for p in open_positions.values())
        
        # Calculate realized P&L from closed positions
        realized_pnl = sum(p.get('realized_pnl_usd', 0) for p in closed_positions)
        
        # Get buying power
        try:
            from robinhood_client import client
            account = client.get_account()
            total_cash = float(account.get('buying_power', 0)) if account else 0
        except:
            total_cash = position_manager.get_available_capital()
        
        total_portfolio_value = total_cash + total_crypto_value
        
        # Trade statistics
        total_trades = len(closed_positions)
        winning_trades = sum(1 for p in closed_positions if p.get('realized_pnl_usd', 0) > 0)
        losing_trades = sum(1 for p in closed_positions if p.get('realized_pnl_usd', 0) < 0)
        win_rate = winning_trades / max(total_trades, 1)
        
        # Calculate max drawdown (simplified)
        max_drawdown = self.calculate_max_drawdown(closed_positions)
        
        metrics = {
            'total_portfolio_value': total_portfolio_value,
            'total_cash': total_cash,
            'total_crypto_value': total_crypto_value,
            'realized_pnl': realized_pnl,
            'unrealized_pnl': unrealized_pnl,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_fees': 0,  # Robinhood doesn't charge trading fees
            'sharpe_ratio': None,  # Would need historical returns
            'max_drawdown': max_drawdown
        }
        
        return metrics
    
    def calculate_max_drawdown(self, closed_positions: List[Dict]) -> float:
        """Calculate maximum drawdown from closed positions"""
        if not closed_positions:
            return 0.0
        
        # Sort by exit timestamp
        sorted_positions = sorted(
            closed_positions,
            key=lambda p: p.get('exit_timestamp', 0)
        )
        
        # Calculate cumulative P&L
        cumulative_pnl = 0
        peak = 0
        max_dd = 0
        
        for position in sorted_positions:
            pnl = position.get('realized_pnl_usd', 0)
            cumulative_pnl += pnl
            
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            
            drawdown = peak - cumulative_pnl
            if drawdown > max_dd:
                max_dd = drawdown
        
        # Return as percentage of initial capital
        return max_dd / config.TOTAL_CAPITAL if config.TOTAL_CAPITAL > 0 else 0
    
    def save_metrics(self):
        """Save current metrics to database"""
        metrics = self.calculate_current_metrics()
        db.insert_performance_metrics(metrics)
    
    def display_metrics(self):
        """Display current metrics to console"""
        metrics = self.calculate_current_metrics()
        
        print("\n" + "=" * 65)
        print("PERFORMANCE METRICS")
        print("=" * 65)
        print(f"Total Portfolio Value: ${metrics['total_portfolio_value']:,.2f}")
        print(f"  Cash: ${metrics['total_cash']:,.2f}")
        print(f"  Crypto: ${metrics['total_crypto_value']:,.2f}")
        print()
        print(f"Realized P&L: ${metrics['realized_pnl']:,.2f}")
        print(f"Unrealized P&L: ${metrics['unrealized_pnl']:,.2f}")
        print(f"Total P&L: ${metrics['realized_pnl'] + metrics['unrealized_pnl']:,.2f}")
        print()
        print(f"Total Trades: {metrics['total_trades']}")
        print(f"  Winning: {metrics['winning_trades']}")
        print(f"  Losing: {metrics['losing_trades']}")
        print(f"  Win Rate: {metrics['win_rate']:.1%}")
        print()
        if metrics['max_drawdown'] > 0:
            print(f"Max Drawdown: {metrics['max_drawdown']:.2%}")
        print("=" * 65 + "\n")
    
    def display_position_summary(self):
        """Display summary of open positions"""
        open_positions = position_manager.get_open_positions()
        
        if not open_positions:
            print("No open positions\n")
            return
        
        print("\n" + "=" * 65)
        print("OPEN POSITIONS")
        print("=" * 65)
        
        for symbol, pos in open_positions.items():
            pnl_pct = pos.get('unrealized_pnl_pct') or 0
            pnl_usd = pos.get('unrealized_pnl_usd') or 0
            hours = pos.get('hours_held') or 0
            
            pnl_sign = "+" if pnl_pct >= 0 else ""
            print(f"{symbol:.<15} {pnl_sign}{pnl_pct:>6.2%} (${pnl_usd:>+8,.2f}) | {hours}h")
        
        print("=" * 65 + "\n")


# Global metrics calculator instance
metrics_calc = MetricsCalculator()
