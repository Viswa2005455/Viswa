"""Sensitivity, tornado and scenario analysis on the DCF model.

Every cell is produced by re-running the full DCF model with the changed inputs —
nothing is interpolated or approximated.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from . import FinanceInputError
from .dcf import OUTPUTS, DCFInputs, check_variable, get_variable, run_dcf, set_variable


@dataclass
class GridCell:
    value: float | None
    error: str | None = None


def _output(inp: DCFInputs, output: str) -> float | None:
    if output not in OUTPUTS:
        raise FinanceInputError(f"Unknown output '{output}'.")
    return OUTPUTS[output](run_dcf(inp))


def two_way(base: DCFInputs, x_var: str, x_values: list[float], y_var: str, y_values: list[float],
            output: str) -> list[list[GridCell]]:
    """Rows follow y_values, columns follow x_values."""
    if x_var == y_var:
        raise FinanceInputError("Choose two different variables.")
    if len(x_values) * len(y_values) > 400:
        raise FinanceInputError("Sensitivity grid is limited to 400 cells.")
    check_variable(base, x_var)
    check_variable(base, y_var)
    grid: list[list[GridCell]] = []
    for y in y_values:
        row = []
        for x in x_values:
            try:
                inp = set_variable(set_variable(base, x_var, x), y_var, y)
                row.append(GridCell(_output(inp, output)))
            except FinanceInputError as e:
                row.append(GridCell(None, str(e)))
        grid.append(row)
    return grid


@dataclass
class TornadoBar:
    variable: str
    base_input: float
    low_input: float
    high_input: float
    low_output: float | None
    high_output: float | None
    swing: float
    error: str | None = None


def tornado(base: DCFInputs, ranges: dict[str, tuple[float, float]], output: str) -> tuple[float | None, list[TornadoBar]]:
    """ranges maps variable -> (low_value, high_value) as absolute input values."""
    base_out = _output(base, output)
    bars: list[TornadoBar] = []
    for var, (lo, hi) in ranges.items():
        try:
            check_variable(base, var)
            base_in = get_variable(base, var)
        except FinanceInputError as e:  # one unusable assumption fails its own bar, not the whole chart
            bars.append(TornadoBar(var, None, lo, hi, None, None, 0.0, str(e)))
            continue
        outs: list[float | None] = []
        err = None
        for v in (lo, hi):
            try:
                outs.append(_output(set_variable(base, var, v), output))
            except FinanceInputError as e:
                outs.append(None)
                err = str(e)
        valid = [o for o in outs if o is not None]
        swing = (max(valid) - min(valid)) if len(valid) == 2 else 0.0
        bars.append(TornadoBar(var, base_in, lo, hi, outs[0], outs[1], swing, err))
    bars.sort(key=lambda b: b.swing, reverse=True)
    return base_out, bars


@dataclass
class ScenarioDef:
    name: str
    revenue_growth_shift: float = 0.0  # added to every year's growth (decimal points)
    ebit_margin_shift: float = 0.0  # added to every year's margin
    overrides: dict[str, float] | None = None  # absolute values for scalar inputs (e.g. wacc)


def apply_scenario(base: DCFInputs, s: ScenarioDef) -> DCFInputs:
    inp = replace(base,
                  revenue_growth=[g + s.revenue_growth_shift for g in base.revenue_growth],
                  ebit_margin=[m + s.ebit_margin_shift for m in base.ebit_margin])
    for k, v in (s.overrides or {}).items():
        if k in ("revenue_growth", "ebit_margin"):
            raise FinanceInputError("Use the shift fields to change growth or margin in a scenario.")
        inp = set_variable(inp, k, v)
    return inp


def break_even(base: DCFInputs, var: str, output: str, target: float, low: float, high: float) -> float | None:
    """Value of `var` in [low, high] at which `output` equals `target` (bisection on the full model).
    Points where the model is invalid (e.g. WACC at or below terminal growth) are skipped, so an
    invalid end of the range does not hide a solution inside it."""
    check_variable(base, var)

    def f(x: float) -> float | None:
        try:
            out = _output(set_variable(base, var, x), output)
        except FinanceInputError:
            return None
        return None if out is None else out - target

    grid = [low + (high - low) * i / 200 for i in range(201)]
    vals = [f(x) for x in grid]
    if all(v is None for v in vals):
        raise FinanceInputError("The model is invalid across the whole search range.")
    bracket = None
    for (x0, v0), (x1, v1) in zip(zip(grid, vals), zip(grid[1:], vals[1:])):
        if v0 is None or v1 is None:
            continue
        if v0 == 0:
            return x0
        if v0 * v1 < 0:
            bracket = (x0, v0, x1, v1)
            break
    if bracket is None:
        return grid[-1] if vals[-1] == 0 else None
    low, f_lo, high, _ = bracket
    for _ in range(200):
        mid = (low + high) / 2
        f_mid = f(mid)
        if f_mid is None:
            raise FinanceInputError("The model is invalid between two valid points of the search range.")
        if abs(f_mid) < 1e-9 or (high - low) < 1e-12:
            return mid
        if f_lo * f_mid < 0:
            high = mid
        else:
            low, f_lo = mid, f_mid
    return (low + high) / 2
