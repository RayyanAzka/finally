"""SQLite access with lazy schema creation and seeding."""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

USER_ID = "default"
DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]
STARTING_CASH = 10000.0
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def default_db_path() -> str:
    """DB_PATH env var, else <project root>/db/finally.db."""
    env = os.environ.get("DB_PATH", "").strip()
    if env:
        return env
    here = Path(__file__).resolve()
    root = here.parents[3] if (here.parents[3] / "planning").exists() else here.parents[2]
    return str(root / "db" / "finally.db")


class Database:
    """Thin wrapper around one shared sqlite3 connection guarded by a lock.

    Use `with db.lock:` around multi-statement transactions (e.g. trades).
    """

    def __init__(self, path: str | None = None):
        self.path = path or default_db_path()
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init()

    def init(self) -> None:
        """Create tables if missing and seed defaults if the profile is absent."""
        with self.lock:
            self.conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            row = self.conn.execute(
                "SELECT 1 FROM users_profile WHERE id = ?", (USER_ID,)
            ).fetchone()
            if row is None:
                now = utcnow()
                self.conn.execute(
                    "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
                    (USER_ID, STARTING_CASH, now),
                )
                self.conn.executemany(
                    "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) "
                    "VALUES (?, ?, ?, ?)",
                    [(new_id(), USER_ID, t, now) for t in DEFAULT_TICKERS],
                )
            self.conn.commit()

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, params).fetchall()

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self.lock:
            self.conn.execute(sql, params)
            self.conn.commit()

    def close(self) -> None:
        with self.lock:
            self.conn.close()
