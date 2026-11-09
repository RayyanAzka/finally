"""Tests for the SSE streaming endpoint."""

import asyncio
import json
from unittest.mock import MagicMock

import pytest
from fastapi.responses import StreamingResponse

from app.market.cache import PriceCache
from app.market.stream import _generate_events, create_stream_router


def _fake_request(disconnect_after: int) -> MagicMock:
    """Request whose is_disconnected() turns True after N checks."""
    request = MagicMock()
    request.client.host = "127.0.0.1"
    calls = {"n": 0}

    async def is_disconnected() -> bool:
        calls["n"] += 1
        return calls["n"] > disconnect_after

    request.is_disconnected = is_disconnected
    return request


async def _collect(cache: PriceCache, disconnect_after: int, interval: float = 0.0) -> list[str]:
    gen = _generate_events(cache, _fake_request(disconnect_after), interval=interval)
    return [event async for event in gen]


class TestStreamRouter:
    def test_each_call_returns_fresh_router(self):
        """Two routers must not share routes (or caches)."""
        r1 = create_stream_router(PriceCache())
        r2 = create_stream_router(PriceCache())
        assert r1 is not r2
        assert [r.path for r in r2.routes] == ["/api/stream/prices"]

    async def test_endpoint_returns_event_stream(self):
        router = create_stream_router(PriceCache())
        endpoint = router.routes[0].endpoint
        response = await endpoint(_fake_request(0))
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-accel-buffering"] == "no"


@pytest.mark.asyncio
class TestGenerateEvents:
    async def test_first_event_is_retry_then_all_prices(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        cache.update("MSFT", 420.0)

        events = await _collect(cache, disconnect_after=1)

        assert events[0] == "retry: 1000\n\n"
        assert events[1].startswith("data: ") and events[1].endswith("\n\n")
        data = json.loads(events[1][len("data: ") :])
        assert set(data) == {"AAPL", "MSFT"}
        assert data["AAPL"]["price"] == 190.0
        assert data["AAPL"]["direction"] == "flat"
        assert "day_change_percent" in data["AAPL"]

    async def test_no_data_when_cache_empty(self):
        events = await _collect(PriceCache(), disconnect_after=2)
        assert events == ["retry: 1000\n\n"]

    async def test_unchanged_version_not_resent(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        events = await _collect(cache, disconnect_after=3)
        assert sum(e.startswith("data:") for e in events) == 1

    async def test_removal_is_pushed(self):
        """Removing a ticker produces a new frame without it."""
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        cache.update("TSLA", 250.0)
        gen = _generate_events(cache, _fake_request(10), interval=0.0)

        assert await anext(gen) == "retry: 1000\n\n"
        first = json.loads((await anext(gen))[len("data: ") :])
        cache.remove("TSLA")
        second = json.loads((await anext(gen))[len("data: ") :])
        await gen.aclose()

        assert set(first) == {"AAPL", "TSLA"}
        assert set(second) == {"AAPL"}

    async def test_cancellation_propagates(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        gen = _generate_events(cache, _fake_request(1000), interval=10.0)

        async def consume():
            async for _ in gen:
                pass

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
