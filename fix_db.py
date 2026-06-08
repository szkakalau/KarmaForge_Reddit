"""One-time fix: add tier column to existing users table."""
import sqlite3

conn = sqlite3.connect('data/processed/karmaforge.db')
try:
    conn.execute("ALTER TABLE users ADD COLUMN tier VARCHAR(16) DEFAULT 'free' NOT NULL")
    print('[OK] tier column added')
except Exception as e:
    print(f'[SKIP] {e}')

# Also ensure subscriptions table exists
conn.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        id VARCHAR(32) PRIMARY KEY,
        user_id VARCHAR(32) NOT NULL UNIQUE REFERENCES users(id),
        stripe_customer_id VARCHAR(64),
        stripe_subscription_id VARCHAR(64),
        plan VARCHAR(16) DEFAULT 'free' NOT NULL,
        status VARCHAR(16) DEFAULT 'active' NOT NULL,
        current_period_start DATETIME,
        current_period_end DATETIME,
        cancel_at_period_end BOOLEAN DEFAULT 0,
        stripe_event_ids JSON DEFAULT '[]',
        created_at DATETIME,
        updated_at DATETIME
    )
""")
print('[OK] subscriptions table ready')

conn.commit()
conn.close()
print('[DONE] Database fixed')
