#!/usr/bin/env python3
"""Offline sanity checks for the Terraform configuration.

This does NOT replace `terraform validate` / `terraform plan`. It exists for
environments without the Terraform binary and catches the most common
mistakes before you get there:

* unbalanced braces / brackets / parentheses / quotes and unterminated heredocs
* references to undeclared variables, locals, resources or data sources
* declared but unused variables

Usage: python3 scripts/tf_static_check.py [terraform_dir]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BLOCK_RE = re.compile(r'^\s*(resource|data)\s+"([^"]+)"\s+"([^"]+)"', re.M)
VAR_DECL_RE = re.compile(r'^\s*variable\s+"([^"]+)"', re.M)
OUTPUT_RE = re.compile(r'^\s*output\s+"([^"]+)"', re.M)
REF_VAR_RE = re.compile(r"\bvar\.([A-Za-z0-9_]+)")
REF_LOCAL_RE = re.compile(r"\blocal\.([A-Za-z0-9_]+)")
REF_DATA_RE = re.compile(r"\bdata\.([a-z0-9_]+)\.([A-Za-z0-9_]+)")
REF_RES_RE = re.compile(r"(?<![.\w\"])((?:aws|random)_[a-z0-9_]+)\.([A-Za-z0-9_]+)")


def strip_comments_and_strings(text: str) -> tuple[str, list[str]]:
    """Return code with comments removed and string contents blanked
    (interpolations kept), plus a list of balance errors."""
    out: list[str] = []
    errors: list[str] = []
    i, n = 0, len(text)
    line = 1
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
        if text.startswith("<<", i) and re.match(r"<<-?([A-Z_]+)\n", text[i:]):
            m = re.match(r"<<-?([A-Z_]+)\n", text[i:])
            assert m
            marker = m.group(1)
            end = re.compile(rf"^\s*{marker}\s*$", re.M)
            em = end.search(text, i + m.end())
            if not em:
                errors.append(f"line {line}: unterminated heredoc {marker}")
                break
            body = text[i + m.end(): em.start()]
            out.append('""' + "".join(re.findall(r"\$\{[^}]*\}", body)))
            line += text[i: em.end()].count("\n")
            i = em.end()
            continue
        if c == "#" or text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i)
            if j < 0:
                errors.append(f"line {line}: unterminated block comment")
                break
            i = j + 2
            continue
        if c == '"':
            j = i + 1
            depth = 0
            interp: list[str] = []
            buf = ""
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text.startswith("${", j):
                    depth += 1
                    buf = "${"
                    j += 2
                    continue
                if depth:
                    buf += text[j]
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                        if depth == 0:
                            interp.append(buf)
                            buf = ""
                    j += 1
                    continue
                if text[j] == '"':
                    break
                if text[j] == "\n":
                    errors.append(f"line {line}: newline inside string")
                    break
                j += 1
            else:
                errors.append(f"line {line}: unterminated string")
            out.append('"' + " ".join(interp) + '"')
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out), errors


def check_balance(code: str) -> list[str]:
    pairs = {"}": "{", "]": "[", ")": "("}
    stack: list[tuple[str, int]] = []
    errors = []
    line = 1
    for ch in code:
        if ch == "\n":
            line += 1
        if ch in "{[(":
            stack.append((ch, line))
        elif ch in "}])":
            if not stack or stack[-1][0] != pairs[ch]:
                errors.append(f"line {line}: unexpected '{ch}'")
                return errors
            stack.pop()
    for ch, ln in stack:
        errors.append(f"line {ln}: unclosed '{ch}'")
    return errors


def locals_keys(code: str) -> set[str]:
    keys: set[str] = set()
    for m in re.finditer(r"^\s*locals\s*\{", code, re.M):
        depth = 1
        i = m.end()
        start = i
        while i < len(code) and depth:
            if code[i] == "{":
                depth += 1
            elif code[i] == "}":
                depth -= 1
            i += 1
        body = code[start: i - 1]
        # top-level assignments only (depth 0 within the locals body)
        d = 0
        for raw in body.split("\n"):
            if d == 0:
                km = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", raw)
                if km:
                    keys.add(km.group(1))
            d += raw.count("{") + raw.count("[") + raw.count("(") - raw.count("}") - raw.count("]") - raw.count(")")
    return keys


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "terraform")
    files = sorted(root.glob("*.tf"))
    problems: list[str] = []
    resources: set[tuple[str, str]] = set()
    datas: set[tuple[str, str]] = set()
    variables: set[str] = set()
    locals_: set[str] = set()
    codes: dict[Path, str] = {}

    for f in files:
        code, errs = strip_comments_and_strings(f.read_text())
        problems += [f"{f.name}: {e}" for e in errs]
        problems += [f"{f.name}: {e}" for e in check_balance(code)]
        codes[f] = code
        raw = f.read_text()
        for kind, typ, name in BLOCK_RE.findall(raw):
            (resources if kind == "resource" else datas).add((typ, name))
        variables |= set(VAR_DECL_RE.findall(raw))
        locals_ |= locals_keys(code)

    used_vars: set[str] = set()
    for f, code in codes.items():
        for v in REF_VAR_RE.findall(code):
            used_vars.add(v)
            if v not in variables:
                problems.append(f"{f.name}: undeclared variable var.{v}")
        for loc in REF_LOCAL_RE.findall(code):
            if loc not in locals_:
                problems.append(f"{f.name}: undeclared local.{loc}")
        for typ, name in REF_DATA_RE.findall(code):
            if (typ, name) not in datas:
                problems.append(f"{f.name}: undeclared data.{typ}.{name}")
        for typ, name in REF_RES_RE.findall(code):
            if (typ, name) not in resources:
                problems.append(f"{f.name}: undeclared resource {typ}.{name}")

    for v in sorted(variables - used_vars):
        problems.append(f"variable '{v}' is declared but never used")

    print(f"Checked {len(files)} files: {len(resources)} resources, {len(datas)} data sources, "
          f"{len(variables)} variables, {len(locals_)} locals, "
          f"{sum(len(OUTPUT_RE.findall(f.read_text())) for f in files)} outputs")
    if problems:
        print("\n".join(sorted(set(problems))))
        return 1
    print("OK - no structural problems found (this is not a substitute for `terraform validate`).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
