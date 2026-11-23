#!/usr/bin/env python3
"""Append-only open-interest history.

WHY: fetch_options.py used to overwrite data/options.json on every run, so the pipeline had
no memory -- you could see today's OI but never how it got there. Requested: keep track of
the OI on every daily run, for every stock we pull.

STORAGE SHAPE (two files, on purpose):

1. data/oi_history/YYYY-MM-DD.json.gz   one file per RUN DAY, full detail, GZIPPED
   spot, call/put OI, P/C, the captured expiry set, and per-contract OI keyed
   "expiry|strike" for every contract in the leaderboard cut.

   Measured: one uncompressed day is ~381 KB -- 121 tickers x ~90 contracts a side, because
   each strike row carries a per-expiry `parts` split. That projects to ~93 MB/year of git.
   JSON gzips about 10x, so this lands near 10 MB/year. The daily files are append-only and
   never edited, so giving up line diffs on them costs nothing.

   Sharded per day rather than one growing file: git stores a whole new copy of a file on
   every change, so a 40 KB/day file costs 40 KB/day while one accumulating JSON would cost
   its entire size again every single day. A same-day re-run overwrites that day's file, so
   retries never duplicate.

2. data/oi_history_summary.json   the compact series, one row per ticker per day
   {"series": {"NVDA": [[date, spot, call_oi, put_oi], ...]}}
   ~6 KB/day, kept forever, plain JSON so it stays diffable. This is all the charting code
   needs to read.

CAVEAT THE READER MUST RESPECT: per-ticker totals are NOT comparable across runs when the
captured expiration set changes -- the 30-day floor rolls forward and contracts expire, so
total OI can jump purely because different expiries are in scope. Every record stores
`n_exp` and the expiry list, and any comparison should hold that constant. contract_series()
follows one real contract across days and is the only like-for-like comparison.
"""
from __future__ import annotations

import glob
import gzip
import json
import os
import sys
from datetime import datetime, timezone

HIST_DIR = "data/oi_history"
SUMMARY = "data/oi_history_summary.json"


def _contracts(lst):
    """Per-contract OI keyed 'expiry|strike' from a strike-level row with a parts split."""
    out = {}
    for c in lst or []:
        strike = c.get("strike")
        parts = c.get("parts") or []
        if parts:
            for p in parts:
                out["%s|%s" % (p.get("expiry"), strike)] = p.get("oi") or 0
        else:
            out["%s|%s" % (c.get("expiry"), strike)] = c.get("oi") or 0
    return out


def build_record(options: dict, generated: str | None = None) -> dict:
    """Turn a finished options.json payload into one dated history record."""
    generated = generated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    day = generated[:10]
    tickers = {}
    for tk, v in options.items():
        if tk.startswith("_") or not isinstance(v, dict):
            continue          # underscore keys are metadata, never tickers
        exps = v.get("expiries_considered")
        if isinstance(exps, str):
            exps = [e for e in exps.split(",") if e.strip()]
        tickers[tk] = {
            "spot": v.get("underlying"),
            "call_oi": v.get("call_oi") or 0,
            "put_oi": v.get("put_oi") or 0,
            "pc": v.get("pc_ratio"),
            "dte": v.get("dte"),
            "n_exp": len(exps) if isinstance(exps, list) else 0,
            "exps": exps if isinstance(exps, list) else [],
            "calls": _contracts(v.get("top_calls")),
            "puts": _contracts(v.get("top_puts")),
        }
    return {"date": day, "generated": generated, "tickers": tickers}


def write(record: dict, hist_dir: str = HIST_DIR, summary: str = SUMMARY) -> tuple:
    """Write the dated detail file (gzipped) and fold the day into the compact summary."""
    os.makedirs(hist_dir, exist_ok=True)
    day = record["date"]
    path = os.path.join(hist_dir, "%s.json.gz" % day)

    # GUARD: never replace an existing day with a narrower one. A partial run
    # (fetch_options --max N) writes to the same date but covers far fewer tickers, so
    # without this a test or truncated run silently swaps a complete day for a fragment.
    # That happened once during testing and had to be restored from git. A re-run with equal
    # or greater coverage still overwrites, so genuine retries keep the latest numbers.
    new_n = len(record.get("tickers") or {})
    if os.path.exists(path):
        try:
            old_n = len(load_day(path).get("tickers") or {})
            if old_n and new_n < old_n * 0.9:
                print("[oi-history] REFUSING to overwrite %s: this run has %d tickers, stored "
                      "has %d -- looks like a partial run" % (day, new_n, old_n), file=sys.stderr)
                return path, summary
        except Exception:
            pass

    payload = json.dumps(record, separators=(",", ":")).encode("utf-8")
    with gzip.open(path, "wb", compresslevel=9) as f:
        f.write(payload)

    data = {"series": {}}
    if os.path.exists(summary):
        try:
            data = json.load(open(summary))
        except Exception:
            data = {"series": {}}
    series = data.setdefault("series", {})
    for tk, v in record["tickers"].items():
        rows = [r for r in series.get(tk, []) if r and r[0] != day]
        # Row = [date, spot, call_oi, put_oi, n_exp].  n_exp is carried so a reader can tell
        # whether a move in the totals is real or just a change in how many expirations are
        # in scope -- without it a 6-expiry day sits beside a 10-expiry day and the gap reads
        # as a 144% jump in positioning, which it is not.
        rows.append([day, v.get("spot"), v.get("call_oi"), v.get("put_oi"), v.get("n_exp")])
        rows.sort(key=lambda r: r[0])
        series[tk] = rows
    with open(summary, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    return path, summary


def load_day(path: str) -> dict:
    """Read one dated record, gzipped or not (so old plain .json files still work)."""
    if path.endswith(".gz"):
        with gzip.open(path, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    return json.load(open(path))


def series(ticker: str, summary: str = SUMMARY):
    """[[date, spot, call_oi, put_oi], ...] for one ticker, oldest first."""
    if not os.path.exists(summary):
        return []
    s = (json.load(open(summary)).get("series") or {}).get(ticker.upper()) or []
    return sorted(s, key=lambda r: r[0])


def days(hist_dir: str = HIST_DIR):
    """Available dated detail files, oldest first."""
    return sorted(glob.glob(os.path.join(hist_dir, "2*-*-*.json*")))


def contract_series(ticker: str, side: str, expiry: str, strike, hist_dir: str = HIST_DIR):
    """Follow ONE real contract across days -> [[date, oi], ...].

    The only like-for-like comparison; totals move when the expiry set changes.
    """
    key = "%s|%s" % (expiry, strike)
    out = []
    for p in days(hist_dir):
        try:
            rec = load_day(p)
        except Exception:
            continue
        v = (rec.get("tickers") or {}).get(ticker.upper())
        if not v:
            continue
        oi = (v.get(side) or {}).get(key)
        if oi is not None:
            out.append([rec["date"], oi])
    return out


def backfill_from_git(start: str = "2026-01-01"):
    """Seed history from the options.json revisions already in git.

    The pipeline overwrote that file for weeks before this store existed, but every run
    committed it -- so early history can be recovered instead of starting from zero.
    """
    import subprocess

    def git(*a):
        return subprocess.run(["git"] + list(a), capture_output=True, text=True).stdout

    made = 0
    revs = [l for l in git("log", "--format=%h|%cI", "--", "data/options.json").strip().split("\n") if l]
    for line in reversed(revs):
        h, iso = line.split("|")
        raw = git("show", "%s:data/options.json" % h)
        if not raw:
            continue
        try:
            rec = build_record(json.loads(raw), generated=iso.replace("+00:00", "Z"))
        except Exception:
            continue
        if rec["date"] < start:
            continue
        write(rec)
        made += 1
    return made


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        print("backfilled %d snapshot(s) from git" % backfill_from_git())
    elif len(sys.argv) > 1 and sys.argv[1] == "rebuild":
        # Regenerate the compact summary from the stored daily detail files.  Needed whenever
        # the summary's row shape changes, since the detail files are the source of truth.
        if os.path.exists(SUMMARY):
            os.remove(SUMMARY)
        n = 0
        for p in days():
            try:
                write(load_day(p))
                n += 1
            except Exception as e:
                print("  skip %s: %s" % (p, e))
        print("rebuilt %s from %d day file(s)" % (SUMMARY, n))
    elif len(sys.argv) > 1 and sys.argv[1] == "size":
        for p in days():
            print("  %-26s %6.0f KB" % (os.path.basename(p), os.path.getsize(p) / 1024))
    else:
        tk = sys.argv[1].upper() if len(sys.argv) > 1 else "NVDA"
        rows = series(tk)
        print("%d day(s) of history for %s" % (len(rows), tk))
        for d, spot, co, po in rows:
            print("  %s  spot %8s  call %10s  put %10s  P/C %5.2f" %
                  (d, ("%.2f" % spot) if spot else "-", format(int(co), ","),
                   format(int(po), ","), (po / co) if co else 0))
