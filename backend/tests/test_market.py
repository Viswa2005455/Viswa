"""Market risk engine (known answers on synthetic prices) and provider parsing (documented response formats)."""

import datetime as dt
import json
import math

import httpx
import numpy as np
import pytest

from app.finance import FinanceInputError
from app.finance.stock_risk import analyse
from app.files.registers import parse_date, read_prices
from app.market import providers
from app.market.providers import EODHD, MarketError, TwelveData


def days(n, start=dt.date(2024, 1, 1)):
    return [(start + dt.timedelta(days=i)).isoformat() for i in range(n)]


def test_steady_growth_has_no_risk():
    n = 400
    closes = [100 * 1.001 ** i for i in range(n)]
    r = analyse(days(n), closes)
    m = r["metrics"]
    assert m["volatility"] == pytest.approx(0, abs=1e-9) and m["max_drawdown"] == 0 and m["var_95_1d"] == pytest.approx(-0.001)
    assert m["above_ma_200"] is True and r["rating"] == "Low" and r["assessment"]["fit"] == "fits"


def test_drawdown_beta_and_rating():
    rng = np.random.default_rng(7)
    rb = rng.normal(0.0004, 0.01, 500)
    ra = 2 * rb  # twice the benchmark's moves -> beta 2, correlation 1
    b = 100 * np.cumprod(1 + rb)
    a = 50 * np.cumprod(1 + ra)
    r = analyse(days(501), [50.0] + list(a), days(501), [100.0] + list(b), profile="conservative")
    assert r["metrics"]["beta"] == pytest.approx(2, rel=1e-6) and r["metrics"]["correlation"] == pytest.approx(1, rel=1e-6)
    assert r["metrics"]["volatility"] == pytest.approx(np.std(ra, ddof=1) * math.sqrt(252), rel=1e-6)
    assert any(f["factor"].startswith("Beta") and f["points"] == 3 for f in r["factors"])
    assert r["assessment"]["fit"] in ("borderline", "does_not_fit") and "not a recommendation" in r["disclaimer"]
    # a 50% crash and partial recovery
    closes = [100.0] * 100 + [50.0] * 50 + [75.0] * 100
    m = analyse(days(250), closes)["metrics"]
    assert m["max_drawdown"] == pytest.approx(-0.5) and m["recovered_on"] is None and m["current_drawdown"] == pytest.approx(-0.25)


def test_missing_prices_are_skipped_not_zero():
    closes = [100.0 + i for i in range(100)]
    closes[10] = None
    r = analyse(days(100), closes)
    assert r["metrics"]["skipped_missing"] == 1 and r["metrics"]["points"] == 99 and r["warnings"]
    with pytest.raises(FinanceInputError):
        analyse(days(10), [1.0] * 10)
    with pytest.raises(FinanceInputError):
        analyse(days(100), [0.0] * 100)


def fake(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_eodhd_parsing():
    def handler(req: httpx.Request):
        assert req.url.params["api_token"] == "k" and req.url.params["fmt"] == "json"
        if req.url.path.startswith("/api/search/"):
            assert req.url.path == "/api/search/tata%20motors" or "tata" in req.url.path
            return httpx.Response(200, json=[{"Code": "TATAMOTORS", "Exchange": "NSE", "Name": "Tata Motors", "Type": "Common Stock",
                                              "Country": "India", "Currency": "INR", "ISIN": "INE155A01022"}])
        if req.url.path == "/api/real-time/RELIANCE.NSE":
            return httpx.Response(200, json={"code": "RELIANCE.NSE", "timestamp": 1792500000, "gmtoffset": 0, "open": 1400,
                                             "high": 1420.5, "low": 1395, "close": 1410.2, "volume": 5000000, "previousClose": 1402,
                                             "change": 8.2, "change_p": 0.5849})
        if req.url.path == "/api/real-time/NOPE.NSE":
            return httpx.Response(200, json={"code": "NOPE.NSE", "close": "NA"})
        if req.url.path == "/api/eod/RELIANCE.NSE":
            return httpx.Response(200, json={"warning": "Data is limited by one year as you have free subscription",
                                             "data": [{"date": "2026-10-19", "open": 1, "high": 1, "low": 1, "close": 1405,
                                                       "adjusted_close": 1404.5, "volume": 10}]})
        if req.url.path == "/api/eod/BAD.NSE":
            return httpx.Response(401, json={"error": "unauthorized"})
        return httpx.Response(404)
    p = EODHD("k", fake(handler))
    assert p._search("tata motors")[0]["symbol"] == "TATAMOTORS.NSE"
    q = p._quote("RELIANCE.NSE")
    assert q.price == 1410.2 and q.change_pct == 0.5849 and q.as_of.startswith("2026-10")
    with pytest.raises(MarketError):
        p._quote("NOPE.NSE")
    h = p._history("RELIANCE.NSE", dt.date(2026, 1, 1), dt.date(2026, 10, 20))
    assert h["closes"] == [1404.5] and "one year" in h["warning"]
    with pytest.raises(MarketError) as e:
        p._history("BAD.NSE", dt.date(2026, 1, 1), dt.date(2026, 10, 20))
    assert "API key" in str(e.value)


def test_twelvedata_parsing_and_errors():
    def handler(req: httpx.Request):
        if req.url.path == "/quote":
            if req.url.params["symbol"] == "LIMIT":
                return httpx.Response(200, json={"code": 429, "message": "You have run out of API credits", "status": "error"})
            assert req.url.params.get("exchange") == "NSE"
            return httpx.Response(200, json={"symbol": "INFY", "name": "Infosys", "exchange": "NSE", "currency": "INR",
                                             "datetime": "2026-10-20", "open": "1500.0", "high": "1510", "low": "1490", "close": "1505.5",
                                             "volume": "100", "previous_close": "1500", "change": "5.5", "percent_change": "0.3667"})
        if req.url.path == "/time_series":
            assert "exchange" not in req.url.params
            return httpx.Response(200, json={"meta": {"symbol": "AAPL", "currency": "USD"}, "status": "ok",
                                             "values": [{"datetime": "2026-10-17", "close": "250.1"}, {"datetime": "2026-10-20", "close": "251"}]})
        if req.url.path == "/symbol_search":
            return httpx.Response(200, json={"data": [{"symbol": "AAPL", "instrument_name": "Apple Inc", "exchange": "NASDAQ",
                                                       "country": "United States", "currency": "USD", "instrument_type": "Common Stock"}],
                                             "status": "ok"})
        return httpx.Response(404)
    p = TwelveData("k", fake(handler))
    assert p._quote("INFY.NSE").price == 1505.5
    with pytest.raises(MarketError) as e:
        p._quote("LIMIT.NSE")
    assert e.value.status == 429
    assert p._history("AAPL.US", dt.date(2026, 10, 1), dt.date(2026, 10, 20))["closes"] == [250.1, 251.0]
    assert p._search("apple")[0]["symbol"] == "AAPL.US"


def test_price_files_and_dates():
    assert parse_date("21-Oct-2026") == "2026-10-21" and parse_date("05/09/2026") == "2026-09-05" and parse_date("2026-10-21") == "2026-10-21"
    assert parse_date("junk") is None and parse_date("31/02/2026") is None
    rows = "\n".join(f"{(dt.date(2026, 1, 1) + dt.timedelta(days=i)).strftime('%d-%b-%Y')},{100 + i},{101 + i}" for i in range(80))
    csv = 'Date,OPEN,close\n' + rows
    r = read_prices("nse.csv", csv.encode())
    assert len(r["dates"]) == 80 and r["closes"][0] == 101 and r["price_column"] == "close"
    with pytest.raises(ValueError):
        read_prices("x.csv", b"a,b\n1,2")


def test_market_api(client, monkeypatch):
    assert client.get("/api/market/status").json()["configured"] is False
    assert client.get("/api/market/quote?symbol=RELIANCE.NSE").status_code == 503
    n = 300
    closes = [100 * (1 + 0.01 * math.sin(i / 5)) for i in range(n)]
    csv = "Date,Close\n" + "\n".join(f"{d},{c}" for d, c in zip(days(n), closes))
    r = client.post("/api/market/risk-from-file", files={"file": ("p.csv", csv.encode())}, data={"profile": "aggressive"})
    assert r.status_code == 200, r.text
    assert r.json()["rating"] in ("Low", "Moderate", "High", "Very high") and len(r.json()["prices"]["dates"]) == n

    class Fake(providers.Provider):
        name, label, attribution = "fake", "Fake", "Fake data"

        def _history(self, symbol, start, end):
            return {"dates": days(n), "closes": closes, "volumes": [None] * n, "warning": None}

        def _quote(self, symbol):
            return providers.Quote(symbol, "X", "NSE", "INR", 1.0, 1.0, 0.0, 0.0, 1, 1, 1, 1, None, "test")

        def _search(self, q):
            return [{"symbol": "X.NSE"}]
    monkeypatch.setattr("app.api.market.get_market_provider", lambda s: Fake("k"))
    assert client.get("/api/market/search?q=x").json()["results"][0]["symbol"] == "X.NSE"
    assert client.get("/api/market/quote?symbol=x.nse").json()["symbol"] == "X.NSE"
    r = client.get("/api/market/risk?symbol=X.NSE&benchmark=NSEI.INDX&years=2")
    assert r.status_code == 200 and r.json()["metrics"]["beta"] == pytest.approx(1)
    assert client.get("/api/market/quote?symbol=bad symbol!").status_code == 422
    raw = json.dumps(client.get("/api/market/status").json())
    assert "api_key" not in raw.lower()
