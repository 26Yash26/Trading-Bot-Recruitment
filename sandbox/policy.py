"""Static analysis of a submitted bot file (sandbox layer 1).

This is an *allowlist*, not a blacklist. Last year's site used a list of banned
substrings (``"import os"``, ``"__class__"``, ...), which loses to
``__im`` ``port__`` or ``getattr(obj, "__cla" + "ss__")``. Parsing to an AST and
allowing only what we recognise closes that whole family.

What survives here still has to get past the process sandbox (layers 2 and 3) —
this layer exists to reject obvious abuse with a clear message at submission
time, not to be the only thing standing between a participant and the VM.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

# Modules a bidding strategy has any business importing.
ALLOWED_MODULES = frozenset(
    {
        # stdlib — pure computation
        "math", "cmath", "random", "statistics", "decimal", "fractions",
        "itertools", "functools", "operator", "collections", "heapq", "bisect",
        "array", "copy", "enum", "dataclasses", "typing", "numbers", "abc",
        "string", "re", "json", "time", "datetime", "warnings",
        # third-party — numeric stack
        "numpy", "pandas", "scipy", "sklearn", "statsmodels",
    }
)

# Builtins that hand back the interpreter itself.
#
# __builtins__, __loader__ and __spec__ belong here, not just in _ESCAPE_ATTRS:
# they are implicit BARE globals in every module's namespace (no import, no
# attribute access needed), and CPython gives a non-__main__ module's
# __builtins__ as a *dict*, not the builtins module — so `__builtins__.eval` is
# an AttributeError, but `__builtins__["eval"]` hands back the real eval() with
# nothing else in this file noticing, because Subscript is not inspected at
# all. __loader__/__spec__ carry a loader object whose get_data(path) reads an
# arbitrary file. Confirmed against child.py's own loading mechanism:
#   _e = __builtins__["eval"]; _e("__import__('os').getcwd()")
# passed check_source() with zero violations before this fix.
BANNED_NAMES = frozenset(
    {
        "eval", "exec", "compile", "open", "__import__", "input", "breakpoint",
        "globals", "locals", "vars", "getattr", "setattr", "delattr", "dir",
        "exit", "quit", "help", "memoryview", "super", "object",
        "__builtins__", "__loader__", "__spec__",
    }
)

# Attribute names that walk the object graph up to the interpreter, even though
# the blanket dunder rule below already covers them. Listed for error clarity.
_ESCAPE_ATTRS = frozenset(
    {
        "__class__", "__bases__", "__subclasses__", "__mro__", "__globals__",
        "__code__", "__closure__", "__dict__", "__builtins__", "__reduce__",
        "__getattribute__", "__init_subclass__", "__loader__", "__spec__",
    }
)

# `.format` / `.format_map` / `.vformat` are a second, unrelated route to the
# same destination: the dotted path in `"{0.__class__.__bases__}".format(x)`
# lives inside a string literal, so it is never an ast.Attribute node at all —
# nothing above ever sees it. string.Formatter (string IS an allowed import)
# reaches the identical mini-language via .vformat. There is no legitimate use
# a bidding bot has for template formatting that an f-string (whose
# interpolated attributes DO go through visit_Attribute, since Python parses
# them as real expressions) or %-formatting (whose spec language has no
# attribute-drilling syntax at all) cannot do just as well.
_FORMAT_ATTRS = frozenset({"format", "format_map", "vformat"})

MAX_SOURCE_BYTES = 512 * 1024
MAX_AST_NODES = 200_000


@dataclass
class PolicyViolation:
    line: int
    message: str

    def __str__(self) -> str:  # pragma: no cover - formatting only
        return f"line {self.line}: {self.message}"


class _Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[PolicyViolation] = []

    def _flag(self, node: ast.AST, message: str) -> None:
        self.violations.append(PolicyViolation(getattr(node, "lineno", 0), message))

    # --- imports -------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root not in ALLOWED_MODULES:
                self._flag(node, f"import of '{alias.name}' is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            self._flag(node, "relative imports are not allowed")
        elif node.module:
            root = node.module.split(".")[0]
            if root not in ALLOWED_MODULES:
                self._flag(node, f"import from '{node.module}' is not allowed")
        self.generic_visit(node)

    # --- names and attributes ------------------------------------------------

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in BANNED_NAMES:
            self._flag(node, f"use of '{node.id}' is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        name = node.attr
        if name.startswith("__") and name.endswith("__"):
            why = "escapes the sandbox" if name in _ESCAPE_ATTRS else "is not allowed"
            self._flag(node, f"attribute '{name}' {why}")
        elif name in BANNED_NAMES:
            # A banned name is just as dangerous reached via `.name` on some
            # other allowed object as it is called bare — `mod.eval`, not just
            # `eval`. The dunder check above never fires for these since none
            # of eval/exec/open/... are dunder-shaped.
            self._flag(node, f"attribute '{name}' is not allowed")
        elif name in _FORMAT_ATTRS:
            self._flag(
                node,
                f"'{name}' is not allowed — it can read attributes named in a "
                "string, invisibly to this check; use an f-string or % formatting",
            )
        self.generic_visit(node)

    # --- statements that only make sense for an escape -----------------------

    def visit_Global(self, node: ast.Global) -> None:
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self.generic_visit(node)


def check_source(source: str) -> list[PolicyViolation]:
    """Return every policy violation in ``source`` (empty list = accepted)."""
    if len(source.encode("utf-8", errors="ignore")) > MAX_SOURCE_BYTES:
        return [PolicyViolation(0, f"file exceeds {MAX_SOURCE_BYTES // 1024} KB")]

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [PolicyViolation(exc.lineno or 0, f"syntax error: {exc.msg}")]

    node_count = sum(1 for _ in ast.walk(tree))
    if node_count > MAX_AST_NODES:
        return [PolicyViolation(0, "file is too large to analyse")]

    visitor = _Visitor()
    visitor.visit(tree)

    if not _defines_bot_class(tree):
        visitor.violations.append(
            PolicyViolation(0, "file does not define a top-level class named 'Bot'")
        )
    return visitor.violations


def _defines_bot_class(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Bot":
            has_get_bid = any(
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == "get_bid"
                for item in node.body
            )
            if has_get_bid:
                return True
    return False


def describe(violations: list[PolicyViolation], limit: int = 5) -> str:
    """Human-readable summary for the submitter."""
    shown = "; ".join(str(v) for v in violations[:limit])
    extra = len(violations) - limit
    return shown + (f" (+{extra} more)" if extra > 0 else "")
