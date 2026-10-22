"""Time-series forecasting for financial series (revenue, expenses, cash).

Methods: linear trend (OLS), simple moving average, simple exponential smoothing (SES),
and constant growth (CAGR). Accuracy is measured with a time-aware holdout: the model is
fitted only on observations before the holdout window and scored on the window, so it is
never trained and tested on the same observations.

Prediction intervals are provided for the linear trend (classical OLS interval, which
assumes independent, normally distributed residuals) and approximated for SES. Forecasts
are estimates, never guarantees.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from scipy import stats

from . import FinanceInputError

Method = Literal["linear", "moving_average", "ses", "cagr"]


@dataclass
class Forecast:
    point: list[float]
    lower: list[float | None]
    upper: list[float | None]
    fitted: list[float | None]
    params: dict[str, float]


@dataclass
class ForecastResult:
    method: str
    history: list[float]
    forecast: list[float]
    lower: list[float | None]
    upper: list[float | None]
    fitted: list[float | None]
    params: dict[str, float]
    backtest: dict[str, float | None]
    confidence: float
    notes: list[str] = field(default_factory=list)


def _validate(series: list[float], min_len: int) -> np.ndarray:
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in series):
        raise FinanceInputError("The series has missing values. Fill or remove them explicitly; they are not treated as zero.")
    y = np.asarray(series, dtype=float)
    if len(y) < min_len:
        raise FinanceInputError(f"This method needs at least {min_len} historical observations.")
    return y


def linear(y: np.ndarray, h: int, conf: float) -> Forecast:
    n = len(y)
    x = np.arange(n, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    fitted = intercept + slope * x
    xf = np.arange(n, n + h, dtype=float)
    point = intercept + slope * xf
    lower: list[float | None] = [None] * h
    upper: list[float | None] = [None] * h
    if n > 2:
        resid = y - fitted
        s = math.sqrt(float(np.sum(resid ** 2)) / (n - 2))
        tcrit = stats.t.ppf(0.5 + conf / 2, n - 2)
        sxx = float(np.sum((x - x.mean()) ** 2))
        half = tcrit * s * np.sqrt(1 + 1 / n + (xf - x.mean()) ** 2 / sxx)
        lower, upper = list(point - half), list(point + half)
    return Forecast(list(point), lower, upper, list(fitted), {"slope": float(slope), "intercept": float(intercept)})


def moving_average(y: np.ndarray, h: int, window: int) -> Forecast:
    if window < 1 or window > len(y):
        raise FinanceInputError("Moving-average window must be between 1 and the number of observations.")
    level = float(np.mean(y[-window:]))
    fitted: list[float | None] = [None] * window + [float(np.mean(y[i - window:i])) for i in range(window, len(y))]
    return Forecast([level] * h, [None] * h, [None] * h, fitted, {"window": window})


def _ses_fit(y: np.ndarray, alpha: float) -> tuple[list[float], float]:
    level = y[0]
    fitted = [float(level)]
    for v in y[1:]:
        fitted.append(float(level))  # one-step-ahead forecast made before seeing v
        level = alpha * v + (1 - alpha) * level
    return fitted, float(level)


def ses(y: np.ndarray, h: int, alpha: float | None, conf: float) -> Forecast:
    if alpha is None:
        # Choose alpha minimising one-step-ahead squared error (grid search; deterministic).
        best = min(np.linspace(0.05, 1.0, 96),
                   key=lambda a: float(np.sum((y[1:] - np.array(_ses_fit(y, a)[0][1:])) ** 2)))
        alpha = float(best)
    if not 0 < alpha <= 1:
        raise FinanceInputError("Smoothing factor alpha must be in (0, 1].")
    fitted, level = _ses_fit(y, alpha)
    resid = y[1:] - np.array(fitted[1:])
    lower: list[float | None] = [None] * h
    upper: list[float | None] = [None] * h
    if len(resid) >= 3:
        # One-step forecast errors are not centred on their mean: a biased forecast (e.g. a trend the
        # flat SES level keeps missing) must widen the interval, so sigma = sqrt(SSE / n).
        sigma = float(math.sqrt(np.mean(resid ** 2)))
        z = stats.norm.ppf(0.5 + conf / 2)
        # Variance of the h-step SES forecast grows as 1 + (h-1) alpha^2 (ETS(A,N,N)).
        half = [z * sigma * math.sqrt(1 + (k - 1) * alpha ** 2) for k in range(1, h + 1)]
        lower = [level - d for d in half]
        upper = [level + d for d in half]
    return Forecast([level] * h, lower, upper, [None] + fitted[1:], {"alpha": alpha})


def cagr(y: np.ndarray, h: int) -> Forecast:
    if y[0] <= 0 or y[-1] <= 0:
        raise FinanceInputError("Constant-growth (CAGR) forecasting needs positive first and last values.")
    n = len(y) - 1
    g = (y[-1] / y[0]) ** (1 / n) - 1
    point = [float(y[-1] * (1 + g) ** k) for k in range(1, h + 1)]
    fitted = [float(y[0] * (1 + g) ** k) for k in range(len(y))]
    return Forecast(point, [None] * h, [None] * h, fitted, {"growth_rate": float(g)})


def _run(method: Method, y: np.ndarray, h: int, conf: float, window: int, alpha: float | None) -> Forecast:
    if method == "linear":
        return linear(y, h, conf)
    if method == "moving_average":
        return moving_average(y, h, window)
    if method == "ses":
        return ses(y, h, alpha, conf)
    if method == "cagr":
        return cagr(y, h)
    raise FinanceInputError(f"Unknown method '{method}'.")


def error_metrics(actual: list[float], predicted: list[float]) -> dict[str, float | None]:
    a, p = np.asarray(actual, float), np.asarray(predicted, float)
    err = a - p
    mae = float(np.mean(np.abs(err)))
    rmse = float(math.sqrt(np.mean(err ** 2)))
    # Percentage error is undefined where the actual is zero, so those periods are left out of MAPE.
    nz = a != 0
    mape = float(np.mean(np.abs(err[nz] / a[nz])) * 100) if np.any(nz) else None
    return {"mae": mae, "rmse": rmse, "mape": mape}


def forecast(series: list[float], method: Method, horizon: int, *, confidence: float = 0.95,
             window: int = 3, alpha: float | None = None, holdout: int | None = None) -> ForecastResult:
    if not 1 <= horizon <= 60:
        raise FinanceInputError("Forecast horizon must be between 1 and 60 periods.")
    if not 0.5 <= confidence < 1:
        raise FinanceInputError("Confidence level must be between 0.5 and 0.99.")
    min_len = {"linear": 3, "moving_average": max(window, 2), "ses": 3, "cagr": 2}.get(method, 3)
    y = _validate(series, min_len)
    notes: list[str] = []

    fc = _run(method, y, horizon, confidence, window, alpha)

    # Time-aware holdout backtest.
    if holdout is None:
        holdout = max(1, min(len(y) // 4, 12))
    backtest: dict[str, float | None] = {"holdout": holdout, "mae": None, "rmse": None, "mape": None}
    if len(y) - holdout >= min_len:
        train = y[:-holdout]
        try:
            bt = _run(method, train, holdout, confidence, window, alpha)
        except FinanceInputError as e:  # the forecast itself is still valid; only accuracy is unknown
            notes.append(f"Backtest could not run on the training window ({e}); accuracy could not be measured.")
        else:
            backtest.update(error_metrics(list(y[-holdout:]), bt.point))
            zeros = int(np.sum(y[-holdout:] == 0))
            if zeros:
                notes.append(f"MAPE leaves out {zeros} holdout period(s) where the actual value is zero.")
    else:
        notes.append("Not enough history for a holdout backtest; accuracy could not be measured.")

    if len(y) < 8:
        notes.append("Short history: forecasts and intervals are highly uncertain.")
    if method == "moving_average":
        notes.append("Moving average projects a flat level; it does not capture trend or seasonality.")
    if method == "cagr":
        notes.append("CAGR uses only the first and last observations; intermediate volatility is ignored.")
    if method == "linear":
        notes.append("Intervals assume independent, normally distributed residuals around a straight-line trend.")
    notes.append("Seasonality is not modelled in this version.")

    return ForecastResult(method, list(map(float, y)), fc.point, fc.lower, fc.upper, fc.fitted, fc.params,
                          backtest, confidence, notes)
