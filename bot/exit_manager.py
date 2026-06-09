"""
Exit condition evaluator - implements priority-ordered exit logic
"""
from typing import Optional, Dict, Tuple
from datetime import datetime
from core import config
from core.database import db
from bot.indicators import indicator_calc
from core.logger import logger


class ExitDecision:
    """Represents an exit decision"""
    def __init__(self, should_exit: bool, reason: str, priority: int):
        self.should_exit = should_exit
        self.reason = reason
        self.priority = priority  # Lower = higher priority


class ExitManager:
    """Evaluates exit conditions for open positions"""
    
    def __init__(self):
        self.exit_config = config.EXIT_CONFIG
        self.indicator_config = config.INDICATOR_CONFIG
        self.multi_strategy = None  # Will be initialized on first use
    
    def _get_multi_strategy(self):
        """Lazy-load multi-strategy manager to avoid circular imports"""
        if self.multi_strategy is None:
            from bot.strategies_advanced import MultiStrategyManager
            self.multi_strategy = MultiStrategyManager()
        return self.multi_strategy
    
    def check_mean_reversion_exit(self, position: Dict) -> Optional[ExitDecision]:
        """
        Check mean reversion exit: exit when price returns to mean (z-score < 0.5)
        OR exit after 3x half-life if position not converging (Phase 3 - OU process)
        Uses BollingerBandStrategy to generate signal
        
        Returns:
            ExitDecision if should exit, None otherwise
        """
        symbol = position['symbol']
        hours_held = position.get('hours_held', 0)
        
        try:
            # Phase 3: Check half-life time stop first (if position held too long)
            from bot.mean_reversion_analytics import analytics
            half_life_multiplier = self.exit_config.get('half_life_exit_multiplier', 3.0)
            
            if analytics.should_exit_on_half_life(symbol, hours_held, half_life_multiplier):
                logger.info(
                    f"{symbol} half-life timeout: held {hours_held} candles (exceeds threshold)",
                    category="EXIT"
                )
                return ExitDecision(
                    should_exit=True,
                    reason="MEAN_REVERSION_HALF_LIFE_TIMEOUT",
                    priority=0
                )
            
            # Phase 1: Check z-score convergence (original logic)
            multi_strat = self._get_multi_strategy()
            signal = multi_strat.bb_strategy.generate_signal(symbol)
            
            # Exit when signal is HOLD (z-score converged to mean)
            if signal and signal.action == 'HOLD' and 'converged to mean' in signal.reason.lower():
                logger.info(
                    f"{symbol} mean reversion exit: {signal.reason}",
                    category="EXIT"
                )
                return ExitDecision(
                    should_exit=True,
                    reason="MEAN_REVERSION_EXIT",
                    priority=0
                )
        except Exception as e:
            logger.error(f"Error checking mean reversion exit for {symbol}: {e}", category="EXIT")
        
        return None
    
    def check_momentum_exit(self, position: Dict) -> Optional[ExitDecision]:
        """
        Check momentum exit: exit when trend reverses (death cross)
        Uses DualMAStrategy to generate signal
        
        Returns:
            ExitDecision if should exit, None otherwise
        """
        symbol = position['symbol']
        try:
            multi_strat = self._get_multi_strategy()
            signal = multi_strat.ma_strategy.generate_signal(symbol)
            
            # Exit on SELL signal (death cross / trend reversal)
            if signal.action == 'SELL' and 'death cross' in signal.reason.lower():
                logger.info(
                    f"{symbol} momentum exit: {signal.reason}",
                    category="EXIT"
                )
                return ExitDecision(
                    should_exit=True,
                    reason="MOMENTUM_REVERSAL_EXIT",
                    priority=0
                )
        except Exception as e:
            logger.error(f"Error checking momentum exit for {symbol}: {e}", category="EXIT")
        
        return None
    
    def evaluate_exit_conditions(self, position: Dict) -> ExitDecision:
        """
        Evaluate all exit conditions in priority order
        
        Priority:
        0. Strategy-specific exits (mean reversion convergence, momentum reversal)
        1. Hard stop loss (strategy-specific: -15% mean rev, -8% momentum, -10% breakout)
        2. Special case: +25% with favorable indicators
        3. Indicator-based take profit
        4. Time-based exit (24h + no movement)
        
        Returns:
            ExitDecision object
        """
        symbol = position['symbol']
        current_price = position['current_price']
        entry_price = position['entry_price']
        unrealized_pnl_pct = position.get('unrealized_pnl_pct', 0)
        hours_held = position.get('hours_held', 0)
        entry_strategy = position.get('entry_strategy', 'legacy')
        
        # Priority 0: STRATEGY-SPECIFIC EXITS (exit when strategy premise breaks)
        if entry_strategy == 'mean_reversion':
            exit_decision = self.check_mean_reversion_exit(position)
            if exit_decision:
                return exit_decision
        elif entry_strategy == 'momentum':
            exit_decision = self.check_momentum_exit(position)
            if exit_decision:
                return exit_decision
        
        # Priority 1: HARD STOP LOSS
        if current_price <= position['stop_loss_level']:
            logger.warning(
                f"{symbol} hit stop loss: ${current_price:,.2f} <= ${position['stop_loss_level']:,.2f}",
                category="EXIT"
            )
            return ExitDecision(
                should_exit=True,
                reason="STOP_LOSS",
                priority=1
            )
        
        # Priority 2: SPECIAL CASE +25% WITH FAVORABLE INDICATORS
        if unrealized_pnl_pct >= self.exit_config['special_tp_pct']:
            if self.are_indicators_favorable(symbol):
                logger.info(
                    f"{symbol} at +{unrealized_pnl_pct*100:.1f}% with favorable indicators",
                    category="EXIT"
                )
                return ExitDecision(
                    should_exit=True,
                    reason="SPECIAL_TP_25PCT",
                    priority=2
                )
        
        # Priority 3: INDICATOR-BASED TAKE PROFIT
        if self.check_indicator_take_profit(symbol, unrealized_pnl_pct):
            return ExitDecision(
                should_exit=True,
                reason="INDICATOR_TP",
                priority=3
            )
        
        # Priority 4: TIME-BASED EXIT (strategy and regime-aware)
        # Get strategy-specific time threshold
        time_exit_config = self.exit_config.get('time_exit_candles', 72)
        
        # Handle both dict (new) and scalar (legacy) formats
        if isinstance(time_exit_config, dict):
            base_threshold = time_exit_config.get(entry_strategy, 72)
        else:
            base_threshold = time_exit_config
        
        # Apply regime multiplier (Phase 2)
        regime_multipliers = self.exit_config.get('regime_time_multipliers', {})
        if regime_multipliers:
            try:
                multi_strat = self._get_multi_strategy()
                regime = multi_strat.get_regime(symbol)
                regime_multiplier = regime_multipliers.get(regime.value, 1.0)
                adjusted_threshold = base_threshold * regime_multiplier
                
                logger.debug(
                    f"{symbol} time threshold: {base_threshold} ({entry_strategy}) * "
                    f"{regime_multiplier} ({regime.value}) = {adjusted_threshold:.0f} candles",
                    category="EXIT"
                )
            except Exception as e:
                logger.debug(f"Could not apply regime multiplier for {symbol}: {e}", category="EXIT")
                adjusted_threshold = base_threshold
        else:
            adjusted_threshold = base_threshold
        
        if hours_held >= adjusted_threshold:
            if self.check_no_significant_movement(position, entry_strategy):
                logger.info(
                    f"{symbol} [{entry_strategy}] held {int(hours_held)} candles (threshold: {adjusted_threshold:.0f}) "
                    f"with no significant movement",
                    category="EXIT"
                )
                return ExitDecision(
                    should_exit=True,
                    reason="TIME_EXIT_NO_MOVEMENT",
                    priority=4
                )
        
        # No exit conditions met
        return ExitDecision(
            should_exit=False,
            reason="HOLD",
            priority=999
        )
    
    def are_indicators_favorable(self, symbol: str) -> bool:
        """
        Check if indicators are still favorable at +25% profit
        
        Conditions (2 of 3 must be true):
        1. RSI between 55-75 (healthy bullish range)
        2. MACD maintaining strength (above signal, histogram not declining)
        3. Note: Volume check skipped (not available from Robinhood API)
        
        Returns:
            True if 2+ conditions met
        """
        favorable_count = 0
        
        # Condition 1: RSI in favorable range
        if indicator_calc.is_rsi_in_favorable_range(symbol):
            favorable_count += 1
        
        # Condition 2: MACD maintaining strength
        if indicator_calc.is_macd_maintaining_strength(symbol):
            favorable_count += 1
        
        # Note: Volume condition skipped as Robinhood API doesn't provide volume data
        # We use 2 of 2 instead of 2 of 3
        
        return favorable_count >= 2
    
    def check_indicator_take_profit(self, symbol: str, current_profit_pct: float) -> bool:
        """
        Check for indicator-based take profit signal
        
        Conditions (ALL must be true):
        1. RSI overbought reversal (RSI crosses below 70 from above)
        2. MACD bearish crossover
        3. Minimum profit threshold (5%)
        
        Alternative (OR condition):
        - Strong reversal: RSI drops 15+ points in 2 hours AND profit > 8%
        """
        # Check minimum profit requirement
        min_profit = self.exit_config['indicator_tp_min_profit']
        if current_profit_pct < min_profit:
            return False
        
        # Primary condition: RSI reversal + MACD bearish cross
        rsi_reversal = indicator_calc.is_rsi_overbought_reversal(symbol)
        macd_bearish = indicator_calc.is_macd_bearish_cross(symbol)
        
        if rsi_reversal and macd_bearish:
            logger.info(
                f"{symbol} showing reversal signals: RSI overbought exit + MACD bearish cross",
                category="EXIT"
            )
            return True
        
        # Alternative condition: Strong RSI drop
        rsi_drop = indicator_calc.get_rsi_drop(symbol, hours=2)
        if rsi_drop and rsi_drop > 15 and current_profit_pct > 0.08:
            logger.info(
                f"{symbol} showing strong reversal: RSI dropped {rsi_drop:.1f} points",
                category="EXIT"
            )
            return True
        
        return False
    
    def check_no_significant_movement(self, position: Dict, entry_strategy: str = 'legacy') -> bool:
        """
        Check if position shows no significant movement (strategy-aware)
        
        Strategy-Specific Thresholds (Phase 2):
        - Mean reversion: 5% (positions consolidate before reverting)
        - Momentum: 2% (stagnation indicates trend exhaustion)
        - Default: 3%
        
        Conditions:
        1. Price changed < threshold% from entry
        2. 6-hour price range < 5%
        
        Returns:
            True if stagnant
        """
        symbol = position['symbol']
        entry_price = position['entry_price']
        current_price = position['current_price']
        
        # Get strategy-specific stagnation threshold (Phase 2)
        stagnant_config = self.exit_config.get('time_exit_stagnant_pct', 0.03)
        
        # Handle both dict (new) and scalar (legacy) formats
        if isinstance(stagnant_config, dict):
            stagnant_threshold = stagnant_config.get(entry_strategy, 0.03)
        else:
            stagnant_threshold = stagnant_config
        
        # Check overall price change from entry
        price_change_pct = abs(current_price - entry_price) / entry_price
        
        if price_change_pct >= stagnant_threshold:
            logger.debug(
                f"{symbol} [{entry_strategy}] showing movement: {price_change_pct:.1%} >= {stagnant_threshold:.1%}",
                category="EXIT"
            )
            return False  # Movement is significant
        
        # Check 6-hour price range (18 candles at 20-min intervals)
        recent_prices = db.get_recent_prices(symbol, candles=18)
        if len(recent_prices) < 18:
            return False  # Not enough data
        
        prices = [p['close'] for p in recent_prices]
        six_hour_high = max(prices)
        six_hour_low = min(prices)
        six_hour_range_pct = (six_hour_high - six_hour_low) / entry_price
        
        range_threshold = self.exit_config['time_exit_range_pct']
        
        return six_hour_range_pct < range_threshold
    
    def get_exit_reason_description(self, reason: str) -> str:
        """Get human-readable description of exit reason"""
        descriptions = {
            "STOP_LOSS": "Hard stop loss triggered at -10%",
            "SPECIAL_TP_25PCT": "Take profit at +25% with favorable indicators",
            "INDICATOR_TP": "Indicator reversal signals detected",
            "TIME_EXIT_NO_MOVEMENT": "24-hour time limit with no significant movement",
            "HOLD": "All conditions checked - holding position"
        }
        return descriptions.get(reason, reason)


# Global exit manager instance
exit_manager = ExitManager()
