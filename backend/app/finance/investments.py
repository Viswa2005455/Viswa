"""Investment analytics: fixed income, equity valuation models, portfolio risk/return and
performance, and derivatives (CFA Program body of knowledge conventions).

All rates are decimals per year unless stated. Bond analytics assume settlement on a coupon
date (no accrued interest). Every result carries its formula so it can be reviewed.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

from . import FinanceInputError

_N = NormalDist()


# --------------------------------------------------------------------------- fixed income

def _bond_flows(face: float, coupon_rate: float, years: float, freq: int) -> tuple[list[float], list[float]]:
    n = round(years * freq)
    if n < 1 or abs(n - years * freq) > 1e-9:
        raise FinanceInputError("Years to maturity must be a whole number of coupon periods.")
    c = face * coupon_rate / freq
    times = [t / freq for t in range(1, n + 1)]
    flows = [c] * n
    flows[-1] += face
    return times, flows


def _price(flows, times, y, freq):
    return sum(cf / (1 + y / freq) ** (t * freq) for cf, t in zip(flows, times))


def bond_analytics(face: float, coupon_rate: float, years: float, freq: int = 2, ytm: float | None = None,
                   price: float | None = None, shock_bp: float = 100) -> dict:
    if face <= 0 or coupon_rate < 0:
        raise FinanceInputError("Face must be positive and the coupon rate non-negative.")
    if freq not in (1, 2, 4, 12):
        raise FinanceInputError("Coupon frequency must be 1, 2, 4 or 12.")
    if (ytm is None) == (price is None):
        raise FinanceInputError("Give either the yield to maturity or the price (not both).")
    times, flows = _bond_flows(face, coupon_rate, years, freq)
    if ytm is None:
        if price <= 0:
            raise FinanceInputError("Price must be positive.")
        lo, hi = -0.99 * freq, 10.0
        f = lambda y: _price(flows, times, y, freq) - price  # noqa: E731
        if f(lo) * f(hi) > 0:
            raise FinanceInputError("No yield reproduces that price.")
        for _ in range(300):
            mid = (lo + hi) / 2
            if f(lo) * f(mid) <= 0:
                hi = mid
            else:
                lo = mid
            if hi - lo < 1e-13:
                break
        ytm = (lo + hi) / 2
    if ytm <= -freq:
        raise FinanceInputError("Yield is too low.")
    p = _price(flows, times, ytm, freq)
    pv = [cf / (1 + ytm / freq) ** (t * freq) for cf, t in zip(flows, times)]
    macaulay = sum(t * v for t, v in zip(times, pv)) / p
    modified = macaulay / (1 + ytm / freq)
    k = [t * freq for t in times]
    convexity = sum(v * kk * (kk + 1) for v, kk in zip(pv, k)) / (p * (1 + ytm / freq) ** 2) / freq ** 2
    dy = shock_bp / 10_000
    actual_up, actual_dn = _price(flows, times, ytm + dy, freq), _price(flows, times, ytm - dy, freq)
    est = lambda d: p * (-modified * d + 0.5 * convexity * d * d)  # noqa: E731
    schedule = [{"time": t, "cash_flow": cf, "pv": v, "weight": v / p} for t, cf, v in zip(times, flows, pv)]
    return {"price": p, "price_pct_of_par": p / face * 100, "ytm": ytm, "current_yield": face * coupon_rate / p,
            "macaulay_duration": macaulay, "modified_duration": modified, "convexity": convexity,
            "money_duration": modified * p, "dv01": modified * p * 0.0001,
            "shock": {"bp": shock_bp, "actual_up": actual_up - p, "actual_down": actual_dn - p,
                      "estimate_up": est(dy), "estimate_down": est(-dy),
                      "duration_only_up": -modified * dy * p, "duration_only_down": modified * dy * p},
            "cash_flows": schedule,
            "formulas": ["Price = Σ CFₜ / (1 + y/m)^(m·t)", "Macaulay D = Σ t·PV(CFₜ) / Price",
                         "Modified D = Macaulay D / (1 + y/m)", "ΔP/P ≈ −ModD·Δy + ½·Convexity·(Δy)²"],
            "note": "Settlement on a coupon date (no accrued interest); yields are quoted with the coupon frequency."}


# --------------------------------------------------------------------------- equity valuation

def gordon(d0: float | None, d1: float | None, g: float, r: float) -> dict:
    if r <= g:
        raise FinanceInputError("The required return must exceed the growth rate (r > g).")
    if d1 is None:
        if d0 is None:
            raise FinanceInputError("Enter D0 (last dividend) or D1 (next dividend).")
        d1 = d0 * (1 + g)
    v = d1 / (r - g)
    return {"value": v, "d1": d1, "dividend_yield": d1 / v, "formula": f"V₀ = D₁ / (r − g) = {d1:,.4f} / ({r:.4%} − {g:.4%})"}


def two_stage_ddm(d0: float, g1: float, n: int, g2: float, r: float) -> dict:
    if r <= g2:
        raise FinanceInputError("The required return must exceed the long-run growth rate.")
    if n < 1:
        raise FinanceInputError("The high-growth period must be at least one year.")
    rows, d, pv_div = [], d0, 0.0
    for t in range(1, n + 1):
        d *= 1 + g1
        pv = d / (1 + r) ** t
        pv_div += pv
        rows.append({"year": t, "dividend": d, "pv": pv})
    terminal = d * (1 + g2) / (r - g2)
    pv_terminal = terminal / (1 + r) ** n
    return {"value": pv_div + pv_terminal, "pv_dividends": pv_div, "terminal_value": terminal, "pv_terminal": pv_terminal,
            "dividends": rows, "formula": f"V₀ = Σ Dₜ/(1+r)ᵗ + [D{n + 1} / (r − g₂)] / (1+r)^{n}"}


def fcfe_value(fcfe0: float, g: float, r: float, shares: float | None = None) -> dict:
    if r <= g:
        raise FinanceInputError("The cost of equity must exceed the growth rate.")
    v = fcfe0 * (1 + g) / (r - g)
    return {"equity_value": v, "per_share": v / shares if shares else None, "fcfe1": fcfe0 * (1 + g),
            "formula": "Equity value = FCFE₁ / (r − g), FCFE = CFO − FCInv + net borrowing"}


def residual_income(book_value: float, roe: float, payout: float, r: float, years: int, terminal_growth: float | None = 0.0,
                    shares: float | None = None) -> dict:
    if not 0 <= payout <= 1:
        raise FinanceInputError("Payout must be between 0 and 1.")
    if years < 1:
        raise FinanceInputError("Forecast at least one year.")
    rows, b, pv_ri = [], book_value, 0.0
    for t in range(1, years + 1):
        e = b * roe
        ri = e - r * b
        pv = ri / (1 + r) ** t
        pv_ri += pv
        rows.append({"year": t, "opening_book": b, "earnings": e, "equity_charge": r * b, "residual_income": ri, "pv": pv})
        b += e * (1 - payout)
    pv_term = 0.0
    if terminal_growth is not None:
        if r <= terminal_growth:
            raise FinanceInputError("The required return must exceed the residual-income growth rate.")
        last = rows[-1]["residual_income"]
        pv_term = last * (1 + terminal_growth) / (r - terminal_growth) / (1 + r) ** years
    v = book_value + pv_ri + pv_term
    g = roe * (1 - payout)
    justified = {}
    if r > g:
        justified = {"pe_trailing": payout * (1 + g) / (r - g), "pe_forward": payout / (r - g), "pb": (roe - g) / (r - g), "sustainable_growth": g}
    return {"value": v, "per_share": v / shares if shares else None, "pv_residual_income": pv_ri, "pv_terminal": pv_term,
            "schedule": rows, "justified_multiples": justified,
            "formula": "V₀ = B₀ + Σ (Eₜ − r·Bₜ₋₁)/(1+r)ᵗ + PV(continuing residual income); g = ROE × (1 − payout)"}


# --------------------------------------------------------------------------- portfolio

def portfolio_stats(weights: list[float], returns: list[float], vols: list[float], corr: list[list[float]],
                    risk_free: float | None = None) -> dict:
    n = len(weights)
    if n < 1 or len(returns) != n or len(vols) != n or len(corr) != n or any(len(row) != n for row in corr):
        raise FinanceInputError("Weights, returns, volatilities and the correlation matrix must have matching sizes.")
    w, mu, s, c = (np.array(x, dtype=float) for x in (weights, returns, vols, corr))
    if abs(w.sum() - 1) > 1e-6:
        raise FinanceInputError(f"Weights must sum to 100% (they sum to {w.sum():.2%}).")
    if np.any(s < 0) or not np.allclose(c, c.T) or np.any(np.abs(c) > 1 + 1e-12) or not np.allclose(np.diag(c), 1):
        raise FinanceInputError("Volatilities must be non-negative and correlations a symmetric matrix with 1s on the diagonal.")
    cov = np.outer(s, s) * c
    if np.min(np.linalg.eigvalsh(cov)) < -1e-12:
        raise FinanceInputError("The correlation matrix is not internally consistent (not positive semi-definite).")
    er = float(w @ mu)
    var = float(w @ cov @ w)
    sd = math.sqrt(max(var, 0.0))
    contrib = (w * (cov @ w)) / var if var > 0 else np.zeros(n)
    out = {"expected_return": er, "variance": var, "std_dev": sd, "risk_contribution": contrib.tolist(),
           "sharpe": (er - risk_free) / sd if risk_free is not None and sd > 0 else None,
           "diversification_ratio": float(w @ s) / sd if sd > 0 else None,
           "formula": "E(Rp) = Σ wᵢE(Rᵢ); σp² = Σ Σ wᵢwⱼσᵢσⱼρᵢⱼ"}
    if n == 2:
        frontier = []
        for x in np.linspace(0, 1, 41):
            ww = np.array([x, 1 - x])
            frontier.append({"w1": float(x), "return": float(ww @ mu), "std_dev": math.sqrt(max(float(ww @ cov @ ww), 0.0))})
        denom = s[0] ** 2 + s[1] ** 2 - 2 * cov[0, 1]
        w_min = float((s[1] ** 2 - cov[0, 1]) / denom) if denom > 0 else None
        out["frontier"] = frontier
        if w_min is not None:
            wm = np.array([w_min, 1 - w_min])
            out["min_variance"] = {"w1": w_min, "return": float(wm @ mu), "std_dev": math.sqrt(max(float(wm @ cov @ wm), 0.0)),
                                   "note": "Weights can fall outside 0–100% (short selling); the frontier shown is long-only."
                                   if not 0 <= w_min <= 1 else "Long-only weights."}
    return out


def performance(portfolio: list[float], benchmark: list[float], risk_free: float, periods_per_year: int = 12) -> dict:
    """Risk-adjusted performance from periodic returns (decimals). risk_free is annual."""
    p, b = np.array(portfolio, dtype=float), np.array(benchmark, dtype=float)
    if len(p) != len(b) or len(p) < 3:
        raise FinanceInputError("Give at least three periods of portfolio and benchmark returns, of equal length.")
    k = periods_per_year
    rp, rb = float(p.mean() * k), float(b.mean() * k)
    sp, sb = float(p.std(ddof=1) * math.sqrt(k)), float(b.std(ddof=1) * math.sqrt(k))
    var_b = float(np.var(b, ddof=1))
    beta = float(np.cov(p, b, ddof=1)[0, 1] / var_b) if var_b > 0 else None
    te = float((p - b).std(ddof=1) * math.sqrt(k))
    downside = p[p < risk_free / k] - risk_free / k
    dd = math.sqrt(float((downside ** 2).sum() / len(p)) * k) if len(downside) else 0.0
    sharpe = (rp - risk_free) / sp if sp > 0 else None
    out = {"annual_return": rp, "benchmark_return": rb, "volatility": sp, "benchmark_volatility": sb, "beta": beta,
           "sharpe": sharpe, "treynor": (rp - risk_free) / beta if beta else None,
           "jensens_alpha": rp - (risk_free + beta * (rb - risk_free)) if beta is not None else None,
           # Modigliani M²: the portfolio's return scaled to the benchmark's volatility; the excess over the
           # benchmark return is reported separately.
           "m_squared": (risk_free + sharpe * sb) if sharpe is not None else None,
           "m_squared_excess": (risk_free + sharpe * sb - rb) if sharpe is not None else None,
           "tracking_error": te, "information_ratio": (rp - rb) / te if te > 0 else None,
           "sortino": (rp - risk_free) / dd if dd > 0 else None,
           "max_drawdown": _max_drawdown(p),
           "notes": [f"Annualised arithmetically from {len(p)} periods ({k} per year).",
                     "Sortino downside deviation divides by all periods (n), counting only returns below the risk-free rate.",
                     "Maximum drawdown starts from the value before the first return.",
                     "Jensen's alpha and Treynor use beta against the benchmark given."]}
    return out


def _max_drawdown(r: np.ndarray) -> float:
    # Wealth starts at 1.0 before the first return, so a loss in the very first period counts.
    wealth = np.concatenate(([1.0], np.cumprod(1 + r)))
    peak = np.maximum.accumulate(wealth)
    return float(((wealth - peak) / peak).min())


# --------------------------------------------------------------------------- derivatives

def black_scholes(s: float, k: float, t: float, r: float, sigma: float, q: float = 0.0) -> dict:
    if s <= 0 or k <= 0 or t <= 0 or sigma <= 0:
        raise FinanceInputError("Spot, strike, time and volatility must be positive.")
    d1 = (math.log(s / k) + (r - q + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    df_r, df_q = math.exp(-r * t), math.exp(-q * t)
    call = s * df_q * _N.cdf(d1) - k * df_r * _N.cdf(d2)
    put = k * df_r * _N.cdf(-d2) - s * df_q * _N.cdf(-d1)
    pdf = _N.pdf(d1)
    greeks = {
        "call": {"delta": df_q * _N.cdf(d1), "gamma": df_q * pdf / (s * sigma * math.sqrt(t)), "vega": s * df_q * pdf * math.sqrt(t) / 100,
                 "theta": (-s * df_q * pdf * sigma / (2 * math.sqrt(t)) - r * k * df_r * _N.cdf(d2) + q * s * df_q * _N.cdf(d1)) / 365,
                 "rho": k * t * df_r * _N.cdf(d2) / 100},
        "put": {"delta": -df_q * _N.cdf(-d1), "gamma": df_q * pdf / (s * sigma * math.sqrt(t)), "vega": s * df_q * pdf * math.sqrt(t) / 100,
                "theta": (-s * df_q * pdf * sigma / (2 * math.sqrt(t)) + r * k * df_r * _N.cdf(-d2) - q * s * df_q * _N.cdf(-d1)) / 365,
                "rho": -k * t * df_r * _N.cdf(-d2) / 100},
    }
    return {"call": call, "put": put, "d1": d1, "d2": d2, "greeks": greeks,
            "parity_check": call - put - (s * df_q - k * df_r),
            "notes": ["Vega and rho are per 1 percentage point; theta is per calendar day.",
                      "Black-Scholes-Merton prices European options on a dividend yield q."]}


def binomial(s: float, k: float, t: float, r: float, sigma: float, steps: int = 200, q: float = 0.0,
             kind: str = "put", american: bool = True) -> dict:
    if steps < 1 or steps > 2000:
        raise FinanceInputError("Steps must be between 1 and 2,000.")
    if kind not in ("call", "put"):
        raise FinanceInputError("Option kind must be 'call' or 'put'.")
    if s <= 0 or k <= 0 or t <= 0 or sigma <= 0:
        raise FinanceInputError("Spot, strike, time and volatility must be positive.")
    dt = t / steps
    u = math.exp(sigma * math.sqrt(dt))
    d = 1 / u
    p = (math.exp((r - q) * dt) - d) / (u - d)
    if not 0 < p < 1:
        raise FinanceInputError("Risk-neutral probability is outside (0, 1); use more steps.")
    disc = math.exp(-r * dt)
    prices = s * u ** np.arange(steps, -1, -1) * d ** np.arange(0, steps + 1)
    payoff = np.maximum(prices - k, 0) if kind == "call" else np.maximum(k - prices, 0)
    values = payoff
    for i in range(steps - 1, -1, -1):
        values = disc * (p * values[:-1] + (1 - p) * values[1:])
        if american:
            spot = s * u ** np.arange(i, -1, -1) * d ** np.arange(0, i + 1)
            exercise = np.maximum(spot - k, 0) if kind == "call" else np.maximum(k - spot, 0)
            values = np.maximum(values, exercise)
    return {"value": float(values[0]), "u": u, "d": d, "p": p, "steps": steps, "kind": kind, "style": "American" if american else "European",
            "formula": "Cox-Ross-Rubinstein: u = e^(σ√Δt), d = 1/u, p = (e^((r−q)Δt) − d)/(u − d)"}


def put_call_parity(call: float, put: float, s: float, k: float, r: float, t: float, q: float = 0.0) -> dict:
    lhs = call + k * math.exp(-r * t)
    rhs = put + s * math.exp(-q * t)
    gap = lhs - rhs
    if abs(gap) < 1e-6 * max(1.0, s):
        action = "Parity holds: no arbitrage."
    elif gap > 0:
        action = ("The fiduciary call is overpriced: sell the call and borrow PV(K); buy the put and buy the share. "
                  "This locks in the mispricing today.")
    else:
        action = ("The protective put is overpriced: sell the put and short the share; buy the call and lend PV(K). "
                  "This locks in the mispricing today.")
    return {"fiduciary_call": lhs, "protective_put": rhs, "mispricing": gap, "action": action,
            "formula": "c + K·e^(−rT) = p + S·e^(−qT)"}


def strategy_payoff(legs: list[dict], spot_range: tuple[float, float] | None = None) -> dict:
    """legs: {type: call|put|stock, position: long|short, strike, premium, quantity}"""
    if not legs:
        raise FinanceInputError("Add at least one leg.")
    strikes = [l.get("strike") or 0 for l in legs if l["type"] != "stock"] + [l.get("premium") or 0 for l in legs if l["type"] == "stock"]
    centre = max(strikes) if strikes else 100.0
    lo, hi = spot_range or (0.0, centre * 2 if centre > 0 else 200.0)
    xs = np.linspace(lo, hi, 101)
    total = np.zeros_like(xs)
    cost = 0.0
    for l in legs:
        sign = 1 if l["position"] == "long" else -1
        q = float(l.get("quantity", 1))
        prem = float(l.get("premium") or 0)
        if l["type"] == "call":
            pay = np.maximum(xs - float(l["strike"]), 0)
        elif l["type"] == "put":
            pay = np.maximum(float(l["strike"]) - xs, 0)
        elif l["type"] == "stock":
            pay = xs.copy()
        else:
            raise FinanceInputError("Leg type must be call, put or stock.")
        total += sign * q * (pay - prem)
        cost += sign * q * prem
    breakevens: list[float] = []
    for i in range(len(xs)):
        if abs(total[i]) < 1e-12:
            pts = [float(xs[i])]
        elif i + 1 < len(xs) and total[i] * total[i + 1] < 0:
            pts = [float(xs[i] - total[i] * (xs[i + 1] - xs[i]) / (total[i + 1] - total[i]))]
        else:
            pts = []
        for x in pts:
            if not breakevens or abs(breakevens[-1] - x) > 1e-9 * max(1.0, abs(x)):
                breakevens.append(x)
    return {"points": [{"spot": float(x), "profit": float(v)} for x, v in zip(xs, total)], "net_premium": cost,
            "max_profit_in_range": float(total.max()), "max_loss_in_range": float(total.min()), "breakevens": breakevens}
