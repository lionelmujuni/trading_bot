"""
Mean Reversion Analytics - Ornstein-Uhlenbeck Process Analysis
Implements half-life calculations for mean-reverting strategies (Chan Ch.3)
"""
import numpy as np
import pandas as pd
from typing import Optional, Dict
from core.database import db
from core.logger import logger


class MeanReversionAnalytics:
    """
    Calculates mean reversion characteristics using Ornstein-Uhlenbeck process
    
    The OU process models mean-reverting prices as:
    dy(t) = θ(μ - y(t))dt + σdW(t)
    
    Where:
    - θ (theta) = mean reversion rate
    - μ (mu) = long-term mean price level
    - Half-life = -log(2) / log(theta_estimate)
    """
    
    def __init__(self):
        self.cache = {}  # Cache half-life calculations per cycle
        self.min_observations = 50  # Minimum candles for stable estimate
        self.max_observations = 100  # Use recent 100 candles
    
    def calculate_half_life(self, symbol: str, use_cache: bool = True) -> Optional[float]:
        """
        Calculate half-life of mean reversion for a symbol
        
        Uses AR(1) regression on log prices:
        Δy(t) = λy(t-1) + ε(t)
        
        Where theta = -λ and half_life = -log(2) / log(1 + λ)
        
        Args:
            symbol: Trading pair symbol (e.g., "BTC-USD")
            use_cache: Return cached value if available
        
        Returns:
            Half-life in number of candles, or None if insufficient data
        """
        # Check cache
        if use_cache and symbol in self.cache:
            return self.cache[symbol]
        
        try:
            # Get price history
            price_data = db.get_recent_prices(symbol, candles=self.max_observations)
            
            if not price_data or len(price_data) < self.min_observations:
                logger.debug(
                    f"Insufficient data for half-life: {symbol} has {len(price_data) if price_data else 0} candles",
                    category="ANALYTICS"
                )
                return None
            
            # Extract close prices
            prices = np.array([p['close'] for p in price_data])
            
            # Use log prices for OU process (geometric process)
            log_prices = np.log(prices)
            
            # Calculate first differences: Δy(t) = y(t) - y(t-1)
            y = log_prices[1:]  # y(t)
            y_lag = log_prices[:-1]  # y(t-1)
            delta_y = y - y_lag  # Δy(t)
            
            # AR(1) regression: Δy(t) = λ * y(t-1) + ε(t)
            # Using numpy's least squares
            # Add intercept term for detrended regression
            X = np.vstack([y_lag, np.ones(len(y_lag))]).T
            
            # Solve: [λ, intercept] = argmin ||Δy - X*[λ, intercept]||²
            coeffs, residuals, rank, s = np.linalg.lstsq(X, delta_y, rcond=None)
            lambda_coeff = coeffs[0]
            
            # Calculate theta (mean reversion rate)
            # For discrete time: theta ≈ -λ
            theta = -lambda_coeff
            
            # Half-life calculation
            # Half-life = time for price to move halfway back to mean
            # Formula: t_half = -log(2) / log(theta_estimate)
            # Where theta_estimate = 1 + λ (discrete approximation)
            
            if theta <= 0:
                # No mean reversion detected (momentum or random walk)
                logger.debug(
                    f"No mean reversion for {symbol}: theta={theta:.4f} (λ={lambda_coeff:.4f})",
                    category="ANALYTICS"
                )
                return None
            
            # Discrete-time half-life formula
            theta_estimate = 1 + lambda_coeff
            
            if theta_estimate <= 0 or theta_estimate >= 1:
                # Invalid theta (explosive or non-stationary)
                logger.debug(
                    f"Invalid theta for {symbol}: {theta_estimate:.4f}",
                    category="ANALYTICS"
                )
                return None
            
            half_life = -np.log(2) / np.log(theta_estimate)
            
            # Sanity check: half-life should be positive and reasonable (1-200 candles)
            if half_life < 1 or half_life > 200:
                logger.warning(
                    f"Unusual half-life for {symbol}: {half_life:.1f} candles (θ={theta:.4f})",
                    category="ANALYTICS"
                )
                return None
            
            # Cache result
            self.cache[symbol] = half_life
            
            logger.debug(
                f"Half-life calculated for {symbol}: {half_life:.1f} candles "
                f"(θ={theta:.4f}, λ={lambda_coeff:.4f})",
                category="ANALYTICS"
            )
            
            return half_life
            
        except Exception as e:
            logger.error(
                f"Error calculating half-life for {symbol}: {e}",
                category="ANALYTICS"
            )
            return None
    
    def get_mean_reversion_stats(self, symbol: str) -> Optional[Dict]:
        """
        Get comprehensive mean reversion statistics
        
        Returns:
            Dict with half_life, mean_reversion_rate, confidence, or None
        """
        try:
            price_data = db.get_recent_prices(symbol, candles=self.max_observations)
            
            if not price_data or len(price_data) < self.min_observations:
                return None
            
            prices = np.array([p['close'] for p in price_data])
            log_prices = np.log(prices)
            
            # AR(1) regression
            y = log_prices[1:]
            y_lag = log_prices[:-1]
            delta_y = y - y_lag
            
            X = np.vstack([y_lag, np.ones(len(y_lag))]).T
            coeffs, residuals, rank, s = np.linalg.lstsq(X, delta_y, rcond=None)
            
            lambda_coeff = coeffs[0]
            intercept = coeffs[1]
            theta = -lambda_coeff
            
            if theta <= 0:
                return None
            
            theta_estimate = 1 + lambda_coeff
            
            if theta_estimate <= 0 or theta_estimate >= 1:
                return None
            
            half_life = -np.log(2) / np.log(theta_estimate)
            
            # Calculate R² for confidence measure
            ss_res = np.sum(residuals) if len(residuals) > 0 else np.sum((delta_y - X @ coeffs)**2)
            ss_tot = np.sum((delta_y - np.mean(delta_y))**2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            
            # Long-term mean level (μ)
            # From intercept: intercept = θ*μ, so μ = intercept/θ
            long_term_mean_log = intercept / theta if theta != 0 else log_prices[-1]
            long_term_mean = np.exp(long_term_mean_log)
            
            return {
                'half_life': half_life,
                'mean_reversion_rate': theta,
                'lambda': lambda_coeff,
                'long_term_mean': long_term_mean,
                'current_price': prices[-1],
                'r_squared': r_squared,
                'confidence': 'high' if r_squared > 0.3 else 'medium' if r_squared > 0.1 else 'low',
                'observations': len(prices)
            }
            
        except Exception as e:
            logger.error(
                f"Error calculating mean reversion stats for {symbol}: {e}",
                category="ANALYTICS"
            )
            return None
    
    def clear_cache(self):
        """Clear cached half-life calculations"""
        self.cache.clear()
    
    def should_exit_on_half_life(
        self,
        symbol: str,
        hours_held: int,
        multiplier: float = 3.0
    ) -> bool:
        """
        Check if position should exit based on half-life timeout
        
        Args:
            symbol: Trading pair symbol
            hours_held: Number of candles position has been held
            multiplier: Exit after this many half-lives (default 3.0)
        
        Returns:
            True if position held > multiplier * half_life
        """
        half_life = self.calculate_half_life(symbol, use_cache=True)
        
        if half_life is None:
            # No half-life available, don't trigger half-life exit
            return False
        
        threshold = half_life * multiplier
        
        if hours_held > threshold:
            logger.info(
                f"{symbol} exceeds half-life threshold: {hours_held} > {threshold:.1f} "
                f"({multiplier}x {half_life:.1f} candle half-life)",
                category="ANALYTICS"
            )
            return True
        
        return False


# Singleton instance
analytics = MeanReversionAnalytics()
