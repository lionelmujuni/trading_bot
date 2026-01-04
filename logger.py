"""
Structured logging module for the crypto trading bot
"""
import logging
import sys
from datetime import datetime
from typing import Optional, Dict, Any
import config
from database import db


class BotLogger:
    """Custom logger with console and database output"""
    
    def __init__(self, name: str = "CryptoBot"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_level = getattr(logging, config.LOGGING_CONFIG.get('console_level', 'INFO'))
        console_handler.setLevel(console_level)
        
        # Format: [2025-12-29 10:30:15] INFO - Message
        console_format = logging.Formatter(
            '[%(asctime)s] %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_format)
        
        # Only add handler if not already added
        if not self.logger.handlers:
            self.logger.addHandler(console_handler)
        
        # Prevent propagation to root logger
        self.logger.propagate = False
    
    def _log(self, level: str, message: str, category: str = None, details: Dict = None):
        """Internal logging method that writes to both console and database"""
        # Console logging
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        if category:
            log_method(f"[{category}] {message}")
        else:
            log_method(message)
        
        # Database logging
        try:
            db.log(level.upper(), message, category, details)
        except Exception as e:
            self.logger.error(f"Failed to write to database log: {e}")
    
    def info(self, message: str, category: str = None, details: Dict = None):
        """Log info message"""
        self._log("INFO", message, category, details)
    
    def warning(self, message: str, category: str = None, details: Dict = None):
        """Log warning message"""
        self._log("WARNING", message, category, details)
    
    def error(self, message: str, category: str = None, details: Dict = None):
        """Log error message"""
        self._log("ERROR", message, category, details)
    
    def debug(self, message: str, category: str = None, details: Dict = None):
        """Log debug message"""
        self._log("DEBUG", message, category, details)
    
    def trade(self, action: str, symbol: str, quantity: float, price: float, **kwargs):
        """Log trade activity"""
        message = f"{action} {quantity:.6f} {symbol} @ ${price:,.2f}"
        details = {
            'action': action,
            'symbol': symbol,
            'quantity': quantity,
            'price': price,
            **kwargs
        }
        self._log("INFO", message, "TRADE", details)
    
    def signal(self, symbol: str, signal_type: str, confidence: float, reason: str):
        """Log trading signal"""
        message = f"{signal_type} signal for {symbol} (confidence: {confidence:.2%})"
        details = {
            'symbol': symbol,
            'signal_type': signal_type,
            'confidence': confidence,
            'reason': reason
        }
        self._log("INFO", message, "SIGNAL", details)
    
    def position_update(self, symbol: str, pnl_pct: float, hours_held: int, status: str):
        """Log position update"""
        pnl_str = f"+{pnl_pct:.2%}" if pnl_pct >= 0 else f"{pnl_pct:.2%}"
        message = f"{symbol} position: {pnl_str} P&L, held {hours_held}h, {status}"
        details = {
            'symbol': symbol,
            'pnl_pct': pnl_pct,
            'hours_held': hours_held,
            'status': status
        }
        self._log("INFO", message, "POSITION", details)
    
    def exit(self, symbol: str, reason: str, pnl_pct: float, pnl_usd: float):
        """Log position exit"""
        pnl_str = f"+{pnl_pct:.2%}" if pnl_pct >= 0 else f"{pnl_pct:.2%}"
        message = f"EXIT {symbol}: {reason} - {pnl_str} (${pnl_usd:,.2f})"
        details = {
            'symbol': symbol,
            'reason': reason,
            'pnl_pct': pnl_pct,
            'pnl_usd': pnl_usd
        }
        self._log("INFO", message, "EXIT", details)
    
    def cold_start_progress(self, hours_collected: int, total_required: int):
        """Log cold start progress"""
        pct = (hours_collected / total_required) * 100
        message = f"Cold start: {hours_collected}/{total_required} hours ({pct:.0f}%)"
        self._log("INFO", message, "SYSTEM")
    
    def system(self, message: str, details: Dict = None):
        """Log system event"""
        self._log("INFO", message, "SYSTEM", details)
    
    def api_error(self, endpoint: str, error: str, details: Dict = None):
        """Log API error"""
        message = f"API error on {endpoint}: {error}"
        error_details = {'endpoint': endpoint, 'error': error}
        if details:
            error_details.update(details)
        self._log("ERROR", message, "API", error_details)
    
    def get_recent_logs(self, hours: int = 24, level: str = None) -> list:
        """Retrieve recent logs from database"""
        return db.get_recent_logs(hours, level)
    
    def print_separator(self, char: str = "=", length: int = 65):
        """Print visual separator"""
        print(char * length)
    
    def print_header(self, title: str):
        """Print formatted header"""
        self.print_separator()
        print(title)
        self.print_separator()
    
    def print_status_table(self, data: Dict[str, Any]):
        """Print formatted status table"""
        for key, value in data.items():
            print(f"{key:.<30} {value}")


# Global logger instance
logger = BotLogger()
