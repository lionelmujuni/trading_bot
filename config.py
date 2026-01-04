"""
Configuration settings for the crypto trading bot
"""
import os
from typing import List, Dict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Configuration
API_KEY = os.getenv("API_KEY", "")
BASE64_PRIVATE_KEY = os.getenv("BASE64_PRIVATE_KEY", "")
BASE_URL = "https://trading.robinhood.com"

# CryptoCompare API Configuration
CRYPTOCOMPARE_API_KEY = os.getenv("CRYPTOCOMPARE_API_KEY", "")

# Trading Pairs Configuration
# Empty list means the bot will automatically discover ALL available pairs from Robinhood
# that have data on CryptoCompare (~49+ pairs). Populated dynamically at startup.
TRADING_PAIRS: List[str] = []

# Capital Allocation
TOTAL_CAPITAL = float(os.getenv("TOTAL_CAPITAL", "5000.00"))
# Position size is determined per-trade based on MAX_POSITION_SIZE_PCT
# Old model: divide capital equally across all pairs upfront
# New model: allocate capital dynamically based on trading signals up to max position size
MAX_POSITION_SIZE_PCT = float(os.getenv("MAX_POSITION_SIZE_PCT", "5.0")) / 100
MAX_POSITION_SIZE_USD = TOTAL_CAPITAL * MAX_POSITION_SIZE_PCT
CAPITAL_PER_PAIR = MAX_POSITION_SIZE_USD  # Use max position size as default per-pair allocation

# Trading Mode
TRADING_MODE = os.getenv("TRADING_MODE", "paper").lower()  # paper or live

# Time Interval Configuration
INTERVAL_SECONDS = 1200  # 20 minutes per candle

# Risk Management
STOP_LOSS_PCT = -0.10  # -10% hard stop loss
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "5.0")) / 100

# Exit Strategy Configuration
EXIT_CONFIG = {
    "stop_loss_pct": -0.10,
    "special_tp_pct": 0.25,  # +25% with favorable indicators
    "indicator_tp_min_profit": 0.05,  # 5% minimum for indicator TP
    
    # Strategy-Specific Time Exits (Chan Ch.3)
    # Mean reversion needs more time to converge (2x standard)
    # Momentum needs faster exits when trend stalls (0.75x standard)
    "time_exit_candles": {
        "mean_reversion": 144,  # 48 hours (2x standard for convergence)
        "momentum": 54,  # 18 hours (0.75x for trend following)
        "breakout": 72,  # 24 hours (standard)
        "legacy": 72,  # 24 hours (backward compatible)
    },
    
    # Regime-Based Time Exit Multipliers
    # Ranging markets: give positions more time to converge
    # Trending markets: exit faster when trend exhausted
    "regime_time_multipliers": {
        "ranging": 1.5,  # 1.5x time in ranging markets
        "trending": 0.75,  # 0.75x time in trending markets
        "unknown": 1.0,  # No adjustment if regime unclear
    },
    
    # Strategy-Specific Stagnation Thresholds
    # Mean reversion: looser threshold (positions consolidate before reverting)
    # Momentum: tighter threshold (stagnation indicates trend exhaustion)
    "time_exit_stagnant_pct": {
        "mean_reversion": 0.05,  # <5% movement for mean reversion
        "momentum": 0.02,  # <2% movement for momentum
        "breakout": 0.03,  # <3% movement for breakout
        "legacy": 0.03,  # <3% movement (default)
    },
    
    "time_exit_range_pct": 0.05,  # <5% range over 18 candles (6 hours)
    
    # Half-Life Exit Multiplier (Phase 3 - Ornstein-Uhlenbeck)
    # Exit mean reversion positions after N half-lives if not converging
    "half_life_exit_multiplier": 3.0,  # Exit after 3x half-life
}


# Strategy-Specific Stop Loss (Chan Ch.3)
# Mean reversion can tolerate wider stops (positions mean-revert before hitting stop)
# Momentum needs tighter stops (trends can reverse quickly)
STRATEGY_STOP_LOSS = {
    "mean_reversion": -0.15,  # -15% for mean reversion (wider tolerance)
    "momentum": -0.08,  # -8% for momentum (tighter control)
    "breakout": -0.10,  # -10% for breakout (standard)
    "legacy": -0.10,  # -10% for legacy strategy
}

# Indicator Parameters
INDICATOR_CONFIG = {
    "rsi": {
        "period": 14,
        "oversold": 30,
        "buy_threshold": 35,
        "overbought": 70,
        "sell_threshold": 75,
        "favorable_min": 55,
        "favorable_max": 75,
    },
    "macd": {
        "fast": 12,
        "slow": 26,
        "signal": 9,
    },
    "roc": {
        "period": 12,
        "buy_threshold": 8.0,  # 8% upward momentum
        "sell_threshold": -8.0,  # -8% downward momentum
    },
}

# Entry Signal Configuration
ENTRY_CONFIG = {
    "min_indicators_agree": 2,  # At least 2 of 3 must agree
    "min_confidence": 0.66,  # 66% confidence threshold
    "cooldown_candles": 6,  # Minimum candles between trades (2 hours = 6 x 20min)
}

# Multi-Strategy Configuration (Ernest P. Chan's Advanced Strategies)
MULTI_STRATEGY_CONFIG = {
    "enabled": True,  # Set to False to use legacy RSI/MACD/ROC strategy
    
    # Bollinger Bands Mean Reversion (Chan Ch.3)
    "bollinger_bands": {
        "lookback": 20,  # 20 candles = ~6.7 hours
        "std_dev": 2.0,  # Standard deviations for bands
        "entry_zscore": 2.0,  # Enter when |z| > 2
        "exit_zscore": 0.5,  # Exit when |z| < 0.5
    },
    
    # Dual MA Momentum (Chan Ch.6)
    "dual_ma": {
        "short_period": 9,   # 9 candles = 3 hours
        "long_period": 36,   # 36 candles = 12 hours
    },
    
    # Intraday Breakout (Chan Ch.7)
    "breakout": {
        "lookback": 20,  # Volatility lookback period
        "vol_threshold": 2.0,  # Minimum z-score for breakout
    },
    
    # Regime Detection (Chan Ch.8)
    "regime_detection": {
        "lookback": 50,  # ~16.7 hours for regime analysis
        "trend_threshold": 0.5,  # Normalized slope threshold
    },
    
    # Kelly Criterion Position Sizing (Chan Ch.8)
    "kelly_criterion": {
        "enabled": True,
        "safety_factor": 0.5,  # Use half-Kelly for safety
        "min_trades": 20,  # Minimum trades before using Kelly
        "default_fraction": 0.05,  # Default 5% allocation
    },
}

# Strategy Weights by Market Regime
STRATEGY_WEIGHTS = {
    "trending": {
        "momentum": 0.5,  # Favor trend-following in trending markets
        "breakout": 0.3,
        "mean_reversion": 0.2,
    },
    "ranging": {
        "mean_reversion": 0.6,  # Favor mean reversion in ranging markets
        "momentum": 0.2,
        "breakout": 0.2,
    },
    "unknown": {
        "mean_reversion": 0.4,  # Balanced when regime unclear
        "momentum": 0.3,
        "breakout": 0.3,
    },
}

# Cold Start Configuration
COLD_START_CONFIG = {
    "min_candles_required": 101,  # Candles of data needed before trading (~33.7 hours worth)
    "data_checkpoint_file": "cold_start_checkpoint.json",
}

# Rate Limiting (Robinhood API limits)
RATE_LIMIT_CONFIG = {
    "max_requests_per_minute": 100,
    "burst_capacity": 300,
    "refill_rate": 100 / 60,  # tokens per second
}

# Database Configuration
DATABASE_CONFIG = {
    "db_path": "crypto_bot.db",
    "position_state_file": "positions.json",
    "backup_interval_candles": 72,  # 24 hours = 72 candles at 20-min intervals
}

# Logging Configuration
LOGGING_CONFIG = {
    "console_level": "INFO",
    "file_level": "DEBUG",
    "log_file": "crypto_bot.log",
    "max_log_size_mb": 50,
}

# Notifications (Optional)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ENABLE_NOTIFICATIONS = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# Validation
def validate_config() -> bool:
    """Validate critical configuration settings"""
    if not API_KEY or API_KEY == "your_api_key_here":
        print("ERROR: API_KEY not set in .env file")
        return False
    
    if not BASE64_PRIVATE_KEY or BASE64_PRIVATE_KEY == "your_base64_private_key_here":
        print("ERROR: BASE64_PRIVATE_KEY not set in .env file")
        return False
    
    if TOTAL_CAPITAL <= 0:
        print("ERROR: TOTAL_CAPITAL must be greater than 0")
        return False
    
    if TRADING_MODE not in ["paper", "live"]:
        print(f"ERROR: TRADING_MODE must be 'paper' or 'live', got '{TRADING_MODE}'")
        return False
    
    return True

# Display Configuration Summary
def display_config():
    """Display current configuration"""
    print("\n" + "=" * 65)
    print("MOMENTUM CRYPTO BOT - CONFIGURATION")
    print("=" * 65)
    print(f"Trading Mode: {TRADING_MODE.upper()}")
    print(f"Total Capital: ${TOTAL_CAPITAL:,.2f}")
    
    if TRADING_PAIRS:
        print(f"Trading Pairs: {len(TRADING_PAIRS)} pairs")
        print(f"  {', '.join(TRADING_PAIRS[:5])}..." if len(TRADING_PAIRS) > 5 else f"  {', '.join(TRADING_PAIRS)}")
    else:
        print(f"Trading Pairs: Discovering all available pairs from Robinhood...")
    
    print(f"Max Position Size: ${MAX_POSITION_SIZE_USD:,.2f} ({MAX_POSITION_SIZE_PCT*100:.1f}% of capital)")
    print(f"Stop Loss: {STOP_LOSS_PCT*100:.0f}%")
    print(f"Cold Start Required: {COLD_START_CONFIG['min_candles_required']} candles (~35 hours at 20-min intervals)")
    print(f"Interval: {INTERVAL_SECONDS//60} minutes")
    print("=" * 65 + "\n")
