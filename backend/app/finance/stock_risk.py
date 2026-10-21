"""Market risk of a listed share from its daily closing prices, and how it fits an investor's
risk profile.

Every metric is computed from the price history supplied (live data from the configured provider,
or a file of prices the user uploads); nothing is estimated or filled in. A missing close is
skipped, never treated as zero. The risk rating is a transparent points score whose bands are
shown with the result. It describes risk; it is not advice to buy or sell.
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np

from . import FinanceInputError

TRADING_DAYS = 252
MIN_POINTS = 60

# (metric, bands); each band is (upper bound, points). Points 0 = low risk ... 3 = very high.
BANDS = {
    "volatility": [(0.20, 0), (0.30, 1), (0.45, 2), (math.inf, 3)],
    "max_drawdown": [(0.20, 0), (0.35, 1), (0.50, 2), (math.inf, 3)],  # depth as a positive fraction
    "beta": [(0.80, 0), (1.20, 1), (1.60, 2), (math.inf, 3)],
    "var_95": [(0.02, 0), (0.03, 1), (0.045, 2), (math.inf, 3)],
}
RATINGS = [(25, "Low"), (50, "Moderate"), (75, "High"), (101, "Very high")]
PROFILES = {  # highest rating that fits, and the one that is borderline
    "conservative": ("Low", "Moderate"),
    "balanced": ("Moderate", "High"),
    "aggressive": ("High", "Very high"),
}
ORDER = ["Low", "Moderate", "High", "Very high"]
DISCLAIMER = ("A description of historical price risk, not a recommendation to buy, hold or sell. Past volatility does not "
              "predict future returns. Check the business, valuation and your own circumstances, or consult a SEBI-registered adviser.")


def _band(name: str, value: float) -> int:
    for upper, pts in BANDS[name]:
        if value <= upper:
            return pts
    return 3


def _clean(dates: list[str], closes: list[float | None]) -> tuple[list[dt.date], np.ndarray, int]:
    if len(dates) != len(closes):
        raise FinanceInputError("Dates and prices must have the same length.")
    rows = []
    skipped = 0
    for d, c in zip(dates, closes):
        if c is None or not math.isfinite(c):
            skipped += 1
            continue
        if c <= 0:
            raise FinanceInputError("Prices must be positive.")
        try:
            day = dt.date.fromisoformat(str(d)[:10])
        except ValueError as e:
            raise FinanceInputError(f"'{d}' is not a date (use YYYY-MM-DD).") from e
        rows.append((day, float(c)))
    rows.sort()
    dedup: dict[dt.date, float] = {}
    for day, c in rows:
        dedup[day] = c  # last value for a repeated date
    days = list(dedup)
    return days, np.array([dedup[d] for d in days]), skipped


def analyse(dates: list[str], closes: list[float | None], benchmark_dates: list[str] | None = None,
            benchmark_closes: list[float | None] | None = None, risk_free: float = 0.065, profile: str = "balanced",
            horizon_years: float = 5.0) -> dict:
    if profile not in PROFILES:
        raise FinanceInputError("Risk profile must be conservative, balanced or aggressive.")
    if not (0 <= risk_free < 1):
        raise FinanceInputError("Risk-free rate must be a decimal between 0 and 1 (e.g. 0.065).")
    days, px, skipped = _clean(dates, closes)
    if len(px) < MIN_POINTS:
        raise FinanceInputError(f"At least {MIN_POINTS} daily prices are needed; {len(px)} were supplied.")
    rets = px[1:] / px[:-1] - 1
    years = max((days[-1] - days[0]).days / 365.25, 1 / 365.25)
    cagr = (px[-1] / px[0]) ** (1 / years) - 1
    vol = float(np.std(rets, ddof=1) * math.sqrt(TRADING_DAYS))
    downside = rets[rets < 0]
    down_dev = float(np.sqrt(np.mean(np.minimum(rets, 0) ** 2)) * math.sqrt(TRADING_DAYS)) if len(downside) else 0.0
    peak = np.maximum.accumulate(px)
    dd = px / peak - 1
    trough = int(np.argmin(dd))
    peak_i = int(np.argmax(px[: trough + 1])) if trough > 0 else 0
    recovered = next((days[i].isoformat() for i in range(trough, len(px)) if px[i] >= px[peak_i]), None) if trough > 0 else None
    var95 = float(-np.percentile(rets, 5))
    cvar95 = float(-rets[rets <= np.percentile(rets, 5)].mean())
    last_year = px[-min(len(px), TRADING_DAYS):]
    ma200 = float(px[-200:].mean()) if len(px) >= 200 else None
    metrics = {
        "points": int(len(px)), "skipped_missing": skipped, "from": days[0].isoformat(), "to": days[-1].isoformat(), "years": years,
        "last_price": float(px[-1]), "cagr": float(cagr), "volatility": vol, "downside_deviation": down_dev,
        "sharpe": (cagr - risk_free) / vol if vol > 0 else None, "sortino": (cagr - risk_free) / down_dev if down_dev > 0 else None,
        "max_drawdown": float(dd[trough]), "max_drawdown_peak": days[peak_i].isoformat(), "max_drawdown_trough": days[trough].isoformat(),
        "recovered_on": recovered, "current_drawdown": float(dd[-1]),
        "var_95_1d": var95, "cvar_95_1d": cvar95, "var_95_10d": var95 * math.sqrt(10),
        "high_52w": float(last_year.max()), "low_52w": float(last_year.min()),
        "from_52w_high": float(px[-1] / last_year.max() - 1), "ma_200": ma200,
        "above_ma_200": bool(px[-1] > ma200) if ma200 is not None else None,
        "best_day": float(rets.max()), "worst_day": float(rets.min()), "positive_days": float((rets > 0).mean()),
        "beta": None, "correlation": None, "benchmark_points": None,
    }
    warnings = []
    if years < 1:
        warnings.append("Less than one year of prices: risk figures are less reliable.")
    if skipped:
        warnings.append(f"{skipped} missing prices were skipped (not treated as zero).")

    if benchmark_dates is not None and benchmark_closes is not None:
        bdays, bpx, _ = _clean(benchmark_dates, benchmark_closes)
        bmap = dict(zip(bdays, bpx))
        common = [d for d in days if d in bmap]
        if len(common) >= MIN_POINTS:
            amap = dict(zip(days, px))
            a = np.array([amap[d] for d in common])
            b = np.array([bmap[d] for d in common])
            ra, rb = a[1:] / a[:-1] - 1, b[1:] / b[:-1] - 1
            var_b = float(np.var(rb, ddof=1))
            metrics["beta"] = float(np.cov(ra, rb, ddof=1)[0, 1] / var_b) if var_b > 0 else None
            metrics["correlation"] = float(np.corrcoef(ra, rb)[0, 1]) if np.std(ra) > 0 and np.std(rb) > 0 else None
            metrics["benchmark_points"] = len(common)
        else:
            warnings.append("Too few dates in common with the benchmark to estimate beta.")

    factors = [
        {"factor": "Volatility (annualised)", "value": vol, "points": _band("volatility", vol),
         "bands": "below 20% / 20–30% / 30–45% / above 45%"},
        {"factor": "Largest fall from a peak", "value": -metrics["max_drawdown"], "points": _band("max_drawdown", -metrics["max_drawdown"]),
         "bands": "under 20% / 20–35% / 35–50% / over 50%"},
        {"factor": "1-day loss not exceeded on 95% of days (VaR)", "value": var95, "points": _band("var_95", var95),
         "bands": "under 2% / 2–3% / 3–4.5% / over 4.5%"},
    ]
    if metrics["beta"] is not None:
        factors.append({"factor": "Beta to the benchmark", "value": metrics["beta"], "points": _band("beta", metrics["beta"]),
                        "bands": "below 0.8 / 0.8–1.2 / 1.2–1.6 / above 1.6"})
    trend_pts = 0
    if metrics["above_ma_200"] is False:
        trend_pts = 2 if metrics["current_drawdown"] < -0.20 else 1
    factors.append({"factor": "Trend: price vs its 200-day average", "value": metrics["above_ma_200"], "points": trend_pts,
                    "bands": "above (0) / below (1) / below and more than 20% off its peak (2)"})
    max_points = 3 * (len(factors) - 1) + 2  # the trend factor scores at most 2
    score = round(100 * sum(f["points"] for f in factors) / max_points)
    rating = next(label for limit, label in RATINGS if score < limit)

    fits, borderline = PROFILES[profile]
    r_i = ORDER.index(rating)
    if r_i <= ORDER.index(fits):
        fit, msg = "fits", f"The share's historical risk ({rating}) is within the range for a {profile} investor."
    elif r_i <= ORDER.index(borderline):
        fit, msg = "borderline", (f"The share's historical risk ({rating}) is above the usual range for a {profile} investor; "
                                  "keep the position small or wait for more evidence.")
    else:
        fit, msg = "does_not_fit", f"The share's historical risk ({rating}) is well above what a {profile} investor usually accepts."
    if horizon_years < 3 and r_i >= 2:
        msg += " With a horizon under three years, a fall like the largest one shown may not recover in time."
    return {"metrics": metrics, "factors": factors, "score": score, "rating": rating, "profile": profile,
            "assessment": {"fit": fit, "message": msg}, "warnings": warnings, "disclaimer": DISCLAIMER,
            "method": {"returns": "simple daily returns", "annualisation": f"x sqrt({TRADING_DAYS})", "var": "historical, 5th percentile",
                       "var_10d": "1-day VaR x sqrt(10)", "risk_free": risk_free}}
