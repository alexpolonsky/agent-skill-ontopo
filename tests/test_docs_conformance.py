#!/usr/bin/env python3
"""Verify every ontopo-cli.py invocation in the docs actually parses.

Catches documentation drift: a flag that was renamed or never existed, a
positional argument documented as an option, a command that was removed.

Runs offline. Each documented command is parsed with --check-args, which
validates arguments and exits before any network call, so this test is fast
and cannot flake on upstream availability.

Usage:
    python3 tests/test_docs_conformance.py
"""

import re
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "scripts" / "ontopo-cli.py"
DOCS = ["SKILL.md", "README.md"]

# Lines that invoke the CLI, with or without the {baseDir} skill placeholder.
INVOCATION = re.compile(r"ontopo-cli\.py(?P<args>.*)$")

# A trailing "  # comment", but not a '#' inside a quoted string.
TRAILING_COMMENT = re.compile(r"""\s+\#(?:[^"']*)$""")


def extract_invocations(path):
    """Yield (lineno, argument_string) for each documented CLI call."""
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        # Skip prose and comment-only lines.
        if line.startswith("#") or "ontopo-cli.py" not in line:
            continue
        # Skip markdown table rows and prose references.
        if line.startswith("|") or not re.search(r"(python3|^\s*\./)", line):
            continue
        match = INVOCATION.search(line)
        if not match:
            continue
        args = TRAILING_COMMENT.sub("", match.group("args")).strip()
        if args:
            yield lineno, args


def main():
    if not CLI.exists():
        print(f"FAIL: CLI not found at {CLI}")
        return 1

    checked, failures = 0, []

    for doc_name in DOCS:
        doc = REPO_ROOT / doc_name
        if not doc.exists():
            continue
        for lineno, args in extract_invocations(doc):
            try:
                argv = shlex.split(args)
            except ValueError as exc:
                failures.append((doc_name, lineno, args, f"unparseable quoting: {exc}"))
                continue

            checked += 1
            proc = subprocess.run(
                [sys.executable, str(CLI), "--check-args", *argv],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout).strip().splitlines()
                failures.append((doc_name, lineno, args, err[-1] if err else "non-zero exit"))

    # A test that validates nothing must not report success.
    if checked == 0:
        print("FAIL: no CLI invocations found in docs - the extractor is broken")
        return 1

    print(f"Docs conformance: {checked - len(failures)}/{checked} documented commands parse")

    if failures:
        print("\nDocumented commands that do not parse:")
        for doc_name, lineno, args, err in failures:
            print(f"  {doc_name}:{lineno}: ontopo-cli.py {args}")
            print(f"      -> {err}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
