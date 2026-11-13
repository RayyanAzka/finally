# FinAlly API Contract (backend -> frontend)

All endpoints are same-origin, JSON, no auth. Timestamps are ISO-8601 UTC strings (except SSE `timestamp`, unix seconds float).
Errors: non-2xx with `{"detail": "<human readable message>"}` (400 validation/trade errors, 404 not found, 422 malformed body).

## GET /api/stream/prices  (SSE)
`text/event-stream`. First line `retry: 1000`. Each event is `data: <json>` where json is a map ticker -> update, sent whenever prices change (~500ms):
```json
{"AAPL": {"ticker":"AAPL","price":190.5,"previous_price":190.4,"timestamp":1731500000.1,
          "change":0.1,"change_percent":0.0525,"direction":"up"}, "GOOGL": {...}}
```
`direction` is "up" | "down" | "flat". Contains every ticker known to the system (watchlist + held positions).

## GET /api/health
`{"status":"ok"}`

## GET /api/portfolio
```json
{
  "cash_balance": 10000.0,
  "total_value": 10000.0,            // cash + sum(market_value)
  "total_cost": 0.0,                 // sum(quantity*avg_cost)
  "unrealized_pnl": 0.0,             // total_value - cash - total_cost
  "unrealized_pnl_percent": 0.0,
  "positions": [
    {"ticker":"AAPL","quantity":10.0,"avg_cost":190.0,"current_price":191.0,
     "market_value":1910.0,"unrealized_pnl":10.0,"unrealized_pnl_percent":0.526,
     "weight":0.16}                  // market_value / total_value
  ]
}
```

## POST /api/portfolio/trade
Request: `{"ticker":"AAPL","quantity":10,"side":"buy"}` (side: "buy"|"sell"; quantity > 0, fractional OK; ticker case-insensitive).
200 response: `{"success":true,"trade":{"id","ticker","side","quantity","price","executed_at"},"portfolio":<same shape as GET /api/portfolio>}`
400 `{"detail":"Insufficient cash ..."}` / `"Insufficient shares ..."` / `"No price available for XYZ"`.
Selling the full position deletes the position row. A portfolio snapshot is recorded after each trade.

## GET /api/portfolio/history
`{"snapshots":[{"total_value":10000.0,"recorded_at":"2026-01-01T00:00:00+00:00"}, ...]}` oldest first (max last 1000).
Snapshots are recorded every 30s and after each trade; one is also recorded at startup.

## GET /api/watchlist
`{"watchlist":[{"ticker":"AAPL","price":190.5,"previous_price":190.4,"change":0.1,"change_percent":0.05,"direction":"up","added_at":"..."}]}`
`price` fields are null if no price has arrived yet.

## POST /api/watchlist
Request `{"ticker":"PYPL"}` -> 200 `{"success":true,"ticker":"PYPL","added":true}` (`added:false` if already present). Ticker normalized to upper-case; must match `^[A-Z][A-Z0-9.\-]{0,9}$` else 400.

## DELETE /api/watchlist/{ticker}
200 `{"success":true,"ticker":"PYPL"}`; 404 if not on watchlist. (Ticker keeps streaming if user still holds a position.)

## POST /api/chat
Request: `{"message":"Buy 5 AAPL"}`
Response (always 200 unless body malformed):
```json
{
  "message": "assistant text",
  "trades": [ {"ticker":"AAPL","side":"buy","quantity":5,"success":true,"price":190.5,"error":null} ],
  "watchlist_changes": [ {"ticker":"PYPL","action":"add","success":true,"error":null} ],
  "created_at": "..."
}
```
Failed actions have `success:false` and an `error` string (also appended to the stored assistant message context). Render these inline as confirmations/errors.

Mock mode (`LLM_MOCK=true`) rules, deterministic: message containing "buy <qty> <TICKER>" or "sell <qty> <TICKER>" executes that trade; "add <TICKER>"/"remove <TICKER>" (with "watchlist" or alone) changes watchlist; otherwise returns a canned portfolio summary reply.

## GET /api/chat/history
`{"messages":[{"id","role":"user"|"assistant","content","actions":{"trades":[...],"watchlist_changes":[...]}|null,"created_at"}]}` oldest first, last 50.

## Static files
If `backend/static/` (or `STATIC_DIR` env) exists it's served at `/` (html mode); `/api/*` takes precedence.

## Deployment / environment (confirmed with DevOps)
- Entry point: `uvicorn app.main:app` (module `backend/app/main.py` exposes `app`).
- `DB_PATH` env (default `<project root>/db/finally.db`; in the container where backend lives at `/app` this resolves to `/app/db/finally.db`). Parent dir is created if missing.
- `STATIC_DIR` env (default `<backend dir>/static`, i.e. `/app/static` in the container). Mounted at `/` after the API routes with `html=True` (serves `index.html` for `/`).
- Reads `LLM_MOCK`, `MASSIVE_API_KEY`, `OPENROUTER_API_KEY` from the environment; a `.env` in cwd/backend/project root is also loaded (without overriding real env).
- `/api/portfolio.positions[]` items include `ticker` and `quantity`; `/api/watchlist` returns an object `{"watchlist":[...]}`; oversell/overspend trades return HTTP 400.
