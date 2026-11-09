# FinAlly — AI Trading Workstation

FinAlly (Finance Ally) streams live market data, lets you trade a simulated $10,000 portfolio, and includes an LLM chat assistant that can analyze positions and execute trades from natural language. It aims for a dark, data-dense Bloomberg-terminal look.

Built entirely by coding agents as a capstone project for an agentic AI coding course.

## Status

| Component | State |
|---|---|
| Market data (GBM simulator, Massive client, price cache, SSE router) | Done — `backend/app/market/`, see [planning/MARKET_DATA_SUMMARY.md](planning/MARKET_DATA_SUMMARY.md) |
| Portfolio/watchlist/chat API, database, LLM integration | Planned |
| Frontend, Dockerfile, E2E tests | Planned |

The Docker quick start below is the target workflow and will not work until the remaining components are built.

## Features

- Live prices over SSE with green/red flash animations and sparklines
- Market-order trading, instant fills, no fees
- Portfolio heatmap, P&L chart and positions table
- AI chat that analyzes holdings and auto-executes trades and watchlist changes
- Watchlist of 10 default tickers, editable manually or via chat

## Architecture

One container, one port (8000):

- **Frontend:** Next.js (static export), TypeScript, Tailwind
- **Backend:** FastAPI (Python, managed with `uv`)
- **Database:** SQLite at `db/finally.db`, lazily initialized
- **AI:** LiteLLM → OpenRouter (Cerebras) with structured outputs
- **Market data:** built-in simulator by default, Massive API if a key is set

## Quick Start (target)

```bash
cp .env.example .env      # add OPENROUTER_API_KEY
docker compose up --build # then open http://localhost:8000
docker compose down       # stop; data persists (add -v to wipe)
```

## Environment Variables

| Variable | Description |
|---|---|
| `OPENROUTER_API_KEY` | Needed for AI chat unless `LLM_MOCK=true` |
| `MASSIVE_API_KEY` | Optional; real market data instead of the simulator |
| `LLM_MOCK` | Optional; `true` for deterministic mock LLM responses (tests) |
| `DB_PATH` | Optional; SQLite file path (default `db/finally.db`) |

## Market Data Demo

```bash
cd backend
uv sync
uv run python market_data_demo.py
```

## Project Structure

```
finally/
├── frontend/    # Next.js static export
├── backend/     # FastAPI uv project
├── planning/    # PLAN.md and agent reference docs
├── test/        # Playwright E2E tests
└── db/          # SQLite volume mount (runtime)
```

See [planning/PLAN.md](planning/PLAN.md) for the full specification.

## License

See [LICENSE](LICENSE).
