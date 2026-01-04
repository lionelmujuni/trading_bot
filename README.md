# Advanced Multi-Strategy Crypto Trading Bot

A Python-based automated cryptocurrency trading bot implementing Ernest P. Chan's quantitative trading strategies with the Robinhood Crypto API. Features regime-aware strategy selection, Bollinger Bands mean reversion, dual moving average momentum, breakout detection, Kelly Criterion position sizing, and dynamic market data bootstrapping from CryptoCompare.

## Features

### Trading Strategies (Multi-Strategy System)

- **Regime Detection**: Automatically detects trending vs. ranging markets using linear regression slope analysis
- **Bollinger Bands Mean Reversion**: Trades price deviations (z-score > 2σ) for range-bound markets
- **Dual MA Momentum**: Golden/death cross signals (9/36 period MAs) for trending markets  
- **Intraday Breakout**: Volume-confirmed volatility breakouts (2σ+ moves with 1.5x+ volume)
- **Kelly Criterion Position Sizing**: Optimal capital allocation based on win rate and avg win/loss
- **Adaptive Weighting**: Favors mean reversion (60%) in ranging markets, momentum (50%) in trending markets

### Legacy Strategy (Optional)

- **RSI(14), MACD(12,26,9), ROC(12)**: Multi-indicator confluence requiring 2 of 3 agreements
- Toggle between advanced and legacy strategies via `MULTI_STRATEGY_CONFIG['enabled']` in config

### Risk Management

- **Dynamic Pair Discovery**: Auto-fetches all ~49 available cryptos from Robinhood on first run
- **Equal Allocation**: Divides capital equally across all discovered trading pairs
- **34-Hour Cold Start**: Accumulates 101 candles (20-min intervals) organically before trading
- **Data Source Validation**: Tests each symbol on CryptoCompare individually for availability
- **Exit Strategy**:
  - Hard stop loss at -10%
  - Special take profit at +25% with favorable indicators
  - Indicator-based reversal exits (RSI overbought + MACD bearish cross)
  - Time-based exits after 24 hours with <3% movement

### Infrastructure

- **Paper Trading Mode**: Test strategies without risking real capital
- **Rate Limiting**: Token bucket rate limiter for API compliance (100 req/min)
- **Graceful Shutdown**: Saves state on Ctrl+C for safe restarts
- **Comprehensive Logging**: Console and database logging with full trade history
- **SQLite Database**: Stores prices, indicators, positions, orders, signals, and metrics

## Project Structure

```
crypto_bot/
├── main.py                  # Main bot orchestrator
├── cli.py                   # Command-line interface
├── config.py                # Configuration settings
├── database.py              # SQLite database layer
├── robinhood_client.py      # Robinhood API client
├── data_bootstrap.py        # Historical data fetcher (CryptoCompare)
├── cold_start.py            # Cold start manager
├── indicators.py            # Technical indicator calculations (RSI, MACD, ROC)
├── strategies_advanced.py   # Multi-strategy system (Chan's strategies)
├── strategy.py              # Entry signal generator (multi-strategy + legacy)
├── exit_manager.py          # Exit condition evaluator
├── position_manager.py      # Position tracking & execution
├── logger.py                # Structured logging
├── metrics.py               # Performance metrics
├── test_strategies.py       # Strategy testing utility
├── requirements.txt         # Python dependencies
├── .env.template            # Environment template
└── README.md                # This file
```

## Installation

### 1. Prerequisites

- Python 3.8 or higher
- Robinhood account with Crypto Trading enabled
- API credentials from [Robinhood API Credentials Portal](https://robinhood.com/account/settings/crypto)
- CryptoCompare API key (free tier available at https://min-api.cryptocompare.com)

### 2. Install Dependencies

```powershell
cd C:\Users\User\Documents\crypto_bot
pip install -r requirements.txt
```

### 3. Generate API Keys

Run the provided script to generate Ed25519 keypair:

```powershell
python -c "import nacl.signing; import base64; key = nacl.signing.SigningKey.generate(); print('Private:', base64.b64encode(key.encode()).decode()); print('Public:', base64.b64encode(key.verify_key.encode()).decode())"
```

### 4. Configure Environment

Copy `.env.template` to `.env` and add your credentials:

```powershell
copy .env.template .env
```

Edit `.env`:
```env
API_KEY=your_robinhood_api_key_here
BASE64_PRIVATE_KEY=your_base64_private_key_here
CRYPTOCOMPARE_API_KEY=your_cryptocompare_api_key_here
TOTAL_CAPITAL=5000.00
TRADING_MODE=paper  # Use 'paper' for testing, 'live' for real trading
```

## Usage

### Start the Bot

```powershell
python cli.py start
```

Or run directly:
```powershell
python main.py
```

### Check Status

```powershell
python cli.py status
```

### View Trade History

```powershell
python cli.py history
python cli.py history --limit 20
```

### View Signal Status

```powershell
python cli.py signals
```

### Test Strategies

```powershell
python test_strategies.py
```

### Test API Connection

```powershell
python cli.py test-api
```

### Reset Database (Testing)

```powershell
python cli.py reset
```

## Trading Strategy

### Multi-Strategy System (Default)

The bot uses a sophisticated multi-strategy approach based on Ernest P. Chan's "Algorithmic Trading: Winning Strategies and Their Rationale":

#### 1. Regime Detection

Market regime is detected using linear regression slope analysis over 50 candles (~16.7 hours):

- **Trending**: High normalized slope (>0.5) → Favor momentum and breakout strategies
- **Ranging**: Low normalized slope (≤0.5) → Favor mean reversion strategies

#### 2. Strategy Selection & Weighting

**Ranging Markets** (most common in crypto):
- Mean Reversion (Bollinger Bands): 60% weight
- Momentum (Dual MA): 20% weight
- Breakout: 20% weight

**Trending Markets**:
- Momentum (Dual MA): 50% weight
- Breakout: 30% weight
- Mean Reversion: 20% weight

#### 3. Individual Strategies

**Bollinger Bands Mean Reversion** (Chan Ch.3):
- Entry: Price deviates >2σ from 20-candle moving average
- Exit: Price returns to within 0.5σ of mean
- Best for: Range-bound markets, oversold/overbought bounces
- Example: BUY when z-score < -2.0 (price 2 standard deviations below mean)

**Dual MA Crossover Momentum** (Chan Ch.6):
- Short MA: 9 candles (3 hours)
- Long MA: 36 candles (12 hours)
- Golden Cross (BUY): Short MA crosses above long MA
- Death Cross (SELL): Short MA crosses below long MA
- Best for: Trending markets, capturing sustained moves

**Intraday Breakout** (Chan Ch.7):
- Detects: 2σ+ price moves with 1.5x+ average volume
- Filters: Requires both price volatility AND volume confirmation
- Best for: High volatility periods, momentum continuation

#### 4. Entry Conditions

- **Regime-Weighted Score**: Each strategy's signal is weighted by current market regime
- **Confidence Threshold**: Minimum 66% confidence required
- **Cooldown Period**: 2 hours (6 candles) between trades per symbol
- **No Existing Position**: Won't open new position if one already exists

#### 5. Position Sizing (Kelly Criterion)

- **Kelly Formula**: f = (p×b - q) / b
  - p = win rate
  - q = loss rate (1-p)
  - b = avg win / avg loss
- **Half-Kelly**: Uses 50% of calculated Kelly fraction for safety
- **Default**: 25% of available capital per position until 20+ trades establish statistics

### Legacy Strategy (Optional)

Set `MULTI_STRATEGY_CONFIG['enabled'] = False` in config.py to use:

**Entry Conditions:**
- **Confluence Required**: 2 of 3 indicators must agree (BUY signal)
- **RSI < 35**: Oversold momentum
- **MACD Bullish Cross**: MACD line crosses above signal line
- **ROC > 8%**: Strong upward momentum
- **Confidence ≥ 66%**: At least 2/3 indicators bullish
- **No Bearish Signals**: None of the 3 indicators show SELL

### Exit Conditions (Both Strategies)

Priority-ordered exit logic (first condition met triggers exit):

1. **Hard Stop Loss (-10%)**: Immediate exit if price drops 10% from entry
2. **Special TP (+25%)**: Exit at +25% profit if indicators still favorable:
   - RSI between 55-75 (healthy bullish range)
   - MACD maintaining strength (above signal, histogram not declining)
3. **Indicator Take Profit**: Exit on reversal signals with minimum 5% profit:
   - RSI crosses below 70 from above (overbought reversal)
   - MACD bearish crossover
4. **Time Exit (24h)**: Exit after 24 hours (72 candles) if:
   - Price moved <3% over entire holding period
   - 6-hour range was <5%

## Cold Start Phase

The bot requires 34 hours of price data before trading:

**Timeline (20-minute candles):**
- **Hours 0-33**: Collecting 101 candles of base data
- **Hour 14**: RSI(14) calculation available
- **Hour 26**: MACD(12,26,9) calculation available  
- **Hour 34**: All indicators ready → Trading begins
- **Hour 35+**: Live trading active with multi-strategy system

**Bootstrap Process:**
1. Fetches list of all available cryptos from Robinhood (~49 symbols)
2. Tests each symbol individually on CryptoCompare for data availability
3. Collects 105 candles (101 required + 4 buffer) for each available symbol
4. Progress displayed every 10 symbols and saved to checkpoint
5. Checkpoint allows crash recovery without starting over

**Data Sources:**
- **Market Data**: CryptoCompare min-api (20-minute aggregated candles)
- **Market Cap**: Robinhood API (for symbol validation)
- **Trade Execution**: Robinhood API

## Configuration

### Multi-Strategy Configuration

Edit `config.py` to customize strategy parameters:

```python
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
        "default_fraction": 0.25,  # Default 25% allocation
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
}
```

### General Configuration

```python
# Trading pairs (auto-discovered on first run)
TRADING_PAIRS = ["BTC-USD", "ETH-USD", ...]  # ~49 pairs dynamically fetched

# Capital allocation
TOTAL_CAPITAL = 5000.00  # Divided equally across all pairs

# Risk management
STOP_LOSS_PCT = -0.10  # -10%
MAX_POSITION_SIZE_PCT = 0.25  # 25% max per position

# Legacy indicator thresholds (used for exits even with multi-strategy)
INDICATOR_CONFIG = {
    "rsi": {"period": 14, "buy_threshold": 35, "sell_threshold": 75},
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "roc": {"period": 12, "buy_threshold": 8.0}
}
```

## Database

All data is stored in `crypto_bot.db` SQLite database:

- **price_history**: OHLC price data with best bid/ask (20-minute candles)
- **indicators**: Calculated RSI, MACD, ROC values (used for exits)
- **positions**: Open and closed position records with P&L
- **orders**: Order execution history
- **trading_signals**: Entry signal log with strategy type, confidence scores, and reasons
- **performance_metrics**: Portfolio performance snapshots
- **bot_log**: Structured activity log

## Strategy Testing

Test strategies without running the bot:

```powershell
python test_strategies.py
```

Output shows:
- Market regime for each symbol (trending/ranging)
- Signals from each strategy (Bollinger Bands, Dual MA, Breakout)
- Best weighted signal selected by regime-aware manager
- Confidence scores and reasoning for each signal

## Safety Features

- **Paper Trading Mode**: Test without risking capital (default mode)
- **Rate Limiting**: Respects CryptoCompare (1 req/sec) and Robinhood (100 req/min) limits
- **Error Handling**: Retries with exponential backoff on API failures
- **Graceful Shutdown**: Saves state on Ctrl+C, resumes from checkpoint
- **Position Limits**: Equal allocation prevents over-concentration
- **Stop Loss**: Hard -10% stop on all positions
- **Data Validation**: Validates order sizes against exchange minimums
- **None-Value Handling**: All metrics handle missing data gracefully

## Monitoring

The bot logs all activity:

- **Console**: Real-time updates with formatted output
  - `[STRATEGY]` tags show regime detection and strategy selection
  - `[SIGNAL]` tags show entry signals with confidence
  - `[POSITION]` tags show P&L updates every cycle
  - `[EXIT]` tags show exit conditions and reasons

- **Database**: Structured logs stored in `bot_log` table
- **Trade Log**: Entry/exit with strategy type, P&L tracking, hold duration
- **Signal Log**: Strategy type, confidence, strength, and reasoning
- **Position Updates**: Every 20 minutes with current P&L

**Example Log Output:**
```
[STRATEGY] BTC-USD [ranging] Best signal: mean_reversion BUY (confidence: 0.73, strength: 2.19)
[SIGNAL] BUY signal for BTC-USD (confidence: 73.16%)
[TRADE] Opening position for BTC-USD
[POSITION] BTC-USD position: +2.5% P&L, held 1.2h, OPEN
```

## Troubleshooting

### API Authentication Errors

- Verify `API_KEY` and `BASE64_PRIVATE_KEY` in `.env`
- Ensure keys are valid and not expired
- Check timestamp synchronization (within 30 seconds)

### CryptoCompare Errors

- Add `CRYPTOCOMPARE_API_KEY` to `.env` (free tier available)
- Check rate limits (1 request per second)
- Verify symbols have data available on CryptoCompare

### Cold Start Not Progressing

- Check API connection: `python cli.py test-api`
- Verify price data collection in database: `python cli.py status`
- Check logs for errors and rate limit issues
- Ensure CryptoCompare API key is valid

### No Trades Executing

- Ensure cold start complete (34 hours, 101+ candles per symbol)
- Check multi-strategy signals: `python test_strategies.py`
- Verify sufficient capital allocated
- Check cooldown periods (2 hours between trades per symbol)
- Review strategy confidence thresholds (minimum 66%)
- Confirm `MULTI_STRATEGY_CONFIG['enabled'] = True`

### TypeError / None Value Errors

All fixed in current version:
- Position metrics handle None values gracefully
- Indicators always calculated (needed for exit logic)
- Metrics calculation handles missing data

### Database Issues

- Reset database: `python cli.py reset` (WARNING: deletes all data)
- Check file permissions on `crypto_bot.db`
- Ensure SQLite3 installed

## Performance Notes

- **Candle Interval**: 20 minutes (optimized for crypto volatility)
- **Data History**: ~34 hours per symbol (~14 GB for 49 pairs)
- **Evaluation Frequency**: Every 20 minutes on the hour (00, 20, 40)
- **Strategy Calculation**: <2 seconds for all 49 symbols
- **Bootstrap Time**: ~25-30 minutes for 49 symbols (with rate limiting)

## Disclaimer

**This software is for educational purposes only. Cryptocurrency trading carries significant risk. Past performance does not guarantee future results. Only trade with capital you can afford to lose. The authors assume no responsibility for financial losses.**

The strategies implemented are based on Ernest P. Chan's "Algorithmic Trading: Winning Strategies and Their Rationale" and adapted for 20-minute cryptocurrency trading. Results will vary based on market conditions, capital allocation, and risk parameters.

## References

- Ernest P. Chan - "Algorithmic Trading: Winning Strategies and Their Rationale"
- Robinhood API Documentation: https://docs.robinhood.com
- CryptoCompare API: https://min-api.cryptocompare.com

## Support

For issues or questions:
- Review Robinhood API documentation: https://docs.robinhood.com
- Review CryptoCompare API documentation: https://min-api.cryptocompare.com
- Check database logs: See `bot_log` table
- Test API connection: `python cli.py test-api`
- Test strategies: `python test_strategies.py`

## License

MIT License - See source files for details.
