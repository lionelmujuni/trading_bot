"""
Database Migration: Add entry_strategy column to positions table
Run this to update existing database with Phase 1 changes
"""
import sqlite3
import sys


def migrate_database():
    """Add entry_strategy column to existing positions table"""
    print("="*60)
    print("DATABASE MIGRATION: Add entry_strategy Column")
    print("="*60)
    
    try:
        conn = sqlite3.connect('crypto_bot.db')
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(positions)")
        cols = cursor.fetchall()
        col_names = [col[1] for col in cols]
        
        if 'entry_strategy' in col_names:
            print("\n✓ Column 'entry_strategy' already exists")
            print("  No migration needed")
            conn.close()
            return True
        
        print("\n→ Adding 'entry_strategy' column...")
        
        # Add the column
        cursor.execute("""
            ALTER TABLE positions 
            ADD COLUMN entry_strategy TEXT DEFAULT 'legacy'
        """)
        
        conn.commit()
        
        # Verify addition
        cursor.execute("PRAGMA table_info(positions)")
        cols = cursor.fetchall()
        col_names = [col[1] for col in cols]
        
        if 'entry_strategy' in col_names:
            print("✓ SUCCESS: Column added successfully")
            
            # Show column details
            for col in cols:
                if col[1] == 'entry_strategy':
                    print(f"\n  Column Details:")
                    print(f"  - Name: {col[1]}")
                    print(f"  - Type: {col[2]}")
                    print(f"  - Default: {col[4] if col[4] else 'NULL'}")
            
            # Update existing positions to 'legacy'
            cursor.execute("UPDATE positions SET entry_strategy = 'legacy' WHERE entry_strategy IS NULL")
            updated_count = cursor.rowcount
            conn.commit()
            
            print(f"\n✓ Updated {updated_count} existing position(s) to 'legacy' strategy")
            
            conn.close()
            return True
        else:
            print("✗ FAIL: Column not found after ALTER TABLE")
            conn.close()
            return False
            
    except sqlite3.OperationalError as e:
        print(f"\n✗ FAIL: Database error: {e}")
        return False
    except Exception as e:
        print(f"\n✗ FAIL: Unexpected error: {e}")
        return False


def verify_migration():
    """Verify the migration was successful"""
    print("\n" + "="*60)
    print("VERIFICATION")
    print("="*60)
    
    try:
        conn = sqlite3.connect('crypto_bot.db')
        cursor = conn.cursor()
        
        # Check schema
        cursor.execute("PRAGMA table_info(positions)")
        cols = cursor.fetchall()
        
        print(f"\nPositions table has {len(cols)} columns:")
        for i, col in enumerate(cols, 1):
            default_str = f" (default: {col[4]})" if col[4] else ""
            print(f"  {i:2d}. {col[1]:25s} {col[2]:10s}{default_str}")
        
        # Check existing positions
        cursor.execute("SELECT COUNT(*) FROM positions")
        total_positions = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM positions WHERE entry_strategy IS NOT NULL")
        positions_with_strategy = cursor.fetchone()[0]
        
        print(f"\nPosition Records:")
        print(f"  - Total positions: {total_positions}")
        print(f"  - With entry_strategy: {positions_with_strategy}")
        
        if total_positions > 0:
            cursor.execute("""
                SELECT entry_strategy, COUNT(*) 
                FROM positions 
                GROUP BY entry_strategy
            """)
            strategy_counts = cursor.fetchall()
            
            print(f"\n  Strategy Distribution:")
            for strategy, count in strategy_counts:
                print(f"    - {strategy or 'NULL':15s}: {count}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"\n✗ Error during verification: {e}")
        return False


if __name__ == "__main__":
    print("\nStarting database migration...\n")
    
    success = migrate_database()
    
    if success:
        verify_migration()
        print("\n" + "="*60)
        print("✓ MIGRATION COMPLETE")
        print("="*60)
        print("\nYou can now run: python test_phase1.py")
        sys.exit(0)
    else:
        print("\n" + "="*60)
        print("✗ MIGRATION FAILED")
        print("="*60)
        sys.exit(1)
