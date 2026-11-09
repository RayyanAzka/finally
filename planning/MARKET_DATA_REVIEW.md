# Market Data Backend — Code Review (Second Pass)

**Date:** 2026-11-09
**Scope:** `backend/app/market/` (9 modules), `backend/tests/market/` (6 test modules), `backend/pyproject.toml`, `backend/market_data_demo.py`
**Reference docs:** `PLAN.md`, `MARKET_DATA_SUMMARY.md`, `MARKET_DATA_DESIGN.md`, `archive/*` (including the first review, `archive/MARKET_DATA_REVIEW.md`)

---

## 1. Summary

The subsystem is well-structured and the simulator path is solid: GBM math is correct, correlations come out as designed, the SSE endpoint works end to end, and the suite is fast and stable.

**However, the Massive (real market data) path does not work.** It reads `snap.last_trade.timestamp`, but the SDK's `LastTrade` model has no such field. Every snapshot raises `AttributeError` and is skipped, so with `MASSIVE_API_KEY` set the cache stays empty and the UI shows no prices. The unit tests miss this because they build snapshots from `MagicMock`, which accepts any attribute name. `MARKET_DATA_SUMMARY.md` says the subsystem is "complete, tested, reviewed, all issues resolved", which is not accurate for this path.

| Severity | Count | Items |
|---|---|---|
| Critical | 1 | 3.1 |
| High | 1 | 3.2 |
| Medium | 3 | 3.3 – 3.5 |
| Low | 5 | 3.6 – 3.10 |
| Tests | 6 | §4 |

**Verdict:** Fix 3.1 and 3.2, and add the real-model test from §4, before building on the Massive source. Fix 3.3 before writing API route tests. The simulator path is ready for downstream work now.

---

## 2. Test and Tooling Results

Environment: `uv sync --extra dev`, Python 3.13.17 (the venv picked up the host interpreter; there is no `.python-version`, while the Dockerfile in PLAN.md targets 3.12), `massive` 2.2.0.

| Check | Result |
|---|---|
| `pytest` | **73 passed**, 0 failed, about 1.2 s |
| Flakiness | 8 consecutive runs, all 73 passed each time |
| `ruff check app/ tests/` | Clean |
| `ruff format --check` | 3 test files would be reformatted (`test_models.py`, `test_simulator.py`, `test_simulator_source.py`) |
| Demo (`uv run market_data_demo.py`) | Starts and renders without error |

**Coverage: 91% overall** (up from 84% in the first review, since `massive` is now installed).

| Module | Cover | Missing |
|---|---|---|
| models, cache, factory, interface, seed_prices, `__init__` | 100% | — |
| simulator.py | 98% | duplicate guard in `_add_ticker_internal` (149), exception handler in `_run_loop` (268-269) |
| massive_client.py | 94% | `_poll_loop` body (85-87), real `_fetch_snapshots` (125) |
| stream.py | **33%** | the whole endpoint and generator (26-48, 62-87) |

High line coverage of `massive_client.py` is misleading: the lines run, but against mocks that don't match the real SDK (see 3.1).

### Additional verification performed
Scratch scripts (not committed) checked behaviour the suite doesn't cover:

- **Real SDK object through `_poll_once`** → snapshot skipped, cache empty (3.1).
- **`remove_ticker` during an in-flight poll** → removed ticker comes back in the cache (3.2).
- **`create_stream_router` called twice** → same router object returned, with 2 `/prices` routes (3.3).
- **Live SSE over uvicorn + httpx** → `200 text/event-stream`, first frame `retry: 1000`, then a `data:` frame containing every cached ticker. Works.
- **Full 10-ticker default set** → Cholesky builds (10×10); a 50-ticker set with 40 unknowns also builds (the matrix stays positive-definite).
- **Realised AAPL/MSFT log-return correlation** over 5,000 ticks = **0.598** (target 0.6). Correct.
- **Per-tick AAPL σ** ≈ 0.0064% (≈ 1.2¢ at $190), consistent with σ = 22% annualised.

---

## 3. Issues

### 3.1 Massive client reads a field that doesn't exist (Critical)

`massive_client.py:103`
```python
timestamp = snap.last_trade.timestamp / 1000.0
```
The `massive` SDK's `LastTrade` (`massive/rest/models/trades.py`) has `sip_timestamp`, `participant_timestamp` and `trf_timestamp`, but **no `timestamp`**. With a real `TickerSnapshot`:

```
WARNING Skipping snapshot for AAPL: 'LastTrade' object has no attribute 'timestamp'
AAPL in cache after real-model poll: None
```

The `except (AttributeError, TypeError)` block hides this as a per-ticker warning, so the poller runs "successfully" while writing nothing.

The unit conversion is also wrong. The v2 snapshot `lastTrade.t` (mapped to `sip_timestamp`) is in **nanoseconds**, not milliseconds. The code's `/ 1000.0` would give timestamps around year 55,000.

**Fix:**
```python
trade = snap.last_trade
price = trade.price
timestamp = trade.sip_timestamp / 1e9 if trade.sip_timestamp else None  # SIP ns → s
```
Also skip snapshots where `price is None`. `round(None, 2)` would raise `TypeError`, which is caught, but an explicit check is clearer. Update `archive/MASSIVE_API.md` and `MARKET_DATA_DESIGN.md` §6, which describe the timestamp as milliseconds.

### 3.2 Removed ticker resurrected by an in-flight Massive poll (High)

`_poll_once` runs `_fetch_snapshots` in a worker thread for up to a few seconds. If `remove_ticker("TSLA")` runs during that window, it removes TSLA from `_tickers` and the cache. The poll then returns and writes TSLA back into the cache:

```
tickers: ['AAPL'] | TSLA resurrected in cache: True
```

TSLA then streams over SSE indefinitely, because it is never polled again and never removed again. Users who remove a ticker will see it come back.

**Fix:** In `_poll_once`, only write snapshots whose ticker is still tracked:
```python
active = set(self._tickers)
for snap in snapshots:
    if snap.ticker not in active:
        continue
```
Related: `_fetch_snapshots` passes the live `self._tickers` list to a worker thread while `add_ticker` may `append` to it on the loop thread. Pass a copy (`tickers=list(self._tickers)`) to make the thread boundary explicit.

### 3.3 Module-level SSE router: duplicate routes, cross-binding (Medium; unresolved from first review §3.6)

`stream.py:17` creates one module-level `router`, and each call to `create_stream_router(cache)` adds another `/prices` route to it. Confirmed: two calls return the same object with two `/prices` routes. The first registered handler wins, so a second app (e.g. a test fixture) streams the **first** cache. This will cause confusing failures as soon as API tests start building apps per test.

**Fix:** Create the router inside the factory:
```python
def create_stream_router(price_cache: PriceCache) -> APIRouter:
    router = APIRouter(prefix="/api/stream", tags=["streaming"])
    @router.get("/prices")
    ...
    return router
```

### 3.4 Inconsistent ticker normalisation between sources (Medium)

`MassiveDataSource.add_ticker`/`remove_ticker` call `.upper().strip()`, but `SimulatorDataSource` doesn't:

```
simulator tickers after add('aapl'): ['AAPL', 'aapl']
```

The simulator would track `aapl` as a separate ticker at a random $50–300 price. The interface docstring says nothing about normalisation, so behaviour depends on which source is active.

**Fix:** Pick one place. Ideally the API layer validates and normalises (`^[A-Z.]{1,6}$` after `.upper().strip()`), and both sources normalise defensively too. Document this in `interface.py`.

### 3.5 Simulator silently drops `add_ticker` before `start()` (Medium)

`SimulatorDataSource.add_ticker` is guarded by `if self._sim:`, so calls before `start()` are dropped. `MassiveDataSource.add_ticker` works before `start()` (it appends to `_tickers`, though `start()` then overwrites the list). Neither matches the other, and neither is documented. In practice the lifespan calls `start()` first, so this is a latent trap rather than an active bug. Either raise `RuntimeError` when not started, or document "must call `start()` first" on the interface. Similarly, a second `start()` call leaks the first background task in both sources. The interface calls this "undefined behaviour"; a guard that raises would be cheap.

### 3.6 `PriceCache.remove()` doesn't bump `version` (Low)

The SSE generator only emits when `version` changes. After a removal it keeps sending nothing new until the next `update()`. With the simulator that's 500 ms. With Massive it can be up to 15 s, during which the client's last frame still includes the removed ticker. Bump `_version` in `remove()` when a key was actually popped.

Since every frame is a full snapshot, the frontend should *replace* its price map on each frame, not merge into it, or removed tickers will linger forever. Note this for the Frontend agent.

### 3.7 `timestamp or time.time()` treats `0.0` as missing (Low)

`cache.py:30`: use `timestamp if timestamp is not None else time.time()`. This only matters for synthetic data, but it fits with fixing 3.1.

### 3.8 SSE generator swallows `CancelledError` (Low)

`stream.py:86-87` catches `CancelledError` and returns normally. Under anyio/Starlette that usually works, because the cancel scope re-raises, but swallowing cancellation is an anti-pattern and can delay shutdown. Log it and re-raise, or use `finally:` for the log line.

### 3.9 `version` read without lock (Low; unchanged from first review §3.4)

Safe on GIL CPython. Note that the venv is already running 3.13, where free-threaded builds exist. Taking the lock costs nothing.

### 3.10 Tick-to-tick `change_percent` vs. PLAN's "daily change %" (Low / spec gap)

`change_percent` compares against the previous tick, so it hovers around ±0.01%. PLAN.md §10 asks for **daily** change % in the watchlist. `MARKET_DATA_DESIGN.md` §11.1 already proposes `session_open`, and the Massive snapshot provides `prev_day.close` / `todays_change_percent` for free. This needs a decision before the frontend watchlist is built. Otherwise the watchlist column will read ~0.00% at all times.

---

## 4. Test Suite Assessment

The suite is fast, deterministic in practice, and readable. Gaps:

1. **Massive tests mock the SDK too loosely (critical gap).** `_make_snapshot` uses `MagicMock`, which is why 3.1 got through. Build fixtures with the real model so tests break if field names drift:
   ```python
   from massive.rest.models import TickerSnapshot
   snap = TickerSnapshot.from_dict({"ticker": "AAPL", "lastTrade": {"p": 190.5, "t": 1707580800000000000}})
   ```
   `test_timestamp_conversion` currently asserts the wrong unit and should be rewritten with this fixture.
2. **No SSE tests** (`stream.py` 33%). Add one ASGI test that reads the `retry:` line and the first `data:` frame. httpx isn't a dev dependency yet. Add `httpx` to `[project.optional-dependencies].dev`, since downstream API route tests will need it for `TestClient` anyway.
3. **No regression test for 3.2** (remove during an in-flight poll). The scratch script in §2 can be turned into one directly.
4. **Tests that assert nothing:**
   - `test_exception_resilience` never injects an exception. It only checks the task is alive. Patch `step` with `side_effect=[RuntimeError, {...}]` and assert the loop continues, which also covers `simulator.py:268-269`.
   - `test_custom_event_probability` has no assertions. With `event_probability=1.0`, assert that a single `step()` moves the price by at least about 2%.
5. **Missing simulator invariants** recommended in the design doc §12: a 10-ticker Cholesky test and a seeded correlation test (I verified both by hand: 10×10 builds, ρ = 0.598).
6. **No concurrent-writer test for `PriceCache`** (design doc §12 has one ready to paste).

Minor: `conftest.py` defines an `event_loop_policy` fixture that duplicates the default and can be deleted. `@pytest.mark.asyncio` decorators are redundant under `asyncio_mode = "auto"`. Run `ruff format` on the 3 flagged files.

---

## 5. What Is Done Well

- **Clean strategy pattern.** One ABC, two sources, one cache, and consumers are agnostic to the source. Easy to integrate.
- **Correct GBM.** Log-normal step with the Itô correction (`mu - σ²/2`), unrounded internal state with rounding only at the cache, and positive prices guaranteed.
- **Correlations work as designed** (measured ρ = 0.598 vs. 0.6 target). TSLA override and fallback for unknown tickers are sensible; matrix stays positive-definite even with many unknown tickers.
- **Resilient loops.** Both background tasks log and continue; `stop()` is idempotent and awaits cancellation.
- **Cache seeded at start / on add**, so SSE has data on its first frame.
- **SSE details are right.** `retry: 1000`, `X-Accel-Buffering: no`, disconnect detection, and version-gated emission.
- **Previous review items 3.1, 3.2, 3.3, 3.5, 3.7 and §4.3** (build config, lazy imports, return type, private access, unused imports, correlation constants) are confirmed fixed.

---

## 6. Recommended Actions

**Must fix (blocks Massive mode):**
1. 3.1: use `last_trade.sip_timestamp / 1e9`; guard `price is None`.
2. 3.2: ignore snapshots for tickers no longer tracked; pass a copy of the ticker list to the thread.
3. Rewrite the Massive test fixtures with real `TickerSnapshot.from_dict` (§4.1) and add the race regression test (§4.3).

**Should fix (before downstream API work):**
4. 3.3: move the router into the factory.
5. 3.4: normalise tickers consistently and validate at the API layer.
6. Add `httpx` to dev deps and an SSE smoke test (§4.2).
7. 3.10: decide on daily-change semantics (design doc §11.1) before the frontend watchlist is built.
8. Pin Python: add `.python-version` with `3.12` to match the Dockerfile.

**Nice to have:**
9. 3.5–3.9 and the remaining items in §4.
10. Correct `MARKET_DATA_SUMMARY.md`. Its "all issues resolved" status and the timestamp description in the design docs should reflect this review.

---

## 7. Resolution (2026-11-09)

All items above are fixed on branch `fix/market-data-review`, except pinning Python 3.12 (§6 item 8). Tests: **106 passed** (8 consecutive runs), coverage **99%**, `ruff check` and `ruff format --check` clean.

| Item | Fix |
|---|---|
| 3.1 | `massive_client.py` reads `last_trade.sip_timestamp / 1e9`, skips trades with no price, and passes `prev_day.close` as `session_open`. Verified against a real `TickerSnapshot`. |
| 3.2 | `_poll_once` drops snapshots for tickers no longer tracked. `_fetch_snapshots(tickers)` gets a copy, and `add_ticker` rebinds the list instead of appending. Regression test added. |
| 3.3 | `create_stream_router` builds its own `APIRouter`. |
| 3.4 | `models.normalize_ticker` is used by both sources. The interface documents it. |
| 3.5 | Both sources accept `add_ticker` before `start()` (merged at start). A second `start()` raises `RuntimeError`. |
| 3.6 | `PriceCache.remove` bumps `version` when a key was removed. |
| 3.7 | `timestamp if timestamp is not None else time.time()`. |
| 3.8 | `CancelledError` is logged and re-raised. |
| 3.9 | `version` is read under the lock. |
| 3.10 | `PriceUpdate.session_open` and `day_change_percent` (also in `to_dict()` / SSE). Simulator reference = seed price; Massive = previous close. |
| §4 | Real-model Massive fixtures, race test, `test_stream.py` (direct generator tests, so no `httpx` needed), cache concurrency/version tests, 10- and 50-ticker Cholesky, seeded correlation (0.5–0.7), event-shock test, real exception-resilience test, deterministic event-probability test. Redundant `conftest` fixture removed. |

**Not done:** `.python-version` pinned to 3.12. Neither this host nor `uv` had a 3.12 interpreter installed, and downloading one was declined. The Dockerfile should still use `python:3.12-slim`.
