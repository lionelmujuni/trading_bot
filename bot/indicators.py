"""
Technical indicators calculation module
Implements RSI, MACD, and ROC for momentum trading
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from core import config
from core.database import db


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """
    Calculate Relative Strength Index (RSI)
    
    Args:
        prices: List of closing prices (oldest to newest)
        period: RSI period (default 14)
    
    Returns:
        RSI value between 0-100, or None if insufficient data
    """
    if len(prices) < period + 1:
        return None
    
    df = pd.DataFrame({'close': prices})
    
    # Calculate price changes
    delta = df['close'].diff()
    
    # Separate gains and losses
    gains = delta.where(delta > 0, 0.0)
    losses = -delta.where(delta < 0, 0.0)
    
    # Calculate average gains and losses
    avg_gain = gains.rolling(window=period, min_periods=period).mean()
    avg_loss = losses.rolling(window=period, min_periods=period).mean()
    
    # Calculate RS and RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None


def calculate_macd(
    prices: List[float], 
    fast: int = 12, 
    slow: int = 26, 
    signal: int = 9
) -> Optional[Dict[str, float]]:
    """
    Calculate MACD (Moving Average Convergence Divergence)
    
    Args:
        prices: List of closing prices (oldest to newest)
        fast: Fast EMA period (default 12)
        slow: Slow EMA period (default 26)
        signal: Signal line EMA period (default 9)
    
    Returns:
        Dict with macd, signal, histogram, or None if insufficient data
    """
    if len(prices) < slow + signal:
        return None
    
    df = pd.DataFrame({'close': prices})
    
    # Calculate EMAs
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    
    # Calculate MACD line
    macd_line = ema_fast - ema_slow
    
    # Calculate signal line
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    
    # Calculate histogram
    histogram = macd_line - signal_line
    
    return {
        'macd': float(macd_line.iloc[-1]),
        'signal': float(signal_line.iloc[-1]),
        'histogram': float(histogram.iloc[-1]),
        'ema_12': float(ema_fast.iloc[-1]),
        'ema_26': float(ema_slow.iloc[-1])
    }


def calculate_roc(prices: List[float], period: int = 12) -> Optional[float]:
    """
    Calculate Rate of Change (ROC)
    
    Args:
        prices: List of closing prices (oldest to newest)
        period: Lookback period (default 12)
    
    Returns:
        ROC percentage, or None if insufficient data
    """
    if len(prices) < period + 1:
        return None
    
    current_price = prices[-1]
    past_price = prices[-(period + 1)]
    
    roc = ((current_price - past_price) / past_price) * 100
    return float(roc)


def calculate_ema(prices: List[float], period: int) -> Optional[float]:
    """
    Calculate Exponential Moving Average
    
    Args:
        prices: List of closing prices (oldest to newest)
        period: EMA period
    
    Returns:
        EMA value or None if insufficient data
    """
    if len(prices) < period:
        return None
    
    df = pd.DataFrame({'close': prices})
    ema = df['close'].ewm(span=period, adjust=False).mean()
    return float(ema.iloc[-1])


class IndicatorCalculator:
    """Main indicator calculator class"""
    
    def __init__(self):
        self.config = config.INDICATOR_CONFIG
    
    def calculate_all_indicators(self, symbol: str) -> Optional[Dict[str, float]]:
        """
        Calculate all indicators for a symbol using database price history
        
        Returns:
            Dict with all indicator values, or None if insufficient data
        """
        # Get required price history
        min_candles = config.COLD_START_CONFIG['min_candles_required']
        price_data = db.get_recent_prices(symbol, candles=min_candles)
        
        if not price_data or len(price_data) < min_candles:
            return None
        
        # Extract closing prices
        prices = [p['close'] for p in price_data]
        
        # Calculate indicators
        indicators = {}
        
        # RSI
        rsi = calculate_rsi(prices, period=self.config['rsi']['period'])
        if rsi is not None:
            indicators['rsi_14'] = rsi
        
        # MACD
        macd_data = calculate_macd(
            prices,
            fast=self.config['macd']['fast'],
            slow=self.config['macd']['slow'],
            signal=self.config['macd']['signal']
        )
        if macd_data:
            indicators.update({
                'macd': macd_data['macd'],
                'macd_signal': macd_data['signal'],
                'macd_histogram': macd_data['histogram'],
                'ema_12': macd_data['ema_12'],
                'ema_26': macd_data['ema_26']
            })
        
        # ROC
        roc = calculate_roc(prices, period=self.config['roc']['period'])
        if roc is not None:
            indicators['roc_12'] = roc
        
        return indicators if indicators else None
    
    def get_indicator_signals(self, symbol: str) -> Dict[str, str]:
        """
        Get trading signals from indicators
        
        Returns:
            Dict with signal for each indicator: BUY, SELL, or NEUTRAL
        """
        indicators = db.get_latest_indicators(symbol)
        
        if not indicators:
            return {}
        
        signals = {}
        
        # RSI Signal
        rsi = indicators.get('rsi_14')
        if rsi is not None:
            if rsi < self.config['rsi']['buy_threshold']:
                signals['rsi'] = 'BUY'
            elif rsi > self.config['rsi']['sell_threshold']:
                signals['rsi'] = 'SELL'
            else:
                signals['rsi'] = 'NEUTRAL'
        
        # MACD Signal (check for crossover)
        macd = indicators.get('macd')
        macd_signal = indicators.get('macd_signal')
        histogram = indicators.get('macd_histogram')
        
        if macd is not None and macd_signal is not None:
            # Get previous MACD to detect crossover
            prev_indicators = db.get_recent_indicators(symbol, hours=2)
            if len(prev_indicators) >= 2:
                prev_hist = prev_indicators[0].get('macd_histogram')
                if prev_hist is not None and histogram is not None:
                    # Bullish crossover
                    if prev_hist < 0 and histogram > 0:
                        signals['macd'] = 'BUY'
                    # Bearish crossover
                    elif prev_hist > 0 and histogram < 0:
                        signals['macd'] = 'SELL'
                    else:
                        signals['macd'] = 'NEUTRAL'
                else:
                    signals['macd'] = 'NEUTRAL'
            else:
                signals['macd'] = 'NEUTRAL'
        
        # ROC Signal
        roc = indicators.get('roc_12')
        if roc is not None:
            if roc > self.config['roc']['buy_threshold']:
                signals['roc'] = 'BUY'
            elif roc < self.config['roc']['sell_threshold']:
                signals['roc'] = 'SELL'
            else:
                signals['roc'] = 'NEUTRAL'
        
        return signals
    
    def is_rsi_overbought_reversal(self, symbol: str) -> bool:
        """Check if RSI shows overbought reversal pattern"""
        recent = db.get_recent_indicators(symbol, hours=2)
        if len(recent) < 2:
            return False
        
        prev_rsi = recent[0].get('rsi_14')
        current_rsi = recent[1].get('rsi_14')
        
        if prev_rsi and current_rsi:
            overbought_level = self.config['rsi']['overbought']
            return prev_rsi > overbought_level and current_rsi < overbought_level
        
        return False
    
    def is_macd_bearish_cross(self, symbol: str) -> bool:
        """Check if MACD shows bearish crossover"""
        recent = db.get_recent_indicators(symbol, hours=2)
        if len(recent) < 2:
            return False
        
        prev_hist = recent[0].get('macd_histogram')
        current_hist = recent[1].get('macd_histogram')
        
        if prev_hist is not None and current_hist is not None:
            return prev_hist > 0 and current_hist < 0
        
        return False
    
    def is_rsi_in_favorable_range(self, symbol: str) -> bool:
        """Check if RSI is in favorable bullish range (55-75)"""
        indicators = db.get_latest_indicators(symbol)
        if not indicators:
            return False
        
        rsi = indicators.get('rsi_14')
        if rsi is None:
            return False
        
        min_val = self.config['rsi']['favorable_min']
        max_val = self.config['rsi']['favorable_max']
        return min_val <= rsi <= max_val
    
    def is_macd_maintaining_strength(self, symbol: str) -> bool:
        """Check if MACD maintains bullish momentum"""
        recent = db.get_recent_indicators(symbol, hours=2)
        if len(recent) < 2:
            return False
        
        current = recent[1]
        prev = recent[0]
        
        macd = current.get('macd')
        signal = current.get('macd_signal')
        current_hist = current.get('macd_histogram')
        prev_hist = prev.get('macd_histogram')
        
        if not all([macd, signal, current_hist, prev_hist]):
            return False
        
        # MACD above signal and histogram not declining significantly
        return macd > signal and current_hist >= prev_hist * 0.95
    
    def get_rsi_drop(self, symbol: str, hours: int = 2) -> Optional[float]:
        """Get RSI drop over specified hours"""
        recent = db.get_recent_indicators(symbol, hours=hours + 1)
        if len(recent) < hours + 1:
            return None
        
        oldest_rsi = recent[0].get('rsi_14')
        newest_rsi = recent[-1].get('rsi_14')
        
        if oldest_rsi and newest_rsi:
            return oldest_rsi - newest_rsi
        
        return None


# Global indicator calculator instance
indicator_calc = IndicatorCalculator()
