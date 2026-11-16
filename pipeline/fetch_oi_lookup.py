#!/usr/bin/env python3
"""Broad open-interest lookup index — top calls and puts by OI for a WIDE universe.

Why this exists separately from fetch_options.py
------------------------------------------------
`fetch_options.py` covers ~130 names and stores a rich record per ticker (OCC symbol,
TradingView URL, bid/ask, ADV…).  That file powers the dashboard board and every stock
page, so it must stay small.

The ticker-lookup section needs to answer "type any ticker" instead.  That means ~520
S&P 500 names, which is far too much to put on the critical path.  So this writes a
SEPARATE, TRIMMED file that the browser fetches LAZILY — only when the user opens the
lookup section.  Same measurement method as the board (nearest 6 expirations, 7–75 DTE,
top 10 strikes per side) so the two never disagree.

`symbol` and `tv_url` are dropped: both are pure functions of (ticker, expiry, strike,
type) and the browser rebuilds them.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import warnings

warnings.filterwarnings("ignore")
import yfinance as yf

SP500_CSV = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"


def occ_symbol(root: str, expiry: str, cp: str, strike: float) -> str:
    """AAPL + 2026-12-18 + C + 360 -> AAPL261218C360.0  (strike un-padded, like the board)"""
    ymd = expiry.replace("-", "")[2:]                    # YYMMDD
    st = f"{strike:.3f}".rstrip("0")
    if st.endswith("."):
        st += "0"
    return f"{root}{ymd}{cp}{st}"


def tv_url(root: str, expiry: str, cp: str, strike: float) -> str:
    return f"https://www.tradingview.com/symbols/OPRA-{occ_symbol(root, expiry, cp, strike)}/"


def num(x, default=0):
    try:
        f = float(x)
        if f != f:                                       # NaN
            return default
        return int(f) if f == int(f) else f
    except Exception:
        return default


def expire_list(exps, lo=7, hi=75, limit=6):
    """The nearest `limit` expirations inside the DTE window — same rule as the board."""
    today = time.time()
    out = []
    for e in exps or []:
        try:
            dt = (time.mktime(time.strptime(e, "%Y-%m-%d")) - today) / 86400.0
        except Exception:
            continue
        if lo <= dt <= hi:
            out.append((dt, e))
    out.sort()
    return [e for _, e in out[:limit]]


def build_side(chains, exp_list, want, top_n, spot=None):
    """Aggregate OI per strike across the chosen expirations; keep the top `top_n`."""
    agg = {}
    for e in exp_list:
        df = chains.get(e)
        if df is None or df.empty:
            continue
        for _, r in df.iterrows():
            try:
                k = float(r["strike"])
            except Exception:
                continue
            oi = num(r.get("openInterest"), 0)
            if oi <= 0:
                continue
            a = agg.setdefault(k, {"strike": k, "oi": 0, "parts": {},
                                   "volume": 0, "price": None, "iv": None})
            a["oi"] += oi
            a["parts"][e] = a["parts"].get(e, 0) + oi
            a["volume"] += num(r.get("volume"), 0)
    rows = sorted(agg.values(), key=lambda x: -x["oi"])[:top_n]
    for a in rows:
        dom = max(a["parts"], key=lambda e: a["parts"][e]) if a["parts"] else None
        a.pop("parts", None)
        a["expiry"] = dom
        src = chains.get(dom)
        if src is not None and not src.empty:
            try:
                m = src[src["strike"] == a["strike"]]
                if len(m):
                    r0 = m.iloc[0]
                    a["volume"] = num(r0.get("volume"), a["volume"])
                    bid, ask = num(r0.get("bid"), 0), num(r0.get("ask"), 0)
                    # A price is reported ONLY from a live quote: the midpoint when the book
                    # is two-sided, otherwise the one side that exists.
                    #
                    # `lastPrice` is deliberately NOT used as a fallback.  For illiquid
                    # deep-in-the-money strikes yfinance returns bid=ask=0 and a last print
                    # from days ago, which produced prices BELOW intrinsic — impossible, since
                    # a call can never trade under spot-strike.  Worst case seen: DD's $55
                    # call showing $2.25 against $98.78 of intrinsic; 679 of 10,614 rows
                    # (6.4%) were affected.  Same rule as IV: a wrong number is worse than none.
                    if bid > 0 and ask > 0:
                        a["price"] = round((bid + ask) / 2.0, 2)
                    elif bid > 0 or ask > 0:
                        a["price"] = round(bid or ask, 2)
                    else:
                        # Fall back to the last print, because Yahoo leaves the order book
                        # EMPTY for most of many chains (ABT: 45 strikes, 5 quoted) — a
                        # bid/ask-only rule starved the column to 1,028 of 10,741 rows.
                        # The print is stale often enough to matter, so it is kept only if
                        # it survives the intrinsic test below.
                        last = num(r0.get("lastPrice"), 0)
                        a["price"] = round(last, 2) if last > 0 else None
                    # A call can never be worth less than spot-strike (nor a put less than
                    # strike-spot).  Anything under that is a stale quote, not a price:
                    # without this, DD's $55 call showed $2.25 against $98.78 of intrinsic
                    # and 679 of 10,614 rows were impossible.
                    if a["price"] is not None and spot:
                        _intr = max(0.0, spot - a["strike"]) if want == "c" \
                            else max(0.0, a["strike"] - spot)
                        if _intr > 0 and a["price"] < _intr - 0.01:
                            a["price"] = None
                    # IV is deliberately NOT carried. yfinance returns 1e-05 placeholders
                    # for any strike without a live quote and implausible values (6%) for
                    # others, so a "VIX-like" column here would be confidently wrong.  The
                    # ask was open interest; a junk IV is worse than no IV.
            except Exception:
                pass
    return rows


def fetch_one(t):
    tk = yf.Ticker(t)
    exps = expire_list(list(tk.options or []))
    if not exps:
        return None
    call_ch, put_ch = {}, {}
    for e in exps:
        for attempt in (1, 2):
            try:
                oc = tk.option_chain(e)
                call_ch[e], put_ch[e] = oc.calls, oc.puts
                break
            except Exception:
                if attempt == 2:
                    break
                time.sleep(0.4)
    if not call_ch and not put_ch:
        return None
    # spot first — build_side needs it to reject quotes below intrinsic
    try:
        spot = float(tk.fast_info.get("lastPrice") or 0) or None
    except Exception:
        spot = None

    calls = build_side(call_ch, exps, "c", 10, spot=spot)
    puts = build_side(put_ch, exps, "p", 10, spot=spot)
    if not calls and not puts:
        return None

    # "Most active" = the expiry carrying the most open interest overall, which is the
    # number worth showing.  (exps[0] is merely the NEAREST, which is a different thing
    # and read as a bug on first pass.)
    per_exp = {}
    for src in (call_ch, put_ch):
        for e, df in src.items():
            if df is None or df.empty:
                continue
            per_exp[e] = per_exp.get(e, 0) + int(df["openInterest"].fillna(0).sum())
    active = max(per_exp, key=lambda e: per_exp[e]) if per_exp else exps[0]

    c_oi = sum(c["oi"] for c in calls)
    p_oi = sum(p["oi"] for p in puts)
    return {
        "underlying": round(spot, 2) if spot else None,
        "expiry": active,
        "dte": round((time.mktime(time.strptime(active, "%Y-%m-%d")) - time.time()) / 86400.0),
        "call_oi": c_oi, "put_oi": p_oi,
        "pc_ratio": round(p_oi / c_oi, 2) if c_oi else None,
        "top_calls": calls, "top_puts": puts,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/oi_lookup.json")
    ap.add_argument("--sp500", default=SP500_CSV)
    ap.add_argument("--extra", default="", help="comma-separated extra tickers to include")
    ap.add_argument("--sleep", type=float, default=0.15, help="pause between tickers")
    ap.add_argument("--max", type=int, default=0, help="cap the universe (0 = all)")
    a = ap.parse_args()

    universe = []
    # The app's OWN tickers go FIRST.  Yahoo throttles hard on a crawl this size, so a
    # partial run must still cover the names the app is actually about — appending them
    # after the S&P 500 (as this did at first) meant a throttled run missed NVDA, ORCL,
    # TSLA and every other featured ticker while dutifully fetching 'A' through 'F'.
    for f in ("data/options.json", "data/profiles.json"):
        try:
            for t in json.load(open(f)).keys():
                if not t.startswith("_"):
                    universe.append(t)
        except Exception:
            pass
    try:
        import urllib.request
        with urllib.request.urlopen(a.sp500, timeout=30) as r:
            txt = r.read().decode("utf-8", "replace")
        for row in csv.DictReader(txt.splitlines()):
            s = (row.get("Symbol") or "").strip().replace(".", "-")
            if s:
                universe.append(s)
    except Exception as e:
        print(f"[oi-lookup] S&P list failed ({type(e).__name__}); falling back", file=sys.stderr)
    universe += [x for x in a.extra.split(",") if x.strip()]

    seen, ordered = set(), []
    for t in universe:
        t = t.strip().upper()
        if t and t not in seen:
            seen.add(t)
            ordered.append(t)
    if a.max:
        ordered = ordered[: a.max]

    # ---- resumable: keep whatever is already done so a re-run continues ----------
    out = {}
    if os.path.exists(a.out):
        try:
            out = json.load(open(a.out))
            out = {k: v for k, v in out.items() if not k.startswith("_")}
        except Exception:
            out = {}
    todo = [t for t in ordered if t not in out]
    print(f"[oi-lookup] universe {len(ordered)} · already done {len(out)} · to fetch {len(todo)}",
          file=sys.stderr)
    if not todo:
        print("[oi-lookup] nothing to do", file=sys.stderr)
        return 0

    t0 = time.time()
    fails = 0
    for n, t in enumerate(todo, 1):
        try:
            rec = fetch_one(t)
            fails = 0
        except Exception as e:
            fails += 1
            print(f"  ! {t}: {type(e).__name__} {e}", file=sys.stderr)
            rec = None
            # CIRCUIT BREAKER.  Once Yahoo starts throttling it tends to time out on every
            # request, at ~30 s apiece — that turns a 22-minute crawl into hours and risks
            # the CI timeout.  Back off, then bail out and let the NEXT run resume.
            if fails >= 10:
                print(f"[oi-lookup] {fails} consecutive failures — Yahoo is throttling. "
                      f"Pausing 60s; will stop if it keeps up.", file=sys.stderr)
                time.sleep(60)
                if fails >= 25:
                    print(f"[oi-lookup] giving up after {fails} consecutive failures. "
                          f"Wrote {len(out)} tickers; re-run to resume.", file=sys.stderr)
                    json.dump(out, open(a.out, "w"))
                    return 0
                fails = 0
        if rec:
            out[t] = rec
        time.sleep(a.sleep)
        if n % 20 == 0 or n == len(todo):
            el = time.time() - t0
            rate = el / n
            print(f"  {n}/{len(todo)}  {t:6s}  done={len(out)}  "
                  f"{rate:.2f}s/tkr  eta {rate*(len(todo)-n)/60:.1f}m", file=sys.stderr)
            os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
            json.dump(out, open(a.out, "w"))      # incremental — partial progress survives

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"))
    sz = os.path.getsize(a.out)
    print(f"[oi-lookup] wrote {a.out} — {len(out)} tickers, {sz/1e6:.2f} MB, "
          f"{(time.time()-t0)/60:.1f} min", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
