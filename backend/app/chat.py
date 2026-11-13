"""LLM chat: prompt construction, structured output parsing, action execution."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from . import portfolio as pf
from . import watchlist as wl
from .db import Database, utcnow
from .db.database import USER_ID, new_id
from .market import MarketDataSource, PriceCache

logger = logging.getLogger(__name__)

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}
HISTORY_LIMIT = 20

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant inside a simulated trading workstation.
The user trades a virtual portfolio with fake money using market orders at the live price.
You can: analyze portfolio composition, risk concentration and P&L; suggest trades with brief
reasoning; execute trades when the user asks or agrees; and manage the watchlist proactively.
Be concise and data-driven. Only include trades when the user asked for or agreed to them.
Always respond with valid JSON matching the schema: {"message": str, "trades": [{"ticker",
"side": "buy"|"sell", "quantity": number}], "watchlist_changes": [{"ticker",
"action": "add"|"remove"}]}. Use empty arrays when there is nothing to do."""


class TradeRequest(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistChange(BaseModel):
    ticker: str
    action: Literal["add", "remove"]


class LLMResponse(BaseModel):
    message: str
    trades: list[TradeRequest] = Field(default_factory=list)
    watchlist_changes: list[WatchlistChange] = Field(default_factory=list)


def parse_llm_output(raw: str | None) -> LLMResponse:
    """Parse structured output; degrade gracefully to a plain-text message."""
    if not raw or not raw.strip():
        return LLMResponse(message="Sorry, I got an empty response. Please try again.")
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return LLMResponse.model_validate_json(text)
    except (ValidationError, ValueError):
        pass
    try:
        data = json.loads(text)
        if isinstance(data, dict) and isinstance(data.get("message"), str):
            return LLMResponse(message=data["message"])
    except ValueError:
        pass
    return LLMResponse(message=text)


def mock_response(message: str, pf_summary: dict) -> LLMResponse:
    """Deterministic mock used when LLM_MOCK=true."""
    trades, changes = [], []
    parts = []
    m = re.search(
        r"\b(buy|sell)\s+(\d+(?:\.\d+)?)\s+(?:shares?\s+of\s+)?([A-Za-z][A-Za-z0-9.\-]{0,9})",
        message,
        re.I,
    )
    if m:
        side, qty, ticker = m.group(1).lower(), float(m.group(2)), m.group(3).upper()
        trades.append(TradeRequest(ticker=ticker, side=side, quantity=qty))
        parts.append(f"Placing a {side} order for {qty:g} shares of {ticker}.")
    w = re.search(r"\b(add|remove)\s+([A-Za-z][A-Za-z0-9.\-]{0,9})\b", message, re.I)
    if w and not m:
        action, ticker = w.group(1).lower(), w.group(2).upper()
        changes.append(WatchlistChange(ticker=ticker, action=action))
        parts.append(f"{'Adding' if action == 'add' else 'Removing'} {ticker} "
                     f"{'to' if action == 'add' else 'from'} your watchlist.")
    if not parts:
        parts.append(
            f"Your portfolio is worth ${pf_summary['total_value']:,.2f} with "
            f"${pf_summary['cash_balance']:,.2f} in cash across "
            f"{len(pf_summary['positions'])} positions."
        )
    return LLMResponse(message=" ".join(parts), trades=trades, watchlist_changes=changes)


def _context(db: Database, cache: PriceCache) -> str:
    p = pf.get_portfolio(db, cache)
    wl_rows = wl.list_watchlist(db, cache)
    ctx = {
        "cash_balance": p["cash_balance"],
        "total_value": p["total_value"],
        "positions": p["positions"],
        "watchlist": [{"ticker": w["ticker"], "price": w["price"]} for w in wl_rows],
    }
    return "Current portfolio context (JSON):\n" + json.dumps(ctx)


def _history(db: Database) -> list[dict]:
    rows = db.query(
        "SELECT role, content FROM (SELECT role, content, created_at, rowid AS rid "
        "FROM chat_messages WHERE user_id = ? ORDER BY created_at DESC, rid DESC LIMIT ?) "
        "ORDER BY created_at ASC, rid ASC",
        (USER_ID, HISTORY_LIMIT),
    )
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def _call_llm_sync(messages: list[dict]) -> str | None:
    from litellm import completion

    response = completion(
        model=MODEL,
        messages=messages,
        response_format=LLMResponse,
        reasoning_effort="low",
        extra_body=EXTRA_BODY,
    )
    return response.choices[0].message.content


def get_history_messages(db: Database, limit: int = 50) -> list[dict]:
    rows = db.query(
        "SELECT id, role, content, actions, created_at FROM ("
        " SELECT id, role, content, actions, created_at, rowid AS rid FROM chat_messages"
        " WHERE user_id = ? ORDER BY created_at DESC, rid DESC LIMIT ?)"
        " ORDER BY created_at ASC, rid ASC",
        (USER_ID, limit),
    )
    return [
        {
            "id": r["id"],
            "role": r["role"],
            "content": r["content"],
            "actions": json.loads(r["actions"]) if r["actions"] else None,
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def _store(db: Database, role: str, content: str, actions: dict | None) -> str:
    now = utcnow()
    db.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (new_id(), USER_ID, role, content, json.dumps(actions) if actions else None, now),
    )
    return now


async def handle_chat(
    db: Database, cache: PriceCache, source: MarketDataSource, user_message: str
) -> dict:
    portfolio_before = pf.get_portfolio(db, cache)
    history = _history(db)
    _store(db, "user", user_message, None)

    if os.environ.get("LLM_MOCK", "").strip().lower() == "true":
        llm = mock_response(user_message, portfolio_before)
    else:
        messages = (
            [{"role": "system", "content": SYSTEM_PROMPT},
             {"role": "system", "content": _context(db, cache)}]
            + history
            + [{"role": "user", "content": user_message}]
        )
        try:
            raw = await asyncio.to_thread(_call_llm_sync, messages)
            llm = parse_llm_output(raw)
        except Exception as exc:  # network, auth, provider errors
            logger.exception("LLM call failed")
            llm = LLMResponse(message=f"Sorry, I couldn't reach the AI service ({type(exc).__name__}).")

    trade_results = []
    for t in llm.trades:
        entry = {"ticker": t.ticker.upper(), "side": t.side, "quantity": t.quantity,
                 "success": False, "price": None, "error": None}
        try:
            done = pf.execute_trade(db, cache, t.ticker, t.side, t.quantity)
            entry.update(success=True, price=done["price"])
        except pf.TradeError as exc:
            entry["error"] = str(exc)
        trade_results.append(entry)

    wl_results = []
    for c in llm.watchlist_changes:
        entry = {"ticker": c.ticker.upper(), "action": c.action, "success": False, "error": None}
        try:
            if c.action == "add":
                entry["ticker"], _ = await wl.add_ticker(db, source, c.ticker)
                entry["success"] = True
            else:
                removed = await wl.remove_ticker(db, source, c.ticker)
                if removed:
                    entry["success"] = True
                else:
                    entry["error"] = f"{entry['ticker']} is not on the watchlist"
        except wl.WatchlistError as exc:
            entry["error"] = str(exc)
        wl_results.append(entry)

    message = llm.message
    errors = [f"{r['side']} {r['quantity']:g} {r['ticker']}: {r['error']}"
              for r in trade_results if r["error"]]
    errors += [f"{r['action']} {r['ticker']}: {r['error']}" for r in wl_results if r["error"]]
    if errors:
        message += "\n\nSome actions failed:\n- " + "\n- ".join(errors)

    actions = {"trades": trade_results, "watchlist_changes": wl_results}
    created_at = _store(db, "assistant", message, actions if (trade_results or wl_results) else None)
    return {
        "message": message,
        "trades": trade_results,
        "watchlist_changes": wl_results,
        "created_at": created_at,
    }
