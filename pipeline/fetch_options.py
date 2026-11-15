#!/usr/bin/env python3
"""Options read per ticker: where open interest is concentrated, contract prices,
expiration dates, and a TradingView link for each contract.

Data: Yahoo option chains (yfinance).  We look at the nearest few expirations in a
sensible window and aggregate open interest BY STRIKE, so a strike that is heavily
positioned across several expiries shows up once, with its dominant expiration.

TradingView symbol format (verified 2026-11):
    OCC  AAPL261127C00362500
    TV   OPRA:AAPL261127C362.5
  i.e. root + YYMMDD + C/P + strike (no zero padding, one decimal kept).
  Page:  https://www.tradingview.com/symbols/OPRA-AAPL261127C362.5/

Output: data/options.json
  { "AAPL": { "underlying":356.27,
              "expiry":"2026-11-27", "dte":12,          # most-active expiry
              "expiries_considered":[...],
              "call_oi":..., "put_oi":..., "pc_ratio":0.83,
              "top_calls":[{strike,oi,expiry,dte,volume,price,bid,ask,iv,
                            symbol,tv_url,parts:[{expiry,oi}]}],
              "top_puts":[...] } }

Usage: python fetch_options.py [--in data/app_data.json] [--out data/options.json]
                               [--max 60] [--top 10]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import warnings
from datetime import date, datetime

warnings.filterwarnings("ignore")


def tv_symbol(occ: str):
    """OCC contract symbol -> TradingView option symbol (or None)."""
    m = re.match(r"^([A-Z0-9.]+?)(\d{6})([CP])(\d{8})$", (occ or "").upper())
    if not m:
        return None
    root, ymd, cp, strike = m.groups()
    st = int(strike) / 1000.0
    s = f"{st:.3f}".rstrip("0")
    if s.endswith("."):
        s += "0"
    return f"{root}{ymd}{cp}{s}"


def tv_url(occ: str):
    s = tv_symbol(occ)
    return f"https://www.tradingview.com/symbols/OPRA-{s}/" if s else None


def price_of(row):
    """Best available contract price: last trade, else mid of bid/ask."""
    try:
        last = float(row.get("lastPrice") or 0)
    except Exception:
        last = 0.0
    try:
        b, a = float(row.get("bid") or 0), float(row.get("ask") or 0)
    except Exception:
        b = a = 0.0
    if last > 0:
        return round(last, 2), "last"
    if b > 0 and a > 0:
        return round((b + a) / 2, 2), "mid"
    m = max(b, a)
    return (round(m, 2), "last") if m > 0 else (None, None)


def num(x, default=0):
    try:
        f = float(x)
        return default if f != f else f          # NaN check
    except Exception:
        return default


def expire_list(exps, lo=7, hi=75, limit=6):
    """Nearest expirations inside the window, oldest first."""
    today = date.today()
    out = []
    for e in exps:
        try:
            d = datetime.strptime(e, "%Y-%m-%d").date()
        except Exception:
            continue
        dte = (d - today).days
        if lo <= dte <= hi:
            out.append((e, dte))
        if len(out) >= limit:
            break
    return out


def most_active(chains, exp_list):
    """Expiry carrying the most open interest overall (for the header)."""
    best = None
    for e, dte in exp_list:
        c, p = chains[e]
        tot = num(c["openInterest"].fillna(0).sum()) + num(p["openInterest"].fillna(0).sum())
        if best is None or tot > best[2]:
            best = (e, dte, tot)
    return best


def build_side(chains, exp_list, side_idx, top_n):
    """Top strikes by open interest, aggregated across the considered expiries.

    Each strike is reported once, with the expiration that holds most of its OI.
    """
    agg: dict[float, dict] = {}
    for e, _dte in exp_list:
        df = chains[e][side_idx]
        for _, r in df.iterrows():
            oi = num(r.get("openInterest"))
            if oi <= 0:
                continue
            st = float(r["strike"])
            a = agg.setdefault(st, {"oi": 0.0, "parts": {}, "rows": {}})
            a["oi"] += oi
            a["parts"][e] = int(a["parts"].get(e, 0) + oi)
            a["rows"][e] = r
    ranked = sorted(agg.items(), key=lambda kv: -kv[1]["oi"])[:top_n]
    out = []
    for st, a in ranked:
        dom = max(a["parts"], key=lambda e: a["parts"][e])
        r = a["rows"][dom]
        price, basis = price_of(r)
        exp_dte = dict(exp_list)[dom]
        out.append({
            "strike": st,
            "oi": int(a["oi"]),
            "expiry": dom,
            "dte": exp_dte,
            "volume": int(num(r.get("volume"))),
            "price": price,
            "price_basis": basis,
            "bid": num(r.get("bid")) or None,
            "ask": num(r.get("ask")) or None,
            "iv": round(num(r.get("impliedVolatility")) * 100, 1) or None,
            "symbol": tv_symbol(r.get("contractSymbol")),
            "tv_url": tv_url(r.get("contractSymbol")),
            "parts": [{"expiry": e, "oi": a["parts"][e]}
                      for e in sorted(a["parts"], key=lambda e: -a["parts"][e])],
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/app_data.json")
    ap.add_argument("--out", default="data/options.json")
    ap.add_argument("--max", type=int, default=60)
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        print("[options] yfinance not installed", file=sys.stderr)
        return 2

    data = json.load(open(a.inp))
    tickers = sorted((data.get("prices") or {}).keys())[: a.max]
    print(f"[options] {len(tickers)} tickers, top {a.top} per side", file=sys.stderr)

    out, ok, skipped = {}, 0, []
    for i, t in enumerate(tickers, 1):
        try:
            tk = yf.Ticker(t)
            exps = list(tk.options or [])
            if not exps:
                skipped.append(t)
                continue
            exp_list = expire_list(exps)
            if not exp_list:
                skipped.append(t)
                continue
            chains = {}
            for e, _ in exp_list:
                try:
                    ch = tk.option_chain(e)
                    chains[e] = (ch.calls, ch.puts)
                except Exception:
                    continue
            if not chains:
                skipped.append(t)
                continue
            exp_list = [(e, d) for e, d in exp_list if e in chains]

            call_oi = sum(int(num(chains[e][0]["openInterest"].fillna(0).sum())) for e, _ in exp_list)
            put_oi = sum(int(num(chains[e][1]["openInterest"].fillna(0).sum())) for e, _ in exp_list)
            top_exp = most_active(chains, exp_list)
            try:
                spot = float(tk.fast_info.get("lastPrice") or 0) or None
            except Exception:
                spot = None

            out[t] = {
                "underlying": spot,
                "expiry": top_exp[0] if top_exp else exp_list[0][0],
                "dte": top_exp[1] if top_exp else exp_list[0][1],
                "expiries_considered": [e for e, _ in exp_list],
                "call_oi": call_oi,
                "put_oi": put_oi,
                "pc_ratio": round(put_oi / call_oi, 2) if call_oi else None,
                "top_calls": build_side(chains, exp_list, 0, a.top),
                "top_puts": build_side(chains, exp_list, 1, a.top),
            }
            ok += 1
            print(f"  [{i}/{len(tickers)}] {t:6s} exps={len(exp_list)} "
                  f"callOI={call_oi:>8,} putOI={put_oi:>8,}", file=sys.stderr)
        except Exception as e:
            print(f"  ! {t}: {type(e).__name__} {e}", file=sys.stderr)
            skipped.append(t)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"))
    print(f"[options] wrote {a.out} — {ok} tickers with data, no options: {skipped}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
