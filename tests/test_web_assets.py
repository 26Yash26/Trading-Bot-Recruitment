"""The front end has no build step, so nothing else catches a broken module.

`deploy/nginx-app.conf` spells out the failure mode: ES modules resolve their
imports *before* executing anything, so one module that fails to parse, or one
`import { thing }` naming an export that does not exist, discards the whole
graph. The page renders the static footer and nothing else, with no error unless
devtools is open. There is no bundler, no linter and no CI here to notice.

So two cheap structural checks, run on every served module:

  1. delimiters balance, the realistic way a hand-edited template literal breaks;
  2. every named import resolves to a real export in the module it names.

Neither is a parser. Both catch the mistakes that actually happen when editing
1000-line files full of nested template literals by hand.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_JS = REPO_ROOT / "web" / "js"

#: Modules the browser loads. `server/late_variations.js` is served from the API
#: rather than as a static asset, but it is the same kind of file with the same
#: failure mode, so it is checked alongside.
MODULES = sorted(WEB_JS.rglob("*.js")) + [REPO_ROOT / "server" / "late_variations.js"]

PAIRS = {")": "(", "]": "[", "}": "{"}

#: A `/` here starts a regex literal, not a division. The usual heuristic: a
#: regex may follow an operator or an opening delimiter, never a value.
BEFORE_REGEX = set("(,=:[!&|?{};+-*%~^") | {""}


def check_delimiters(source: str, name: str) -> None:
    """Walk `source`, skipping strings and comments, and match every delimiter.

    Template literals are walked into, because `${...}` holds real code, and
    code inside a template literal is exactly where these files do their work.
    The brace opened by `${` is marked on the stack, so an object literal or an
    arrow-function body *inside* an interpolation closes itself rather than
    ending the interpolation early.
    """
    # (character, line, opened_an_interpolation)
    stack: list[tuple[str, int, bool]] = []
    in_template = False    # lexing a `...` literal rather than code
    i, line, n = 0, 1, len(source)
    previous = ""          # last significant character, for the regex heuristic

    def fail(message: str) -> None:
        raise AssertionError(f"{name}: {message}")

    while i < n:
        ch = source[i]

        if ch == "\n":
            line += 1
            i += 1
            continue

        if in_template:
            if ch == "\\":
                i += 2
                continue
            if ch == "`":
                in_template = False
                i += 1
                previous = "x"
                continue
            if ch == "$" and i + 1 < n and source[i + 1] == "{":
                stack.append(("{", line, True))
                in_template = False
                i += 2
                previous = "{"
                continue
            i += 1
            continue

        # --- ordinary code
        if source.startswith("//", i):
            nl = source.find("\n", i)
            if nl == -1:
                break
            i = nl
            continue
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            if end == -1:
                fail(f"unterminated block comment from line {line}")
            line += source.count("\n", i, end)
            i = end + 2
            continue

        if ch in "\"'":
            quote, i = ch, i + 1
            while i < n and source[i] != quote:
                if source[i] == "\\":
                    i += 1
                elif source[i] == "\n":
                    fail(f"unterminated string on line {line}")
                i += 1
            i += 1
            previous = "x"
            continue

        if ch == "`":
            in_template = True
            i += 1
            continue

        if ch == "/" and previous in BEFORE_REGEX:
            i += 1
            while i < n and source[i] != "/":
                if source[i] == "\\":
                    i += 1
                elif source[i] == "\n":
                    fail(f"unterminated regex on line {line}")
                i += 1
            i += 1
            while i < n and source[i].isalpha():   # flags
                i += 1
            previous = "x"
            continue

        if ch in "([{":
            stack.append((ch, line, False))
        elif ch in ")]}":
            if not stack:
                fail(f"stray {ch!r} on line {line}")
            opener, opened, interpolation = stack.pop()
            if opener != PAIRS[ch]:
                fail(
                    f"{ch!r} on line {line} closes {opener!r} opened on line {opened}"
                )
            if interpolation:
                # That `}` ended a `${...}`; the rest of the literal follows.
                in_template = True

        if not ch.isspace():
            previous = ch
        i += 1

    if in_template:
        raise AssertionError(f"{name}: unterminated template literal")
    if stack:
        opener, opened, _ = stack[-1]
        raise AssertionError(f"{name}: unclosed {opener!r} from line {opened}")


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_module_delimiters_balance(path):
    check_delimiters(path.read_text(encoding="utf-8"), path.name)


# --- imports resolve ------------------------------------------------------------

IMPORT_RE = re.compile(
    r"import\s*\{(?P<names>[^}]*)\}\s*from\s*[\"'](?P<source>[^\"']+)[\"']", re.S
)
EXPORT_RE = re.compile(
    r"^export\s+(?:async\s+)?(?:const|let|var|function|class)\s+(\w+)", re.M
)
EXPORT_LIST_RE = re.compile(r"^export\s*\{([^}]*)\}", re.M)


def exported_names(path: Path) -> set[str]:
    source = path.read_text(encoding="utf-8")
    names = set(EXPORT_RE.findall(source))
    for block in EXPORT_LIST_RE.findall(source):
        for entry in block.split(","):
            entry = entry.strip()
            if not entry:
                continue
            # `export { a as b }` publishes `b`.
            names.add(entry.split(" as ")[-1].strip())
    return names


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_named_imports_exist_in_the_module_they_name(path):
    """The link-time failure, caught at test time.

    `import { esc } from "../ui.js"` where `ui.js` no longer exports `esc` does
    not fail that one call, it discards every module in the graph, and the whole
    site renders blank.
    """
    source = path.read_text(encoding="utf-8")
    for match in IMPORT_RE.finditer(source):
        target = match.group("source")
        if not target.startswith("."):
            continue                       # a bare specifier; nothing to resolve
        resolved = (path.parent / target).resolve()
        assert resolved.is_file(), f"{path.name} imports missing {target}"

        available = exported_names(resolved)
        wanted = {
            entry.strip().split(" as ")[0].strip()
            for entry in match.group("names").split(",")
            if entry.strip()
        }
        missing = sorted(wanted - available)
        assert not missing, (
            f"{path.name} imports {', '.join(missing)} from {target}, "
            f"which does not export {'it' if len(missing) == 1 else 'them'}"
        )


# --- the checker itself ---------------------------------------------------------
#
# A structural check that cannot fail is worse than no check: it is a green tick
# that means nothing. These pin both directions.

VALID = {
    "object literal inside an interpolation":
        'const a = `x ${items.map((i) => { return i.n; }).join("")} y`;',
    "nested template literals":
        'const a = `${cond ? `<b>${esc(v)}</b>` : ""}`;',
    "a brace-heavy ternary inside an interpolation":
        'const a = `${ x ? "{" : "}" }`;',
    "regex literals":
        'const p = path.replace(/\\/+$/, "") || "/";\nconst RE = /^([A-Z]{2})_([1-9])$/i;',
    "division, which is not a regex":
        "const ratio = (done / total) * 100;",
    "braces and quotes inside a template's literal text":
        'const a = `class="w-{4} \'q\'" ${v}`;',
    "comments holding unbalanced delimiters":
        'const a = 1; // a stray ) and }\n/* and { in a block */\nconst b = 2;',
    "an apostrophe inside a double-quoted string":
        'const a = "it\'s fine";',
}

BROKEN = {
    "an unclosed brace": "function f() { return 1;",
    "a stray closer": "const a = 1; }",
    "mismatched pair": "const a = ( 1 ];",
    "an unterminated template literal": 'const a = `hello ${name}',
    "a brace left open inside an interpolation": 'const a = `${ items.map((i) => { ) }`;',
}


@pytest.mark.parametrize("source", VALID.values(), ids=list(VALID))
def test_the_checker_accepts_valid_javascript(source):
    check_delimiters(source, "sample.js")


@pytest.mark.parametrize("source", BROKEN.values(), ids=list(BROKEN))
def test_the_checker_rejects_broken_javascript(source):
    with pytest.raises(AssertionError):
        check_delimiters(source, "sample.js")


def test_a_missing_export_would_be_caught(tmp_path):
    """The import check, proved against a module that really is missing one."""
    (tmp_path / "ui.js").write_text("export const esc = (s) => s;\n", encoding="utf-8")
    consumer = tmp_path / "page.js"
    consumer.write_text('import { esc, gone } from "./ui.js";\n', encoding="utf-8")

    with pytest.raises(AssertionError, match="gone"):
        test_named_imports_exist_in_the_module_they_name(consumer)
