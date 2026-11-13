from fastapi.testclient import TestClient

from app.main import create_app
from tests.api.conftest import FakeSource


def test_fresh_portfolio(client):
    p = client.get("/api/portfolio").json()
    assert p["cash_balance"] == 10000.0 and p["total_value"] == 10000.0
    assert p["positions"] == []


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_buy_and_sell(client, cache):
    r = client.post("/api/portfolio/trade", json={"ticker": "aapl", "quantity": 10, "side": "buy"})
    assert r.status_code == 200
    p = r.json()["portfolio"]
    assert p["cash_balance"] == 9000.0
    assert p["positions"][0]["ticker"] == "AAPL" and p["positions"][0]["quantity"] == 10
    cache.update("AAPL", 110.0)
    p = client.get("/api/portfolio").json()
    assert p["unrealized_pnl"] == 100.0 and p["total_value"] == 10100.0
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "sell"})
    assert r.status_code == 200
    p = r.json()["portfolio"]
    assert p["positions"] == [] and p["cash_balance"] == 10100.0


def test_avg_cost(client, cache):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "buy"})
    cache.update("AAPL", 200.0)
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "buy"})
    pos = client.get("/api/portfolio").json()["positions"][0]
    assert pos["avg_cost"] == 150.0 and pos["quantity"] == 20


def test_sell_at_loss(client, cache):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "buy"})
    cache.update("AAPL", 90.0)
    p = client.post(
        "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 4, "side": "sell"}
    ).json()["portfolio"]
    assert p["cash_balance"] == 9000.0 + 360.0
    assert p["positions"][0]["quantity"] == 6 and p["positions"][0]["unrealized_pnl"] == -60.0


def test_overspend_and_oversell(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1000, "side": "buy"})
    assert r.status_code == 400 and "Insufficient cash" in r.json()["detail"]
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "sell"})
    assert r.status_code == 400 and "Insufficient shares" in r.json()["detail"]


def test_bad_trades(client):
    for body in (
        {"ticker": "AAPL", "quantity": -1, "side": "buy"},
        {"ticker": "AAPL", "quantity": 1, "side": "hold"},
        {"ticker": "NOPE", "quantity": 1, "side": "buy"},
    ):
        assert client.post("/api/portfolio/trade", json=body).status_code == 400
    assert client.post("/api/portfolio/trade", json={"ticker": "AAPL"}).status_code == 422


def test_fractional_and_history(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 0.5, "side": "buy"})
    snaps = client.get("/api/portfolio/history").json()["snapshots"]
    assert len(snaps) >= 2
    assert snaps[-1]["total_value"] == 10000.0


def test_watchlist_crud(client):
    wl = client.get("/api/watchlist").json()["watchlist"]
    assert len(wl) == 10 and wl[0]["price"] == 100.0
    assert client.post("/api/watchlist", json={"ticker": "pypl"}).json() == {
        "success": True,
        "ticker": "PYPL",
        "added": True,
    }
    assert client.post("/api/watchlist", json={"ticker": "PYPL"}).json()["added"] is False
    assert client.post("/api/watchlist", json={"ticker": "bad ticker!"}).status_code == 400
    assert client.delete("/api/watchlist/PYPL").status_code == 200
    assert client.delete("/api/watchlist/PYPL").status_code == 404


def test_chat_mock_trade_and_failure(client):
    r = client.post("/api/chat", json={"message": "please buy 5 AAPL"}).json()
    assert r["trades"][0]["success"] is True
    assert client.get("/api/portfolio").json()["positions"][0]["quantity"] == 5
    r = client.post("/api/chat", json={"message": "buy 100000 AAPL"}).json()
    assert r["trades"][0]["success"] is False and "Insufficient cash" in r["message"]
    r = client.post("/api/chat", json={"message": "add PYPL"}).json()
    assert r["watchlist_changes"][0]["success"] is True
    r = client.post("/api/chat", json={"message": "how am I doing?"}).json()
    assert "portfolio" in r["message"]
    msgs = client.get("/api/chat/history").json()["messages"]
    assert msgs[0]["role"] == "user" and msgs[1]["actions"]["trades"][0]["ticker"] == "AAPL"


def test_sse_route_registered(client):
    assert any(r.path == "/api/stream/prices" for r in client.app.routes)


def test_static_mount(tmp_path, cache):
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "index.html").write_text("hello")
    app = create_app(
        db_path=str(tmp_path / "x.db"),
        cache=cache,
        source=FakeSource(cache),
        static_dir=str(tmp_path / "s"),
    )
    with TestClient(app) as c:
        assert c.get("/").text == "hello"
        assert c.get("/api/health").status_code == 200
