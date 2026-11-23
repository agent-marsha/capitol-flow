#!/usr/bin/env python3
"""Rebuild an NVDA open-interest history from the committed options.json snapshots.

There is no OI history table in the pipeline -- fetch_options.py overwrites
data/options.json on every run. But the daily refresh COMMITS that file, so git holds one
snapshot per refresh. This walks those revisions and reconstructs the series.

IMPORTANT CAVEAT this script exists to make visible: the total call/put OI in a snapshot is
NOT comparable across snapshots on its own, because the set of expirations captured changes
as the 30-day floor rolls forward and contracts expire. A jump in the total can be purely a
change of which expiries are in scope. So this reports BOTH:
  * the raw total per snapshot, and
  * OI for a FIXED contract (same strike + same expiry) followed across snapshots,
which is the only like-for-like comparison.
"""
import json
import subprocess
import sys

TICKER = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
OUT = "/tmp/%s_oi_hist.json" % TICKER.lower()


def git(*args):
    return subprocess.run(["git"] + list(args), capture_output=True, text=True).stdout


def main():
    revs = [l for l in git("log", "--format=%h|%ci", "--", "data/options.json").strip().split("\n") if l]
    rows = []
    for line in reversed(revs):          # oldest -> newest
        h, when = line.split("|")
        raw = git("show", "%s:data/options.json" % h)
        try:
            o = json.loads(raw)
        except Exception:
            continue
        t = o.get(TICKER)
        if not isinstance(t, dict):
            continue
        calls = t.get("top_calls") or []
        puts = t.get("top_puts") or []
        exps = t.get("expiries_considered")
        if isinstance(exps, str):
            exps = [e for e in exps.split(",") if e.strip()]
        # Rows are strike-level with `oi` = the sum across expiries, plus a `parts` list giving
        # the per-expiry split.  Key on expiry|strike so we follow TRUE contracts (one ticker,
        # one strike, one expiry) instead of a strike that silently rolls into later expiries.
        def contracts(lst):
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

        rows.append({
            "commit": h,
            "when": when[:16],
            "n_exp": len(exps) if isinstance(exps, list) else 0,
            "call_oi": t.get("call_oi") or 0,
            "put_oi": t.get("put_oi") or 0,
            "dte": t.get("dte"),
            "spot": t.get("underlying"),
            "calls": contracts(t.get("top_calls")),
            "puts": contracts(t.get("top_puts")),
        })

    print("%-9s %-17s %4s %11s %11s %6s %7s" %
          ("commit", "date (UTC)", "exps", "call OI", "put OI", "P/C", "spot"))
    for r in rows:
        pc = (r["put_oi"] / r["call_oi"]) if r["call_oi"] else 0
        print("%-9s %-17s %4d %11s %11s %6.2f %7s" %
              (r["commit"], r["when"], r["n_exp"],
               format(int(r["call_oi"]), ","), format(int(r["put_oi"]), ","), pc,
               ("%.2f" % r["spot"]) if r["spot"] else "-"))

    # contracts present in EVERY snapshot -> the only clean comparison
    if rows:
        common_c = set(rows[0]["calls"])
        common_p = set(rows[0]["puts"])
        for r in rows[1:]:
            common_c &= set(r["calls"])
            common_p &= set(r["puts"])
        print("\ncontracts present in ALL %d snapshots: %d calls, %d puts"
              % (len(rows), len(common_c), len(common_p)))

        def trend(key, side):
            vals = [r[side][key] for r in rows]
            return vals

        top_c = sorted(common_c, key=lambda k: -trend(k, "calls")[-1])[:6]
        print("\n=== CALL OI, same contract every snapshot ===")
        print("%-22s %s" % ("contract", "  ".join("%9s" % r["when"][5:10] for r in rows)))
        for k in top_c:
            print("%-22s %s" % (k, "  ".join("%9s" % format(int(v), ",") for v in trend(k, "calls"))))
        top_p = sorted(common_p, key=lambda k: -trend(k, "puts")[-1])[:6]
        print("\n=== PUT OI, same contract every snapshot ===")
        print("%-22s %s" % ("contract", "  ".join("%9s" % r["when"][5:10] for r in rows)))
        for k in top_p:
            print("%-22s %s" % (k, "  ".join("%9s" % format(int(v), ",") for v in trend(k, "puts"))))

    json.dump(rows, open(OUT, "w"), indent=1)
    print("\nsaved %d snapshots -> %s" % (len(rows), OUT))


if __name__ == "__main__":
    main()
