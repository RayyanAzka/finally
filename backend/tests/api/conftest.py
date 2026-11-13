import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.market import MarketDataSource, PriceCache


class FakeSource(MarketDataSource):
    def __init__(self, cache):
        self.cache = cache
        self.tickers = []

    async def start(self, tickers):
        self.tickers = list(tickers)
        for t in tickers:
            self.cache.update(t, 100.0)

    async def stop(self):
        pass

    async def add_ticker(self, ticker):
        self.tickers.append(ticker)
        self.cache.update(ticker, 50.0)

    async def remove_ticker(self, ticker):
        self.tickers.remove(ticker)
        self.cache.remove(ticker)

    def get_tickers(self):
        return list(self.tickers)


@pytest.fixture
def cache():
    return PriceCache()


@pytest.fixture
def client(tmp_path, cache, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    app = create_app(
        db_path=str(tmp_path / "t.db"),
        cache=cache,
        source=FakeSource(cache),
        static_dir=str(tmp_path / "nostatic"),
    )
    with TestClient(app) as c:
        yield c
