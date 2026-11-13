"""Watchlist logic."""

from __future__ import annotations

import re

from .db import Database, utcnow
from .db.database import USER_ID, new_id
from .market import MarketDataSource, PriceCache

TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class WatchlistError(ValueError):
    pass


def normalize_ticker(ticker: str) -> str:
    t = (ticker or "").strip().upper()
    if not TICKER_RE.match(t):
        raise WatchlistError(f"Invalid ticker: {ticker!r}")
    return t


def list_watchlist(db: Database, cache: PriceCache) -> list[dict]:
    rows = db.query(
        "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at, ticker",
        (USER_ID,),
    )
    out = []
    for r in rows:
        u = cache.get(r["ticker"])
        out.append(
            {
                "ticker": r["ticker"],
                "price": u.price if u else None,
                "previous_price": u.previous_price if u else None,
                "change": u.change if u else None,
                "change_percent": u.change_percent if u else None,
                "direction": u.direction if u else None,
                "added_at": r["added_at"],
            }
        )
    return out


def watched_tickers(db: Database) -> list[str]:
    """Watchlist plus held positions: everything the market source must track."""
    rows = db.query(
        "SELECT ticker FROM watchlist WHERE user_id = ? "
        "UNION SELECT ticker FROM positions WHERE user_id = ?",
        (USER_ID, USER_ID),
    )
    return [r[0] for r in rows]


async def add_ticker(db: Database, source: MarketDataSource, ticker: str) -> tuple[str, bool]:
    t = normalize_ticker(ticker)
    with db.lock:
        exists = db.query(
            "SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?", (USER_ID, t)
        )
        if exists:
            return t, False
        db.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (new_id(), USER_ID, t, utcnow()),
        )
    await source.add_ticker(t)
    return t, True


async def remove_ticker(db: Database, source: MarketDataSource, ticker: str) -> str | None:
    """Returns the ticker if removed, None if it was not on the watchlist."""
    t = (ticker or "").strip().upper()
    with db.lock:
        if not db.query("SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?", (USER_ID, t)):
            return None
        db.execute("DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (USER_ID, t))
        held = db.query("SELECT 1 FROM positions WHERE user_id = ? AND ticker = ?", (USER_ID, t))
    if not held:
        await source.remove_ticker(t)
    return t
