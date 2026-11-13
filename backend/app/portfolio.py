"""Portfolio logic: valuation, trade execution, snapshots."""

from __future__ import annotations

import math

from .db import Database, utcnow
from .db.database import USER_ID, new_id
from .market import PriceCache


class TradeError(ValueError):
    """Raised when a trade fails validation."""


def _cash(db: Database) -> float:
    return db.query("SELECT cash_balance FROM users_profile WHERE id = ?", (USER_ID,))[0][0]


def get_portfolio(db: Database, cache: PriceCache) -> dict:
    cash = _cash(db)
    rows = db.query(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? ORDER BY ticker",
        (USER_ID,),
    )
    positions = []
    total_cost = 0.0
    market_total = 0.0
    for r in rows:
        price = cache.get_price(r["ticker"])
        if price is None:
            price = r["avg_cost"]
        mv = r["quantity"] * price
        cost = r["quantity"] * r["avg_cost"]
        total_cost += cost
        market_total += mv
        positions.append(
            {
                "ticker": r["ticker"],
                "quantity": r["quantity"],
                "avg_cost": round(r["avg_cost"], 4),
                "current_price": round(price, 4),
                "market_value": round(mv, 2),
                "unrealized_pnl": round(mv - cost, 2),
                "unrealized_pnl_percent": round((mv - cost) / cost * 100, 4) if cost else 0.0,
            }
        )
    total_value = cash + market_total
    for p in positions:
        p["weight"] = round(p["market_value"] / total_value, 6) if total_value else 0.0
    pnl = market_total - total_cost
    return {
        "cash_balance": round(cash, 2),
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "unrealized_pnl": round(pnl, 2),
        "unrealized_pnl_percent": round(pnl / total_cost * 100, 4) if total_cost else 0.0,
        "positions": positions,
    }


def execute_trade(db: Database, cache: PriceCache, ticker: str, side: str, quantity: float) -> dict:
    """Validate and execute a market order at the cached price. Returns the trade dict."""
    ticker = (ticker or "").strip().upper()
    side = (side or "").strip().lower()
    if side not in ("buy", "sell"):
        raise TradeError("Side must be 'buy' or 'sell'")
    if (
        isinstance(quantity, bool)
        or not isinstance(quantity, (int, float))
        or not math.isfinite(quantity)
        or quantity <= 0
    ):
        raise TradeError("Quantity must be a positive number")
    price = cache.get_price(ticker)
    if price is None:
        raise TradeError(f"No price available for {ticker}")

    with db.lock:
        cash = _cash(db)
        found = db.query(
            "SELECT id, quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
            (USER_ID, ticker),
        )
        pos = found[0] if found else None
        now = utcnow()
        conn = db.conn
        if side == "buy":
            cost = quantity * price
            if cost > cash + 1e-9:
                raise TradeError(f"Insufficient cash: need ${cost:,.2f}, have ${cash:,.2f}")
            conn.execute(
                "UPDATE users_profile SET cash_balance = ? WHERE id = ?", (cash - cost, USER_ID)
            )
            if pos:
                new_qty = pos["quantity"] + quantity
                new_avg = (pos["quantity"] * pos["avg_cost"] + cost) / new_qty
                conn.execute(
                    "UPDATE positions SET quantity = ?, avg_cost = ?, updated_at = ? WHERE id = ?",
                    (new_qty, new_avg, now, pos["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (new_id(), USER_ID, ticker, quantity, price, now),
                )
        else:
            owned = pos["quantity"] if pos else 0.0
            if quantity > owned + 1e-9:
                raise TradeError(f"Insufficient shares: want to sell {quantity:g}, own {owned:g}")
            conn.execute(
                "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
                (cash + quantity * price, USER_ID),
            )
            remaining = owned - quantity
            if remaining <= 1e-9:
                conn.execute("DELETE FROM positions WHERE id = ?", (pos["id"],))
            else:
                conn.execute(
                    "UPDATE positions SET quantity = ?, updated_at = ? WHERE id = ?",
                    (remaining, now, pos["id"]),
                )
        trade = {
            "id": new_id(),
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "price": price,
            "executed_at": now,
        }
        conn.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (trade["id"], USER_ID, ticker, side, quantity, price, now),
        )
        conn.commit()
    record_snapshot(db, cache)
    return trade


def record_snapshot(db: Database, cache: PriceCache) -> None:
    total = get_portfolio(db, cache)["total_value"]
    db.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "VALUES (?, ?, ?, ?)",
        (new_id(), USER_ID, total, utcnow()),
    )


def get_history(db: Database, limit: int = 1000) -> list[dict]:
    rows = db.query(
        "SELECT total_value, recorded_at FROM ("
        " SELECT total_value, recorded_at FROM portfolio_snapshots WHERE user_id = ?"
        " ORDER BY recorded_at DESC LIMIT ?) ORDER BY recorded_at ASC",
        (USER_ID, limit),
    )
    return [{"total_value": r["total_value"], "recorded_at": r["recorded_at"]} for r in rows]
