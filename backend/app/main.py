"""FastAPI application for FinAlly."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import chat as chat_mod
from . import portfolio as pf
from . import watchlist as wl
from .db import Database
from .market import MarketDataSource, PriceCache, create_market_data_source, create_stream_router

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL = 30.0


class TradeBody(BaseModel):
    ticker: str
    quantity: float
    side: str


class WatchlistBody(BaseModel):
    ticker: str


class ChatBody(BaseModel):
    message: str


def _load_env() -> None:
    """Load .env from the project root (or cwd) if python-dotenv-less parsing finds one."""
    here = Path(__file__).resolve()
    for d in (Path.cwd(), here.parents[1], here.parents[2]):
        f = d / ".env"
        if f.is_file():
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return


def create_app(
    db_path: str | None = None,
    cache: PriceCache | None = None,
    source: MarketDataSource | None = None,
    static_dir: str | None = None,
    snapshot_interval: float = SNAPSHOT_INTERVAL,
) -> FastAPI:
    """Build the app. Dependencies are injectable for tests."""
    cache = cache if cache is not None else PriceCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(db_path)
        src = source or create_market_data_source(cache)
        app.state.db, app.state.cache, app.state.source = db, cache, src
        await src.start(wl.watched_tickers(db))
        pf.record_snapshot(db, cache)

        async def snapshot_loop():
            while True:
                await asyncio.sleep(snapshot_interval)
                try:
                    pf.record_snapshot(db, cache)
                except Exception:
                    logger.exception("snapshot failed")

        task = asyncio.create_task(snapshot_loop())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await src.stop()
            db.close()

    app = FastAPI(title="FinAlly", lifespan=lifespan)
    app.include_router(create_stream_router(cache))

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/portfolio")
    async def get_portfolio(request: Request):
        s = request.app.state
        return pf.get_portfolio(s.db, s.cache)

    @app.post("/api/portfolio/trade")
    async def trade(body: TradeBody, request: Request):
        s = request.app.state
        try:
            t = pf.execute_trade(s.db, s.cache, body.ticker, body.side, body.quantity)
        except pf.TradeError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"success": True, "trade": t, "portfolio": pf.get_portfolio(s.db, s.cache)}

    @app.get("/api/portfolio/history")
    async def history(request: Request):
        return {"snapshots": pf.get_history(request.app.state.db)}

    @app.get("/api/watchlist")
    async def get_watchlist(request: Request):
        s = request.app.state
        return {"watchlist": wl.list_watchlist(s.db, s.cache)}

    @app.post("/api/watchlist")
    async def add_watchlist(body: WatchlistBody, request: Request):
        s = request.app.state
        try:
            ticker, added = await wl.add_ticker(s.db, s.source, body.ticker)
        except wl.WatchlistError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"success": True, "ticker": ticker, "added": added}

    @app.delete("/api/watchlist/{ticker}")
    async def remove_watchlist(ticker: str, request: Request):
        s = request.app.state
        removed = await wl.remove_ticker(s.db, s.source, ticker)
        if removed is None:
            raise HTTPException(404, f"{ticker.upper()} is not on the watchlist")
        return {"success": True, "ticker": removed}

    @app.post("/api/chat")
    async def chat(body: ChatBody, request: Request):
        s = request.app.state
        if not body.message.strip():
            raise HTTPException(400, "Message must not be empty")
        return await chat_mod.handle_chat(s.db, s.cache, s.source, body.message)

    @app.get("/api/chat/history")
    async def chat_history(request: Request):
        return {"messages": chat_mod.get_history_messages(request.app.state.db)}

    @app.exception_handler(HTTPException)
    async def http_exc(request: Request, exc: HTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    static = static_dir or os.environ.get("STATIC_DIR") or str(Path(__file__).resolve().parents[1] / "static")
    if Path(static).is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="static")

    return app


def _default_app() -> FastAPI:
    _load_env()
    return create_app()


app = _default_app()
