#!/usr/bin/env python3
"""Capitol Flow — daily strategy digest.

Prints a short, Discord-ready reminder of the house trading rules plus the day's top
trend-aligned candidates from data/strategy.json. Designed to run as a zero-LLM cron job:
stdout IS the message.

Pulls the latest committed data first (the cloud refresh commits it), regenerates
strategy.json if it is missing, then prints the digest. Exits 0 with a short note if the
data is not there yet, so the cron never fails silently.

Usage: python strategy_digest.py [--repo /root/capitol-flow] [--top 5]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

RULES = ("Rules: underpriced options · 4h/Daily trend · underlying <$200 (ideal <$150) · "
         "top-25 OI · major swing levels")


def run(cmd, cwd):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=90)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="/root/capitol-flow")
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args()
    repo = a.repo

    # 1. Get the freshest committed data (non-fatal — fall back to what's on disk).
    run(["git", "pull", "--ff-only", "--quiet"], repo)

    # 2. Regenerate the scan if it is missing or older than the option data.
    sj = os.path.join(repo, "data", "strategy.json")
    oj = os.path.join(repo, "data", "options.json")
    need = not os.path.exists(sj)
    if not need and os.path.exists(oj):
        need = os.path.getmtime(sj) < os.path.getmtime(oj)
    if need:
        run([sys.executable, os.path.join(repo, "pipeline", "strategy.py"),
             "--app", os.path.join(repo, "data", "app_data.json"),
             "--options", oj, "--out", sj], repo)

    if not os.path.exists(sj):
        print("Capitol Flow — no strategy scan available yet (data/strategy.json missing).")
        return
    with open(sj) as fh:
        s = json.load(fh)

    opps = (s.get("opportunities") or [])[:a.top]
    gen = str(s.get("generated") or "")[:10]
    try:
        when = datetime.strptime(gen, "%Y-%m-%d").strftime("%b %-d")
    except Exception:
        when = gen
    n = (s.get("counts") or {}).get("candidates", 0)

    lines = [f"◆ **Capitol Flow — strategy scan · {when}**", RULES, ""]
    if opps:
        lines.append(f"*{n} trend-aligned candidates scanned. Top {len(opps)}:*")
        for i, c in enumerate(opps, 1):
            kind = (c.get("type") or "").upper()
            trend = (c.get("trend") or "").upper()
            viol = " ⚠ violation" if "violation" in (c.get("why") or "") else ""
            lines.append(
                f"{i}. **{c.get('ticker')} ${c.get('strike'):g} {kind}** · {c.get('expiry')} · "
                f"mid ${c.get('price'):.2f} · OI {round(c.get('oi', 0)):,} · vol {round(c.get('volume', 0)):,} · "
                f"{trend}{viol} · underlying ${c.get('underlying'):.2f}"
            )
    else:
        lines.append("No trend-aligned contracts cleared the filters today.")
    lines.append("")
    lines.append("Full board: https://agent-marsha.github.io/capitol-flow/")
    lines.append("_Informational only — not investment advice._")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
