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
  * daily OHLC  (1 year)     for the candlestick + Bollinger view
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
    """Daily + hourly OHLCV for every ticker, in TWO batched downloads.

    Hourly used to be fetched one ticker at a time (yf.Ticker(t).history), which is slow
    and hammers Yahoo — fine for 60 tickers, not for a larger charted set. Both frames now
    come from a single grouped yf.download each.
    """
    import yfinance as yf
    out: dict[str, dict] = {t: {"daily": [], "hourly": []} for t in tickers}

    def _rows(df, daily: bool) -> list[dict]:
        rows = []
        for ts, row in df.iterrows():
            try:
                rows.append({
                    "t": ts.date().isoformat() if daily else int(ts.timestamp()),
                    "o": round(float(row["Open"]), 4), "h": round(float(row["High"]), 4),
                    "l": round(float(row["Low"]), 4), "c": round(float(row["Close"]), 4),
                    "v": int(row["Volume"] or 0),
                })
            except Exception:
                continue
        return rows

    def _frame(period: str, interval: str, field: str) -> None:
        try:
            data = yf.download(tickers, period=period, interval=interval,
                               group_by="ticker", progress=False,
                               auto_adjust=False, threads=True)
        except Exception as e:
            print(f"  {field} download failed: {e}", file=sys.stderr)
            return
        for t in tickers:
            try:
                df = data[t] if len(tickers) > 1 else data
                if df is not None:
                    out[t][field] = _rows(df.dropna(), field == "daily")
            except Exception:
                continue

    _frame("1y", "1d", "daily")
    _frame("60d", "1h", "hourly")
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
                pub = c.get("pubDate") or c.get("displayTime") or ""
                if not pub and a.get("providerPublishTime"):
                    # yf.Search returns flat items with an epoch publish time
                    pub = datetime.utcfromtimestamp(int(a["providerPublishTime"])).date().isoformat()
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


# ------------------------------------------------------------- big money
def aggregate_big_money(txs: list[dict]) -> list[dict]:
    """Per-ticker estimated dollars committed by LARGE trades.

    Disclosure amounts are ranges, so we use the range MIDPOINT and label the
    result 'estimated'. 'Over $5,000,000' falls back to its low bound.
    """
    agg: dict[str, dict] = {}
    for t in txs:
        if not t.get("is_large") or not t.get("ticker"):
            continue
        lo = t.get("amount_low") or 0
        hi = t.get("amount_high") or lo
        mid = (lo + hi) / 2
        a = agg.setdefault(t["ticker"], {
            "ticker": t["ticker"], "asset": t.get("asset_raw", ""),
            "buy_est": 0.0, "sell_est": 0.0, "n_buy": 0, "n_sell": 0,
            "last_date": "", "politicians": set(),
        })
        if t["direction"] == "buy":
            a["buy_est"] += mid
            a["n_buy"] += 1
        elif t["direction"] == "sell":
            a["sell_est"] += mid
            a["n_sell"] += 1
        a["politicians"].add(t["politician"])
        if (t.get("txn_date") or "") > a["last_date"]:
            a["last_date"] = t["txn_date"]
    out = []
    for a in agg.values():
        a["politicians"] = sorted(a["politicians"])
        a["n_politicians"] = len(a["politicians"])
        a["total_est"] = a["buy_est"] + a["sell_est"]
        a["net_est"] = a["buy_est"] - a["sell_est"]
        a["buy_est"] = round(a["buy_est"])
        a["sell_est"] = round(a["sell_est"])
        a["total_est"] = round(a["total_est"])
        a["net_est"] = round(a["net_est"])
        out.append(a)
    out.sort(key=lambda x: x["total_est"], reverse=True)
    return out


# --------------------------------------------------------------------- main
def fetch_sectors(tickers: list[str]) -> dict:
    """Sector + industry label per ticker, from data/profiles.json (SEC SIC codes).

    Deliberately NOT Yahoo's `.info`: that endpoint rate-limits bursts, and a failed
    burst used to blank out every sector — which silently zeroed the committee-oversight
    flags with it. SEC's submissions API is authoritative and does not behave that way.
    """
    try:
        prof = json.load(open("data/profiles.json"))
    except Exception:
        print("[enrich] data/profiles.json missing — sectors unavailable", file=sys.stderr)
        return {}
    out = {}
    # Return the WHOLE profile map, not just the congressional tickers — the dashboard's
    # open-interest board also covers the high-OI option universe, and those rows need a
    # sector too (TSLA/INTC were rendering blank because of this filter).
    for t, p in prof.items():
        out[t] = {"sector": p.get("sector"), "industry": p.get("industry"),
                  "sic": p.get("sic"), "name": p.get("name")}
    return out


def load_committees() -> dict:
    try:
        return json.load(open("data/committees.json"))
    except Exception:
        return {}


# ------------------------------------------------------------- oversight
def attach_oversight(txs: list[dict], people: dict, com: dict, sectors: dict,
                     insiders: dict | None = None) -> None:
    """Flag trades where the politician sits on a committee that oversees the sector,
    or is / was an OFFICER or DIRECTOR of the company itself.

    The second case is the one committee logic cannot reach: not "regulates the
    company" but "ran the company".
    """
    members = com.get("members") or {}
    sec_map = com.get("sector_committees") or {}
    ins = insiders or {}
    for t in txs:
        t["oversight"] = []
        t["insider"] = None
        pol = t.get("politician")
        ticker = t.get("ticker")
        # officer / director of the traded company (verified against an SEC Form 4)
        if pol and ticker and ticker in (ins.get(pol) or {}):
            t["insider"] = ins[pol][ticker]
        bio = (people.get(pol) or {}).get("bioguide")
        if not bio or not ticker:
            continue
        sector = (sectors.get(ticker) or {}).get("sector")
        relevant = set(sec_map.get(sector or "", []))
        if not relevant:
            continue
        for seat in members.get(bio, []):
            if seat.get("code") in relevant:
                t["oversight"].append({
                    "code": seat["code"],
                    "title": seat.get("title"),
                    "rank": seat.get("rank"),
                })


# --------------------------------------------------- open-interest board
def build_oi_board(tickers: list[str], options: dict, prices: dict,
                   sectors: dict, txs: list[dict]) -> list[dict]:
    """Rank the tracked stocks by total open interest in their option market.

    Absolute open interest largely measures market cap, so each row also carries a
    RELATIVE figure — open interest expressed as days of the stock's own average daily
    share volume — which is what separates "big because it's Apple" from "unusually
    loaded".  We also cross-reference the app's core signal: how many politicians
    traded that ticker.
    """
    from collections import Counter, defaultdict
    trades_n: Counter = Counter()
    pols: dict = defaultdict(set)
    for t in txs:
        tk = t.get("ticker")
        if tk:
            trades_n[tk] += 1
            if t.get("politician"):
                pols[tk].add(t["politician"])

    board = []
    # Iterate the OPTION universe, not the congressional one — the board must also show
    # high-open-interest names Congress never touched (SPY, TSLA, the retail favourites).
    for tk in sorted(options.keys()):
        if tk.startswith("_"):
            continue          # metadata keys (_top_oi) are not tickers
        o = options.get(tk) or {}
        call = o.get("call_oi") or 0
        put = o.get("put_oi") or 0
        total = call + put
        if total <= 0:
            continue
        # ADV: prefer the batched value from fetch_options; else derive from our prices
        adv = o.get("adv") or 0
        if not adv:
            daily = (prices.get(tk) or {}).get("daily") or []
            vols = [b.get("v") or 0 for b in daily[-30:]]
            adv = sum(vols) / len(vols) if vols else 0
        # contracts control 100 shares each; compare to average daily share volume
        days = round((total * 100) / adv, 1) if adv > 0 else None
        board.append({
            "ticker": tk,
            "sector": (sectors.get(tk) or {}).get("sector"),
            "call_oi": call,
            "put_oi": put,
            "total_oi": total,
            "pc_ratio": round(put / call, 2) if call else None,
            "expiry": o.get("expiry"),
            "dte": o.get("dte"),
            "adv": int(adv),
            "oi_days_of_volume": days,
            "n_trades": trades_n.get(tk, 0),
            "n_politicians": len(pols.get(tk, ())),
            # does this app have a stock page for it (i.e. did Congress trade it)?
            "tracked": tk in prices,
        })
    board.sort(key=lambda r: -r["total_oi"])
    return board


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/house_trades.json")
    ap.add_argument("--out", default="data/app_data.json")
    ap.add_argument("--window", type=int, default=14)
    ap.add_argument("--days", type=int, default=120, help="keep trades within N days")
    ap.add_argument("--max-tickers", type=int, default=120)
    ap.add_argument("--also", nargs="*", default=["data/senate_trades.json"],
                    help="extra transaction files to merge (e.g. the Senate)")
    a = ap.parse_args()

    src = load(a.inp)
    txs = list(src["transactions"])
    sources = [src.get("source", "")]
    for extra in (a.also or []):
        if os.path.exists(extra):
            e = load(extra)
            txs += e["transactions"]
            sources.append(e.get("source", ""))
            print(f"[enrich] merged {len(e['transactions'])} trades from {extra}", file=sys.stderr)
    chamber_counts = {}
    for t in txs:
        chamber_counts[t.get("chamber", "?")] = chamber_counts.get(t.get("chamber", "?"), 0) + 1
    print(f"[enrich] chambers: {chamber_counts}", file=sys.stderr)

    # politician roster (state / party / photo), resolved by politicians.py
    people = {}
    if os.path.exists("data/politicians.json"):
        try:
            people = json.load(open("data/politicians.json"))
            print(f"[enrich] {len(people)} politicians resolved", file=sys.stderr)
        except Exception as e:
            print(f"[enrich] politicians.json unreadable: {e}", file=sys.stderr)

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
    big_money = aggregate_big_money(txs)
    for c in clusters:
        for tid in c["trades"]:
            for t in txs:
                if t["id"] == tid:
                    t.setdefault("cluster_ids", []).append(
                        f"{c['ticker']}:{c['n_politicians']}p")

    # Prioritise the tickers the UI leans on: cluster signals first (most politicians),
    # then large trades, then most-traded — instead of alphabetical order.
    score: dict[str, tuple] = {}
    for t in txs:
        tk = t.get("ticker")
        if not tk:
            continue
        cl, lg, n = score.get(tk, (0, 0, 0))
        score[tk] = (cl, lg + (1 if t["is_large"] else 0), n + 1)
    for c in clusters:
        cl, lg, n = score.get(c["ticker"], (0, 0, 0))
        score[c["ticker"]] = (max(cl, c["n_politicians"]), lg, n)
    # Which tickers get price history?  Score-ranked, BUT always include the biggest
    # option markets that Congress also traded: they're featured on the dashboard's
    # open-interest board, and clicking one must not land on an empty chart.  (INTC is
    # #5 by open interest but has a single $1K-$15K trade, so score alone dropped it.)
    try:
        _opts = json.load(open("data/options.json"))
        _by_oi = sorted(_opts, key=lambda k: -((_opts[k].get("call_oi") or 0)
                                               + (_opts[k].get("put_oi") or 0)))
    except Exception:
        _by_oi = []
    ranked = sorted(score, key=lambda k: (-score[k][0], -score[k][1], -score[k][2], k))
    must = [t for t in _by_oi[:25] if t in score]        # traded AND option-heavy
    seen: set = set()
    tickers = []
    for t in must + ranked:
        if t not in seen:
            seen.add(t)
            tickers.append(t)
    tickers = tickers[: a.max_tickers]
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

    print("[enrich] resolving sectors + committee oversight...", file=sys.stderr)
    sectors = fetch_sectors(tickers)
    com = load_committees()
    try:
        insiders = json.load(open("data/insiders.json"))
    except Exception:
        insiders = {}
    attach_oversight(txs, people, com, sectors, insiders)
    n_over = sum(1 for t in txs if t.get("oversight"))
    n_ins = sum(1 for t in txs if t.get("insider"))
    print(f"[enrich] oversight: {n_over} trades via committee jurisdiction; "
          f"{n_ins} via verified officer/director status", file=sys.stderr)
    member_committees = {
        v["bioguide"]: [{"code": s["code"], "title": s.get("title")}
                        for s in (com.get("members") or {}).get(v["bioguide"], [])]
        for v in (people or {}).values() if v.get("bioguide")
    }
    committee_names = {k: v.get("short") for k, v in (com.get("committees") or {}).items()}

    # dashboard board: stocks by total option open interest
    try:
        options = json.load(open("data/options.json"))
    except Exception:
        options = {}
        print("[enrich] data/options.json missing — OI board unavailable", file=sys.stderr)
    oi_board = build_oi_board(tickers, options, prices, sectors, txs)
    if oi_board:
        tops = ", ".join(f"{r['ticker']} {r['total_oi']:,}" for r in oi_board[:3])
        print(f"[enrich] OI board: {len(oi_board)} tickers (top: {tops})", file=sys.stderr)

    bundle = {
        "generated": datetime.utcnow().isoformat() + "Z",
        "source": " · ".join(s for s in sources if s),
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
        "big_money": big_money,
        "politicians": people,
        "committees": committee_names,
        "member_committees": member_committees,
        "insiders": insiders,
        "sectors": sectors,
        "oi_board": oi_board,
        # cross-ticker top-50 leaderboard, computed in fetch_options from the full chains
        "top_oi": options.get("_top_oi"),
        "prices": prices,
        "news": news,
    }
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(bundle, open(a.out, "w"))
    print(f"[enrich] wrote {a.out} ({os.path.getsize(a.out)//1024} KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
