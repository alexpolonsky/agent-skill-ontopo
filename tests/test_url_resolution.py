#!/usr/bin/env python3
"""Regression tests for booking-URL resolution and weekday date parsing.

Guards against the dead-link bug: ids taken from `available` output are
ephemeral search-post ids, and the url command used to echo them into a URL
that renders nothing. Every URL the command emits must point at a page that
identifies itself as a live booking page.

Weekday parsing is tested offline; URL resolution hits the live API.

Usage:
    python3 tests/test_url_resolution.py
"""

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "scripts" / "ontopo-cli.py"

spec = importlib.util.spec_from_file_location("cli", CLI)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

failures = []


def check(label, condition, detail=""):
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        failures.append(label)


print("parse_date weekdays (offline)")
now = datetime.now()
for name, idx in [("monday", 0), ("friday", 4), ("fri", 4), ("sunday", 6)]:
    got = cli.parse_date(name)
    expected = (now + timedelta(days=(idx - now.weekday()) % 7)).strftime("%Y%m%d")
    check(f"'{name}' -> next {name}", got == expected, f"(got {got}, expected {expected})")
check("today's weekday name means today",
      cli.parse_date(now.strftime("%A").lower()) == now.strftime("%Y%m%d"))
check("existing formats unaffected",
      cli.parse_date("tomorrow") == (now + timedelta(days=1)).strftime("%Y%m%d"))
try:
    cli.parse_date("someday")
    check("invalid input still rejected", False)
except ValueError as e:
    check("invalid input still rejected", "weekday" in str(e))


def run_url(venue_id):
    proc = subprocess.run(
        [sys.executable, str(CLI), "url", venue_id, "--json"],
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, proc.stdout


print("url resolution (live API)")
# Venue slug and page id must keep working (documented flows).
for label, vid, expect_page in [("venue slug", "23971178", "36960535"),
                                ("page id", "36960535", "36960535")]:
    code, out = run_url(vid)
    data = json.loads(out)
    check(f"{label} resolves", code == 0 and data.get("url", "").endswith(expect_page),
          f"(got {out[:80]})")

# A fresh search-post id from `available` must NOT be echoed into the URL.
proc = subprocess.run(
    [sys.executable, str(CLI), "available", "tomorrow", "19:00",
     "--city", "tel-aviv", "--json"],
    capture_output=True, text=True, timeout=120,
)
avail = json.loads(proc.stdout)
venues = avail.get("venues") or avail.get("results") or []
post = venues[0]["post"] if "post" in venues[0] else venues[0]
post_slug = str(post.get("slug", post.get("venue_id", "")))
page_slug = str(post.get("page_slug", post.get("page_id", "")))
code, out = run_url(post_slug)
if code == 0:
    resolved = json.loads(out).get("url", "").rsplit("/", 1)[-1]
    check("post slug not echoed into URL", resolved != post_slug,
          f"(echoed {post_slug})")
    check("post slug recovered to its page", resolved == page_slug,
          f"(resolved {resolved}, page_slug {page_slug})")
else:
    # A clean refusal is also acceptable - just never a dead link.
    check("post slug not echoed into URL", True)
    check("post slug recovered to its page", "does not resolve" in out, f"({out[:80]})")

# Garbage must error, not produce a link.
code, out = run_url("99999999")
check("garbage id refused", "does not resolve" in out, f"({out[:80]})")

print()
if failures:
    print(f"FAILED: {len(failures)}: {', '.join(failures)}")
    sys.exit(1)
print("All url-resolution and weekday checks passed.")
