#!/usr/bin/env python3
"""Options read per ticker: where open interest is concentrated, contract prices,
and a TradingView link for each contract.

Data: Yahoo option chains (yfinance).  We pick the single most-active expiry in a
sensible window, then report the strikes carrying the most open interest on the
CALL side and the PUT side — the classic "walls".

TradingView symbol format (verified 2026-11):
    OCC  AAPL261116C00355000
    TV   OPRA:AAPL261116C355.0
  i.e. root + YYMMDD + C/P + strike (no zero padding, one decimal kept).
  Page:  https://www.tradingview.com/symbols/OPRA-AAPL261116C355.0/

Output: data/options.json
  { "AAPL": { "underlying":356.27, "expiry":"2026-12-18", "dte":33,
              "call_oi":..., "put_oi":..., "pc_ratio":0.83,
              "top_calls":[{strike,oi,volume,price,bid,ask,iv,symbol,tv_url}],
              "top_puts":[...], "expiries":[...] } }

Usage: python fetch_options.py [--in data/app_data.json] [--out data/options.json]
                               [--max 60] [--top 4]
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
    """Best available contract price: last, else mid of bid/ask."""
    try:
        last = float(row.get("lastPrice") or 0)
    except Exception:
        last = 0.0
    try:
        b, a = float(row.get("bid") or 0), float(row.get("ask") or 0)
    except Exception:
        b = a = 0.0
    if last > 0:
        return round(last, 2)
    if b > 0 and a > 0:
        return round((b + a) / 2, 2)
    return round(max(b, a), 2) if max(b, a) > 0 else None


def pick_expiry(exps, chains, lo=7, hi=75):
    """The most-active expiry inside the window (by total open interest)."""
    today = date.today()
    best = None
    for e in exps[:10]:
        try:
            d = datetime.strptime(e, "%Y-%m-%d").date()
        except Exception:
            continue
        dte = (d - today).days
        if dte < lo or dte > hi:
            continue
        ch = chains.get(e)
        if not ch:
            continue
        c, p = ch
        total = int((c["openInterest"].fillna(0)).sum() + (p["openInterest"].fillna(0)).sum())
        if best is None or total > best[1]:
            best = (e, total, dte)
    return best  # (expiry, total_oi, dte) or None


def top_rows(df, n):
    d = df.copy()
    d["openInterest"] = d["openInterest"].fillna(0)
    d = d[d["openInterest"] > 0].nlargest(n, "openInterest")
    out = []
    for _, r in d.iterrows():
        out.append({
            "strike": float(r["strike"]),
            "oi": int(r["openInterest"]),
            "volume": int(r.get("volume") or 0) if r.get("volume") == r.get("volume") else 0,
            "price": price_of(r),
            "bid": float(r["bid"]) if r.get("bid") == r.get("bid") else None,
            "ask": float(r["ask"]) if r.get("ask") == r.get("ask") else None,
            "iv": round(float(r["impliedVolatility"]) * 100, 1) if r.get("impliedVolatility") == r.get("impliedVolatility") else None,
            "symbol": tv_symbol(r.get("contractSymbol")),
            "tv_url": tv_url(r.get("contractSymbol")),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/app_data.json")
    ap.add_argument("--out", default="data/options.json")
    ap.add_argument("--max", type=int, default=60)
    ap.add_argument("--top", type=int, default=4)
    a = ap.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        print("[options] yfinance not installed", file=sys.stderr)
        return 2

    data = json.load(open(a.inp))
    tickers = sorted((data.get("prices") or {}).keys())[: a.max]
    print(f"[options] {len(tickers)} tickers", file=sys.stderr)

    out, ok, skipped = {}, 0, []
    for i, t in enumerate(tickers, 1):
        try:
            tk = yf.Ticker(t)
            exps = list(tk.options or [])
            if not exps:
                skipped.append(t)
                continue
            chains = {}
            for e in exps[:8]:
                try:
                    ch = tk.option_chain(e)
                    chains[e] = (ch.calls, ch.puts)
                except Exception:
                    continue
            pick = pick_expiry(exps, chains)
            if not pick:
                skipped.append(t)
                continue
            exp, _, dte = pick
            calls, puts = chains[exp]
            call_oi = int(calls["openInterest"].fillna(0).sum())
            put_oi = int(puts["openInterest"].fillna(0).sum())
            spot = None
            try:
                spot = float(tk.fast_info.get("lastPrice") or 0) or None
            except Exception:
                pass
            out[t] = {
                "underlying": spot,
                "expiry": exp,
                "dte": dte,
                "call_oi": call_oi,
                "put_oi": put_oi,
                "pc_ratio": round(put_oi / call_oi, 2) if call_oi else None,
                "top_calls": top_rows(calls, a.top),
                "top_puts": top_rows(puts, a.top),
                "expiries": exps[:8],
            }
            ok += 1
            print(f"  [{i}/{len(tickers)}] {t:6s} exp={exp} dte={dte:3d} "
                  f"callOI={call_oi:>7,} putOI={put_oi:>7,}", file=sys.stderr)
        except Exception as e:
            print(f"  ! {t}: {type(e).__name__} {e}", file=sys.stderr)
            skipped.append(t)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"))
    print(f"[options] wrote {a.out} — {ok} tickers with data, no options: {skipped}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
