"""A small, safe evaluator for common Excel formulas.

Why: many financial exports (e.g. Screener.in, Moneycontrol, files written by scripts) store
formulas but no saved results, so reading the file without Excel gives empty cells. This
module recalculates the common cases so the data can still be analysed. Every value it
produces is reported as "calculated by Finance Intelligence Studio" so the user can verify it
against Excel.

Safety: formulas are tokenised and parsed by hand — nothing is passed to Python's eval or
exec. Recursion depth, the number of evaluated cells and range sizes are capped, and
circular references are detected.

Supported: numbers, strings, TRUE/FALSE, cell references (A1, $A$1, Sheet!A1, 'My Sheet'!A1),
ranges inside functions, + - * / ^ & %, comparisons (= <> < > <= >=), and the functions SUM,
AVERAGE, MIN, MAX, COUNT, COUNTA, ABS, ROUND, ROUNDUP, ROUNDDOWN, IF, IFERROR, AND, OR, NOT,
SUMPRODUCT, PRODUCT, MEDIAN, POWER, SQRT, LN, EXP, INT, MOD. Anything else is reported as
unsupported and left blank.
"""

from __future__ import annotations

import math
import re
from typing import Any, Callable

from openpyxl.utils import column_index_from_string


class FormulaError(Exception):
    """An Excel error value such as #DIV/0! (IFERROR can catch these)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Unsupported(Exception):
    """The formula uses something this evaluator does not implement."""


class TooDeep(Unsupported):
    """A chain of formulas is too long to follow in one go (not cached, so it can be retried)."""


_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<ref>(?:(?:'(?:[^']|'')+'|[A-Za-z_][\w.]*)!)?\$?[A-Za-z]{1,3}\$?\d+(?::\$?[A-Za-z]{1,3}\$?\d+)?(?![\w(]))
  | (?P<num>\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|\.\d+)
  | (?P<str>"(?:[^"]|"")*")
  | (?P<func>[A-Za-z][A-Za-z0-9.]*(?=\())
  | (?P<bool>TRUE|FALSE)\b
  | (?P<op><>|<=|>=|[-+*/^&%=<>(),:])
""", re.X | re.I)

MAX_CELLS = 200_000
MAX_DEPTH = 50  # about 12 Python frames per level, well inside the recursion limit
MAX_RANGE = 50_000


def tokenize(formula: str) -> list[tuple[str, str]]:
    s = formula[1:] if formula.startswith("=") else formula
    pos, out = 0, []
    while pos < len(s):
        m = _TOKEN.match(s, pos)
        if not m:
            raise Unsupported(f"syntax near '{s[pos:pos + 12]}'")
        kind = m.lastgroup
        if kind != "ws":
            out.append((kind, m.group()))
        pos = m.end()
    return out


def _split_ref(text: str, current_sheet: str) -> tuple[str, str]:
    if "!" in text:
        sheet, addr = text.rsplit("!", 1)
        if sheet.startswith("'"):
            sheet = sheet[1:-1].replace("''", "'")
        return sheet, addr.replace("$", "").upper()
    return current_sheet, text.replace("$", "").upper()


def _rc(addr: str) -> tuple[int, int]:
    m = re.match(r"([A-Z]{1,3})(\d+)$", addr)
    if not m:
        raise Unsupported(f"reference {addr}")
    return int(m.group(2)) - 1, column_index_from_string(m.group(1)) - 1


class Range:
    def __init__(self, values: list[Any]):
        self.values = values


def _num(v: Any) -> float:
    """Excel coercion for arithmetic: blank -> 0, TRUE -> 1, numeric text -> number."""
    if isinstance(v, FormulaError):
        raise v
    if v is None or v == "":
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", ""))
        except ValueError:
            raise FormulaError("#VALUE!")
    raise FormulaError("#VALUE!")  # dates etc. are not supported in arithmetic here


def _flatten(args: list[Any]) -> list[Any]:
    out = []
    for a in args:
        out.extend(a.values if isinstance(a, Range) else [a])
    return out


def _numbers(args: list[Any]) -> list[float]:
    """Numbers for SUM/AVERAGE/...: ranges ignore text and blanks, like Excel."""
    out = []
    for a in args:
        if isinstance(a, Range):
            for v in a.values:
                if isinstance(v, FormulaError):
                    raise v
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    out.append(float(v))
        else:
            out.append(_num(a))
    return out


def _round(x: float, digits: float, mode: str) -> float:
    f = 10 ** int(digits)
    if mode == "up":
        return math.copysign(math.ceil(abs(x) * f - 1e-12) / f, x)
    if mode == "down":
        return math.copysign(math.floor(abs(x) * f + 1e-12) / f, x)
    return math.copysign(math.floor(abs(x) * f + 0.5) / f, x)  # Excel rounds half away from zero


def _truthy(v: Any) -> bool:
    if isinstance(v, FormulaError):
        raise v
    if isinstance(v, str):
        if v.upper() in ("TRUE", "FALSE"):
            return v.upper() == "TRUE"
        raise FormulaError("#VALUE!")
    return bool(_num(v))


def _raise(code: str):
    raise FormulaError(code)


def _guard(fn: Callable[[], float]) -> float:
    try:
        return fn()
    except (OverflowError, ValueError, ZeroDivisionError):
        raise FormulaError("#NUM!")


def _power(x: float, y: float) -> float:
    if x == 0 and y < 0:
        raise FormulaError("#DIV/0!")
    r = _guard(lambda: x ** y)
    if isinstance(r, complex):
        raise FormulaError("#NUM!")
    return r


def _median(n: list[float]) -> float:
    if not n:
        raise FormulaError("#NUM!")
    n = sorted(n)
    m = len(n) // 2
    return n[m] if len(n) % 2 else (n[m - 1] + n[m]) / 2


def _mod(x: float, y: float) -> float:
    if y == 0:
        raise FormulaError("#DIV/0!")
    return x - y * math.floor(x / y)  # Excel: result has the sign of the divisor


def _sumproduct(args: list[Any]) -> float:
    arrays = [a.values if isinstance(a, Range) else [a] for a in args]
    if len({len(a) for a in arrays}) != 1:
        raise FormulaError("#VALUE!")
    total = 0.0
    for items in zip(*arrays):
        p = 1.0
        for v in items:
            p *= v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0
        total += p
    return total


FUNCS: dict[str, Callable[[list[Any]], Any]] = {
    "SUM": lambda a: sum(_numbers(a)),
    "AVERAGE": lambda a: sum(n) / len(n) if (n := _numbers(a)) else _raise("#DIV/0!"),
    "MIN": lambda a: min(_numbers(a), default=0.0),
    "MAX": lambda a: max(_numbers(a), default=0.0),
    "COUNT": lambda a: float(sum(1 for v in _flatten(a) if isinstance(v, (int, float)) and not isinstance(v, bool))),
    "COUNTA": lambda a: float(sum(1 for v in _flatten(a) if v not in (None, ""))),
    "ABS": lambda a: abs(_num(a[0])),
    "ROUND": lambda a: _round(_num(a[0]), _num(a[1]) if len(a) > 1 else 0, "half"),
    "ROUNDUP": lambda a: _round(_num(a[0]), _num(a[1]) if len(a) > 1 else 0, "up"),
    "ROUNDDOWN": lambda a: _round(_num(a[0]), _num(a[1]) if len(a) > 1 else 0, "down"),
    "AND": lambda a: all(_truthy(v) for v in _flatten(a)),
    "OR": lambda a: any(_truthy(v) for v in _flatten(a)),
    "NOT": lambda a: not _truthy(a[0]),
    "SUMPRODUCT": _sumproduct,
    "PRODUCT": lambda a: math.prod(_numbers(a)),
    "MEDIAN": lambda a: _median(_numbers(a)),
    "POWER": lambda a: _power(_num(a[0]), _num(a[1])),
    "SQRT": lambda a: math.sqrt(x) if (x := _num(a[0])) >= 0 else _raise("#NUM!"),
    "LN": lambda a: math.log(x) if (x := _num(a[0])) > 0 else _raise("#NUM!"),
    "EXP": lambda a: _guard(lambda: math.exp(_num(a[0]))),
    "INT": lambda a: float(math.floor(_num(a[0]))),
    "MOD": lambda a: _mod(_num(a[0]), _num(a[1])),
}
LAZY = {"IF", "IFERROR"}


class WorkbookEvaluator:
    """Evaluates formula cells on demand across all sheets of a workbook.

    values:   {sheet: grid of stored values (row-major, 0-based)}
    formulas: {sheet: {(row, col): "=formula"}}
    """

    def __init__(self, values: dict[str, list[list[Any]]], formulas: dict[str, dict[tuple[int, int], str]]):
        self.values = values
        self.formulas = formulas
        self.cache: dict[tuple[str, int, int], Any] = {}
        self.visiting: set[tuple[str, int, int]] = set()
        self.evaluated = 0
        self.unsupported: dict[str, int] = {}
        self.sheet_lookup = {s.lower(): s for s in values}

    # -- cell access -------------------------------------------------------
    def _stored(self, sheet: str, r: int, c: int) -> Any:
        grid = self.values.get(sheet)
        if grid is None or r >= len(grid) or c >= len(grid[r]):
            return None
        return grid[r][c]

    def cell(self, sheet: str, r: int, c: int) -> Any:
        sheet = self.sheet_lookup.get(sheet.lower(), sheet)
        if sheet not in self.values:
            raise FormulaError("#REF!")
        f = self.formulas.get(sheet, {}).get((r, c))
        stored = self._stored(sheet, r, c)
        if f is None or stored not in (None, ""):
            return stored
        return self.evaluate_cell(sheet, r, c)

    def evaluate_cell(self, sheet: str, r: int, c: int) -> Any:
        key = (sheet, r, c)
        if key in self.cache:
            cached = self.cache[key]
            if isinstance(cached, Unsupported):
                raise cached
            return cached
        if key in self.visiting:
            raise FormulaError("#CIRCULAR")
        if len(self.visiting) > MAX_DEPTH:
            raise TooDeep("formula chain too deep")
        self.evaluated += 1
        if self.evaluated > MAX_CELLS:
            raise TooDeep("too many formula cells")
        self.visiting.add(key)
        try:
            value = self.evaluate(self.formulas[sheet][(r, c)], sheet)
        except FormulaError as e:
            value = e
        except TooDeep:
            raise
        except Unsupported as e:
            self.cache[key] = e
            raise
        finally:
            self.visiting.discard(key)
        self.cache[key] = value
        return value

    # -- parsing / evaluation ------------------------------------------------
    def evaluate(self, formula: str, sheet: str) -> Any:
        tokens = tokenize(formula)
        p = _Parser(tokens, self, sheet)
        result = p.expr()
        if p.i != len(tokens):
            raise Unsupported("unexpected trailing input")
        if isinstance(result, Range):
            if len(result.values) == 1:
                return result.values[0]
            raise FormulaError("#VALUE!")
        return result

    def range_values(self, text: str, sheet: str) -> Range:
        sh, addr = _split_ref(text, sheet)
        a, b = addr.split(":")
        (r1, c1), (r2, c2) = _rc(a), _rc(b)
        r1, r2 = sorted((r1, r2))
        c1, c2 = sorted((c1, c2))
        if (r2 - r1 + 1) * (c2 - c1 + 1) > MAX_RANGE:
            raise Unsupported("range too large")
        return Range([self.cell(sh, r, c) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)])


class _Parser:
    """Recursive-descent parser that evaluates while parsing (operator precedence like Excel)."""

    def __init__(self, tokens, ev: WorkbookEvaluator, sheet: str):
        self.t, self.i, self.ev, self.sheet = tokens, 0, ev, sheet

    def peek(self, value: str | None = None, kind: str | None = None) -> bool:
        if self.i >= len(self.t):
            return False
        k, v = self.t[self.i]
        return (value is None or v.upper() == value) and (kind is None or k == kind)

    def take(self) -> tuple[str, str]:
        if self.i >= len(self.t):
            raise Unsupported("unexpected end of formula")
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expect(self, value: str) -> None:
        k, v = self.take()
        if v != value:
            raise Unsupported(f"expected '{value}'")

    # comparison < concatenation < additive < multiplicative < power < unary < percent < primary
    def expr(self):
        left = self.concat()
        while self.peek(kind="op") and self.t[self.i][1] in ("=", "<>", "<", ">", "<=", ">="):
            op = self.take()[1]
            right = self.concat()
            left = self._compare(op, left, right)
        return left

    def _compare(self, op, a, b):
        for v in (a, b):
            if isinstance(v, FormulaError):
                raise v
        if isinstance(a, str) or isinstance(b, str):
            x, y = str(a if a is not None else "").lower(), str(b if b is not None else "").lower()
        else:
            x, y = _num(a), _num(b)
        return {"=": x == y, "<>": x != y, "<": x < y, ">": x > y, "<=": x <= y, ">=": x >= y}[op]

    def concat(self):
        left = self.additive()
        while self.peek("&"):
            self.take()
            right = self.additive()
            left = f"{self._text(left)}{self._text(right)}"
        return left

    @staticmethod
    def _text(v):
        if isinstance(v, FormulaError):
            raise v
        if v is None:
            return ""
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)

    def additive(self):
        left = self.term()
        while self.peek("+") or self.peek("-"):
            op = self.take()[1]
            right = self.term()
            left = _num(left) + _num(right) if op == "+" else _num(left) - _num(right)
        return left

    def term(self):
        left = self.power()
        while self.peek("*") or self.peek("/"):
            op = self.take()[1]
            right = self.power()
            if op == "*":
                left = _num(left) * _num(right)
            else:
                d = _num(right)
                if d == 0:
                    raise FormulaError("#DIV/0!")
                left = _num(left) / d
        return left

    def power(self):
        base = self.unary()
        if self.peek("^"):
            self.take()
            exp = self.power()
            return _power(_num(base), _num(exp))
        return base

    def unary(self):
        if self.peek("-"):
            self.take()
            return -_num(self.unary())
        if self.peek("+"):
            self.take()
            return _num(self.unary())
        v = self.primary()
        while self.peek("%"):
            self.take()
            v = _num(v) / 100
        return v

    def primary(self):
        kind, text = self.take()
        if kind == "num":
            return float(text)
        if kind == "str":
            return text[1:-1].replace('""', '"')
        if kind == "bool":
            return text.upper() == "TRUE"
        if kind == "ref":
            if ":" in text:
                return self.ev.range_values(text, self.sheet)
            sh, addr = _split_ref(text, self.sheet)
            r, c = _rc(addr)
            v = self.ev.cell(sh, r, c)
            if isinstance(v, FormulaError):
                raise v
            return v
        if kind == "func":
            return self.function(text.upper())
        if text == "(":
            v = self.expr()
            self.expect(")")
            return v
        raise Unsupported(f"token '{text}'")

    def _args_raw(self) -> list[int]:
        """Return token start indices of each argument without evaluating (for IF/IFERROR)."""
        self.expect("(")
        starts, depth = [], 0
        if self.peek(")"):
            self.take()
            return starts
        starts.append(self.i)
        while True:
            k, v = self.take()
            if v == "(":
                depth += 1
            elif v == ")":
                if depth == 0:
                    return starts
                depth -= 1
            elif v == "," and depth == 0:
                starts.append(self.i)

    def _eval_at(self, start: int):
        saved = self.i
        self.i = start
        try:
            return self.expr()
        finally:
            self.i = saved

    def function(self, name: str):
        if name in LAZY:
            starts = self._args_raw()
            if name == "IF":
                if not 2 <= len(starts) <= 3:
                    raise Unsupported("IF needs 2 or 3 arguments")
                cond = _truthy(self._eval_at(starts[0]))
                if cond:
                    return self._eval_at(starts[1])
                return self._eval_at(starts[2]) if len(starts) == 3 else False
            if len(starts) != 2:
                raise Unsupported("IFERROR needs 2 arguments")
            try:
                v = self._eval_at(starts[0])
                if isinstance(v, FormulaError):
                    raise v
                return v
            except FormulaError:
                return self._eval_at(starts[1])
        if name not in FUNCS:
            self.ev.unsupported[name] = self.ev.unsupported.get(name, 0) + 1
            raise Unsupported(f"function {name}")
        self.expect("(")
        args = []
        if not self.peek(")"):
            while True:
                args.append(self.expr())
                if self.peek(","):
                    self.take()
                    continue
                break
        self.expect(")")
        try:
            return FUNCS[name](args)
        except IndexError:
            raise Unsupported(f"{name}: missing argument")
