#!/usr/bin/env python3
"""Enrich parsed politician trades into the app's data bundle.

Reads  data/house_trades.json          (from fetch_house.py)
Writes data/app_data.json              (everything the frontend needs)

Applies the four editorial rules:
  1. Sales sorted most-recent-first (and shown with equal weight to buys).
  2. Large trades flagged  (>= $100k "large", >= $500k "very large").
  3. Clusters flagged: >= 2 distinct politicians trading the same ticker
     within a +/-NN-day window.
  4. (Rule 4 is a view concern; the data marks buys and sells symmetrically.)

Also attaches, per ticker:
  * daily OHLC  (6 months)   for the candlestick + Bollinger view
  * hourly OHLC (60 days, 1h)
  * recent news headlines (for the "news around the trade date" panel)

Usage: python enrich.py [--window 14] [--out data/app_data.json]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import warnings
from collections import defaultdict
from datetime import datetime, date, timedelta

warnings.filterwarnings("ignore")

LARGE = 100_000
VERY_LARGE = 500_000


def load(path: str) -> dict:
    return json.load(open(path))


# ---------------------------------------------------------------- price data
def fetch_prices(tickers: list[str]) -> dict:
    import yfinance as yf
    out: dict[str, dict] = {}
    try:
        daily = yf.download(tickers, period="6mo", interval="1d",
                            group_by="ticker", progress=False, auto_adjust=False, threads=True)
    except Exception as e:
        print(f"  daily download failed: {e}", file=sys.stderr)
        daily = None
    for t in tickers:
        rec = {"daily": [], "hourly": []}
        try:
            df = daily[t] if daily is not None and len(tickers) > 1 else daily
            if df is not None:
                df = df.dropna()
                for ts, row in df.iterrows():
                    rec["daily"].append({
                        "t": ts.date().isoformat(), "o": round(float(row["Open"]), 4),
                        "h": round(float(row["High"]), 4), "l": round(float(row["Low"]), 4),
                        "c": round(float(row["Close"]), 4), "v": int(row["Volume"] or 0),
                    })
        except Exception:
            pass
        try:
            h = yf.Ticker(t).history(period="60d", interval="1h")
            h = h.dropna()
            for ts, row in h.iterrows():
                rec["hourly"].append({
                    "t": int(ts.timestamp()), "o": round(float(row["Open"]), 4),
                    "h": round(float(row["High"]), 4), "l": round(float(row["Low"]), 4),
                    "c": round(float(row["Close"]), 4), "v": int(row["Volume"] or 0),
                })
        except Exception:
            pass
        out[t] = rec
    return out


# --------------------------------------------------------------------- news
def fetch_news(tickers: list[str], limit_per: int = 6) -> dict:
    import yfinance as yf
    out: dict[str, list] = {}
    for t in tickers:
        items = []
        try:
            s = yf.Search(t, news_count=limit_per)
            for a in (s.news or [])[:limit_per]:
                c = a.get("content") or {}
                url = (c.get("canonicalUrl") or c.get("clickThroughUrl") or {}).get("url")
                title = c.get("title") or a.get("title")
                pub = c.get("pubDate") or ""
                prov = (c.get("provider") or {}).get("displayName") or a.get("publisher")
                if title:
                    items.append({"title": title, "url": url or a.get("link"),
                                  "publisher": prov, "date": (pub or "")[:10]})
        except Exception:
            pass
        out[t] = items
    return out


# ----------------------------------------------------------------- clusters
def find_clusters(trades: list[dict], window_days: int) -> list[dict]:
    """Tickers traded by >=2 distinct politicians within a rolling window."""
    by_t: dict[str, list[dict]] = defaultdict(list)
    for tr in trades:
        if tr.get("ticker") and tr.get("txn_date"):
            by_t[tr["ticker"]].append(tr)
    clusters = []
    for t, rows in by_t.items():
        rows.sort(key=lambda r: r["txn_date"])
        for i, seed in enumerate(rows):
            d0 = date.fromisoformat(seed["txn_date"])
            grp = [r for r in rows
                   if abs((date.fromisoformat(r["txn_date"]) - d0).days) <= window_days]
            pols = {r["politician"] for r in grp}
            if len(pols) >= 2:
                key = (t, tuple(sorted(pols)))
                if not any(c["ticker"] == t and set(c["politicians"]) == pols for c in clusters):
                    clusters.append({
                        "ticker": t, "politicians": sorted(pols),
                        "n_politicians": len(pols), "n_trades": len(grp),
                        "window_start": min(r["txn_date"] for r in grp),
                        "window_end": max(r["txn_date"] for r in grp),
                        "buys": sum(1 for r in grp if r["txn_type"] == "P"),
                        "sells": sum(1 for r in grp if r["txn_type"] == "S"),
                        "trades": [r["id"] for r in grp],
                    })
    # strongest first: most politicians, then most trades
    clusters.sort(key=lambda c: (c["n_politicians"], c["n_trades"]), reverse=True)
    return clusters


# --------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/house_trades.json")
    ap.add_argument("--out", default="data/app_data.json")
    ap.add_argument("--window", type=int, default=14)
    ap.add_argument("--days", type=int, default=120, help="keep trades within N days")
    ap.add_argument("--max-tickers", type=int, default=60)
    a = ap.parse_args()

    src = load(a.inp)
    txs = src["transactions"]

    cutoff = (date.today() - timedelta(days=a.days)).isoformat()
    txs = [t for t in txs if (t.get("txn_date") or "") >= cutoff]
    for i, t in enumerate(txs):
        t["id"] = f"T{i:05d}"
        ah = t.get("amount_high") or 0
        al = t.get("amount_low") or 0
        t["is_large"] = ah >= LARGE
        t["is_very_large"] = ah >= VERY_LARGE
        t["direction"] = "buy" if t["txn_type"] == "P" else ("sell" if t["txn_type"] == "S" else "other")

    # ---- RULE 1 & 4: sales first (most recent first), then buys (most recent first) ----
    sales = sorted([t for t in txs if t["direction"] == "sell"],
                   key=lambda r: r["txn_date"], reverse=True)
    buys = sorted([t for t in txs if t["direction"] == "buy"],
                  key=lambda r: r["txn_date"], reverse=True)
    others = [t for t in txs if t["direction"] == "other"]
    ordered = sales + buys + others

    clusters = find_clusters(txs, a.window)
    for c in clusters:
        for tid in c["trades"]:
            for t in txs:
                if t["id"] == tid:
                    t.setdefault("cluster_ids", []).append(
                        f"{c['ticker']}:{c['n_politicians']}p")

    tickers = sorted({t["ticker"] for t in txs if t.get("ticker")})[: a.max_tickers]
    print(f"[enrich] {len(txs)} trades · {len(tickers)} tickers · {len(clusters)} clusters",
          file=sys.stderr)

    print(f"[enrich] fetching prices for {len(tickers)} tickers...", file=sys.stderr)
    prices = fetch_prices(tickers)
    for t in tickers:
        n = len(prices.get(t, {}).get("daily", []))
        if n:
            print(f"    {t}: {n} daily bars", file=sys.stderr)

    print("[enrich] fetching news...", file=sys.stderr)
    news = fetch_news(tickers)

    bundle = {
        "generated": datetime.utcnow().isoformat() + "Z",
        "source": src["source"],
        "window_days": a.window,
        "large_threshold": LARGE,
        "very_large_threshold": VERY_LARGE,
        "counts": {
            "trades": len(txs), "sales": len(sales), "buys": len(buys),
            "tickers": len(tickers), "clusters": len(clusters),
            "large": sum(1 for t in txs if t["is_large"]),
        },
        "trades": ordered,
        "clusters": clusters,
        "prices": prices,
        "news": news,
    }
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(bundle, open(a.out, "w"))
    print(f"[enrich] wrote {a.out} ({os.path.getsize(a.out)//1024} KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
