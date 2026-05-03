import sqlite3
import os

DB_PATH = os.path.join("data", "seen_pins.db")


def init_db():
    """Create the seen_pins table if it doesn't exist."""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_pins (
            pin_id TEXT PRIMARY KEY,
            seen_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def is_seen(pin_id: str) -> bool:
    """Return True if this pin has already been posted."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT 1 FROM seen_pins WHERE pin_id = ?", (pin_id,)).fetchone()
    conn.close()
    return row is not None


def mark_seen(pin_id: str):
    """Record a pin as posted so it won't be posted again."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO seen_pins (pin_id) VALUES (?)", (pin_id,))
    conn.commit()
    conn.close()
