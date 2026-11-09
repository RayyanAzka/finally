"""Tests for MassiveDataSource (mocked API, real SDK models)."""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest
from massive.rest.models import TickerSnapshot

from app.market.cache import PriceCache
from app.market.massive_client import MassiveDataSource

TS_NS = 1707580800_000_000_000  # SIP timestamps are Unix nanoseconds


def _make_snapshot(
    ticker: str, price: float | None, timestamp_ns: int = TS_NS, prev_close: float | None = None
) -> TickerSnapshot:
    """Build a real SDK snapshot from a v2 snapshot API payload.

    Using the real model (not MagicMock) means tests fail if the code reads
    a field the SDK doesn't have.
    """
    payload: dict = {"ticker": ticker, "lastTrade": {"p": price, "s": 100, "t": timestamp_ns}}
    if prev_close is not None:
        payload["prevDay"] = {"c": prev_close}
    return TickerSnapshot.from_dict(payload)


def _make_source(cache: PriceCache, tickers: list[str]) -> MassiveDataSource:
    source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
    source._tickers = list(tickers)
    source._client = MagicMock()  # Satisfy the _poll_once guard
    return source


@pytest.mark.asyncio
class TestMassiveDataSource:
    """Unit tests for MassiveDataSource with mocked API."""

    async def test_poll_updates_cache(self):
        """Test that polling updates the cache."""
        cache = PriceCache()
        source = _make_source(cache, ["AAPL", "GOOGL"])

        mock_snapshots = [_make_snapshot("AAPL", 190.50), _make_snapshot("GOOGL", 175.25)]

        with patch.object(source, "_fetch_snapshots", return_value=mock_snapshots):
            await source._poll_once()

        assert cache.get_price("AAPL") == 190.50
        assert cache.get_price("GOOGL") == 175.25

    async def test_fetch_receives_ticker_copy(self):
        """The worker thread gets a snapshot of the ticker list, not the live list."""
        cache = PriceCache()
        source = _make_source(cache, ["AAPL"])

        with patch.object(source, "_fetch_snapshots", return_value=[]) as mock_fetch:
            await source._poll_once()

        (tickers,) = mock_fetch.call_args.args
        assert tickers == ["AAPL"]
        assert tickers is not source._tickers

    async def test_malformed_snapshot_skipped(self):
        """Snapshots with no last trade or no price are skipped gracefully."""
        cache = PriceCache()
        source = _make_source(cache, ["AAPL", "BAD", "NOPRICE"])

        good_snap = _make_snapshot("AAPL", 190.50)
        bad_snap = TickerSnapshot.from_dict({"ticker": "BAD"})  # last_trade is None
        no_price = _make_snapshot("NOPRICE", None)

        with patch.object(source, "_fetch_snapshots", return_value=[good_snap, bad_snap, no_price]):
            await source._poll_once()

        assert cache.get_price("AAPL") == 190.50
        assert cache.get_price("BAD") is None
        assert cache.get_price("NOPRICE") is None

    async def test_api_error_does_not_crash(self):
        """Test that API errors don't crash the poller."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        source = _make_source(cache, ["AAPL"])

        with patch.object(source, "_fetch_snapshots", side_effect=Exception("network error")):
            await source._poll_once()  # Should not raise

        assert cache.get_price("AAPL") == 190.00  # Last known price kept

    async def test_timestamp_conversion(self):
        """SIP timestamps are converted from nanoseconds to seconds."""
        cache = PriceCache()
        source = _make_source(cache, ["AAPL"])

        with patch.object(source, "_fetch_snapshots", return_value=[_make_snapshot("AAPL", 190.5)]):
            await source._poll_once()

        update = cache.get("AAPL")
        assert update is not None
        assert update.timestamp == 1707580800.0

    async def test_missing_timestamp_uses_now(self):
        """A trade without a timestamp falls back to the current time."""
        cache = PriceCache()
        source = _make_source(cache, ["AAPL"])
        snap = TickerSnapshot.from_dict({"ticker": "AAPL", "lastTrade": {"p": 190.5}})

        before = time.time()
        with patch.object(source, "_fetch_snapshots", return_value=[snap]):
            await source._poll_once()

        assert cache.get("AAPL").timestamp >= before

    async def test_prev_close_sets_session_open(self):
        """Previous close becomes the reference for daily change."""
        cache = PriceCache()
        source = _make_source(cache, ["AAPL"])
        snap = _make_snapshot("AAPL", 198.0, prev_close=180.0)

        with patch.object(source, "_fetch_snapshots", return_value=[snap]):
            await source._poll_once()

        update = cache.get("AAPL")
        assert update.session_open == 180.0
        assert update.day_change_percent == 10.0

    async def test_untracked_snapshot_ignored(self):
        """Snapshots for tickers not being tracked are not written."""
        cache = PriceCache()
        source = _make_source(cache, ["AAPL"])
        snaps = [_make_snapshot("AAPL", 190.0), _make_snapshot("TSLA", 250.0)]

        with patch.object(source, "_fetch_snapshots", return_value=snaps):
            await source._poll_once()

        assert "TSLA" not in cache

    async def test_remove_during_poll_not_resurrected(self):
        """A ticker removed while a poll is in flight must stay removed."""
        cache = PriceCache()
        source = _make_source(cache, ["AAPL", "TSLA"])

        def slow_fetch(tickers):
            time.sleep(0.2)
            return [_make_snapshot(t, 100.0) for t in tickers]

        with patch.object(source, "_fetch_snapshots", side_effect=slow_fetch):
            poll = asyncio.create_task(source._poll_once())
            await asyncio.sleep(0.05)
            await source.remove_ticker("TSLA")
            await poll

        assert source.get_tickers() == ["AAPL"]
        assert "TSLA" not in cache
        assert cache.get_price("AAPL") == 100.0

    async def test_add_ticker(self):
        """Test adding a ticker."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)

        await source.add_ticker("AAPL")
        assert "AAPL" in source.get_tickers()

    async def test_add_ticker_uppercase_normalization(self):
        """Test that tickers are normalized to uppercase."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)

        await source.add_ticker("aapl")
        assert "AAPL" in source.get_tickers()

    async def test_add_ticker_strips_whitespace(self):
        """Test that ticker whitespace is stripped."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)

        await source.add_ticker("  AAPL  ")
        assert "AAPL" in source.get_tickers()

    async def test_remove_ticker(self):
        """Test removing a ticker."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)
        source._tickers = ["AAPL", "GOOGL"]
        cache.update("AAPL", 190.00)

        await source.remove_ticker("aapl")
        assert "AAPL" not in source.get_tickers()
        assert cache.get("AAPL") is None

    async def test_get_tickers(self):
        """Test getting the list of active tickers."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)
        source._tickers = ["AAPL", "GOOGL"]

        tickers = source.get_tickers()
        assert tickers == ["AAPL", "GOOGL"]

    async def test_empty_tickers_skips_poll(self):
        """Test that polling is skipped when there are no tickers."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)
        source._tickers = []

        # Should not call _fetch_snapshots
        with patch.object(source, "_fetch_snapshots") as mock_fetch:
            await source._poll_once()
            mock_fetch.assert_not_called()

    async def test_stop_is_idempotent(self):
        """Test that stop() can be called multiple times."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)

        await source.stop()
        await source.stop()  # Should not raise

    async def test_stop_cancels_task(self):
        """Test that stop() cancels the polling task."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=10.0)

        with patch("app.market.massive_client.RESTClient"):
            with patch.object(source, "_fetch_snapshots", return_value=[]):
                await source.start(["AAPL"])

        assert source._task is not None
        assert not source._task.done()

        await source.stop()
        assert source._task is None

    async def test_start_immediate_poll(self):
        """Test that start() does an immediate poll before starting the loop."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)

        with patch("app.market.massive_client.RESTClient"):
            with patch.object(
                source, "_fetch_snapshots", return_value=[_make_snapshot("AAPL", 190.50)]
            ):
                await source.start(["AAPL"])

        assert cache.get_price("AAPL") == 190.50

        await source.stop()

    async def test_start_merges_pre_added_tickers(self):
        """Tickers added before start() are kept; start tickers are normalized."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        await source.add_ticker("PYPL")

        with patch("app.market.massive_client.RESTClient"):
            with patch.object(source, "_fetch_snapshots", return_value=[]):
                await source.start(["aapl", "PYPL"])

        assert source.get_tickers() == ["PYPL", "AAPL"]
        await source.stop()

    async def test_double_start_raises(self):
        """Calling start() twice is rejected instead of leaking a task."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)

        with patch("app.market.massive_client.RESTClient"):
            with patch.object(source, "_fetch_snapshots", return_value=[]):
                await source.start(["AAPL"])
                with pytest.raises(RuntimeError):
                    await source.start(["AAPL"])

        await source.stop()

    async def test_poll_loop_polls_on_interval(self):
        """The background loop keeps polling after the initial poll."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=0.02)

        with patch("app.market.massive_client.RESTClient"):
            with patch.object(source, "_fetch_snapshots", return_value=[]) as mock_fetch:
                await source.start(["AAPL"])
                await asyncio.sleep(0.1)
                await source.stop()

        assert mock_fetch.call_count >= 3
