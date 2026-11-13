from app.chat import mock_response, parse_llm_output
from app.db import Database


def test_parse_full():
    r = parse_llm_output(
        '{"message":"hi","trades":[{"ticker":"AAPL","side":"buy","quantity":2}],'
        '"watchlist_changes":[{"ticker":"X","action":"add"}]}'
    )
    assert r.message == "hi" and r.trades[0].quantity == 2
    assert r.watchlist_changes[0].action == "add"


def test_parse_message_only_and_fenced():
    assert parse_llm_output('{"message":"yo"}').trades == []
    assert parse_llm_output('```json\n{"message":"yo"}\n```').message == "yo"


def test_parse_malformed():
    assert parse_llm_output("just text").message == "just text"
    assert parse_llm_output("").message
    assert parse_llm_output(None).message
    r = parse_llm_output('{"message":"ok","trades":[{"ticker":"A","side":"bogus","quantity":1}]}')
    assert r.message == "ok" and r.trades == []


def test_mock():
    s = {"total_value": 1.0, "cash_balance": 1.0, "positions": []}
    assert mock_response("Sell 3 tsla", s).trades[0].ticker == "TSLA"
    assert mock_response("remove nflx", s).watchlist_changes[0].action == "remove"


def test_db_seed_idempotent(tmp_path):
    p = str(tmp_path / "sub" / "f.db")
    db = Database(p)
    db.execute("UPDATE users_profile SET cash_balance = 5 WHERE id = 'default'")
    db.close()
    db = Database(p)
    assert db.query("SELECT cash_balance FROM users_profile")[0][0] == 5
    assert db.query("SELECT COUNT(*) FROM watchlist")[0][0] == 10
