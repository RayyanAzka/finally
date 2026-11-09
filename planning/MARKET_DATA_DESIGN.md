# Market Data Backend — Design

Design and reference implementation for the FinAlly market data subsystem: the unified interface, shared price cache, GBM simulator, Massive (Polygon.io) client, SSE endpoint, and how the rest of the backend consumes them.

All code lives in `backend/app/market/`. The snippets in §2–§9 mirror the code that is already built and tested (73 tests). §10 onward covers integration with the not-yet-built parts of the platform, and §11 lists gaps between the code and `PLAN.md` that downstream work should close.

Older, narrower design notes are in `planning/archive/`; this document supersedes them.

---

## 1. Architecture

```
                 MarketDataSource (ABC)
                 ├── SimulatorDataSource   default, no API key
                 └── MassiveDataSource     when MASSIVE_API_KEY is set
                            │  writes
                            ▼
                      PriceCache  (thread-safe, in-memory, latest price per ticker)
                            │  reads
        ┌───────────────────┼─────────────────────┐
        ▼                   ▼                     ▼
  SSE /api/stream/prices   Portfolio valuation   Trade execution
```

Principles:

- **Push into a cache, read from the cache.** Sources never return prices to callers. The simulator ticks at 500 ms, Massive polls at 15 s, and SSE reads at 500 ms regardless. Consumers do not know which source is active.
- **One writer at a time.** Exactly one `MarketDataSource` exists per process, chosen at startup by environment variable.
- **`PriceUpdate` is the only type that leaves this package.**
- **Resilience over strictness.** A failed tick or poll is logged and retried; the cache keeps the last known price.

### File layout

```
backend/app/market/
  __init__.py        # re-exports PriceUpdate, PriceCache, MarketDataSource,
                     #   create_market_data_source, create_stream_router
  models.py          # PriceUpdate (frozen dataclass)
  cache.py           # PriceCache
  interface.py       # MarketDataSource ABC
  seed_prices.py     # seed prices, GBM params, correlation constants
  simulator.py       # GBMSimulator (math) + SimulatorDataSource (async wrapper)
  massive_client.py  # MassiveDataSource
  factory.py         # create_market_data_source()
  stream.py          # SSE router
```

Dependencies (`backend/pyproject.toml`): `fastapi`, `uvicorn[standard]`, `numpy`, `massive`. `massive` is a core dependency, imported at module top-level in `massive_client.py`.

---

## 2. Data model — `models.py`

```python
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """Immutable snapshot of a single ticker's price at a point in time."""

    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)  # Unix seconds

    @property
    def change(self) -> float:
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def direction(self) -> str:  # "up" | "down" | "flat"
        if self.price > self.previous_price:
            return "up"
        if self.price < self.previous_price:
            return "down"
        return "flat"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "timestamp": self.timestamp,
            "change": self.change,
            "change_percent": self.change_percent,
            "direction": self.direction,
        }
```

Notes:

- `change`, `change_percent` and `direction` are derived properties, so they can never disagree with `price`/`previous_price`.
- **`previous_price` means "the price before this update"** — it drives the green/red flash animation. It is *not* the previous day's close. See §11.1 for the daily-change gap.
- `to_dict()` is the single serialization point for SSE and REST.

---

## 3. Price cache — `cache.py`

```python
from __future__ import annotations

import time
from threading import Lock

from .models import PriceUpdate


class PriceCache:
    """Thread-safe in-memory cache of the latest price for each ticker."""

    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._lock = Lock()
        self._version: int = 0  # bumped on every update; used for SSE change detection

    def update(self, ticker: str, price: float, timestamp: float | None = None) -> PriceUpdate:
        with self._lock:
            ts = timestamp or time.time()
            prev = self._prices.get(ticker)
            previous_price = prev.price if prev else price   # first update → flat
            update = PriceUpdate(
                ticker=ticker,
                price=round(price, 2),
                previous_price=round(previous_price, 2),
                timestamp=ts,
            )
            self._prices[ticker] = update
            self._version += 1
            return update

    def get(self, ticker: str) -> PriceUpdate | None:
        with self._lock:
            return self._prices.get(ticker)

    def get_all(self) -> dict[str, PriceUpdate]:
        with self._lock:
            return dict(self._prices)          # shallow copy; PriceUpdate is immutable

    def get_price(self, ticker: str) -> float | None:
        update = self.get(ticker)
        return update.price if update else None

    def remove(self, ticker: str) -> None:
        with self._lock:
            self._prices.pop(ticker, None)

    @property
    def version(self) -> int:
        return self._version

    def __len__(self) -> int:
        with self._lock:
            return len(self._prices)

    def __contains__(self, ticker: str) -> bool:
        with self._lock:
            return ticker in self._prices
```

Why `threading.Lock` and not `asyncio.Lock`: the Massive client is synchronous and is run via `asyncio.to_thread`, so writes may come from a real OS thread. A `threading.Lock` is correct from both threads and the event loop; the critical sections are a dict lookup and assignment, so contention is negligible.

Why a `version` counter: Massive only produces new data every ~15 s. SSE ticks every 500 ms; comparing `version` lets it skip re-serializing identical payloads. (Reading `_version` without the lock is safe on CPython; take the lock if moving to a free-threaded build.)

Prices are rounded to 2 decimals on write, so every consumer sees the same value the user sees in the UI — important for trade fills.

---

## 4. Unified interface — `interface.py`

```python
from __future__ import annotations

from abc import ABC, abstractmethod


class MarketDataSource(ABC):
    @abstractmethod
    async def start(self, tickers: list[str]) -> None:
        """Begin producing updates. Call exactly once."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop background work. Safe to call repeatedly."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Track a ticker. No-op if already tracked."""

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Stop tracking a ticker and evict it from the cache. No-op if absent."""

    @abstractmethod
    def get_tickers(self) -> list[str]:
        """Currently tracked tickers."""
```

Contract every implementation must honour:

| Method | Guarantee |
|---|---|
| `start` | Cache has a price for each ticker the source can price **before** `start` returns, so the first SSE frame is never empty. |
| `stop` | Cancels and awaits the background task; idempotent; no cache writes afterwards. |
| `add_ticker` | Normalizes nothing the caller must not already have normalized (see §10: callers uppercase and validate). |
| `remove_ticker` | Removes from both the tracked set and the cache. |
| background task | Never dies from an exception in one cycle. |

### Factory — `factory.py`

```python
import logging
import os

from .cache import PriceCache
from .interface import MarketDataSource
from .massive_client import MassiveDataSource
from .simulator import SimulatorDataSource

logger = logging.getLogger(__name__)


def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    """MASSIVE_API_KEY set and non-empty → Massive; otherwise → simulator.
    Returns an unstarted source; caller must `await source.start(tickers)`."""
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        logger.info("Market data source: Massive API (real data)")
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)
    logger.info("Market data source: GBM Simulator")
    return SimulatorDataSource(price_cache=price_cache)
```

Whitespace-only keys count as unset — a common `.env` mistake (`MASSIVE_API_KEY= `).

---

## 5. Simulator

### 5.1 Constants — `seed_prices.py`

```python
SEED_PRICES: dict[str, float] = {
    "AAPL": 190.00, "GOOGL": 175.00, "MSFT": 420.00, "AMZN": 185.00, "TSLA": 250.00,
    "NVDA": 800.00, "META": 500.00, "JPM": 195.00,   "V": 280.00,    "NFLX": 600.00,
}

# sigma = annualized volatility, mu = annualized drift
TICKER_PARAMS: dict[str, dict[str, float]] = {
    "AAPL":  {"sigma": 0.22, "mu": 0.05},
    "GOOGL": {"sigma": 0.25, "mu": 0.05},
    "MSFT":  {"sigma": 0.20, "mu": 0.05},
    "AMZN":  {"sigma": 0.28, "mu": 0.05},
    "TSLA":  {"sigma": 0.50, "mu": 0.03},   # high vol
    "NVDA":  {"sigma": 0.40, "mu": 0.08},   # high vol, strong drift
    "META":  {"sigma": 0.30, "mu": 0.05},
    "JPM":   {"sigma": 0.18, "mu": 0.04},
    "V":     {"sigma": 0.17, "mu": 0.04},
    "NFLX":  {"sigma": 0.35, "mu": 0.05},
}
DEFAULT_PARAMS = {"sigma": 0.25, "mu": 0.05}          # tickers added at runtime

CORRELATION_GROUPS = {
    "tech":    {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"},
    "finance": {"JPM", "V"},
}
INTRA_TECH_CORR = 0.6
INTRA_FINANCE_CORR = 0.5
CROSS_GROUP_CORR = 0.3     # cross-sector and unknown tickers
TSLA_CORR = 0.3            # TSLA is in no group; moves mostly on its own
```

Unknown tickers (e.g. `PYPL`) start at `random.uniform(50, 300)` with `DEFAULT_PARAMS`.

### 5.2 The math

Geometric Brownian Motion, one step:

```
S(t+dt) = S(t) · exp( (mu − σ²/2)·dt + σ·√dt·Z )
```

- `dt = 0.5 / (252 · 6.5 · 3600) ≈ 8.48e-8` (one 500 ms tick as a fraction of a trading year).
- `Z` is a *correlated* standard normal: draw `n` independent normals `z`, then `Z = L @ z`, where `L = cholesky(C)` and `C` is the correlation matrix built from the groups above.
- `exp(...)` is always positive, so prices cannot go negative.
- **Shock events:** per ticker per tick, probability `0.001` of an extra ±2–5% jump. With 10 tickers at 2 ticks/s that is one visible move roughly every 50 s.

Sanity check of magnitude: for TSLA (σ = 0.5), per-tick σ·√dt ≈ 0.5 · 2.9e-4 ≈ 1.5e-4, i.e. about 4 cents on a $250 stock. Visible flicker, no wild swings; shocks provide the drama.

### 5.3 `GBMSimulator` — pure, synchronous, no I/O

```python
class GBMSimulator:
    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR

    def __init__(self, tickers, dt=DEFAULT_DT, event_probability=0.001):
        self._dt = dt
        self._event_prob = event_probability
        self._tickers: list[str] = []
        self._prices: dict[str, float] = {}
        self._params: dict[str, dict[str, float]] = {}
        self._cholesky: np.ndarray | None = None
        for t in tickers:
            self._add_ticker_internal(t)
        self._rebuild_cholesky()

    def step(self) -> dict[str, float]:
        n = len(self._tickers)
        if n == 0:
            return {}
        z = np.random.standard_normal(n)
        if self._cholesky is not None:
            z = self._cholesky @ z

        out: dict[str, float] = {}
        for i, t in enumerate(self._tickers):
            mu, sigma = self._params[t]["mu"], self._params[t]["sigma"]
            drift = (mu - 0.5 * sigma**2) * self._dt
            diffusion = sigma * math.sqrt(self._dt) * z[i]
            self._prices[t] *= math.exp(drift + diffusion)

            if random.random() < self._event_prob:                       # shock
                self._prices[t] *= 1 + random.uniform(0.02, 0.05) * random.choice([-1, 1])

            out[t] = round(self._prices[t], 2)
        return out

    def add_ticker(self, ticker):    # no-op if present; rebuilds Cholesky
        if ticker in self._prices:
            return
        self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    def remove_ticker(self, ticker): # no-op if absent; rebuilds Cholesky
        if ticker not in self._prices:
            return
        self._tickers.remove(ticker)
        del self._prices[ticker], self._params[ticker]
        self._rebuild_cholesky()

    def get_price(self, ticker) -> float | None: return self._prices.get(ticker)
    def get_tickers(self) -> list[str]:          return list(self._tickers)

    def _add_ticker_internal(self, ticker):      # batch-friendly: no Cholesky rebuild
        if ticker in self._prices:
            return
        self._tickers.append(ticker)
        self._prices[ticker] = SEED_PRICES.get(ticker, random.uniform(50.0, 300.0))
        self._params[ticker] = TICKER_PARAMS.get(ticker, dict(DEFAULT_PARAMS))

    def _rebuild_cholesky(self):
        n = len(self._tickers)
        if n <= 1:
            self._cholesky = None
            return
        corr = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                corr[i, j] = corr[j, i] = self._pairwise_correlation(
                    self._tickers[i], self._tickers[j])
        self._cholesky = np.linalg.cholesky(corr)

    @staticmethod
    def _pairwise_correlation(t1, t2) -> float:
        if t1 == "TSLA" or t2 == "TSLA":
            return TSLA_CORR
        tech, fin = CORRELATION_GROUPS["tech"], CORRELATION_GROUPS["finance"]
        if t1 in tech and t2 in tech:
            return INTRA_TECH_CORR
        if t1 in fin and t2 in fin:
            return INTRA_FINANCE_CORR
        return CROSS_GROUP_CORR
```

Every correlation used (0.3 / 0.5 / 0.6) is ≤ 0.6 with unit diagonal, so the matrix is positive definite for any mix of tickers and `cholesky` cannot fail. (If the constants are ever changed, keep all off-diagonals well below 1 and re-run the 10-ticker test in §12.)

### 5.4 `SimulatorDataSource` — async wrapper

```python
class SimulatorDataSource(MarketDataSource):
    def __init__(self, price_cache, update_interval=0.5, event_probability=0.001):
        self._cache = price_cache
        self._interval = update_interval
        self._event_prob = event_probability
        self._sim: GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers):
        self._sim = GBMSimulator(tickers=tickers, event_probability=self._event_prob)
        for t in tickers:                                    # seed so SSE has data immediately
            p = self._sim.get_price(t)
            if p is not None:
                self._cache.update(ticker=t, price=p)
        self._task = asyncio.create_task(self._run_loop(), name="simulator-loop")

    async def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def add_ticker(self, ticker):
        if self._sim:
            self._sim.add_ticker(ticker)
            p = self._sim.get_price(ticker)                  # price available instantly
            if p is not None:
                self._cache.update(ticker=ticker, price=p)

    async def remove_ticker(self, ticker):
        if self._sim:
            self._sim.remove_ticker(ticker)
        self._cache.remove(ticker)

    def get_tickers(self):
        return self._sim.get_tickers() if self._sim else []

    async def _run_loop(self):
        while True:
            try:
                if self._sim:
                    for t, p in self._sim.step().items():
                        self._cache.update(ticker=t, price=p)
            except Exception:
                logger.exception("Simulator step failed")    # never kill the feed
            await asyncio.sleep(self._interval)
```

`step()` for ~10–50 tickers takes microseconds, so it runs inline on the event loop — no thread needed.

### 5.5 Example

```python
cache = PriceCache()
src = SimulatorDataSource(cache, update_interval=0.5)
await src.start(["AAPL", "TSLA"])
print(cache.get("AAPL"))
# PriceUpdate(ticker='AAPL', price=190.0, previous_price=190.0, timestamp=...)
await asyncio.sleep(2)
print(cache.get("AAPL").to_dict())
# {'ticker': 'AAPL', 'price': 190.04, 'previous_price': 190.03, 'change': 0.01,
#  'change_percent': 0.0053, 'direction': 'up', 'timestamp': 1.7e9}
await src.stop()
```

---

## 6. Massive API client — `massive_client.py`

### 6.1 API facts

- Package `massive` (formerly Polygon.io). `RESTClient(api_key=...)` — synchronous.
- Base URL `https://api.massive.com`; the client sets the `Authorization: Bearer` header.
- **Endpoint used:** snapshot for many tickers in **one** call — `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT,…`, via `client.get_snapshot_all(market_type=SnapshotMarketType.STOCKS, tickers=[...])`. One call per poll is what keeps the free tier (5 req/min) viable.
- Fields used per snapshot: `ticker`, `last_trade.price`, `last_trade.timestamp` (Unix **milliseconds**). Also available: `day.previous_close`, `day.change_percent`, `day.open/high/low/close/volume` (see §11.1).
- Errors raised by the client: 401 bad key, 403 plan lacks endpoint, 429 rate limit, 5xx (client retries 3×).
- Outside market hours `last_trade.price` is the last trade (possibly after-hours), so prices are static; that is expected.

### 6.2 Poll interval

| Tier | `poll_interval` |
|---|---|
| Free (5 req/min) | 15 s (default; leaves headroom) |
| Paid | 2–5 s |

Expose it via an optional env var `MASSIVE_POLL_INTERVAL` (see §11.4); the factory currently uses the default.

### 6.3 Implementation

```python
from massive import RESTClient
from massive.rest.models import SnapshotMarketType


class MassiveDataSource(MarketDataSource):
    def __init__(self, api_key: str, price_cache: PriceCache, poll_interval: float = 15.0):
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None
        self._client: RESTClient | None = None

    async def start(self, tickers):
        self._client = RESTClient(api_key=self._api_key)
        self._tickers = list(tickers)
        await self._poll_once()                              # prime the cache before returning
        self._task = asyncio.create_task(self._poll_loop(), name="massive-poller")

    async def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._client = None

    async def add_ticker(self, ticker):
        ticker = ticker.upper().strip()
        if ticker not in self._tickers:
            self._tickers.append(ticker)                     # priced on the next poll

    async def remove_ticker(self, ticker):
        ticker = ticker.upper().strip()
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)

    def get_tickers(self):
        return list(self._tickers)

    async def _poll_loop(self):
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_once()

    async def _poll_once(self):
        if not self._tickers or not self._client:
            return
        try:
            snapshots = await asyncio.to_thread(self._fetch_snapshots)   # sync client → thread
            for snap in snapshots:
                try:
                    self._cache.update(
                        ticker=snap.ticker,
                        price=snap.last_trade.price,
                        timestamp=snap.last_trade.timestamp / 1000.0,    # ms → s
                    )
                except (AttributeError, TypeError) as e:
                    logger.warning("Skipping snapshot for %s: %s", getattr(snap, "ticker", "???"), e)
        except Exception as e:
            logger.error("Massive poll failed: %s", e)       # retry next interval

    def _fetch_snapshots(self) -> list:
        return self._client.get_snapshot_all(
            market_type=SnapshotMarketType.STOCKS, tickers=self._tickers)
```

### 6.4 Failure behaviour

| Failure | Behaviour |
|---|---|
| 401 / 403 | Logged each interval; cache stays empty (or stale). Fix `.env`, restart. |
| 429 | Logged; next poll after `poll_interval` retries. |
| Network error / 5xx | Logged; retried next interval. |
| One malformed snapshot | That ticker skipped with a warning; others processed. |
| Ticker unknown to Massive | Absent from the response → never gets a cache entry (see §10.3). |
| Whole poll fails | Cache keeps last-known prices; SSE keeps streaming them. |

Known limitations: `add_ticker` mutates `self._tickers` while a poll thread may be iterating the same list in `_fetch_snapshots`. In practice `get_snapshot_all` receives the list reference once at call time, but to be safe pass a copy: `tickers=list(self._tickers)`.

---

## 7. SSE endpoint — `stream.py`

```python
router = APIRouter(prefix="/api/stream", tags=["streaming"])


def create_stream_router(price_cache: PriceCache) -> APIRouter:
    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _generate_events(price_cache, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    return router


async def _generate_events(price_cache, request, interval=0.5) -> AsyncGenerator[str, None]:
    yield "retry: 1000\n\n"                                   # browser reconnect delay: 1 s
    last_version = -1
    try:
        while True:
            if await request.is_disconnected():
                break
            if price_cache.version != last_version:
                last_version = price_cache.version
                prices = price_cache.get_all()
                if prices:
                    yield f"data: {json.dumps({t: u.to_dict() for t, u in prices.items()})}\n\n"
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass
```

Wire format — one event, **all tickers in a single JSON object keyed by ticker**:

```
retry: 1000

data: {"AAPL":{"ticker":"AAPL","price":190.5,"previous_price":190.42,"timestamp":1707580800.5,"change":0.08,"change_percent":0.0420,"direction":"up"},"GOOGL":{...}}

```

Frontend consumption:

```ts
const es = new EventSource("/api/stream/prices");
es.onopen = () => setStatus("connected");
es.onerror = () => setStatus("reconnecting");       // EventSource retries automatically
es.onmessage = (e) => {
  const prices: Record<string, PriceUpdate> = JSON.parse(e.data);
  for (const p of Object.values(prices)) {
    flash(p.ticker, p.direction);                   // green/red class, fade ~500 ms
    pushSparklinePoint(p.ticker, p.price);          // accumulate client-side
  }
};
```

Behaviour notes:

- Because of version-based change detection, with Massive the client receives a frame only when a poll updated something (~every 15 s); with the simulator, roughly every 500 ms. The frontend must not assume a fixed cadence.
- `create_stream_router` registers onto a module-level `router`; call it once per process. In tests that build several apps, construct a fresh `APIRouter` inside the factory instead (one-line fix; see review item 3.6 in `archive/MARKET_DATA_REVIEW.md`).

---

## 8. Application lifecycle

`backend/app/main.py` (to be written with the rest of the backend). Create the cache and source in `lifespan`; register routers at app-construction time, not inside lifespan.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = PriceCache()
    source = create_market_data_source(cache)
    app.state.price_cache = cache
    app.state.market_source = source

    tickers = set(db.get_watchlist_tickers())
    tickers |= {p.ticker for p in db.get_positions()}       # held tickers must always be priced
    await source.start(sorted(tickers))

    yield

    await source.stop()


app = FastAPI(title="FinAlly", lifespan=lifespan)
```

Routers that need the cache before `lifespan` has run (SSE) should read it lazily from `app.state` rather than receive it at construction. The current `create_stream_router(price_cache)` takes the cache eagerly; two clean options:

```python
# Option A (simple): construct the cache at import time, share it with lifespan
price_cache = PriceCache()
app = FastAPI(lifespan=lifespan)
app.include_router(create_stream_router(price_cache))

# Option B: make the endpoint read request.app.state.price_cache
```

Option A is recommended — `PriceCache` has no startup cost, and `lifespan` simply uses the module-level instance.

Dependencies for other routes:

```python
def get_price_cache(request: Request) -> PriceCache:    return request.app.state.price_cache
def get_market_source(request: Request) -> MarketDataSource: return request.app.state.market_source
```

---

## 9. Usage by other backend modules

### 9.1 Trade execution (`POST /api/portfolio/trade`, and LLM auto-trades)

```python
price = cache.get_price(ticker)
if price is None:
    raise HTTPException(400, f"Price not yet available for {ticker}. Try again shortly.")
# fill at `price`; no fees; market orders only
```

Use `get_price` at the instant of execution so the fill matches the displayed price.

### 9.2 Portfolio valuation (`GET /api/portfolio`, snapshots every 30 s)

```python
def total_value(cash: float, positions, cache: PriceCache) -> float:
    value = cash
    for p in positions:
        price = cache.get_price(p.ticker) or p.avg_cost     # fall back if no price yet
        value += p.quantity * price
    return value
```

### 9.3 Watchlist (`POST/DELETE /api/watchlist`)

```python
@router.post("/watchlist")
async def add(payload: WatchlistAdd, source=Depends(get_market_source), cache=Depends(get_price_cache)):
    ticker = payload.ticker.upper().strip()
    # validate format first: ^[A-Z]{1,5}$ (see §10.3)
    db.insert_watchlist(ticker)
    await source.add_ticker(ticker)
    return {"ticker": ticker, "price": cache.get_price(ticker)}   # None for Massive until next poll


@router.delete("/watchlist/{ticker}")
async def remove(ticker: str, source=Depends(get_market_source)):
    ticker = ticker.upper().strip()
    db.delete_watchlist(ticker)
    position = db.get_position(ticker)
    if position is None or position.quantity == 0:           # keep pricing held tickers
        await source.remove_ticker(ticker)
    return {"status": "ok"}
```

### 9.4 `GET /api/watchlist` response

Merge DB rows with the cache:

```json
[{"ticker": "AAPL", "price": 190.5, "previous_price": 190.42,
  "change_percent": 0.042, "direction": "up"}, ...]
```

---

## 10. Edge cases

### 10.1 Empty watchlist
`start([])` is valid for both sources: the simulator yields nothing, Massive skips the API call. SSE sends no `data:` frames until something is tracked.

### 10.2 Ticker with a position removed from the watchlist
Keep it in the source (§9.3), otherwise valuation silently falls back to `avg_cost`. Only a position of quantity 0 (row removed on full sell) allows `remove_ticker`. Conversely, when the position is later fully sold and the ticker is no longer on the watchlist, call `source.remove_ticker` then.

### 10.3 Invalid / unknown tickers
- **Simulator** accepts anything and invents a price in $50–$300. Validate format (`^[A-Z]{1,5}$`) at the API layer so `add_ticker("asdf!!")` is rejected with 400.
- **Massive** silently returns no snapshot for unknown symbols; the ticker would sit in the watchlist with no price. After adding, the watchlist route may wait for one poll or return `price: null`, and the UI should render `—`. Optionally, check `get_snapshot_ticker` once at add time to reject unknown symbols.

### 10.4 Source switching
`MASSIVE_API_KEY` is read once at startup. Switching sources requires a restart. The cache is in-memory only and starts empty each run; the simulator's price paths also restart from seed prices (no persistence by design).

### 10.5 Simulator mid-session add
New ticker gets an immediate cache entry (flat direction), then ticks from the next loop. The Cholesky matrix rebuild is O(n²), trivial for n < 50.

### 10.6 Shutdown
`stop()` is awaited in lifespan teardown. SSE generators exit via `is_disconnected()` or `CancelledError`.

---

## 11. Gaps vs. PLAN.md (work for downstream agents)

### 11.1 "Daily change %" in the watchlist
`PLAN.md` §10 lists *daily change %*. `PriceUpdate.change_percent` is currently **tick-to-tick**, not vs. the previous close. Proposed additive change that keeps the interface intact:

```python
# models.py
@dataclass(frozen=True, slots=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)
    session_open: float | None = None        # reference price for daily change

    @property
    def day_change_percent(self) -> float:
        ref = self.session_open or self.previous_price
        return round((self.price - ref) / ref * 100, 4) if ref else 0.0
```

- `PriceCache.update(..., session_open=None)`: keep the first-ever `session_open` per ticker (`prev.session_open if prev else (session_open or price)`), so a caller-provided value wins only on the first write.
- Simulator: `session_open` = seed price (the price at process start).
- Massive: pass `snap.day.previous_close` (or `snap.prev_daily_bar.close`), re-reading it each poll since it changes at the session boundary — in that case let the supplied value override.
- Add `day_change_percent` to `to_dict()` (frontend watchlist uses it; the flash still uses `direction`).

Alternative with zero backend change: the frontend computes daily change from the first price it saw after page load. Simpler, but resets on reload and is not a true daily change.

### 11.2 Prices in the cache vs. fractional rounding
`PriceCache` rounds to 2 decimals. Fine for display and fills; for fractional-share P&L the portfolio code should do its arithmetic from these rounded prices consistently, and round only at presentation.

### 11.3 Test gaps (from review)
SSE endpoint has no tests; no concurrency test for `PriceCache`; no 10-ticker Cholesky test (§12).

### 11.4 Configuration
Not yet configurable via environment: Massive poll interval and simulator interval. Optional additions in `factory.py`:

```python
poll = float(os.environ.get("MASSIVE_POLL_INTERVAL", "15"))
return MassiveDataSource(api_key=api_key, price_cache=price_cache, poll_interval=poll)
```

---

## 12. Testing

Existing suite (`backend/tests/market/`, pytest + pytest-asyncio with `asyncio_mode = "auto"`): `test_models`, `test_cache`, `test_simulator`, `test_simulator_source`, `test_factory`, `test_massive`. Run:

```bash
cd backend && uv run --extra dev pytest --cov=app
```

Representative tests, including the recommended additions.

**Simulator math and invariants**

```python
def test_prices_positive():
    sim = GBMSimulator(["AAPL"])
    assert all(sim.step()["AAPL"] > 0 for _ in range(10_000))

def test_full_default_set_builds_cholesky():
    sim = GBMSimulator(list(SEED_PRICES))                    # 10 tickers
    assert sim._cholesky is not None and sim._cholesky.shape == (10, 10)
    assert set(sim.step()) == set(SEED_PRICES)

def test_correlation_is_realized():
    np.random.seed(0)
    sim = GBMSimulator(["AAPL", "MSFT"], event_probability=0)
    a, b = [], []
    prev = {"AAPL": 190.0, "MSFT": 420.0}
    for _ in range(5000):
        cur = sim.step()
        a.append(math.log(cur["AAPL"] / prev["AAPL"]))
        b.append(math.log(cur["MSFT"] / prev["MSFT"]))
        prev = cur
    assert 0.4 < np.corrcoef(a, b)[0, 1] < 0.8               # target 0.6
```
(The correlation test is statistical; 2-decimal rounding adds noise, so keep the wide band and the fixed seed. If flaky, test on `sim._prices` directly instead of rounded output.)

**Massive parsing (no network, no key)**

```python
def _snap(ticker, price, ts_ms):
    s = MagicMock(); s.ticker = ticker
    s.last_trade.price = price; s.last_trade.timestamp = ts_ms
    return s

async def test_poll_updates_cache_and_converts_ms():
    cache = PriceCache()
    src = MassiveDataSource("k", cache, poll_interval=60)
    src._client = MagicMock()
    src._tickers = ["AAPL"]
    with patch.object(src, "_fetch_snapshots", return_value=[_snap("AAPL", 190.5, 1707580800000)]):
        await src._poll_once()
    u = cache.get("AAPL")
    assert u.price == 190.5 and u.timestamp == 1707580800.0

async def test_api_error_keeps_last_price():
    cache = PriceCache(); cache.update("AAPL", 190.0)
    src = MassiveDataSource("k", cache); src._client = MagicMock(); src._tickers = ["AAPL"]
    with patch.object(src, "_fetch_snapshots", side_effect=RuntimeError("429")):
        await src._poll_once()                               # must not raise
    assert cache.get_price("AAPL") == 190.0
```

**Cache thread-safety**

```python
def test_concurrent_updates_keep_version_consistent():
    cache = PriceCache()
    def work(n):
        for i in range(1000):
            cache.update(f"T{n}", 100 + i)
    threads = [Thread(target=work, args=(n,)) for n in range(8)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert cache.version == 8000 and len(cache) == 8
```

**SSE (httpx + ASGI)** — build an app with `create_stream_router(cache)`, then read the stream and assert the first lines are `retry: 1000` and a `data:` JSON containing every cached ticker. Cancel the request after the first frame; with a never-ending generator, use `httpx.AsyncClient(transport=ASGITransport(app))` and `client.stream("GET", "/api/stream/prices")` with `aiter_lines()`.

**Factory**

```python
def test_factory_selects_source(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "")
    assert isinstance(create_market_data_source(PriceCache()), SimulatorDataSource)
    monkeypatch.setenv("MASSIVE_API_KEY", "abc")
    assert isinstance(create_market_data_source(PriceCache()), MassiveDataSource)
```

E2E (`test/`) runs with the simulator: assert default 10 tickers render, price text changes within a few seconds, and the connection indicator turns green; for SSE resilience, restart the container (or block the route) and assert the indicator goes yellow, then green again.

---

## 13. Configuration summary

| Parameter | Where | Default | Notes |
|---|---|---|---|
| `MASSIVE_API_KEY` | env | empty | Non-empty → Massive; otherwise simulator |
| `update_interval` | `SimulatorDataSource` | 0.5 s | Simulator tick |
| `event_probability` | `GBMSimulator` | 0.001 | Shock chance per ticker per tick |
| `dt` | `GBMSimulator` | ≈ 8.48e-8 | Tick as a fraction of a trading year; must match `update_interval` if changed |
| `poll_interval` | `MassiveDataSource` | 15.0 s | 15 s free tier; 2–5 s paid |
| SSE `interval` | `_generate_events` | 0.5 s | Push cadence |
| SSE `retry` | `_generate_events` | 1000 ms | EventSource reconnect delay |

If `update_interval` is changed, scale `dt` proportionally (`dt = update_interval / TRADING_SECONDS_PER_YEAR`), otherwise simulated volatility will no longer match the stated annualized σ.

Demo: `cd backend && uv run market_data_demo.py` shows a live Rich dashboard of the simulator.
