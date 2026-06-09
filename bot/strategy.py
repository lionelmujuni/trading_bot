"""
Trading strategy - implements multi-indicator confluence for entry signals
"""
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from core import config
from core.database import db
from bot.indicators import indicator_calc
from core.logger import logger
from bot.position_manager import position_manager

# Import advanced multi-strategy system
try:
    from bot.strategies_advanced import multi_strategy, KellyCriterion
    MULTI_STRATEGY_AVAILABLE = True
except ImportError:
    MULTI_STRATEGY_AVAILABLE = False
    logger.warning("Advanced strategies not available - using legacy indicators", category="STRATEGY")


class TradingStrategy:
    """Multi-indicator momentum strategy with advanced multi-strategy support"""
    
    def __init__(self):
        self.entry_config = config.ENTRY_CONFIG
        self.indicator_config = config.INDICATOR_CONFIG
        self.multi_strategy_enabled = (
            MULTI_STRATEGY_AVAILABLE and 
            config.MULTI_STRATEGY_CONFIG.get('enabled', False)
        )
    
    def generate_multi_strategy_signal(self, symbol: str) -> Tuple[bool, Optional[int]]:
        """
        Generate entry signal using advanced multi-strategy system
        (Bollinger Bands, MA Crossover, Breakout, Regime Detection)
        
        Returns:
            (should_enter, signal_id) tuple
        """
        # Check if already have position
        if position_manager.has_open_position(symbol):
            return False, None
        
        # Check cooldown period
        if not self.check_cooldown(symbol):
            return False, None
        
        # Get best signal from multi-strategy manager
        strategy_signal = multi_strategy.get_best_signal(symbol)
        
        if not strategy_signal:
            return False, None
        
        # Only act on BUY signals
        if strategy_signal.action != 'BUY':
            return False, None
        
        # Check confidence threshold
        min_confidence = self.entry_config.get('min_confidence', 0.66)
        if strategy_signal.confidence < min_confidence:
            return False, None
        
        # Calculate position size using Kelly Criterion if enabled
        kelly_config = config.MULTI_STRATEGY_CONFIG.get('kelly_criterion', {})
        if kelly_config.get('enabled', True):
            kelly_fraction = KellyCriterion.calculate_from_history(symbol)
            strategy_signal.position_size_multiplier = kelly_fraction / kelly_config.get('default_fraction', 0.25)
        
        # Record signal in database
        timestamp = int(datetime.now().timestamp())
        signal_id = db.insert_signal(
            symbol=symbol,
            timestamp=timestamp,
            signal_type='BUY',
            confidence=strategy_signal.confidence,
            rsi=None,  # Advanced strategies don't use RSI
            macd=None,
            roc=None,
            reason=f"[{strategy_signal.strategy_type.value}] {strategy_signal.reason}"
        )
        
        logger.signal(
            symbol=symbol,
            signal_type='BUY',
            confidence=strategy_signal.confidence,
            reason=f"[{strategy_signal.strategy_type.value}] {strategy_signal.reason}"
        )
        
        return True, signal_id
    
    def generate_entry_signal(self, symbol: str) -> Tuple[bool, Optional[int]]:
        """
        Generate entry signal using multi-indicator confluence
        
        Returns:
            (should_enter, signal_id) tuple
        """
        # Check if already have position
        if position_manager.has_open_position(symbol):
            return False, None
        
        # Check cooldown period
        if not self.check_cooldown(symbol):
            return False, None
        
        # Get indicator signals
        signals = indicator_calc.get_indicator_signals(symbol)
        
        if not signals:
            logger.debug(f"No indicators available for {symbol}", category="SIGNAL")
            return False, None
        
        # Count bullish and bearish signals
        bullish_count = sum(1 for s in signals.values() if s == 'BUY')
        bearish_count = sum(1 for s in signals.values() if s == 'SELL')
        total_signals = len(signals)
        
        # Calculate confidence
        if bullish_count > 0:
            confidence = bullish_count / total_signals
        else:
            confidence = 0.0
        
        # Check entry conditions
        min_agree = self.entry_config['min_indicators_agree']
        min_confidence = self.entry_config['min_confidence']
        
        # BUY condition: at least 2 indicators bullish, no bearish signals
        should_enter = (
            bullish_count >= min_agree and
            bearish_count == 0 and
            confidence >= min_confidence
        )
        
        if should_enter:
            # Get current indicator values
            indicators = db.get_latest_indicators(symbol)
            
            # Build reason string
            reason_parts = []
            for ind_name, signal in signals.items():
                if signal == 'BUY':
                    reason_parts.append(ind_name.upper())
            reason = f"Confluence: {', '.join(reason_parts)}"
            
            # Record signal in database
            timestamp = int(datetime.now().timestamp())
            signal_id = db.insert_signal(
                symbol=symbol,
                timestamp=timestamp,
                signal_type='BUY',
                confidence=confidence,
                rsi=indicators.get('rsi_14'),
                macd=indicators.get('macd'),
                roc=indicators.get('roc_12'),
                reason=reason
            )
            
            logger.signal(
                symbol=symbol,
                signal_type='BUY',
                confidence=confidence,
                reason=reason
            )
            
            return True, signal_id
        
        return False, None
    
    def check_cooldown(self, symbol: str) -> bool:
        """Check if symbol is in cooldown period"""
        cooldown_candles = self.entry_config['cooldown_candles']
        
        # Get recent signals
        recent_signals = db.get_recent_signals(symbol, candles=cooldown_candles)
        
        if not recent_signals:
            return True  # No recent signals, OK to trade
        
        # Check if last signal was recent
        last_signal_time = recent_signals[0]['timestamp']
        current_time = int(datetime.now().timestamp())
        time_since = current_time - last_signal_time
        candles_since = time_since / config.INTERVAL_SECONDS
        
        if candles_since < cooldown_candles:
            logger.debug(
                f"{symbol} in cooldown: {candles_since:.1f} candles / {cooldown_candles} candles",
                category="SIGNAL"
            )
            return False
        
        return True
    
    def evaluate_all_symbols(self):
        """Evaluate entry signals for all trading pairs"""
        available_capital = position_manager.get_available_capital()
        
        if available_capital < config.CAPITAL_PER_PAIR:
            logger.debug("Insufficient capital for new positions", category="SIGNAL")
            return
        
        for symbol in config.TRADING_PAIRS:
            try:
                # Check if we have enough data
                price_count = db.get_price_count(symbol)
                if price_count < config.COLD_START_CONFIG['min_candles_required']:
                    continue
                
                # Always calculate legacy indicators (needed for exit logic)
                latest_indicators = db.get_latest_indicators(symbol)
                if not latest_indicators:
                    # Calculate and store indicators
                    indicators = indicator_calc.calculate_all_indicators(symbol)
                    if indicators:
                        timestamp = int(datetime.now().timestamp())
                        db.insert_indicators(symbol, timestamp, indicators)
                        logger.debug(f"Calculated indicators for {symbol}", category="DATA")
                
                # Generate entry signal (multi-strategy or legacy)
                if self.multi_strategy_enabled:
                    should_enter, signal_id = self.generate_multi_strategy_signal(symbol)
                else:
                    should_enter, signal_id = self.generate_entry_signal(symbol)
                
                if should_enter:
                    logger.info(f"Opening position for {symbol}", category="TRADE")
                    position_manager.open_position(symbol, signal_id)
                    
            except Exception as e:
                logger.error(f"Error evaluating {symbol}: {e}", category="SIGNAL")
    
    def get_signal_summary(self, symbol: str) -> Dict:
        """Get current signal status for a symbol"""
        signals = indicator_calc.get_indicator_signals(symbol)
        indicators = db.get_latest_indicators(symbol)
        
        if not signals or not indicators:
            return {}
        
        return {
            'symbol': symbol,
            'signals': signals,
            'indicators': {
                'rsi': indicators.get('rsi_14'),
                'macd': indicators.get('macd'),
                'macd_signal': indicators.get('macd_signal'),
                'roc': indicators.get('roc_12')
            },
            'bullish_count': sum(1 for s in signals.values() if s == 'BUY'),
            'bearish_count': sum(1 for s in signals.values() if s == 'SELL'),
        }


# Global strategy instance
strategy = TradingStrategy()
