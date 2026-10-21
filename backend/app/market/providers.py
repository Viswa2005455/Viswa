"""Market data providers. The API key stays on the server; the browser only sees the results.

Symbols use the form TICKER.EXCHANGE, e.g. RELIANCE.NSE, 500325.BSE, BP.LSE, AAPL.US, 7203.TSE.

  eodhd       EOD Historical Data (https://eodhd.com): about 70 exchanges including NSE and BSE.
              Free key: 20 calls a day and one year of history; the key "demo" works for a few US
              symbols (AAPL.US, TSLA.US, AMZN.US, VTI.US) for trying the app.
  twelvedata  Twelve Data (https://twelvedata.com): free key covers US shares; India and most
              other exchanges need a paid plan.

Both providers' free and personal plans are for the key holder's own use: showing the data to
other people (for example on a hosted copy used by a team) needs the provider's commercial
licence. Response formats follow each provider's documentation; errors that arrive with HTTP 200
are detected and reported.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from dataclasses import dataclass
from urllib.parse import quote as urlquote

import httpx


class MarketError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


@dataclass
class Quote:
    symbol: str
    name: str | None
    exchange: str | None
    currency: str | None
    price: float | None
    previous_close: float | None
    change: float | None
    change_pct: float | None  # percent, e.g. -0.58
    open: float | None
    high: float | None
    low: float | None
    volume: float | None
    as_of: str | None
    delay: str


def _num(v) -> float | None:
    if v in (None, "", "NA", "N/A", "None", "null"):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN


def split_symbol(symbol: str) -> tuple[str, str | None]:
    s = symbol.strip().upper()
    if "." in s:
        t, ex = s.rsplit(".", 1)
        return t, ex
    return s, None


class _Cache:
    def __init__(self):
        self._d: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            hit = self._d.get(key)
            if hit and hit[0] > time.monotonic():
                return hit[1]
            return None

    def put(self, key: str, value, ttl: float):
        with self._lock:
            if len(self._d) > 2000:
                self._d.clear()
            self._d[key] = (time.monotonic() + ttl, value)


CACHE = _Cache()
QUOTE_TTL, HISTORY_TTL, SEARCH_TTL = 15 * 60, 6 * 3600, 24 * 3600


class Provider:
    name = "none"
    label = "Not configured"
    attribution = ""

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self.key = api_key
        self.client = client or httpx.Client(timeout=15.0, headers={"User-Agent": "FinanceIntelligenceStudio/1.0"})

    def _get(self, url: str, params: dict) -> object:
        try:
            r = self.client.get(url, params=params)
        except httpx.HTTPError as e:
            raise MarketError(f"Could not reach {self.label} ({type(e).__name__}). Check the internet connection.") from e
        if r.status_code in (401, 403):
            raise MarketError(f"{self.label} refused the request: the API key is wrong or the plan does not cover this symbol.", 502)
        if r.status_code == 402:
            raise MarketError(f"{self.label}: this symbol or exchange is not in your plan.", 502)
        if r.status_code == 429:
            raise MarketError(f"{self.label}: the plan's request limit was reached. Try again later.", 429)
        if r.status_code == 404:
            raise MarketError("Symbol not found.", 404)
        if r.status_code >= 400:
            raise MarketError(f"{self.label} returned an error ({r.status_code}).")
        try:
            return r.json()
        except ValueError as e:
            raise MarketError(f"{self.label} sent a response that is not JSON.") from e

    # cached wrappers -------------------------------------------------------
    def search(self, query: str) -> list[dict]:
        k = f"{self.name}:s:{query.lower()}"
        hit = CACHE.get(k)
        if hit is None:
            hit = self._search(query)
            CACHE.put(k, hit, SEARCH_TTL)
        return hit

    def quote(self, symbol: str) -> Quote:
        k = f"{self.name}:q:{symbol}"
        hit = CACHE.get(k)
        if hit is None:
            hit = self._quote(symbol)
            CACHE.put(k, hit, QUOTE_TTL)
        return hit

    def history(self, symbol: str, start: dt.date, end: dt.date) -> dict:
        k = f"{self.name}:h:{symbol}:{start}:{end}"
        hit = CACHE.get(k)
        if hit is None:
            hit = self._history(symbol, start, end)
            CACHE.put(k, hit, HISTORY_TTL)
        return hit

    def _search(self, query: str) -> list[dict]:
        raise NotImplementedError

    def _quote(self, symbol: str) -> Quote:
        raise NotImplementedError

    def _history(self, symbol: str, start: dt.date, end: dt.date) -> dict:
        raise NotImplementedError


class EODHD(Provider):
    name = "eodhd"
    label = "EODHD"
    base = "https://eodhd.com/api"
    attribution = "Market data: EOD Historical Data (eodhd.com)"

    def _p(self, **kw) -> dict:
        return {"api_token": self.key, "fmt": "json", **kw}

    def _search(self, query: str) -> list[dict]:
        data = self._get(f"{self.base}/search/{urlquote(query, safe='')}", self._p(limit=15))
        if not isinstance(data, list):
            raise MarketError("Unexpected search response from EODHD.")
        return [{"symbol": f"{d.get('Code')}.{d.get('Exchange')}", "name": d.get("Name"), "exchange": d.get("Exchange"),
                 "country": d.get("Country"), "currency": d.get("Currency"), "type": d.get("Type"), "isin": d.get("ISIN")}
                for d in data if d.get("Code") and d.get("Exchange")]

    def _quote(self, symbol: str) -> Quote:
        d = self._get(f"{self.base}/real-time/{symbol}", self._p())
        if not isinstance(d, dict) or _num(d.get("close")) is None:
            raise MarketError("No price returned for this symbol (it may not exist or not be in your plan).", 404)
        ts = d.get("timestamp")
        as_of = dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).isoformat() if isinstance(ts, (int, float)) else None
        _, ex = split_symbol(symbol)
        return Quote(symbol=symbol, name=None, exchange=ex, currency=None, price=_num(d.get("close")),
                     previous_close=_num(d.get("previousClose")), change=_num(d.get("change")), change_pct=_num(d.get("change_p")),
                     open=_num(d.get("open")), high=_num(d.get("high")), low=_num(d.get("low")), volume=_num(d.get("volume")),
                     as_of=as_of, delay="Delayed (typically 15–20 minutes) or last close, depending on plan")

    def _history(self, symbol: str, start: dt.date, end: dt.date) -> dict:
        data = self._get(f"{self.base}/eod/{symbol}", self._p(**{"from": start.isoformat(), "to": end.isoformat(), "period": "d"}))
        warning = None
        if isinstance(data, dict):  # free plans add a warning wrapper, or an error message
            warning = data.get("warning") or data.get("message")
            data = data.get("data") if isinstance(data.get("data"), list) else []
        if not isinstance(data, list):
            raise MarketError("Unexpected history response from EODHD.")
        rows = [(r.get("date"), _num(r.get("adjusted_close")) or _num(r.get("close")), _num(r.get("volume"))) for r in data]
        rows = [r for r in rows if r[0]]
        return {"dates": [r[0] for r in rows], "closes": [r[1] for r in rows], "volumes": [r[2] for r in rows],
                "adjusted": True, "warning": warning}


class TwelveData(Provider):
    name = "twelvedata"
    label = "Twelve Data"
    base = "https://api.twelvedata.com"
    attribution = "Market data: Twelve Data (twelvedata.com)"

    def _check(self, d: object) -> dict:
        if not isinstance(d, dict):
            raise MarketError("Unexpected response from Twelve Data.")
        if d.get("status") == "error":
            code = d.get("code")
            msg = d.get("message") or "error"
            raise MarketError(f"Twelve Data: {msg}", 429 if code == 429 else 404 if code in (400, 404) else 502)
        return d

    @staticmethod
    def _params(symbol: str) -> dict:
        t, ex = split_symbol(symbol)
        return {"symbol": t} if ex in (None, "US") else {"symbol": t, "exchange": ex}

    def _search(self, query: str) -> list[dict]:
        d = self._check(self._get(f"{self.base}/symbol_search", {"symbol": query, "outputsize": 15}))
        out = []
        for x in d.get("data") or []:
            ex = x.get("exchange")
            suffix = "US" if x.get("country") == "United States" else ex
            out.append({"symbol": f"{x.get('symbol')}.{suffix}", "name": x.get("instrument_name"), "exchange": ex,
                        "country": x.get("country"), "currency": x.get("currency"), "type": x.get("instrument_type"), "isin": None})
        return out

    def _quote(self, symbol: str) -> Quote:
        d = self._check(self._get(f"{self.base}/quote", {**self._params(symbol), "apikey": self.key}))
        return Quote(symbol=symbol, name=d.get("name"), exchange=d.get("exchange"), currency=d.get("currency"),
                     price=_num(d.get("close")), previous_close=_num(d.get("previous_close")), change=_num(d.get("change")),
                     change_pct=_num(d.get("percent_change")), open=_num(d.get("open")), high=_num(d.get("high")),
                     low=_num(d.get("low")), volume=_num(d.get("volume")), as_of=d.get("datetime"),
                     delay="Real time for US shares on the free plan; other markets depend on the plan")

    def _history(self, symbol: str, start: dt.date, end: dt.date) -> dict:
        d = self._check(self._get(f"{self.base}/time_series", {**self._params(symbol), "interval": "1day", "outputsize": 5000,
                                                                "start_date": start.isoformat(), "end_date": end.isoformat(),
                                                                "order": "asc", "adjust": "all", "apikey": self.key}))
        vals = d.get("values") or []
        return {"dates": [v.get("datetime", "")[:10] for v in vals], "closes": [_num(v.get("close")) for v in vals],
                "volumes": [_num(v.get("volume")) for v in vals], "adjusted": True, "warning": None,
                "currency": (d.get("meta") or {}).get("currency")}


PROVIDERS = {"eodhd": EODHD, "twelvedata": TwelveData}


def get_market_provider(settings) -> Provider | None:
    name = (settings.fis_market_provider or "none").lower()
    key = settings.fis_market_api_key.get_secret_value() if settings.fis_market_api_key else ""
    if name == "none" or name not in PROVIDERS or not key:
        return None
    return PROVIDERS[name](key)
