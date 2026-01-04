"""
Database layer for crypto trading bot
Handles SQLite operations for price history, indicators, positions, orders, and metrics
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from contextlib import contextmanager
import config

class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DATABASE_CONFIG["db_path"]
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize database tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Table 1: Price History
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    datetime TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL NOT NULL,
                    volume REAL,
                    best_bid REAL,
                    best_ask REAL,
                    spread REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, timestamp)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_price_symbol_time 
                ON price_history(symbol, timestamp DESC)
            """)
            
            # Table 2: Indicator Calculations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS indicators (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    datetime TEXT NOT NULL,
                    rsi_14 REAL,
                    macd REAL,
                    macd_signal REAL,
                    macd_histogram REAL,
                    roc_12 REAL,
                    ema_12 REAL,
                    ema_26 REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, timestamp)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_indicators_symbol_time 
                ON indicators(symbol, timestamp DESC)
            """)
            
            # Table 3: Trading Signals
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trading_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    datetime TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    confidence REAL,
                    rsi_value REAL,
                    macd_value REAL,
                    roc_value REAL,
                    reason TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_symbol_time 
                ON trading_signals(symbol, timestamp DESC)
            """)
            
            # Table 4: Positions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_id TEXT UNIQUE NOT NULL,
                    symbol TEXT NOT NULL,
                    entry_time TEXT NOT NULL,
                    entry_timestamp INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    entry_value_usd REAL NOT NULL,
                    entry_order_id TEXT,
                    entry_strategy TEXT DEFAULT 'legacy',
                    current_price REAL,
                    current_value_usd REAL,
                    unrealized_pnl_usd REAL,
                    unrealized_pnl_pct REAL,
                    hours_held INTEGER DEFAULT 0,
                    stop_loss_level REAL NOT NULL,
                    special_tp_level REAL NOT NULL,
                    status TEXT DEFAULT 'OPEN',
                    exit_time TEXT,
                    exit_timestamp INTEGER,
                    exit_price REAL,
                    exit_order_id TEXT,
                    realized_pnl_usd REAL,
                    realized_pnl_pct REAL,
                    exit_reason TEXT,
                    indicator_snapshot TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_positions_symbol 
                ON positions(symbol)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_positions_status 
                ON positions(status)
            """)
            
            # Table 5: Orders
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT UNIQUE NOT NULL,
                    client_order_id TEXT UNIQUE NOT NULL,
                    position_id TEXT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL,
                    status TEXT NOT NULL,
                    signal_id INTEGER,
                    estimated_price REAL,
                    estimated_cost REAL,
                    average_price REAL,
                    filled_quantity REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (signal_id) REFERENCES trading_signals(id),
                    FOREIGN KEY (position_id) REFERENCES positions(position_id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_symbol 
                ON orders(symbol)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_status 
                ON orders(status)
            """)
            
            # Table 6: Trade Executions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT UNIQUE NOT NULL,
                    order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    fee REAL,
                    executed_at TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES orders(order_id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_executions_order 
                ON executions(order_id)
            """)
            
            # Table 7: Holdings Snapshot
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS holdings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_code TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    cost_basis REAL,
                    current_price REAL,
                    market_value REAL,
                    timestamp INTEGER NOT NULL,
                    datetime TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_holdings_asset_time 
                ON holdings(asset_code, timestamp DESC)
            """)
            
            # Table 8: Performance Metrics
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    datetime TEXT NOT NULL,
                    total_portfolio_value REAL NOT NULL,
                    total_cash REAL,
                    total_crypto_value REAL,
                    realized_pnl REAL,
                    unrealized_pnl REAL,
                    total_trades INTEGER,
                    winning_trades INTEGER,
                    losing_trades INTEGER,
                    win_rate REAL,
                    total_fees REAL,
                    sharpe_ratio REAL,
                    max_drawdown REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_performance_time 
                ON performance_metrics(timestamp DESC)
            """)
            
            # Table 9: Bot Activity Log
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    datetime TEXT NOT NULL,
                    level TEXT NOT NULL,
                    category TEXT,
                    message TEXT NOT NULL,
                    details TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_log_time 
                ON bot_log(timestamp DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_log_level 
                ON bot_log(level)
            """)
    
    # ==================== Price History Methods ====================
    
    def insert_price_data(self, symbol: str, timestamp: int, close: float,
                         open_price: float = None, high: float = None, 
                         low: float = None, volume: float = None,
                         best_bid: float = None, best_ask: float = None):
        """Insert or update price data"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            dt = datetime.fromtimestamp(timestamp).isoformat()
            spread = (best_ask - best_bid) if (best_bid and best_ask) else None
            
            cursor.execute("""
                INSERT OR REPLACE INTO price_history 
                (symbol, timestamp, datetime, open, high, low, close, volume, 
                 best_bid, best_ask, spread)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, timestamp, dt, open_price, high, low, close, volume,
                  best_bid, best_ask, spread))
    
    def get_recent_prices(self, symbol: str, candles: int = 105) -> List[Dict]:
        """Get recent price history for a symbol"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM price_history 
                WHERE symbol = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (symbol, candles))
            rows = cursor.fetchall()
            return [dict(row) for row in reversed(rows)]  # Oldest first
    
    def get_price_count(self, symbol: str) -> int:
        """Get count of price records for a symbol"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM price_history WHERE symbol = ?
            """, (symbol,))
            return cursor.fetchone()[0]
    
    # ==================== Indicator Methods ====================
    
    def insert_indicators(self, symbol: str, timestamp: int, indicators: Dict[str, float]):
        """Insert indicator calculations"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            dt = datetime.fromtimestamp(timestamp).isoformat()
            
            cursor.execute("""
                INSERT OR REPLACE INTO indicators 
                (symbol, timestamp, datetime, rsi_14, macd, macd_signal, 
                 macd_histogram, roc_12, ema_12, ema_26)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol, timestamp, dt,
                indicators.get('rsi_14'),
                indicators.get('macd'),
                indicators.get('macd_signal'),
                indicators.get('macd_histogram'),
                indicators.get('roc_12'),
                indicators.get('ema_12'),
                indicators.get('ema_26')
            ))
    
    def get_recent_indicators(self, symbol: str, hours: int = 3) -> List[Dict]:
        """Get recent indicator values"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM indicators 
                WHERE symbol = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (symbol, hours))
            rows = cursor.fetchall()
            return [dict(row) for row in reversed(rows)]
    
    def get_latest_indicators(self, symbol: str) -> Optional[Dict]:
        """Get most recent indicators for a symbol"""
        indicators = self.get_recent_indicators(symbol, hours=1)
        return indicators[0] if indicators else None
    
    # ==================== Signal Methods ====================
    
    def insert_signal(self, symbol: str, timestamp: int, signal_type: str,
                     confidence: float, rsi: float = None, macd: float = None,
                     roc: float = None, reason: str = None) -> int:
        """Insert trading signal"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            dt = datetime.fromtimestamp(timestamp).isoformat()
            
            cursor.execute("""
                INSERT INTO trading_signals 
                (symbol, timestamp, datetime, signal_type, confidence, 
                 rsi_value, macd_value, roc_value, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, timestamp, dt, signal_type, confidence, 
                  rsi, macd, roc, reason))
            return cursor.lastrowid
    
    def get_recent_signals(self, symbol: str, candles: int = 24) -> List[Dict]:
        """Get recent signals for a symbol"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            current_time = int(datetime.now().timestamp())
            since_time = current_time - (candles * config.INTERVAL_SECONDS)
            
            cursor.execute("""
                SELECT * FROM trading_signals 
                WHERE symbol = ? AND timestamp >= ?
                ORDER BY timestamp DESC
            """, (symbol, since_time))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_signal_by_id(self, signal_id: int) -> Optional[Dict]:
        """Get a signal by its ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trading_signals 
                WHERE id = ?
            """, (signal_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # ==================== Position Methods ====================
    
    def insert_position(self, position_data: Dict) -> str:
        """Insert new position"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO positions 
                (position_id, symbol, entry_time, entry_timestamp, entry_price,
                 quantity, entry_value_usd, entry_order_id, entry_strategy, stop_loss_level, 
                 special_tp_level, status, indicator_snapshot)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position_data['position_id'],
                position_data['symbol'],
                position_data['entry_time'],
                position_data['entry_timestamp'],
                position_data['entry_price'],
                position_data['quantity'],
                position_data['entry_value_usd'],
                position_data.get('entry_order_id'),
                position_data.get('entry_strategy', 'legacy'),
                position_data['stop_loss_level'],
                position_data['special_tp_level'],
                position_data.get('status', 'OPEN'),
                json.dumps(position_data.get('indicator_snapshot', {}))
            ))
            return position_data['position_id']
    
    def update_position(self, position_id: str, updates: Dict):
        """Update position fields"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build dynamic UPDATE query
            set_clauses = []
            values = []
            for key, value in updates.items():
                if key == 'indicator_snapshot' and isinstance(value, dict):
                    value = json.dumps(value)
                set_clauses.append(f"{key} = ?")
                values.append(value)
            
            values.append(datetime.now().isoformat())
            values.append(position_id)
            
            query = f"""
                UPDATE positions 
                SET {', '.join(set_clauses)}, updated_at = ?
                WHERE position_id = ?
            """
            cursor.execute(query, values)
    
    def get_open_positions(self) -> List[Dict]:
        """Get all open positions"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM positions 
                WHERE status = 'OPEN'
                ORDER BY entry_timestamp DESC
            """)
            rows = cursor.fetchall()
            positions = []
            for row in rows:
                pos = dict(row)
                if pos.get('indicator_snapshot'):
                    pos['indicator_snapshot'] = json.loads(pos['indicator_snapshot'])
                positions.append(pos)
            return positions
    
    def get_position_by_symbol(self, symbol: str) -> Optional[Dict]:
        """Get open position for a symbol"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM positions 
                WHERE symbol = ? AND status = 'OPEN'
                ORDER BY entry_timestamp DESC
                LIMIT 1
            """, (symbol,))
            row = cursor.fetchone()
            if row:
                pos = dict(row)
                if pos.get('indicator_snapshot'):
                    pos['indicator_snapshot'] = json.loads(pos['indicator_snapshot'])
                return pos
            return None
    
    def get_closed_positions(self, limit: int = 50) -> List[Dict]:
        """Get recent closed positions"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM positions 
                WHERE status = 'CLOSED'
                ORDER BY exit_timestamp DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_closed_positions_by_symbol(self, symbol: str, limit: int = 50) -> List[Dict]:
        """Get recent closed positions for a specific symbol"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM positions 
                WHERE status = 'CLOSED' AND symbol = ?
                ORDER BY exit_timestamp DESC
                LIMIT ?
            """, (symbol, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== Order Methods ====================
    
    def insert_order(self, order_data: Dict) -> int:
        """Insert order record"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO orders 
                (order_id, client_order_id, position_id, symbol, side, order_type,
                 quantity, price, status, signal_id, estimated_price, estimated_cost)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_data.get('order_id', ''),
                order_data['client_order_id'],
                order_data.get('position_id'),
                order_data['symbol'],
                order_data['side'],
                order_data['order_type'],
                order_data['quantity'],
                order_data.get('price'),
                order_data.get('status', 'pending'),
                order_data.get('signal_id'),
                order_data.get('estimated_price'),
                order_data.get('estimated_cost')
            ))
            return cursor.lastrowid
    
    def update_order(self, client_order_id: str, updates: Dict):
        """Update order status and details"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            set_clauses = []
            values = []
            for key, value in updates.items():
                set_clauses.append(f"{key} = ?")
                values.append(value)
            
            values.append(datetime.now().isoformat())
            values.append(client_order_id)
            
            query = f"""
                UPDATE orders 
                SET {', '.join(set_clauses)}, updated_at = ?
                WHERE client_order_id = ?
            """
            cursor.execute(query, values)
    
    # ==================== Metrics Methods ====================
    
    def insert_performance_metrics(self, metrics: Dict):
        """Insert performance snapshot"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            timestamp = int(datetime.now().timestamp())
            dt = datetime.now().isoformat()
            
            cursor.execute("""
                INSERT INTO performance_metrics 
                (timestamp, datetime, total_portfolio_value, total_cash,
                 total_crypto_value, realized_pnl, unrealized_pnl, total_trades,
                 winning_trades, losing_trades, win_rate, total_fees,
                 sharpe_ratio, max_drawdown)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp, dt,
                metrics.get('total_portfolio_value'),
                metrics.get('total_cash'),
                metrics.get('total_crypto_value'),
                metrics.get('realized_pnl'),
                metrics.get('unrealized_pnl'),
                metrics.get('total_trades'),
                metrics.get('winning_trades'),
                metrics.get('losing_trades'),
                metrics.get('win_rate'),
                metrics.get('total_fees'),
                metrics.get('sharpe_ratio'),
                metrics.get('max_drawdown')
            ))
    
    def get_latest_metrics(self) -> Optional[Dict]:
        """Get most recent performance metrics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM performance_metrics 
                ORDER BY timestamp DESC 
                LIMIT 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # ==================== Logging Methods ====================
    
    def log(self, level: str, message: str, category: str = None, details: Dict = None):
        """Insert log entry"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            timestamp = int(datetime.now().timestamp())
            dt = datetime.now().isoformat()
            details_json = json.dumps(details) if details else None
            
            cursor.execute("""
                INSERT INTO bot_log 
                (timestamp, datetime, level, category, message, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (timestamp, dt, level, category, message, details_json))
    
    def get_recent_logs(self, candles: int = 72, level: str = None) -> List[Dict]:
        """Get recent log entries (default 72 candles = 24 hours)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            current_time = int(datetime.now().timestamp())
            since_time = current_time - (candles * config.INTERVAL_SECONDS)
            
            if level:
                cursor.execute("""
                    SELECT * FROM bot_log 
                    WHERE timestamp >= ? AND level = ?
                    ORDER BY timestamp DESC
                    LIMIT 100
                """, (since_time, level))
            else:
                cursor.execute("""
                    SELECT * FROM bot_log 
                    WHERE timestamp >= ?
                    ORDER BY timestamp DESC
                    LIMIT 100
                """, (since_time,))
            
            return [dict(row) for row in cursor.fetchall()]


# Global database instance
db = Database()
