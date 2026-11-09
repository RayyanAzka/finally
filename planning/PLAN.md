# FinAlly — AI Trading Workstation

## Project Specification

## 1. Vision

FinAlly (Finance Ally) is a visually stunning AI-powered trading workstation that streams live market data, lets users trade a simulated portfolio, and integrates an LLM chat assistant that can analyze positions and execute trades on the user's behalf. It looks and feels like a modern Bloomberg terminal with an AI copilot.

This is the capstone project for an agentic AI coding course. It is built entirely by Coding Agents demonstrating how orchestrated AI agents can produce a production-quality full-stack application. Agents interact through files in `planning/`.

## 2. User Experience

### First Launch

The user runs a single command (`docker compose up --build`) and opens `http://localhost:8000` in a browser. No login, no signup. They immediately see:

- A watchlist of 10 default tickers with live-updating prices in a grid
- $10,000 in virtual cash
- A dark, data-rich trading terminal aesthetic
- An AI chat panel ready to assist

### What the User Can Do

- **Watch prices stream** — prices flash green (uptick) or red (downtick) with subtle CSS animations that fade
- **View sparkline mini-charts** — price action beside each ticker in the watchlist, accumulated on the frontend from the SSE stream since page load (sparklines fill in progressively)
- **Click a ticker** to see a larger detailed chart in the main chart area
- **Buy and sell shares** — market orders only, instant fill at current price, no fees, no confirmation dialog
- **Monitor their portfolio** — a heatmap (treemap) showing positions sized by weight and colored by P&L, plus a P&L chart tracking total portfolio value over time
- **View a positions table** — ticker, quantity, average cost, current price, unrealized P&L, % change
- **Chat with the AI assistant** — ask about their portfolio, get analysis, and have the AI execute trades and manage the watchlist through natural language
- **Manage the watchlist** — add/remove tickers manually or via the AI chat

### Visual Design

- **Dark theme**: backgrounds around `#0d1117` or `#1a1a2e`, muted gray borders, no pure black
- **Price flash animations**: brief green/red background highlight on price change, fading over ~500ms via CSS transitions
- **Connection status indicator**: a small colored dot (green = connected, yellow = reconnecting, red = disconnected) visible in the header
- **Professional, data-dense layout**: inspired by Bloomberg/trading terminals — every pixel earns its place
- **Responsive but desktop-first**: optimized for wide screens, functional on tablet

### Color Scheme
- Accent Yellow: `#ecad0a`
- Blue Primary: `#209dd7`
- Purple Secondary: `#753991` (submit buttons)

## 3. Architecture Overview

### Single Container, Single Port

```
┌─────────────────────────────────────────────────┐
│  Docker Container (port 8000)                   │
│                                                 │
│  FastAPI (Python/uv)                            │
│  ├── /api/*          REST endpoints             │
│  ├── /api/stream/*   SSE streaming              │
│  └── /*              Static file serving         │
│                      (Next.js export)            │
│                                                 │
│  SQLite database (volume-mounted)               │
│  Background task: market data polling/sim        │
└─────────────────────────────────────────────────┘
```

- **Frontend**: Next.js with TypeScript, built as a static export (`output: 'export'`), served by FastAPI as static files — single origin, no CORS, one port, one container
- **Backend**: FastAPI (Python), managed as a `uv` project
- **Database**: SQLite, single file at `db/finally.db`, volume-mounted for persistence — no auth means no multi-user means no database server needed
- **Real-time data**: Server-Sent Events (SSE) — simpler than WebSockets, one-way server→client push, works everywhere
- **AI integration**: LiteLLM → OpenRouter (Cerebras for fast inference), with structured outputs for trade execution
- **Market data**: Environment-variable driven — simulator by default, real data via Massive API if key provided

- **Packaging**: one Docker container, run with `docker compose up --build` (compose is just a thin wrapper around the single service); `uv` for reproducible Python dependencies
- **Orders**: market orders only — no order book, limit orders or partial fills, so portfolio math stays simple

---

## 4. Directory Structure

```
finally/
├── frontend/                 # Next.js TypeScript project (static export)
├── backend/                  # FastAPI uv project (Python)
│   └── db/                   # Schema definitions, seed data, migration logic
├── planning/                 # Project-wide documentation for agents
│   ├── PLAN.md               # This document
│   └── ...                   # Additional agent reference docs
├── test/                     # Playwright E2E tests (run from the host) + docker-compose.test.yml (app with LLM_MOCK=true)
├── db/                       # Volume mount target (SQLite file lives here at runtime)
│   └── .gitkeep              # Directory exists in repo; finally.db is gitignored
├── Dockerfile                # Multi-stage build (Node → Python)
├── docker-compose.yml        # Primary way to build and run (single service, volume, env_file, healthcheck)
├── .env                      # Environment variables (gitignored, .env.example committed)
└── .gitignore
```

### Key Boundaries

- **`frontend/`** is a self-contained Next.js project. It knows nothing about Python. It talks to the backend via `/api/*` endpoints and `/api/stream/*` SSE endpoints. Internal structure is up to the Frontend Engineer agent.
- **`backend/`** is a self-contained uv project with its own `pyproject.toml`. It owns all server logic including database initialization, schema, seed data, API routes, SSE streaming, market data, and LLM integration. Internal structure is up to the Backend/Market Data agents.
- **`backend/db/`** contains schema SQL definitions and seed logic. The backend lazily initializes the database on first request — creating tables and seeding default data if the SQLite file doesn't exist or is empty.
- **`db/`** at the top level is the runtime volume mount point. The SQLite file (`db/finally.db`) is created here by the backend and persists across container restarts via Docker volume.
- **`planning/`** contains project-wide documentation, including this plan. All agents reference files here as the shared contract.
- **`test/`** contains Playwright E2E tests and a small `docker-compose.test.yml` that starts the app with `LLM_MOCK=true`; Playwright itself runs on the host. Unit tests live within `frontend/` and `backend/` respectively, following each framework's conventions.
- **Run commands** are plain Docker Compose (`docker compose up --build`, `docker compose down`); there are no separate start/stop scripts. Document them in the README.

---

## 5. Environment Variables

```bash
# Required for LLM chat unless LLM_MOCK=true: OpenRouter API key
OPENROUTER_API_KEY=your-openrouter-api-key-here

# Optional: Massive (Polygon.io) API key for real market data
# If not set, the built-in market simulator is used (recommended for most users)
MASSIVE_API_KEY=

# Optional: Set to "true" for deterministic mock LLM responses (testing)
LLM_MOCK=false

# Optional: SQLite file path. Default: <project root>/db/finally.db locally; the container sets /app/db/finally.db
DB_PATH=
```

### Behavior

- If `MASSIVE_API_KEY` is set and non-empty → backend uses Massive REST API for market data
- If `MASSIVE_API_KEY` is absent or empty → backend uses the built-in market simulator
- If `LLM_MOCK=true` → backend returns deterministic mock LLM responses (for E2E tests)
- Locally the backend reads `.env` from the project root; in Docker the file is supplied via `env_file` / `--env-file` (never baked into the image)
- If neither `OPENROUTER_API_KEY` nor `LLM_MOCK=true` is set, the app still starts; only `/api/chat` fails, with `503 llm_not_configured`

---

## 6. Market Data

### Two Implementations, One Interface

Both the simulator and the Massive client implement the same abstract interface. The backend selects which to use based on the environment variable. All downstream code (SSE streaming, price cache, frontend) is agnostic to the source.

The market data component is already implemented — see `planning/MARKET_DATA_SUMMARY.md`. The additions in this section (session open price, history buffer, unknown-ticker pricing) must be reconciled with that implementation; do not redesign what exists.

### Simulator (Default)

- Generates prices using geometric Brownian motion (GBM) with configurable drift and volatility per ticker
- Updates at ~500ms intervals
- Correlated moves across tickers (e.g., tech stocks move together)
- Occasional random "events" — sudden 2-5% moves on a ticker for drama
- Starts from realistic seed prices (e.g., AAPL ~$190, GOOGL ~$175, etc.)
- Runs as an in-process background task — no external dependencies
- Any valid ticker can be added. The ten defaults have realistic seed prices; an unknown ticker gets a deterministic seed price derived from a hash of its symbol (range $20–$500) and default volatility, so it behaves the same across restarts
- `session_open` is the price at simulator start (or when the ticker was first added); it is the reference for daily change %

### Massive API (Optional, stretch goal)

Built only after the core app works end to end on the simulator, which satisfies every user-facing requirement. If a ticker is unknown to Massive, adding it is rejected with `400 invalid_ticker`. `session_open` is the previous close.

- REST API polling (not WebSocket) — simpler, works on all tiers
- Polls for the union of all watched tickers on a configurable interval
- Free tier (5 calls/min): poll every 15 seconds
- Paid tiers: poll every 2-15 seconds depending on tier
- Parses REST response into the same format as the simulator

### Shared Price Cache

- A single background task (simulator or Massive poller) writes to an in-memory price cache
- The cache holds the latest price, previous price, `session_open`, and timestamp for each ticker
- The cache also keeps a rolling in-memory history per ticker (last 600 points, about 5 minutes at 500ms). It is lost on restart, which is acceptable
- The set of priced tickers is the union of the watchlist and tickers with open positions, so a held ticker keeps streaming even after it is removed from the watchlist
- SSE streams read from this cache and push updates to connected clients
- This architecture supports future multi-user scenarios without changes to the data layer

### SSE Streaming

- Endpoint: `GET /api/stream/prices`
- Long-lived SSE connection; client uses native `EventSource` API
- Server pushes price updates for every priced ticker (watchlist ∪ held positions) at a regular cadence (~500ms)
- One SSE event per ticker update, `event: price`, with a JSON body:
  `{"ticker":"AAPL","price":191.42,"previous_price":191.30,"session_open":190.00,"change_pct":0.75,"direction":"up","timestamp":"2026-01-01T12:00:00Z"}`
  where `direction` is `up`, `down` or `flat` and `change_pct` is relative to `session_open`
- Client handles reconnection automatically (EventSource has built-in retry)

---

## 7. Database

### SQLite with Lazy Initialization

The backend checks for the SQLite database on startup (or first request). If the file doesn't exist or tables are missing, it creates the schema and seeds default data. This means:

- No separate migration step
- No manual database setup
- Fresh Docker volumes start with a clean, seeded database automatically

### Schema

All tables include a `user_id` column defaulting to `"default"`. This is hardcoded for now (single-user) but enables future multi-user support without schema migration. Backend code references a single `DEFAULT_USER_ID` constant rather than scattering the literal.

**users_profile** — User state (cash balance)
- `id` TEXT PRIMARY KEY (default: `"default"`)
- `cash_balance` REAL (default: `10000.0`)
- `created_at` TEXT (ISO timestamp)

**watchlist** — Tickers the user is watching
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `added_at` TEXT (ISO timestamp)
- PRIMARY KEY `(user_id, ticker)` (no separate UUID id)

**positions** — Current holdings (one row per ticker per user)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `quantity` REAL (fractional shares supported)
- `avg_cost` REAL
- `updated_at` TEXT (ISO timestamp)
- PRIMARY KEY `(user_id, ticker)` (no separate UUID id)

**trades** — Trade history (append-only log)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `side` TEXT (`"buy"` or `"sell"`)
- `quantity` REAL (fractional shares supported)
- `price` REAL
- `executed_at` TEXT (ISO timestamp)

**portfolio_snapshots** — Portfolio value over time (for P&L chart). Recorded immediately after each trade and every 60 seconds by a background task. Rows older than 7 days are pruned hourly.
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `total_value` REAL
- `recorded_at` TEXT (ISO timestamp)

**chat_messages** — Conversation history with LLM
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `role` TEXT (`"user"` or `"assistant"`)
- `content` TEXT
- `actions` TEXT (JSON — trades executed, watchlist changes made; null for user messages)
- `created_at` TEXT (ISO timestamp)

### Money and Position Rules

- **Tickers** are trimmed, uppercased and must match `^[A-Z]{1,5}$`; anything else is `400 invalid_ticker`. This applies to REST and LLM-supplied tickers alike.
- **Quantity** must be > 0, with at most 4 decimal places (minimum 0.0001).
- **Rounding:** `cash_balance` is rounded to 2 decimals after every trade; stored prices keep full precision. Displays round to cents.
- **Buy:** new `avg_cost` is the quantity-weighted average of old cost and fill price. **Sell:** `avg_cost` is unchanged.
- **Selling to zero** deletes the position row.
- **Realized P&L** is out of scope; only unrealized P&L is shown.
- **Total portfolio value** = cash + Σ(quantity × current price). This one definition is used by the header, snapshots and the P&L chart.

### Default Seed Data

- One user profile: `id="default"`, `cash_balance=10000.0`
- Ten watchlist entries: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX

---

## 8. API Endpoints

### Market Data
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stream/prices` | SSE stream of live price updates |
| GET | `/api/prices/{ticker}/history` | Rolling recent prices from the cache (up to 600 points), used to seed sparklines and the main chart on page load |

### Portfolio
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolio` | Current positions, cash balance, total value, unrealized P&L |
| POST | `/api/portfolio/trade` | Execute a trade: `{ticker, quantity, side}` |
| GET | `/api/portfolio/history` | Portfolio value snapshots over time (for P&L chart); optional `?since=<ISO timestamp>` |

### Watchlist
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/watchlist` | Current watchlist tickers only; live prices come from the SSE stream (single source of truth for prices) |
| POST | `/api/watchlist` | Add a ticker: `{ticker}` |
| DELETE | `/api/watchlist/{ticker}` | Remove a ticker |

### Chat
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send a message, receive complete JSON response (message + executed actions) |
| GET | `/api/chat/history` | Last 50 chat messages with their actions; loaded when the page opens |

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (for Docker/deployment) |

### Trade and Error Contract

- `POST /api/portfolio/trade` body: `{"ticker":"AAPL","quantity":10,"side":"buy"}`
- Success `200`: `{"trade":{...},"position":{...}|null,"cash_balance":8095.8,"total_value":10000.0}`
- Failure `400`: `{"error":{"code":"<code>","message":"<human readable>"}}` with `code` one of `invalid_ticker`, `invalid_quantity`, `insufficient_cash`, `insufficient_shares`, `price_unavailable`
- All endpoints use this same `error` shape. Each trade runs in a single SQLite transaction (check, update cash, update position, append to trades, record snapshot) so it is atomic.
- `POST /api/watchlist` normalises and validates the ticker the same way; adding an existing ticker is idempotent (`200`); removing one that isn't present is `404`. Removing a ticker with an open position is allowed.

---

## 9. LLM Integration

When writing code to make calls to LLMs, use cerebras-inference skill to use LiteLLM via OpenRouter to the `openrouter/openai/gpt-oss-120b` model with Cerebras as the inference provider. Structured Outputs should be used to interpret the results.

There is an OPENROUTER_API_KEY in the .env file in the project root.

### How It Works

When the user sends a chat message, the backend:

1. Loads the user's current portfolio context (cash, positions with P&L, watchlist with live prices, total portfolio value)
2. Loads the last 20 messages from the `chat_messages` table (no separate token budget; portfolio context is small)
3. Constructs a prompt with a system message, portfolio context, conversation history, and the user's new message
4. Calls the LLM via LiteLLM → OpenRouter, requesting structured output, using the cerebras-inference skill
5. Parses the complete structured JSON response
6. Auto-executes any trades or watchlist changes specified in the response
7. Stores the message and executed actions in `chat_messages`
8. Returns the complete JSON response to the frontend (no token-by-token streaming — Cerebras inference is fast enough that a loading indicator is sufficient)

### Structured Output Schema

The LLM is instructed to respond with JSON matching this schema:

```json
{
  "message": "Your conversational response to the user",
  "trades": [
    {"ticker": "AAPL", "side": "buy", "quantity": 10}
  ],
  "watchlist_changes": [
    {"ticker": "PYPL", "action": "add"}
  ]
}
```

- `message` (required): The conversational text shown to the user
- `trades` (optional): Array of trades to auto-execute. Each trade goes through the same validation as manual trades (sufficient cash for buys, sufficient shares for sells)
- `watchlist_changes` (optional): Array of watchlist modifications; `action` is `"add"` or `"remove"`

### Auto-Execution

Trades specified by the LLM execute automatically — no confirmation dialog. This is a deliberate design choice:
- It's a simulated environment with fake money, so the stakes are zero
- It creates an impressive, fluid demo experience
- It demonstrates agentic AI capabilities — the core theme of the course

Trades run sequentially in the order given, then watchlist changes. A failed trade does not stop the rest of the batch. There is no second LLM call: the backend appends each validation error (e.g., "Could not buy 10 AAPL: insufficient cash") to the response message and lists it in the `actions` JSON as `{"type":"trade","status":"failed","error":{...}}`, alongside successful actions, so the UI can render both inline.

### System Prompt Guidance

The LLM should be prompted as "FinAlly, an AI trading assistant" with instructions to:
- Analyze portfolio composition, risk concentration, and P&L
- Suggest trades with reasoning
- Execute trades when the user asks or agrees
- Manage the watchlist proactively
- Be concise and data-driven in responses
- Always respond with valid structured JSON

### LLM Mock Mode

When `LLM_MOCK=true`, the backend returns deterministic mock responses instead of calling OpenRouter. This enables:
- Fast, free, reproducible E2E tests
- Development without an API key
- CI/CD pipelines

**Mock rules** (case-insensitive, first match wins):
- `buy <qty> <TICKER>` → trade buy; `sell <qty> <TICKER>` → trade sell (e.g., `buy 1000000 AAPL` deliberately fails for error-path tests)
- `add <TICKER>` / `remove <TICKER>` → watchlist change
- anything else → a fixed portfolio-summary message with no actions

### LLM Failure Handling

- LLM timeout, provider error, or output that fails schema validation → `502 {"error":{"code":"llm_error",...}}`; no retry, nothing stored, and the frontend shows an inline error bubble.
- Missing key with mock mode off → `503 llm_not_configured`.
- Only successful exchanges are stored in `chat_messages`.

---

## 10. Frontend Design

### Layout

The frontend is a single-page application with a dense, terminal-inspired layout. The specific component architecture and layout system is up to the Frontend Engineer, but the UI should include these elements:

- **Watchlist panel** — grid/table of watched tickers with: ticker symbol, current price (flashing green/red on change), daily change %, and a sparkline mini-chart (accumulated from SSE since page load)
- **Main chart area** — larger chart for the currently selected ticker, with at minimum price over time. Clicking a ticker in the watchlist selects it here.
- **Portfolio heatmap** — treemap visualization where each rectangle is a position, sized by portfolio weight, colored by P&L (green = profit, red = loss)
- **P&L chart** — line chart showing total portfolio value over time, using data from `portfolio_snapshots`
- **Positions table** — tabular view of all positions: ticker, quantity, avg cost, current price, unrealized P&L, % change
- **Trade bar** — simple input area: ticker field, quantity field, buy button, sell button. Market orders, instant fill.
- **AI chat panel** — docked/collapsible sidebar. Message input, scrolling conversation history, loading indicator while waiting for LLM response. Trade executions and watchlist changes shown inline as confirmations.
- **Header** — portfolio total value (updating live), connection status indicator, cash balance

### Technical Notes

- Use `EventSource` for SSE connection to `/api/stream/prices`
- Charting: Lightweight Charts (canvas) for all line charts via one reusable `LineChart` component (size/options props) used for the sparklines, main chart and P&L chart; Recharts' `Treemap` for the portfolio heatmap
- Single page only (no routes under the static export)
- On load, seed sparklines and the main chart from `/api/prices/{ticker}/history`, then append from SSE; load chat from `/api/chat/history`
- Clicking a watchlist ticker selects it in the main chart and prefills the trade bar's ticker field
- Local development without Docker: run the backend (`uv run uvicorn ...` on port 8000) and `npm run dev` with a Next.js `rewrites` proxy of `/api/*` to `localhost:8000`. If SSE is buffered by the dev proxy, use `npm run build` and let FastAPI serve the export instead
- Price flash effect: on receiving a new price, briefly apply a CSS class with background color transition, then remove it
- All API calls go to the same origin (`/api/*`) — no CORS configuration needed
- Tailwind CSS for styling with a custom dark theme

---

## 11. Docker & Deployment

### Multi-Stage Dockerfile

```
Stage 1: Node 20 slim
  - Copy frontend/
  - npm install && npm run build (produces static export)

Stage 2: Python 3.12 slim
  - Install uv
  - Copy backend/
  - uv sync (install Python dependencies from lockfile)
  - Copy frontend build output into a static/ directory
  - Expose port 8000
  - HEALTHCHECK: `GET /api/health`
  - CMD: uvicorn serving FastAPI app
```

FastAPI serves the static frontend files and all API routes on port 8000.

### Docker Volume

The SQLite database persists via a named Docker volume:

```bash
docker run -v finally-data:/app/db -p 8000:8000 --env-file .env finally
```

The `db/` directory in the project root maps to `/app/db` in the container. The backend resolves the database path from `DB_PATH` (container sets `/app/db/finally.db`; default locally is `db/finally.db`).

### Run Commands (Docker Compose)

`docker-compose.yml` defines the single `finally` service: builds the image, maps port 8000, mounts the `finally-data` volume at `/app/db`, loads `.env` via `env_file`, and uses the `/api/health` healthcheck.

- Start: `docker compose up --build` (add `-d --wait` to run in the background and wait until healthy)
- Stop: `docker compose down` — does NOT remove the volume, so data persists (`docker compose down -v` wipes it)
- Both commands are idempotent and identical on macOS, Linux and Windows, so no OS-specific scripts are needed.

### Optional Cloud Deployment

The container is designed to deploy to AWS App Runner, Render, or any container platform. **Warning:** the app has no authentication and `.env` holds an LLM API key; a public deployment exposes unauthenticated trading and chat calls that spend that key. Treat the core build as local-use only. A Terraform configuration for App Runner may be provided in a `deploy/` directory as a stretch goal, but is not part of the core build.

---

## 12. Testing Strategy

### Unit Tests (within `frontend/` and `backend/`)

**Backend (pytest)**:
- Market data: simulator generates valid prices, GBM math is correct, Massive API response parsing works, both implementations conform to the abstract interface
- Portfolio: trade execution logic, P&L calculations, edge cases (selling more than owned, buying with insufficient cash, selling at a loss)
- LLM: structured output parsing handles all valid schemas, graceful handling of malformed responses, trade validation within chat flow
- API routes: correct status codes, response shapes, error handling

**Frontend (React Testing Library or similar)**:
- Component rendering with mock data
- Price flash animation triggers correctly on price changes
- Watchlist CRUD operations
- Portfolio display calculations
- Chat message rendering and loading state

### E2E Tests (in `test/`)

**Infrastructure**: `test/docker-compose.test.yml` starts the app container with `LLM_MOCK=true` and a fresh volume; Playwright runs on the host (`baseURL=http://localhost:8000`). This keeps browser dependencies out of the production image without a second container.

**Environment**: Tests run with `LLM_MOCK=true` by default for speed and determinism.

**Key Scenarios**:
- Fresh start: default watchlist appears, $10k balance shown, prices are streaming
- Add and remove a ticker from the watchlist
- Buy shares: cash decreases, position appears, portfolio updates
- Sell shares: cash increases, position updates or disappears
- Portfolio visualization: heatmap renders with correct colors, P&L chart has data points
- AI chat (mocked): send a message, receive a response, trade execution appears inline
- SSE resilience: set the browser context offline, then back online, and verify the status dot goes yellow/red then green and prices resume (the in-memory price cache is not affected)

---

## 13. Review Decisions

Outcome of the document review. Each decision has been applied to the section named in brackets; this list is a record, not a second source of truth.

**Kept as originally specified (owner decision):** `user_id` columns on all tables (accessed through one `DEFAULT_USER_ID` constant) [7].

**Accepted simplifications, now applied:**
- `watchlist` and `positions` use `(user_id, ticker)` as primary key, no UUID ids [7]
- Snapshots on each trade plus every 60s, 7-day retention [7]
- No second LLM call for failed trades; errors appended server-side [9]
- `GET /api/watchlist` returns tickers only; prices come only from SSE [8]
- One reusable `LineChart` component for sparkline, main and P&L charts [10]
- Playwright runs on the host; no Playwright container [12]
- Massive client is a stretch goal [6]
- No start/stop scripts; `docker compose up --build` / `down` [4, 11]
- "Why These Choices" table folded into the architecture bullets [3]

**Questions resolved:**

| Topic | Decision | Section |
|---|---|---|
| Unknown tickers in simulator / Massive | Hash-derived seed price; Massive rejects unknown with `invalid_ticker` | 6 |
| Ticker validation and case | Trim, uppercase, `^[A-Z]{1,5}$`, same for LLM | 7 |
| Daily change % | Relative to `session_open` (sim start / previous close) | 6 |
| Removing a held ticker | Allowed; priced set is watchlist ∪ positions | 6, 8 |
| SSE payload | One `price` event per ticker, JSON example given | 6 |
| Quantity, rounding, avg cost, sell to zero, realized P&L | 4 decimals; cash to cents; weighted avg on buy; row deleted at zero; realized P&L out of scope | 7 |
| Trade API contract, atomicity, batch order | Documented success/error shapes and codes; one transaction per trade; sequential, failures don't stop the batch | 8, 9 |
| Mock LLM behaviour | Regex rules for buy/sell/add/remove, else fixed summary | 9 |
| History window, LLM failures, missing key | Last 20 messages; `502 llm_error` / `503 llm_not_configured`, failures not stored | 5, 9 |
| Chat history on refresh | `GET /api/chat/history` | 8, 10 |
| Charting libraries | Lightweight Charts for lines, Recharts Treemap for heatmap | 10 |
| Empty main chart on load | Rolling 600-point history buffer + `/api/prices/{ticker}/history` | 6, 8, 10 |
| Trade bar prefill, routing | Click prefills ticker; single page | 10 |
| DB path, `.env`, Windows dev, healthcheck | `DB_PATH`; `env_file`; Next dev proxy; Docker HEALTHCHECK | 5, 10, 11 |
| Security note | Local use only warning on cloud deployment | 11 |
| SSE resilience test method | Playwright offline/online toggle | 12 |

**Open follow-ups:**
- Verify `planning/MARKET_DATA_SUMMARY.md` against the new market-data additions (`session_open`, 600-point history buffer, hash-derived seed prices, per-ticker `price` SSE event shape). Adjust either the code or this plan if the built component differs.
