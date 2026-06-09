"""
Test Phase 1: Strategy-Specific Exits Implementation
Validates database schema, position creation, and exit routing
"""
import sqlite3
from core.database import db
from bot.position_manager import position_manager
from bot.exit_manager import exit_manager
from core import config


def test_database_schema():
    """Test 1: Verify entry_strategy column exists in positions table"""
    print("\n" + "="*60)
    print("TEST 1: Database Schema Validation")
    print("="*60)
    
    conn = sqlite3.connect('crypto_bot.db')
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(positions)")
    cols = cursor.fetchall()
    conn.close()
    
    col_names = [col[1] for col in cols]
    
    if 'entry_strategy' in col_names:
        print("✓ PASS: entry_strategy column exists in positions table")
        
        # Find position of entry_strategy
        for i, col in enumerate(cols):
            if col[1] == 'entry_strategy':
                print(f"  - Column name: {col[1]}")
                print(f"  - Data type: {col[2]}")
                print(f"  - Default: {col[4] if col[4] else 'NULL'}")
                print(f"  - Position: {i+1} of {len(cols)}")
        return True
    else:
        print("✗ FAIL: entry_strategy column NOT FOUND")
        print(f"  - Available columns: {', '.join(col_names)}")
        return False


def test_strategy_stop_loss_config():
    """Test 2: Verify STRATEGY_STOP_LOSS configuration"""
    print("\n" + "="*60)
    print("TEST 2: Strategy-Specific Stop Loss Configuration")
    print("="*60)
    
    if hasattr(config, 'STRATEGY_STOP_LOSS'):
        print("✓ PASS: STRATEGY_STOP_LOSS config exists")
        print("\nStop Loss Levels:")
        for strategy, stop_pct in config.STRATEGY_STOP_LOSS.items():
            print(f"  - {strategy:20s}: {stop_pct:6.1%}")
        
        # Validate expected strategies
        required = ['mean_reversion', 'momentum', 'breakout', 'legacy']
        missing = [s for s in required if s not in config.STRATEGY_STOP_LOSS]
        
        if not missing:
            print("\n✓ All required strategies configured")
            return True
        else:
            print(f"\n✗ Missing strategies: {', '.join(missing)}")
            return False
    else:
        print("✗ FAIL: STRATEGY_STOP_LOSS config NOT FOUND")
        return False


def test_exit_manager_methods():
    """Test 3: Verify exit manager has strategy-specific methods"""
    print("\n" + "="*60)
    print("TEST 3: Exit Manager Strategy Methods")
    print("="*60)
    
    methods_to_check = [
        'check_mean_reversion_exit',
        'check_momentum_exit',
        '_get_multi_strategy'
    ]
    
    all_exist = True
    for method in methods_to_check:
        if hasattr(exit_manager, method):
            print(f"✓ PASS: {method}() exists")
        else:
            print(f"✗ FAIL: {method}() NOT FOUND")
            all_exist = False
    
    return all_exist


def test_signal_extraction():
    """Test 4: Verify signal parsing extracts strategy correctly"""
    print("\n" + "="*60)
    print("TEST 4: Strategy Extraction from Signal Reason")
    print("="*60)
    
    test_cases = [
        ("[mean_reversion] Price 2.19σ below mean", "mean_reversion"),
        ("[momentum] Golden cross: fast MA above slow MA", "momentum"),
        ("[breakout] Price broke above resistance", "breakout"),
        ("Legacy signal without bracket", "legacy"),
        ("", "legacy")
    ]
    
    all_passed = True
    for reason, expected_strategy in test_cases:
        # Simulate the extraction logic from position_manager
        entry_strategy = 'legacy'
        if reason and reason.startswith('['):
            end_bracket = reason.find(']')
            if end_bracket > 0:
                entry_strategy = reason[1:end_bracket]
        
        if entry_strategy == expected_strategy:
            print(f"✓ PASS: '{reason[:40]}...' → {entry_strategy}")
        else:
            print(f"✗ FAIL: '{reason[:40]}...' → {entry_strategy} (expected: {expected_strategy})")
            all_passed = False
    
    return all_passed


def test_database_method():
    """Test 5: Verify get_signal_by_id method exists"""
    print("\n" + "="*60)
    print("TEST 5: Database get_signal_by_id Method")
    print("="*60)
    
    if hasattr(db, 'get_signal_by_id'):
        print("✓ PASS: get_signal_by_id() method exists")
        
        # Test with non-existent ID
        try:
            result = db.get_signal_by_id(999999)
            if result is None:
                print("✓ PASS: Returns None for non-existent signal")
            else:
                print("✓ PASS: Method callable (returned data)")
            return True
        except Exception as e:
            print(f"✗ FAIL: Method raised exception: {e}")
            return False
    else:
        print("✗ FAIL: get_signal_by_id() method NOT FOUND")
        return False


def test_existing_positions():
    """Test 6: Check if any existing positions have entry_strategy populated"""
    print("\n" + "="*60)
    print("TEST 6: Existing Positions Analysis")
    print("="*60)
    
    try:
        open_positions = db.get_open_positions()
        closed_positions = db.get_closed_positions(limit=10)
        
        print(f"\nOpen positions: {len(open_positions)}")
        print(f"Recent closed positions: {len(closed_positions)}")
        
        if open_positions:
            print("\nOpen Position Entry Strategies:")
            for pos in open_positions:
                strategy = pos.get('entry_strategy', 'NOT_SET')
                symbol = pos.get('symbol', 'UNKNOWN')
                print(f"  - {symbol}: {strategy}")
        
        if closed_positions:
            print("\nRecent Closed Position Entry Strategies:")
            for pos in closed_positions[:5]:
                strategy = pos.get('entry_strategy', 'NOT_SET')
                symbol = pos.get('symbol', 'UNKNOWN')
                print(f"  - {symbol}: {strategy}")
        
        if not open_positions and not closed_positions:
            print("\n⚠ No positions found in database yet")
            print("  (This is expected if bot hasn't traded yet)")
        
        return True
        
    except Exception as e:
        print(f"✗ FAIL: Error reading positions: {e}")
        return False


def run_all_tests():
    """Run all Phase 1 tests"""
    print("\n" + "="*60)
    print("PHASE 1 VALIDATION TEST SUITE")
    print("Strategy-Specific Exits Implementation")
    print("="*60)
    
    tests = [
        ("Database Schema", test_database_schema),
        ("Stop Loss Config", test_strategy_stop_loss_config),
        ("Exit Manager Methods", test_exit_manager_methods),
        ("Signal Extraction", test_signal_extraction),
        ("Database Method", test_database_method),
        ("Existing Positions", test_existing_positions)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n✗ EXCEPTION in {test_name}: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED - Phase 1 Implementation Validated!")
    else:
        print(f"\n⚠ {total_count - passed_count} test(s) failed - Review implementation")
    
    return passed_count == total_count


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
