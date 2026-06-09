import sqlite3

conn = sqlite3.connect('crypto_bot.db')
cursor = conn.cursor()

print("Tables:")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
for table in cursor.fetchall():
    print(f"  - {table[0]}")

print("\nPositions table schema:")
cursor.execute("PRAGMA table_info(positions)")
cols = cursor.fetchall()

if not cols:
    print("  ERROR: No columns found or table doesn't exist")
else:
    for col in cols:
        print(f"  {col[0]:2d}. {col[1]:25s} {col[2]:10s} {'NOT NULL' if col[3] else 'NULL':8s} default={col[4]}")

print(f"\nTotal columns: {len(cols)}")

conn.close()
