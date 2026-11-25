#!/usr/bin/env python3
"""Capitol Flow — strategy scanner.

Applies the five house trading rules (see TRADING_RULES.md) to the refreshed data and writes
data/strategy.json. The app's STRATEGY section renders this file; the daily Discord cron reads
it too.

The rules, verbatim:

  1. Buy underpriced Call/Put options — bet on a trend when prices are low.
  2. Trade the trend on the 4h or Daily chart; ignore intraday moves except at a violation.
  3. Underlying target price under $200; under $150 is ideal.
  4. Follow OI and volume; only contracts inside the top 25 OI.
  5. Read trend with the major swing level method (major swing highs/lows).

Output: data/strategy.json
  { "generated": "...",
    "rules":     [ {"n":1,"title":"...","text":"..."}, ... ],
    "method":    "major swing levels, k=5 daily / k=6 4h",
    "trends":    { "NVDA": {"trend":"up","close":..,"last_swing_high":..,
                            "last_swing_low":..,"violation":false,"d4":"up","d4_violation":false}, ... },
    "opportunities": [ {"ticker","type","strike","expiry","dte","oi","volume","price",
                        "underlying","symbol","tv_url","trend","score","why"} ] }

Usage: python strategy.py [--app data/app_data.json] [--options data/options.json]
                          [--out data/strategy.json] [--top 8]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

# ---- rule thresholds -------------------------------------------------------
MIN_DTE = 30
MAX_DTE = 240
MAX_UNDERLYING = 200.0        # rule 3
IDEAL_UNDERLYING = 150.0      # rule 3 (bonus)
TOP_OI_PER_SIDE = 25          # rule 4
MAX_MONEYNESS = 0.28          # strike within +/-28% of spot
MIN_OI = 250                  # rule 4: real open interest only
DAILY_K = 5                   # major swing lookback, daily bars
H4_K = 6                      # major swing lookback, 4h bars

RULES = [
    {"n": 1, "title": "Buy underpriced options on the trend",
     "text": "Look for Call or Put options that are very underpriced and bet on the trend "
             "when prices are low — enter cheap, not after a run."},
    {"n": 2, "title": "Trade the 4h / Daily trend",
     "text": "Follow the trend on the 4h or Daily chart. Ignore intraday moves except to "
             "enter or exit on a violation of the 4h or Daily trend."},
    {"n": 3, "title": "Underlying under $200",
     "text": "Target underlyings priced under $200. Under $150 is ideal."},
    {"n": 4, "title": "Follow OI and volume",
     "text": "Follow the open-interest and volume indicators. Only contracts inside the top "
             "25 OI — do not get distracted by contracts outside it."},
    {"n": 5, "title": "Major swing level method",
     "text": "Read the trend from major swing highs and lows (higher highs + higher lows = up; "
             "lower highs + lower lows = down). A close through the last major swing level is "
             "the violation that ends the trend. Ref: youtu.be/2h5ryPi6ZYo"},
]


def load(path):
    with open(path) as fh:
        return json.load(fh)


# ---- swing levels (rule 5) -------------------------------------------------
def pivots(bars, k):
    """Return (swing_highs, swing_lows) as lists of (index, price).

    A bar is a major swing high when its high is the strict maximum of the +/-k window."""
    highs, lows = [], []
    n = len(bars)
    if n < 2 * k + 1:
        return highs, lows
    for i in range(k, n - k):
        win = bars[i - k:i + k + 1]
        h = bars[i]["h"]
        l = bars[i]["l"]
        if h == max(b["h"] for b in win) and h > bars[i - 1]["h"] and h > bars[i + 1]["h"]:
            highs.append((i, h))
        if l == min(b["l"] for b in win) and l < bars[i - 1]["l"] and l < bars[i + 1]["l"]:
            lows.append((i, l))
    return highs, lows


def read_trend(bars, k):
    """Classify trend from major swing structure and locate the last major levels."""
    if not bars:
        return {"trend": "range", "close": None, "last_swing_high": None,
                "last_swing_low": None, "violation": False}
    highs, lows = pivots(bars, k)
    close = bars[-1]["c"]
    trend = "range"
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1][1] > highs[-2][1]
        hl = lows[-1][1] > lows[-2][1]
        lh = highs[-1][1] < highs[-2][1]
        ll = lows[-1][1] < lows[-2][1]
        if hh and hl:
            trend = "up"
        elif lh and ll:
            trend = "down"
    lsh = highs[-1][1] if highs else None
    lsl = lows[-1][1] if lows else None
    violation = False
    if trend == "up" and lsl is not None and close < lsl:
        violation = True
    if trend == "down" and lsh is not None and close > lsh:
        violation = True
    return {"trend": trend, "close": round(close, 2),
            "last_swing_high": round(lsh, 2) if lsh is not None else None,
            "last_swing_low": round(lsl, 2) if lsl is not None else None,
            "violation": violation}


def to_4h(hourly):
    """Resample hourly bars into 4h bars (bucketed from the epoch)."""
    if not hourly:
        return []
    buckets = {}
    for b in hourly:
        key = b["t"] // (4 * 3600)
        o = buckets.get(key)
        if o is None:
            buckets[key] = {"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]}
        else:
            o["h"] = max(o["h"], b["h"])
            o["l"] = min(o["l"], b["l"])
            o["c"] = b["c"]
    return [buckets[k] for k in sorted(buckets)]


# ---- scoring (rules 1 + 4) -------------------------------------------------
def contract_score(c, trend, spot, maxima):
    oi = c.get("oi") or 0
    vol = c.get("volume") or 0
    price = c.get("price")
    strike = c.get("strike") or 0
    oi_s = oi / maxima["oi"] if maxima["oi"] else 0
    vol_s = vol / maxima["vol"] if maxima["vol"] else 0
    cheap_s = 1 - min(1.0, (price or 0) / maxima["price"]) if maxima["price"] else 0
    money_s = max(0.0, 1 - abs(strike - spot) / spot / MAX_MONEYNESS) if spot else 0
    tier = 1.0 if spot < IDEAL_UNDERLYING else 0.5 if spot < MAX_UNDERLYING else 0.0
    confirm = 1.0 if trend["trend"] in ("up", "down") and not trend["violation"] else 0.0
    score = (3.0 * oi_s + 2.0 * vol_s + 2.0 * cheap_s + 1.0 * money_s +
             0.75 * tier + 0.75 * confirm)
    return round(score, 4)


def why(c, trend, spot):
    bits = []
    bits.append(f"{trend['trend'].upper()} on the daily" +
                (" (4h confirms)" if trend.get("d4") == trend["trend"] else ""))
    if trend["violation"]:
        bits.append("⚠ violation of last major swing level")
    bits.append(f"top-{TOP_OI_PER_SIDE} OI, vol {c.get('volume') or 0:,}")
    if (c.get("price") or 0) <= 1.0:
        bits.append(f"cheap at ${c['price']:.2f}")
    if spot < IDEAL_UNDERLYING:
        bits.append(f"underlying ${spot:.0f} (<$150)")
    return " · ".join(bits)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default="data/app_data.json")
    ap.add_argument("--options", default="data/options.json")
    ap.add_argument("--out", default="data/strategy.json")
    ap.add_argument("--top", type=int, default=8)
    a = ap.parse_args()

    app = load(a.app)
    try:
        options = load(a.options)
    except Exception:
        options = {}
    prices = app.get("prices") or {}

    # ---- trend read for every name we have prices for ----------------------
    trends = {}
    for tk, series in prices.items():
        daily = series.get("daily") or []
        h4 = to_4h(series.get("hourly") or [])
        d_daily = read_trend(daily, DAILY_K)
        d_4h = read_trend(h4, H4_K)
        d_daily["d4"] = d_4h["trend"]
        d_daily["d4_violation"] = d_4h["violation"]
        trends[tk] = d_daily

    # ---- candidates: top-25 OI per side, trend-aligned, rule 3 in range ----
    cands = []
    for tk, o in options.items():
        if tk.startswith("_") or not isinstance(o, dict):
            continue
        spot = o.get("underlying")
        tr = trends.get(tk)
        if not spot or not tr or spot >= MAX_UNDERLYING:
            continue
        if tr["trend"] == "range":
            continue
        side = "call" if tr["trend"] == "up" else "put"
        book = o.get("top_calls" if side == "call" else "top_puts") or []
        book = book[:TOP_OI_PER_SIDE]
        for c in book:
            if not isinstance(c, dict):
                continue
            oi = c.get("oi") or 0
            vol = c.get("volume") or 0
            price = c.get("price")
            strike = c.get("strike") or 0
            dte = c.get("dte")
            if oi < MIN_OI or vol <= 0 or price is None or price <= 0:
                continue
            if dte is None or not (MIN_DTE <= dte <= MAX_DTE):
                continue
            if spot and abs(strike - spot) / spot > MAX_MONEYNESS:
                continue
            cands.append({"ticker": tk, "type": side, "strike": strike,
                          "expiry": c.get("expiry"), "dte": dte, "oi": oi, "volume": vol,
                          "price": price, "underlying": round(spot, 2),
                          "symbol": c.get("symbol"), "tv_url": c.get("tv_url"),
                          "trend": tr["trend"]})

    maxima = {
        "oi": max((c["oi"] for c in cands), default=1),
        "vol": max((c["volume"] for c in cands), default=1),
        "price": max((c["price"] for c in cands), default=1),
    }
    for c in cands:
        c["score"] = contract_score(c, trends[c["ticker"]], c["underlying"], maxima)
        c["why"] = why(c, trends[c["ticker"]], c["underlying"])
    cands.sort(key=lambda c: -c["score"])

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "rules": RULES,
        "method": f"major swing levels — daily k={DAILY_K}, 4h k={H4_K}",
        "thresholds": {"max_underlying": MAX_UNDERLYING, "ideal_underlying": IDEAL_UNDERLYING,
                       "top_oi_per_side": TOP_OI_PER_SIDE, "min_dte": MIN_DTE, "max_dte": MAX_DTE},
        "counts": {"names": len(prices), "candidates": len(cands)},
        "trends": trends,
        "opportunities": cands[:a.top],
    }
    with open(a.out, "w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"strategy: {len(cands)} candidates across {len(prices)} names; "
          f"wrote top {len(out['opportunities'])} to {a.out}", file=sys.stderr)
    for c in out["opportunities"]:
        print(f"  {c['ticker']:6} {c['type'].upper():4} {c['strike']:g} {c['expiry']} "
              f"${c['price']:.2f} OI {c['oi']:,} vol {c['volume']:,} "
              f"[{c['trend']}] score {c['score']}")


if __name__ == "__main__":
    main()
