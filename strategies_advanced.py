"""
Advanced trading strategies based on Ernest P. Chan's "Algorithmic Trading"
Implements: Mean Reversion (Bollinger Bands), Momentum (MA Cross), Breakout, Pairs Trading
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import config
from database import db
from logger import logger


class StrategyType(Enum):
    """Available strategy types"""
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    PAIRS_TRADING = "pairs_trading"


class MarketRegime(Enum):
    """Market regime types"""
    TRENDING = "trending"
    RANGING = "ranging"
    UNKNOWN = "unknown"


@dataclass
class StrategySignal:
    """Strategy signal output"""
    strategy_type: StrategyType
    action: str  # 'BUY', 'SELL', 'HOLD'
    confidence: float  # 0.0 to 1.0
    strength: float  # Signal strength
    reason: str  # Human-readable reason
    position_size_multiplier: float = 1.0  # Kelly-adjusted multiplier


# ==================== BOLLINGER BANDS MEAN REVERSION ====================

class BollingerBandStrategy:
    """
    Mean reversion strategy using Bollinger Bands (Chan Ch.3)
    Buys when price < lower band, sells when price > upper band
    """
    
    def __init__(self, lookback: int = 20, std_dev: float = 2.0):
        self.lookback = lookback
        self.std_dev = std_dev
        self.entry_zscore = std_dev
        self.exit_zscore = 0.5
    
    def generate_signal(self, symbol: str) -> Optional[StrategySignal]:
        """Generate mean reversion signal based on Bollinger Bands"""
        prices = db.get_recent_prices(symbol, candles=self.lookback + 10)
        
        if len(prices) < self.lookback:
            return None
        
        close_prices = [p['close'] for p in prices]
        current_price = close_prices[-1]
        
        # Calculate Bollinger Bands
        df = pd.DataFrame({'close': close_prices})
        df['ma'] = df['close'].rolling(window=self.lookback).mean()
        df['std'] = df['close'].rolling(window=self.lookback).std()
        
        latest = df.iloc[-1]
        if pd.isna(latest['ma']) or pd.isna(latest['std']):
            return None
        
        ma = float(latest['ma'])
        std = float(latest['std'])
        
        if std == 0:
            return None
        
        # Calculate z-score
        z_score = (current_price - ma) / std
        
        # Generate signals
        if z_score < -self.entry_zscore:
            # Price significantly below mean - BUY signal
            confidence = min(abs(z_score) / 3.0, 1.0)  # Cap at z=3
            return StrategySignal(
                strategy_type=StrategyType.MEAN_REVERSION,
                action='BUY',
                confidence=confidence,
                strength=abs(z_score),
                reason=f"Price {abs(z_score):.2f}σ below mean (oversold)"
            )
        elif z_score > self.entry_zscore:
            # Price significantly above mean - SELL signal
            confidence = min(abs(z_score) / 3.0, 1.0)
            return StrategySignal(
                strategy_type=StrategyType.MEAN_REVERSION,
                action='SELL',
                confidence=confidence,
                strength=abs(z_score),
                reason=f"Price {abs(z_score):.2f}σ above mean (overbought)"
            )
        elif abs(z_score) < self.exit_zscore:
            # Price near mean - exit signal
            return StrategySignal(
                strategy_type=StrategyType.MEAN_REVERSION,
                action='HOLD',
                confidence=0.8,
                strength=0.0,
                reason="Price converged to mean - exit"
            )
        
        return None


# ==================== DUAL MA CROSSOVER MOMENTUM ====================

class DualMAStrategy:
    """
    Trend-following momentum strategy using dual moving average crossover (Chan Ch.6)
    """
    
    def __init__(self, short_period: int = 9, long_period: int = 36):
        self.short_period = short_period  # 3 hours
        self.long_period = long_period    # 12 hours
    
    def generate_signal(self, symbol: str) -> Optional[StrategySignal]:
        """Generate momentum signal based on MA crossover"""
        prices = db.get_recent_prices(symbol, candles=self.long_period + 5)
        
        if len(prices) < self.long_period:
            return None
        
        close_prices = [p['close'] for p in prices]
        
        # Calculate moving averages
        df = pd.DataFrame({'close': close_prices})
        df['ma_short'] = df['close'].rolling(window=self.short_period).mean()
        df['ma_long'] = df['close'].rolling(window=self.long_period).mean()
        
        if len(df) < 2:
            return None
        
        current = df.iloc[-1]
        previous = df.iloc[-2]
        
        if any(pd.isna([current['ma_short'], current['ma_long'],
                         previous['ma_short'], previous['ma_long']])):
            return None
        
        short_ma = float(current['ma_short'])
        long_ma = float(current['ma_long'])
        prev_short = float(previous['ma_short'])
        prev_long = float(previous['ma_long'])
        
        # Calculate separation percentage
        separation_pct = ((short_ma - long_ma) / long_ma) * 100
        
        # Golden cross: short crosses above long (bullish)
        if short_ma > long_ma and prev_short <= prev_long:
            confidence = min(abs(separation_pct) / 5.0, 1.0)
            return StrategySignal(
                strategy_type=StrategyType.MOMENTUM,
                action='BUY',
                confidence=confidence,
                strength=abs(separation_pct),
                reason=f"Golden cross - uptrend forming ({separation_pct:.1f}%)"
            )
        
        # Death cross: short crosses below long (bearish)
        elif short_ma < long_ma and prev_short >= prev_long:
            confidence = min(abs(separation_pct) / 5.0, 1.0)
            return StrategySignal(
                strategy_type=StrategyType.MOMENTUM,
                action='SELL',
                confidence=confidence,
                strength=abs(separation_pct),
                reason=f"Death cross - downtrend forming ({separation_pct:.1f}%)"
            )
        
        # Trend continuation
        elif short_ma > long_ma * 1.02:
            return StrategySignal(
                strategy_type=StrategyType.MOMENTUM,
                action='HOLD',
                confidence=0.7,
                strength=abs(separation_pct),
                reason="Strong uptrend - hold"
            )
        
        return None


# ==================== INTRADAY BREAKOUT ====================

class BreakoutStrategy:
    """
    Intraday breakout strategy (Chan Ch.7)
    Detects large moves with high volume
    """
    
    def __init__(self, lookback: int = 20, vol_threshold: float = 2.0):
        self.lookback = lookback
        self.vol_threshold = vol_threshold
    
    def generate_signal(self, symbol: str) -> Optional[StrategySignal]:
        """Generate breakout signal"""
        prices = db.get_recent_prices(symbol, candles=self.lookback + 5)
        
        if len(prices) < self.lookback + 1:
            return None
        
        close_prices = [p['close'] for p in prices]
        volumes = [p['volume'] for p in prices]
        
        df = pd.DataFrame({'close': close_prices, 'volume': volumes})
        df['return'] = df['close'].pct_change()
        df['vol_std'] = df['return'].rolling(window=self.lookback).std()
        df['vol_avg'] = df['volume'].rolling(window=self.lookback).mean()
        
        latest = df.iloc[-1]
        
        if pd.isna(latest['vol_std']) or pd.isna(latest['vol_avg']):
            return None
        
        price_return = float(latest['return'])
        vol_std = float(latest['vol_std'])
        volume = float(latest['volume'])
        vol_avg = float(latest['vol_avg'])
        
        if vol_std == 0 or vol_avg == 0:
            return None
        
        # Calculate breakout strength
        price_z = price_return / vol_std
        volume_ratio = volume / vol_avg
        
        # Breakout conditions: large price move + high volume
        breakout_up = price_z > self.vol_threshold and volume_ratio > 1.5
        breakout_down = price_z < -self.vol_threshold and volume_ratio > 1.5
        
        if breakout_up:
            confidence = min(abs(price_z) / 4.0, 1.0)
            return StrategySignal(
                strategy_type=StrategyType.BREAKOUT,
                action='BUY',
                confidence=confidence,
                strength=abs(price_z),
                reason=f"Upside breakout: {price_z:.1f}σ move, {volume_ratio:.1f}x volume"
            )
        elif breakout_down:
            confidence = min(abs(price_z) / 4.0, 1.0)
            return StrategySignal(
                strategy_type=StrategyType.BREAKOUT,
                action='SELL',
                confidence=confidence,
                strength=abs(price_z),
                reason=f"Downside breakout: {price_z:.1f}σ move, {volume_ratio:.1f}x volume"
            )
        
        return None


# ==================== REGIME DETECTION ====================

class RegimeDetector:
    """
    Detect market regime to select appropriate strategy (Chan Ch.8)
    """
    
    def __init__(self, lookback: int = 50):
        self.lookback = lookback
    
    def detect_regime(self, symbol: str) -> MarketRegime:
        """Detect if market is trending or ranging"""
        prices = db.get_recent_prices(symbol, candles=self.lookback)
        
        if len(prices) < self.lookback:
            return MarketRegime.UNKNOWN
        
        close_prices = [p['close'] for p in prices]
        
        # Calculate trend strength using linear regression
        x = np.arange(len(close_prices))
        coeffs = np.polyfit(x, close_prices, 1)
        slope = coeffs[0]
        
        # Calculate volatility
        returns = pd.Series(close_prices).pct_change()
        volatility = returns.std()
        
        # Normalize slope
        avg_price = np.mean(close_prices)
        if avg_price == 0 or volatility == 0:
            return MarketRegime.UNKNOWN
        
        normalized_slope = abs(slope) / (avg_price * volatility)
        
        # Determine regime
        if normalized_slope > 0.5:
            return MarketRegime.TRENDING
        else:
            return MarketRegime.RANGING


# ==================== KELLY CRITERION POSITION SIZING ====================

class KellyCriterion:
    """
    Kelly Criterion for optimal position sizing (Chan Ch.8)
    Uses win rate and avg win/loss to calculate optimal fraction
    """
    
    @staticmethod
    def calculate_kelly(win_rate: float, avg_win: float, avg_loss: float, 
                        safety_factor: float = 0.5) -> float:
        """
        Calculate Kelly fraction for position sizing
        
        Args:
            win_rate: Historical win rate (0-1)
            avg_win: Average winning trade return
            avg_loss: Average losing trade return (positive number)
            safety_factor: Reduce Kelly by this factor (default 0.5 for half-Kelly)
        
        Returns:
            Position size fraction (0-1)
        """
        if avg_loss == 0 or win_rate == 0:
            return 0.0
        
        # Kelly formula: f = (p*b - q) / b
        # where p=win_rate, q=1-win_rate, b=avg_win/avg_loss
        b = avg_win / avg_loss
        kelly_fraction = (win_rate * b - (1 - win_rate)) / b
        
        # Apply safety factor and bounds
        kelly_fraction = max(0.0, min(1.0, kelly_fraction)) * safety_factor
        
        return kelly_fraction
    
    @staticmethod
    def calculate_from_history(symbol: str, lookback_trades: int = 20) -> float:
        """Calculate Kelly fraction from recent trade history"""
        from database import db
        import config
        
        # Get Kelly config
        kelly_config = config.MULTI_STRATEGY_CONFIG.get('kelly_criterion', {})
        min_trades = kelly_config.get('min_trades', 20)
        default_fraction = kelly_config.get('default_fraction', 0.25)
        safety_factor = kelly_config.get('safety_factor', 0.5)
        
        # Get closed positions for this symbol
        closed_positions = db.get_closed_positions_by_symbol(symbol, limit=lookback_trades)
        
        if len(closed_positions) < min_trades:
            # Not enough history, use default
            return default_fraction
        
        # Calculate win rate and avg returns
        wins = [p for p in closed_positions if p.get('realized_pnl_usd', 0) > 0]
        losses = [p for p in closed_positions if p.get('realized_pnl_usd', 0) < 0]
        
        if not wins or not losses:
            # Need both wins and losses for Kelly calculation
            return default_fraction
        
        win_rate = len(wins) / len(closed_positions)
        avg_win = sum(abs(p.get('realized_pnl_pct', 0)) for p in wins) / len(wins)
        avg_loss = sum(abs(p.get('realized_pnl_pct', 0)) for p in losses) / len(losses)
        
        # Calculate Kelly fraction
        kelly_fraction = KellyCriterion.calculate_kelly(win_rate, avg_win, avg_loss, safety_factor)
        
        return kelly_fraction


# ==================== MULTI-STRATEGY MANAGER ====================

class MultiStrategyManager:
    """
    Orchestrates multiple strategies and selects best signal based on regime
    """
    
    def __init__(self):
        self.bb_strategy = BollingerBandStrategy()
        self.ma_strategy = DualMAStrategy()
        self.breakout_strategy = BreakoutStrategy()
        self.regime_detector = RegimeDetector()
        
        # Strategy weights by regime
        self.weights = {
            MarketRegime.TRENDING: {
                StrategyType.MOMENTUM: 0.5,
                StrategyType.BREAKOUT: 0.3,
                StrategyType.MEAN_REVERSION: 0.2
            },
            MarketRegime.RANGING: {
                StrategyType.MEAN_REVERSION: 0.6,
                StrategyType.MOMENTUM: 0.2,
                StrategyType.BREAKOUT: 0.2
            },
            MarketRegime.UNKNOWN: {
                StrategyType.MEAN_REVERSION: 0.4,
                StrategyType.MOMENTUM: 0.3,
                StrategyType.BREAKOUT: 0.3
            }
        }
    
    def get_best_signal(self, symbol: str) -> Optional[StrategySignal]:
        """
        Get best trading signal by combining all strategies
        weighted by current market regime
        """
        # Detect regime
        regime = self.regime_detector.detect_regime(symbol)
        
        # Get signals from all strategies
        signals = []
        
        bb_signal = self.bb_strategy.generate_signal(symbol)
        if bb_signal:
            signals.append(bb_signal)
        
        ma_signal = self.ma_strategy.generate_signal(symbol)
        if ma_signal:
            signals.append(ma_signal)
        
        breakout_signal = self.breakout_strategy.generate_signal(symbol)
        if breakout_signal:
            signals.append(breakout_signal)
        
        if not signals:
            return None
        
        # Weight signals by regime
        weights = self.weights[regime]
        best_signal = None
        best_score = 0.0
        
        for signal in signals:
            if signal.action == 'HOLD':
                continue
            
            weight = weights.get(signal.strategy_type, 0.0)
            score = signal.confidence * signal.strength * weight
            
            if score > best_score:
                best_score = score
                best_signal = signal
        
        if best_signal:
            logger.info(
                f"{symbol} [{regime.value}] Best signal: {best_signal.strategy_type.value} "
                f"{best_signal.action} (confidence: {best_signal.confidence:.2f}, "
                f"strength: {best_signal.strength:.2f})",
                category="STRATEGY"
            )
        
        return best_signal
    
    def get_all_signals(self, symbol: str) -> Dict[str, Optional[StrategySignal]]:
        """Get signals from all strategies for analysis"""
        return {
            'bollinger': self.bb_strategy.generate_signal(symbol),
            'momentum': self.ma_strategy.generate_signal(symbol),
            'breakout': self.breakout_strategy.generate_signal(symbol),
            'regime': self.regime_detector.detect_regime(symbol)
        }
    
    def get_regime(self, symbol: str) -> MarketRegime:
        """
        Get current market regime for a symbol
        Exposed for exit manager to use regime-based time stops
        
        Returns:
            MarketRegime enum (TRENDING, RANGING, or UNKNOWN)
        """
        return self.regime_detector.detect_regime(symbol)


# Global multi-strategy manager instance
multi_strategy = MultiStrategyManager()
