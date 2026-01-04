"""
Position manager - handles position tracking, P&L, and order execution
"""
import uuid
import json
import time
from datetime import datetime
from typing import Dict, List, Optional
import config
from database import db
from robinhood_client import client
from logger import logger
from exit_manager import exit_manager


class PositionManager:
    """Manages open and closed positions"""
    
    def __init__(self):
        self.trading_pairs = config.TRADING_PAIRS
        self.capital_per_pair = config.CAPITAL_PER_PAIR
        self.total_capital = config.TOTAL_CAPITAL
        self.trading_mode = config.TRADING_MODE
    
    def get_open_positions(self) -> Dict[str, Dict]:
        """Get all open positions as a dict keyed by symbol"""
        positions = db.get_open_positions()
        return {p['symbol']: p for p in positions}
    
    def get_position_by_symbol(self, symbol: str) -> Optional[Dict]:
        """Get open position for a specific symbol"""
        return db.get_position_by_symbol(symbol)
    
    def has_open_position(self, symbol: str) -> bool:
        """Check if there's an open position for a symbol"""
        return self.get_position_by_symbol(symbol) is not None
    
    def get_available_capital(self) -> float:
        """Calculate available capital for new positions"""
        open_positions = self.get_open_positions()
        allocated = sum(p['entry_value_usd'] for p in open_positions.values())
        return self.total_capital - allocated
    
    def calculate_position_size(self, symbol: str, price: float) -> float:
        """
        Calculate position size for a symbol
        
        Returns:
            Asset quantity to purchase
        """
        allocation = self.capital_per_pair
        quantity = allocation / price
        return quantity
    
    def open_position(
        self, 
        symbol: str, 
        signal_id: Optional[int] = None
    ) -> Optional[Dict]:
        """
        Open a new position for a symbol
        
        Returns:
            Position dict if successful, None otherwise
        """
        try:
            # Check if already have position
            if self.has_open_position(symbol):
                logger.warning(f"Already have open position for {symbol}", category="POSITION")
                return None
            
            # Check available capital
            available = self.get_available_capital()
            if available < self.capital_per_pair:
                logger.warning(
                    f"Insufficient capital for {symbol}: ${available:,.2f} < ${self.capital_per_pair:,.2f}",
                    category="POSITION"
                )
                return None
            
            # Get current price
            current_price = client.get_current_price(symbol)
            if not current_price:
                logger.error(f"Failed to get current price for {symbol}", category="POSITION")
                return None
            
            # Calculate position size
            quantity = self.calculate_position_size(symbol, current_price)
            
            # Validate order size
            if not client.validate_order_size(symbol, quantity):
                logger.error(f"Invalid order size for {symbol}: {quantity}", category="POSITION")
                return None
            
            # Get estimated price
            estimated = client.get_estimated_price(symbol, "ask", str(quantity))
            if not estimated or 'results' not in estimated:
                logger.error(f"Failed to get estimated price for {symbol}", category="POSITION")
                return None
            
            estimated_price = float(estimated['results'][0]['price'])
            estimated_cost = estimated_price * quantity
            
            # Generate client order ID
            client_order_id = str(uuid.uuid4())
            
            # Paper trading mode - simulate order
            if self.trading_mode == "paper":
                logger.info(
                    f"[PAPER] Would BUY {quantity:.6f} {symbol} @ ${estimated_price:,.2f}",
                    category="TRADE"
                )
                order_id = f"paper_{client_order_id[:8]}"
                fill_price = estimated_price
            else:
                # Place actual market buy order
                logger.info(f"Placing BUY order: {quantity:.6f} {symbol}", category="TRADE")
                
                order_response = client.place_order(
                    client_order_id=client_order_id,
                    side="buy",
                    order_type="market",
                    symbol=symbol,
                    order_config={"asset_quantity": str(quantity)}
                )
                
                if not order_response or 'id' not in order_response:
                    logger.error(f"Failed to place order for {symbol}", category="TRADE")
                    return None
                
                order_id = order_response['id']
                
                # Record order in database
                db.insert_order({
                    'order_id': order_id,
                    'client_order_id': client_order_id,
                    'symbol': symbol,
                    'side': 'buy',
                    'order_type': 'market',
                    'quantity': quantity,
                    'status': 'pending',
                    'signal_id': signal_id,
                    'estimated_price': estimated_price,
                    'estimated_cost': estimated_cost
                })
                
                # Wait for order to fill
                logger.info(f"Waiting for order {order_id} to fill...", category="TRADE")
                filled_order = client.poll_order_status(order_id, timeout=30)
                
                if filled_order['state'] != 'filled':
                    logger.error(
                        f"Order {order_id} not filled: {filled_order['state']}",
                        category="TRADE"
                    )
                    db.update_order(client_order_id, {'status': filled_order['state']})
                    return None
                
                fill_price = float(filled_order['average_price'])
                filled_qty = float(filled_order.get('filled_asset_quantity', quantity))
                
                # Update order in database
                db.update_order(client_order_id, {
                    'status': 'filled',
                    'average_price': fill_price,
                    'filled_quantity': filled_qty
                })
                
                quantity = filled_qty  # Use actual filled quantity
            
            # Create position record
            position_id = str(uuid.uuid4())
            entry_time = datetime.now()
            entry_timestamp = int(entry_time.timestamp())
            entry_value = quantity * fill_price
            
            # Get current indicators for snapshot
            indicators = db.get_latest_indicators(symbol)
            
            # Extract strategy type from signal if provided
            entry_strategy = 'legacy'
            if signal_id:
                signal = db.get_signal_by_id(signal_id)
                if signal and signal.get('reason'):
                    reason = signal['reason']
                    # Extract strategy type from reason field: "[mean_reversion] ..."
                    if reason.startswith('['):
                        end_bracket = reason.find(']')
                        if end_bracket > 0:
                            entry_strategy = reason[1:end_bracket]
            
            # Use strategy-specific stop loss
            stop_loss_pct = config.STRATEGY_STOP_LOSS.get(entry_strategy, config.STOP_LOSS_PCT)
            stop_loss_level = fill_price * (1 + stop_loss_pct)
            special_tp_level = fill_price * (1 + config.EXIT_CONFIG['special_tp_pct'])
            
            position_data = {
                'position_id': position_id,
                'symbol': symbol,
                'entry_time': entry_time.isoformat(),
                'entry_timestamp': entry_timestamp,
                'entry_price': fill_price,
                'quantity': quantity,
                'entry_value_usd': entry_value,
                'entry_order_id': order_id,
                'entry_strategy': entry_strategy,
                'current_price': fill_price,
                'current_value_usd': entry_value,
                'unrealized_pnl_usd': 0.0,
                'unrealized_pnl_pct': 0.0,
                'hours_held': 0,
                'stop_loss_level': stop_loss_level,
                'special_tp_level': special_tp_level,
                'status': 'OPEN',
                'indicator_snapshot': indicators or {}
            }
            
            db.insert_position(position_data)
            
            logger.trade(
                action="BUY",
                symbol=symbol,
                quantity=quantity,
                price=fill_price,
                value=entry_value,
                position_id=position_id
            )
            
            return position_data
            
        except Exception as e:
            logger.error(f"Failed to open position for {symbol}: {e}", category="POSITION")
            return None
    
    def close_position(self, position: Dict, exit_reason: str) -> bool:
        """
        Close an open position
        
        Returns:
            True if successful, False otherwise
        """
        try:
            symbol = position['symbol']
            position_id = position['position_id']
            quantity = position['quantity']
            entry_price = position['entry_price']
            
            # Get current price for exit
            current_price = client.get_current_price(symbol)
            if not current_price:
                logger.error(f"Failed to get current price for exit: {symbol}", category="POSITION")
                return False
            
            # Generate client order ID
            client_order_id = str(uuid.uuid4())
            
            # Paper trading mode - simulate order
            if self.trading_mode == "paper":
                logger.info(
                    f"[PAPER] Would SELL {quantity:.6f} {symbol} @ ${current_price:,.2f}",
                    category="TRADE"
                )
                exit_price = current_price
            else:
                # Place actual market sell order
                logger.info(f"Placing SELL order: {quantity:.6f} {symbol}", category="TRADE")
                
                order_response = client.place_order(
                    client_order_id=client_order_id,
                    side="sell",
                    order_type="market",
                    symbol=symbol,
                    order_config={"asset_quantity": str(quantity)}
                )
                
                if not order_response or 'id' not in order_response:
                    logger.error(f"Failed to place exit order for {symbol}", category="TRADE")
                    return False
                
                order_id = order_response['id']
                
                # Record order
                db.insert_order({
                    'order_id': order_id,
                    'client_order_id': client_order_id,
                    'position_id': position_id,
                    'symbol': symbol,
                    'side': 'sell',
                    'order_type': 'market',
                    'quantity': quantity,
                    'status': 'pending'
                })
                
                # Wait for fill
                filled_order = client.poll_order_status(order_id, timeout=30)
                
                if filled_order['state'] != 'filled':
                    logger.error(
                        f"Exit order {order_id} not filled: {filled_order['state']}",
                        category="TRADE"
                    )
                    return False
                
                exit_price = float(filled_order['average_price'])
                
                # Update order
                db.update_order(client_order_id, {
                    'status': 'filled',
                    'average_price': exit_price
                })
            
            # Calculate realized P&L
            exit_value = quantity * exit_price
            realized_pnl = exit_value - position['entry_value_usd']
            realized_pnl_pct = realized_pnl / position['entry_value_usd']
            
            # Update position
            exit_time = datetime.now()
            db.update_position(position_id, {
                'status': 'CLOSED',
                'exit_time': exit_time.isoformat(),
                'exit_timestamp': int(exit_time.timestamp()),
                'exit_price': exit_price,
                'exit_order_id': order_id if self.trading_mode == "live" else None,
                'realized_pnl_usd': realized_pnl,
                'realized_pnl_pct': realized_pnl_pct,
                'exit_reason': exit_reason
            })
            
            logger.exit(
                symbol=symbol,
                reason=exit_reason,
                pnl_pct=realized_pnl_pct,
                pnl_usd=realized_pnl
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to close position for {symbol}: {e}", category="POSITION")
            return False
    
    def update_position_state(self, position: Dict) -> Dict:
        """Update position with current market data"""
        try:
            symbol = position['symbol']
            
            # Get current price
            current_price = client.get_current_price(symbol)
            if not current_price:
                return position
            
            # Calculate current values
            current_value = position['quantity'] * current_price
            unrealized_pnl = current_value - position['entry_value_usd']
            unrealized_pnl_pct = unrealized_pnl / position['entry_value_usd']
            
            # Calculate hours held (stored as hours for display compatibility)
            entry_timestamp = position['entry_timestamp']
            current_timestamp = int(datetime.now().timestamp())
            time_held_seconds = current_timestamp - entry_timestamp
            hours_held = time_held_seconds / 3600  # Keep as hours for display
            
            # Update database
            db.update_position(position['position_id'], {
                'current_price': current_price,
                'current_value_usd': current_value,
                'unrealized_pnl_usd': unrealized_pnl,
                'unrealized_pnl_pct': unrealized_pnl_pct,
                'hours_held': hours_held
            })
            
            # Update position dict
            position['current_price'] = current_price
            position['current_value_usd'] = current_value
            position['unrealized_pnl_usd'] = unrealized_pnl
            position['unrealized_pnl_pct'] = unrealized_pnl_pct
            position['hours_held'] = hours_held
            
            return position
            
        except Exception as e:
            logger.error(f"Failed to update position state for {symbol}: {e}")
            return position
    
    def evaluate_and_exit_positions(self):
        """Evaluate all open positions for exit conditions"""
        open_positions = self.get_open_positions()
        
        for symbol, position in open_positions.items():
            try:
                # Update position with current data
                position = self.update_position_state(position)
                
                # Evaluate exit conditions
                exit_decision = exit_manager.evaluate_exit_conditions(position)
                
                if exit_decision.should_exit:
                    logger.info(
                        f"Exit condition met for {symbol}: {exit_decision.reason}",
                        category="EXIT"
                    )
                    self.close_position(position, exit_decision.reason)
                else:
                    # Log position status
                    logger.position_update(
                        symbol=symbol,
                        pnl_pct=position['unrealized_pnl_pct'],
                        hours_held=position['hours_held'],
                        status="OPEN"
                    )
                    
            except Exception as e:
                logger.error(f"Error evaluating position {symbol}: {e}", category="POSITION")


# Global position manager instance
position_manager = PositionManager()
