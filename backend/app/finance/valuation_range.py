"""Reverse DCF and Monte Carlo valuation range, built on the same FCFF model as dcf.run_dcf.

Reverse DCF: which value of one assumption (by default revenue growth in every forecast year)
makes the DCF value equal today's market price? Every other assumption stays as entered.

Monte Carlo: draws the uncertain assumptions from distributions the user chooses, runs the
full DCF for each draw and reports the spread of values. Draws that break the model (e.g.
WACC at or below terminal growth) are counted and excluded, never silently replaced.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import FinanceInputError
from .dcf import OUTPUTS, SENSITIVITY_VARIABLES, DCFInputs, get_variable, run_dcf, set_variable


REVERSE_RANGES = {
    "revenue_growth": (-0.5, 1.0),
    "ebit_margin": (-0.5, 0.9),
    "terminal_growth": (-0.2, None),  # upper bound is just below WACC
    "wacc": (None, 1.0),              # lower bound is just above terminal growth
    "exit_multiple": (0.1, 200.0),
}


@dataclass
class ReverseResult:
    variable: str
    variable_label: str
    output: str
    target: float
    implied: float | None
    base_value: float
    base_output: float | None
    curve: list[dict]
    message: str
    notes: list[str] = field(default_factory=list)


def _out(inp: DCFInputs, output: str) -> float | None:
    try:
        return OUTPUTS[output](run_dcf(inp))
    except FinanceInputError:
        return None


def reverse_dcf(base: DCFInputs, target: float, variable: str = "revenue_growth", output: str = "value_per_share") -> ReverseResult:
    if variable not in REVERSE_RANGES:
        raise FinanceInputError(f"Reverse DCF can solve for: {', '.join(REVERSE_RANGES)}.")
    if output not in ("value_per_share", "equity_value", "enterprise_value"):
        raise FinanceInputError("Target must be value per share, equity value or enterprise value.")
    if output == "value_per_share" and not base.shares_outstanding:
        raise FinanceInputError("Enter shares outstanding to solve for a share price.")
    if variable == "exit_multiple" and base.terminal_method != "exit_multiple":
        raise FinanceInputError("Exit multiple can only be solved when the terminal method is 'exit multiple'.")
    if variable == "terminal_growth" and base.terminal_method != "gordon":
        raise FinanceInputError("Terminal growth can only be solved with the Gordon growth terminal method.")
    lo, hi = REVERSE_RANGES[variable]
    if variable == "terminal_growth":
        hi = base.wacc - 0.0025
    if variable == "wacc":
        lo = (base.terminal_growth + 0.0025) if base.terminal_method == "gordon" else 0.001
    base_value = get_variable(base, variable)
    base_output = _out(base, output)

    xs = np.linspace(lo, hi, 121)
    ys = [_out(set_variable(base, variable, float(x)), output) for x in xs]
    # Find the first sign change of (value - target) and refine it by bisection.
    implied = None
    for i in range(len(xs) - 1):
        a, b = ys[i], ys[i + 1]
        if a is None or b is None:
            continue
        fa, fb = a - target, b - target
        if fa == 0:
            implied = float(xs[i])
            break
        if fa * fb < 0:
            x0, x1, f0 = float(xs[i]), float(xs[i + 1]), fa
            for _ in range(100):
                mid = (x0 + x1) / 2
                fm = _out(set_variable(base, variable, mid), output)
                if fm is None:
                    break
                fm -= target
                if abs(fm) < 1e-9 * max(1.0, abs(target)) or x1 - x0 < 1e-12:
                    break
                if f0 * fm < 0:
                    x1 = mid
                else:
                    x0, f0 = mid, fm
            implied = (x0 + x1) / 2
            break
    label = SENSITIVITY_VARIABLES[variable]
    notes = ["All other assumptions are kept exactly as entered."]
    if variable in ("revenue_growth", "ebit_margin"):
        notes.append(f"The solved {label.lower()} is applied to every forecast year.")
    if implied is None:
        msg = (f"No {label.lower()} between {lo:.1%} and {hi:.1%} gives that value. The market price may need other "
               "assumptions to change too (e.g. margins or WACC).") if variable != "exit_multiple" else \
              f"No exit multiple between {lo:g}× and {hi:g}× gives that value."
    else:
        shown = f"{implied:.2f}×" if variable == "exit_multiple" else f"{implied:.2%}"
        base_shown = f"{base_value:.2f}×" if variable == "exit_multiple" else f"{base_value:.2%}"
        direction = "more optimistic than" if implied > base_value else "less optimistic than" if implied < base_value else "the same as"
        if variable == "wacc":
            direction = "a lower required return than" if implied < base_value else "a higher required return than" if implied > base_value else "the same as"
        msg = f"The market price implies {label.lower()} of {shown}, which is {direction} your assumption of {base_shown}."
    curve = [{"x": float(x), "value": y} for x, y in zip(xs[::4], ys[::4])]
    return ReverseResult(variable, label, output, target, implied, base_value, base_output, curve, msg, notes)


# --------------------------------------------------------------------------- Monte Carlo

@dataclass
class Distribution:
    variable: str
    kind: str  # "normal" | "triangular" | "uniform"
    a: float   # normal: mean · triangular/uniform: low
    b: float   # normal: standard deviation · triangular: most likely · uniform: high
    c: float | None = None  # triangular: high
    clip_low: float | None = None
    clip_high: float | None = None


@dataclass
class MonteCarloResult:
    output: str
    simulations: int
    valid: int
    invalid: int
    seed: int
    base_output: float | None
    mean: float | None
    std: float | None
    percentiles: dict[str, float]
    histogram: list[dict]
    prob_above_target: float | None
    target: float | None
    distributions: list[dict]
    notes: list[str]


def _validate(d: Distribution):
    if d.variable not in SENSITIVITY_VARIABLES:
        raise FinanceInputError(f"Unknown variable '{d.variable}'.")
    if d.kind == "normal":
        if d.b <= 0:
            raise FinanceInputError(f"{SENSITIVITY_VARIABLES[d.variable]}: standard deviation must be positive.")
    elif d.kind == "triangular":
        if d.c is None or not d.a <= d.b <= d.c or d.a == d.c:
            raise FinanceInputError(f"{SENSITIVITY_VARIABLES[d.variable]}: triangular needs low ≤ most likely ≤ high, with low < high.")
    elif d.kind == "uniform":
        if d.a >= d.b:
            raise FinanceInputError(f"{SENSITIVITY_VARIABLES[d.variable]}: uniform needs low < high.")
    else:
        raise FinanceInputError(f"Unknown distribution '{d.kind}'.")


def _draw(rng: np.random.Generator, d: Distribution, n: int) -> np.ndarray:
    if d.kind == "normal":
        x = rng.normal(d.a, d.b, n)
    elif d.kind == "triangular":
        x = rng.triangular(d.a, d.b, float(d.c), n)
    else:
        x = rng.uniform(d.a, d.b, n)
    if d.clip_low is not None or d.clip_high is not None:
        x = np.clip(x, d.clip_low if d.clip_low is not None else -np.inf, d.clip_high if d.clip_high is not None else np.inf)
    return x


def monte_carlo(base: DCFInputs, dists: list[Distribution], output: str = "value_per_share", n: int = 5000,
                seed: int = 42, target: float | None = None) -> MonteCarloResult:
    if output not in ("value_per_share", "equity_value", "enterprise_value"):
        raise FinanceInputError("Output must be value per share, equity value or enterprise value.")
    if output == "value_per_share" and not base.shares_outstanding:
        raise FinanceInputError("Enter shares outstanding to simulate value per share.")
    if not dists:
        raise FinanceInputError("Choose at least one uncertain assumption.")
    if len({d.variable for d in dists}) != len(dists):
        raise FinanceInputError("Each assumption can have only one distribution.")
    if not 100 <= n <= 20000:
        raise FinanceInputError("Simulations must be between 100 and 20,000.")
    for d in dists:
        _validate(d)
    run_dcf(base)  # the base case itself must be valid
    rng = np.random.default_rng(seed)
    draws = {d.variable: _draw(rng, d, n) for d in dists}
    values = []
    invalid = 0
    for i in range(n):
        inp = base
        for var, arr in draws.items():
            inp = set_variable(inp, var, float(arr[i]))
        v = _out(inp, output)
        if v is None or not np.isfinite(v):
            invalid += 1
        else:
            values.append(v)
    notes = ["Each assumption is drawn independently; in reality growth, margins and WACC often move together, "
             "so the true spread may be wider or narrower.",
             f"Random seed {seed}: the same inputs always give the same result."]
    if invalid:
        notes.append(f"{invalid} of {n} draws were excluded because the model was invalid for them "
                     "(for example WACC at or below terminal growth).")
    arr = np.array(values)
    pct = {f"p{p}": float(np.percentile(arr, p)) for p in (5, 10, 25, 50, 75, 90, 95)} if len(arr) else {}
    hist = []
    if len(arr):
        lo, hi = np.percentile(arr, 0.5), np.percentile(arr, 99.5)
        if hi > lo:
            counts, edges = np.histogram(np.clip(arr, lo, hi), bins=30, range=(lo, hi))
            hist = [{"from": float(edges[k]), "to": float(edges[k + 1]), "count": int(counts[k])} for k in range(30)]
        notes.append("The chart trims the most extreme 0.5% at each end so the shape is readable; percentiles use every valid draw.")
    prob = float((arr > target).mean()) if target is not None and len(arr) else None
    return MonteCarloResult(output, n, len(arr), invalid, seed, _out(base, output),
                            float(arr.mean()) if len(arr) else None, float(arr.std(ddof=1)) if len(arr) > 1 else None,
                            pct, hist, prob, target,
                            [{"variable": d.variable, "label": SENSITIVITY_VARIABLES[d.variable], "kind": d.kind, "a": d.a, "b": d.b, "c": d.c}
                             for d in dists], notes)
