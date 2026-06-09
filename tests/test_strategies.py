"""
Test script for advanced multi-strategy system
"""
from core import config
from bot.strategies_advanced import (
    multi_strategy, 
    BollingerBandStrategy, 
    DualMAStrategy, 
    BreakoutStrategy,
    MarketRegime
)
from core.database import db
from core.logger import logger


def test_strategies():
    """Test all strategies on available symbols"""
    
    print("\n" + "="*60)
    print("MULTI-STRATEGY SYSTEM TEST")
    print("="*60)
    
    # Check configuration
    if config.MULTI_STRATEGY_CONFIG.get('enabled'):
        print("✓ Multi-strategy system ENABLED")
    else:
        print("⚠ Multi-strategy system DISABLED (using legacy indicators)")
    
    print("\nTesting strategies on available symbols...")
    print("-"*60)
    
    # Get symbols with enough data
    symbols_to_test = []
    for symbol in config.TRADING_PAIRS:
        price_count = db.get_price_count(symbol)
        if price_count >= config.COLD_START_CONFIG['min_candles_required']:
            symbols_to_test.append(symbol)
    
    if not symbols_to_test:
        print("❌ No symbols with sufficient data for testing")
        print(f"   Need at least {config.COLD_START_CONFIG['min_candles_required']} candles")
        return
    
    print(f"Found {len(symbols_to_test)} symbols with sufficient data\n")
    
    # Test each symbol
    for symbol in symbols_to_test[:5]:  # Test first 5 for brevity
        print(f"\n📊 {symbol}")
        print("-"*40)
        
        # Detect regime
        regime = multi_strategy.regime_detector.detect_regime(symbol)
        print(f"Market Regime: {regime.value.upper()}")
        
        # Get all signals
        signals = multi_strategy.get_all_signals(symbol)
        
        # Bollinger Bands
        bb_signal = signals['bollinger']
        if bb_signal:
            print(f"  • Bollinger Bands: {bb_signal.action} "
                  f"(confidence: {bb_signal.confidence:.2f}, "
                  f"strength: {bb_signal.strength:.2f})")
            print(f"    Reason: {bb_signal.reason}")
        else:
            print("  • Bollinger Bands: No signal")
        
        # Dual MA
        ma_signal = signals['momentum']
        if ma_signal:
            print(f"  • Dual MA: {ma_signal.action} "
                  f"(confidence: {ma_signal.confidence:.2f}, "
                  f"strength: {ma_signal.strength:.2f})")
            print(f"    Reason: {ma_signal.reason}")
        else:
            print("  • Dual MA: No signal")
        
        # Breakout
        breakout_signal = signals['breakout']
        if breakout_signal:
            print(f"  • Breakout: {breakout_signal.action} "
                  f"(confidence: {breakout_signal.confidence:.2f}, "
                  f"strength: {breakout_signal.strength:.2f})")
            print(f"    Reason: {breakout_signal.reason}")
        else:
            print("  • Breakout: No signal")
        
        # Best signal
        best = multi_strategy.get_best_signal(symbol)
        if best:
            print(f"\n  ⭐ BEST SIGNAL: {best.strategy_type.value} → {best.action}")
            print(f"     Confidence: {best.confidence:.2f}")
            print(f"     Reason: {best.reason}")
        else:
            print("\n  ℹ No actionable signals at this time")
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60 + "\n")


if __name__ == "__main__":
    test_strategies()
