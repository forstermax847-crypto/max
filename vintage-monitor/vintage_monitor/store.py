"""Small SQLite database: which listings have been seen/alerted, plus status.

Only eBay listing IDs and the monitor's own status are stored, never any
seller's personal data (this is what makes eBay's account-deletion
exemption apply).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional

SEEN_KEEP_DAYS = 14
ALERTED_KEEP_DAYS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    search TEXT NOT NULL,
    item_id TEXT NOT NULL,
    first_seen REAL NOT NULL,
    PRIMARY KEY (search, item_id)
);
CREATE TABLE IF NOT EXISTS alerted (
    item_id TEXT PRIMARY KEY,
    alerted_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS seeded (
    search TEXT PRIMARY KEY,
    seeded_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class Store:
    def __init__(self, path: str | Path):
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(str(path), timeout=10)
        self.db.execute("PRAGMA busy_timeout = 10000")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # -- seen / seeded / alerted -------------------------------------------

    def is_seeded(self, search: str) -> bool:
        row = self.db.execute("SELECT 1 FROM seeded WHERE search = ?", (search,)).fetchone()
        return row is not None

    def mark_seeded(self, search: str, ids: Iterable[str], now: float) -> None:
        with self.db:
            self.db.executemany(
                "INSERT OR IGNORE INTO seen (search, item_id, first_seen) VALUES (?, ?, ?)",
                [(search, i, now) for i in ids],
            )
            self.db.execute(
                "INSERT OR REPLACE INTO seeded (search, seeded_at) VALUES (?, ?)", (search, now)
            )

    def is_seen(self, search: str, item_id: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM seen WHERE search = ? AND item_id = ?", (search, item_id)
        ).fetchone()
        return row is not None

    def mark_seen(self, search: str, item_id: str, now: float) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO seen (search, item_id, first_seen) VALUES (?, ?, ?)",
                (search, item_id, now),
            )

    def was_alerted(self, item_id: str) -> bool:
        row = self.db.execute("SELECT 1 FROM alerted WHERE item_id = ?", (item_id,)).fetchone()
        return row is not None

    def mark_alerted(self, search: str, item_id: str, now: float) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO alerted (item_id, alerted_at) VALUES (?, ?)", (item_id, now)
            )
            self.db.execute(
                "INSERT OR IGNORE INTO seen (search, item_id, first_seen) VALUES (?, ?, ?)",
                (search, item_id, now),
            )

    def prune(self, now: float) -> None:
        with self.db:
            self.db.execute("DELETE FROM seen WHERE first_seen < ?", (now - SEEN_KEEP_DAYS * 86400,))
            self.db.execute(
                "DELETE FROM alerted WHERE alerted_at < ?", (now - ALERTED_KEEP_DAYS * 86400,)
            )

    def count_seeded(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM seeded").fetchone()[0]

    # -- key/value status --------------------------------------------------

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.db.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return default if row is None else row[0]

    def set(self, key: str, value) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)",
                (key, None if value is None else str(value)),
            )

    def get_float(self, key: str) -> Optional[float]:
        value = self.get(key)
        try:
            return None if value is None else float(value)
        except ValueError:
            return None

    def get_int(self, key: str) -> int:
        value = self.get(key)
        try:
            return 0 if value is None else int(value)
        except ValueError:
            return 0

    def increment(self, key: str, by: int = 1) -> None:
        self.set(key, self.get_int(key) + by)
