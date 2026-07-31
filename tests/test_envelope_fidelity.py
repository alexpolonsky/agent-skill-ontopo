#!/usr/bin/env python3
"""Verify the JSON envelope preserves every fact the raw payload carries.

The envelope drops upstream UI strings, campaign metadata and localisation
blobs. This test asserts that what it drops is only noise: venue identities,
slot times and availability states must survive identically between --json
(envelope) and --json --raw (upstream passthrough).

Hits the live API. Run before changing any normalisation logic.

Usage:
    python3 tests/test_envelope_fidelity.py
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "scripts" / "ontopo-cli.py"

VENUE = "taizu"
VENUE_ID = "36960535"
failures = []


def run(args):
    proc = subprocess.run(
        [sys.executable, str(CLI), *args, "--json"],
        capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} exited {proc.returncode}: {proc.stderr[:200]}")
    return json.loads(proc.stdout)


def check(label, condition, detail=""):
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        failures.append(label)


def raw_slot_times(availability):
    """Times present in a raw availability blob, as HH:MM."""
    times = set()
    for area in (availability or {}).get("areas") or []:
        for opt in area.get("options") or []:
            if opt.get("method") in ("seat", "standby") and opt.get("time"):
                t = opt["time"]
                times.add(f"{t[:2]}:{t[2:]}" if len(t) == 4 else t)
    return times


print("available")
raw = run(["available", "tomorrow", "19:00", "--city", "tel-aviv", "--raw"])
env = run(["available", "tomorrow", "19:00", "--city", "tel-aviv"])

raw_ids = {str(v.get("post", {}).get("slug", "")) for v in raw["venues"]}
env_ids = {r["venue_id"] for r in env["results"]}
check("venue count preserved", raw["count"] == env["count"],
      f"(raw {raw['count']} vs env {env['count']})")
check("venue ids identical", raw_ids == env_ids,
      f"(symmetric diff {raw_ids ^ env_ids})")

raw_times, env_times = set(), set()
for v in raw["venues"]:
    raw_times |= raw_slot_times(v.get("availability"))
for r in env["results"]:
    env_times |= {sl["time"] for sl in r["slots"]}
check("slot times identical", raw_times == env_times,
      f"(symmetric diff {raw_times ^ env_times})")
check("every venue has a booking url",
      all(r["booking_url"] for r in env["results"]))

print("check")
raw = run(["check", VENUE, "tomorrow", "19:00", "--raw"])
env = run(["check", VENUE, "tomorrow", "19:00"])
check("slot times identical",
      raw_slot_times(raw["availability"]) == {sl["time"] for sl in env["results"][0]["slots"]})
check("available flag matches slots",
      env["results"][0]["available"] ==
      any(sl["status"] == "available" for sl in env["results"][0]["slots"]))
check("booking url present", bool(env["results"][0]["booking_url"]))

print("range")
raw = run(["range", VENUE, "tomorrow", "+3", "--raw"])
env = run(["range", VENUE, "tomorrow", "+3"])
check("day count preserved", len(raw["results"]) == len(env["results"]))
raw_avail = [bool(t.get("available")) for d in raw["results"] for t in d["times"]]
env_avail = [t["status"] == "available" for d in env["results"] for t in d["times"]]
check("availability states identical", raw_avail == env_avail)
check("dates carry day-of-week", all("(" in d["date"] for d in env["results"]))
check("range criteria carries booking_url",
      bool(env["criteria"].get("booking_url")))
range_booking_url = env["criteria"].get("booking_url")

print("info")
raw = run(["info", VENUE_ID, "--raw"])
env = run(["info", VENUE_ID])
r0 = env["results"][0]
check("name preserved", r0["name"] == raw.get("title"))
check("address preserved", r0["address"] == raw.get("address"))
check("phone preserved", r0["phone"] == raw.get("phone"))
check("booking url present", bool(r0["booking_url"]))

print("envelope shape")
for cmd in (["search", VENUE], ["cities"], ["categories"], ["url", VENUE]):
    env = run(cmd)
    missing = {"ok", "command", "criteria", "results", "count",
               "warning", "error"} - set(env)
    check(f"{cmd[0]} has full envelope", not missing, f"(missing {missing})")

print("sample booking link renders (guards against dead-link regressions)")
import urllib.request
sample = range_booking_url
try:
    req = urllib.request.Request(sample, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    # Live booking pages are server-rendered with a real <title>; the dead
    # pages produced by unresolved ids serve the bare SPA shell without one.
    check("booking_url serves a titled page", "<title>" in html, f"({sample})")
except Exception as exc:
    check("booking_url serves a titled page", False, f"({sample}: {exc})")

print("info on a search-post id must not emit a dead booking_url")
post_id = env_avail_first_venue = None
env2 = run(["available", "tomorrow", "19:00", "--city", "tel-aviv"])
if env2["results"]:
    v0 = env2["results"][0]
    r = run(["info", v0["venue_id"]])
    got = r["results"][0].get("booking_url")
    check("info booking_url is None or the venue's real page",
          got is None or got == v0.get("booking_url"),
          f"(info gave {got}, real page {v0.get('booking_url')})")

print("error shape")
# Note: a garbage venue NAME does not error - resolve_venue_name fuzzy-matches
# it to search results[0] (pre-existing looseness, visible in the envelope as
# venue_input != venue_id). A nonexistent numeric ID is the true error path.
env = run(["check", "99999999", "tomorrow", "19:00"])
check("error run has ok=false", env.get("ok") is False)
check("error run has error text", bool(env.get("error")))
check("error text names next step", "search" in (env.get("error") or ""))

print()
if failures:
    print(f"FAILED: {len(failures)} fidelity check(s): {', '.join(failures)}")
    sys.exit(1)
print("All fidelity checks passed - envelope drops no facts.")
