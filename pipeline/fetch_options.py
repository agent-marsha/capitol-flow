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


# Funds are not companies.  The leaderboard is meant to answer "which single bet on a real
# business is the biggest", and funds swamped it: HYG alone took 31 of the 50 puts and TLT
# another 20, because open interest counts CONTRACTS and their options cost $0.02-$0.88 —
# one cheap HYG contract counted the same as one $1,344 NVDA contract.
#
# Mirrors FUND_TICKERS in fundamentals.py (kept in sync by hand rather than importing, so
# a change to one pipeline can never silently reshape the other).  SPY and QQQ are
# explicitly KEPT by request.
LEADERBOARD_FUNDS = {
    "SPY", "QQQ", "IWM", "DIA", "TLT", "TLH", "GLD", "SLV", "USO", "HYG", "EEM", "FXI",
    "VXX", "UVXY", "SOXL", "TQQQ", "SQQQ", "AVUV", "SPYM", "TOELF",
    # bond / Treasury / commodity funds that could reach the top 50
    "LQD", "AGG", "BND", "IEF", "SHY", "JNK", "EMB", "MUB", "TIP", "GDX", "GDXJ", "UNG",
    "XLE", "XLF", "XLV", "XLI", "XLK", "XLP", "XLU", "XLY", "XLB", "XLRE", "XLC",
    "ARKK", "IBIT", "ETHA",
}
LEADERBOARD_KEEP = {"SPY", "QQQ"}          # requested exceptions


def is_fund(t: str) -> bool:
    """True for ETFs/ETNs/trusts that aren't operating companies (SPY/QQQ excepted)."""
    u = (t or "").upper()
    return u in LEADERBOARD_FUNDS and u not in LEADERBOARD_KEEP


def occ_of(root: str, expiry: str, side: str, strike: float) -> str:
    """Build an OCC symbol: ROOT + YYMMDD + C|P + strike to 3dp in 8 digits.

    e.g. ("AAPL", "2026-12-18", "call", 360.0) -> "AAPL261218C360000", which tv_symbol()
    turns into the TradingView form "AAPL261218C360.0".
    """
    ymd = (expiry or "").replace("-", "")[2:]
    cp = "C" if side == "call" else "P"
    return f"{root}{ymd}{cp}{int(round(float(strike) * 1000)):08d}"


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


def expire_list(exps, lo=30, hi=400, limit=10):
    """The next ~10 expirations, starting ONE MONTH out.

    User rule: "all dates you look at should be at least a month out — don't show me
    anything closer than one month — so you start from one month out and grab like the
    next 10 expiration dates."

    So the floor is 30 DTE, nothing nearer is considered, and we take the next 10 listed
    expirations from there.  `hi` is only a sanity guard (~13 months) so a quarterly-only
    listing can't drag in two-year LEAPS; if a ticker has fewer than 10 inside it, it
    simply returns fewer.  The window is now set by the user's rule, not by list position.

    History: this used to be the nearest 6 inside 7-75 DTE, which fetched near-dated
    contracts the user explicitly does not want and capped the list by position.
    """
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


# Underlyings with the deepest option markets, INDEPENDENT of whether Congress traded
# them.  Without these the OI board was bounded by the trade data, so it could never
# show the market's actual biggest option piles (SPY/QQQ, TSLA, the retail favourites).
EXTRA_HIGH_OI = [
    # index / rate / commodity ETFs — the largest option markets there are
    "SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "SLV", "USO", "HYG", "EEM", "FXI",
    "VXX", "UVXY", "SOXL", "TQQQ", "SQQQ",
    # mega / large caps not necessarily in the congressional set
    "NVDA", "TSLA", "GOOGL", "JPM", "JNJ", "MA", "AVGO", "ORCL", "CRM", "ADBE", "AMD",
    "INTC", "CSCO", "QCOM", "TXN", "IBM", "PFE", "MRK", "ABBV", "TMO", "PEP",
    "KO", "MCD", "NKE", "DIS", "BA", "CAT", "GS", "MS", "AXP", "CMCSA", "ORCL",
    # high-retail-option names
    "PLTR", "SOFI", "F", "RIVN", "LCID", "NIO", "GME", "AMC", "MARA", "RIOT",
    "COIN", "HOOD", "SNAP", "UBER", "AAL", "DAL", "CCL", "DKNG", "RBLX", "AI",
    "IONQ", "RGTI", "QBTS", "PYPL", "SHOP", "CRWD", "SNOW", "MSTR", "SMCI", "ARM",
]


def _dedupe(seq) -> list[str]:
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/app_data.json")
    ap.add_argument("--out", default="data/options.json")
    ap.add_argument("--max", type=int, default=60)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--no-extra", action="store_true",
                    help="skip the high-open-interest universe (congressional tickers only)")
    ap.add_argument("--no-history", action="store_true",
                    help="skip appending to the open-interest history (used by backfills/tests)")
    a = ap.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        print("[options] yfinance not installed", file=sys.stderr)
        return 2

    data = json.load(open(a.inp))
    # Pick the tickers that MATTER, not the ones that come first in the alphabet.
    #
    # This was `sorted(prices)[:max]` — an A-through-J slice of the tracked set.  It
    # silently dropped NVDA (position 80 of 120) from options.json, so NVDA's stock page
    # lost its entire options section while every ticker starting with A kept theirs.
    # Nothing about "A" makes a ticker worth fetching; rank by previous-run open interest
    # (the biggest option markets), then by how many congressional trades it has.
    _prices = data.get("prices") or {}
    _oi = {r.get("ticker"): (r.get("total_oi") or 0) for r in (data.get("oi_board") or [])}
    _trades: dict = {}
    for _t in (data.get("trades") or []):
        _tk = _t.get("ticker")
        if _tk:
            _trades[_tk] = _trades.get(_tk, 0) + 1
    ranked = sorted(_prices.keys(), key=lambda t: (-_oi.get(t, 0), -_trades.get(t, 0), t))
    base = ranked[: a.max]
    extras = [] if a.no_extra else [t for t in _dedupe(EXTRA_HIGH_OI) if t not in set(base)]
    tickers = base + extras
    print(f"[options] {len(tickers)} tickers ({len(base)} ranked by OI/trades + "
          f"{len(extras)} high-OI), top {a.top} per side", file=sys.stderr)

    out, ok, skipped = {}, 0, []
    ledger = []          # every contract in the window, across every ticker — see below
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

            # ---- global contract ledger -------------------------------------------
            # The cross-ticker leaderboard (top 50 calls / top 50 puts by OI) CANNOT be
            # built from the per-ticker top-10 above: a huge name's 11th-largest contract
            # can outrank a small name's 1st, so a top-10-per-ticker cut silently
            # undertstates the leaderboard.  Every contract in the window is collected
            # here instead, while the full chains are already in memory.  Costs no extra
            # network calls.
            for e, dte in exp_list:
                cdf, pdf = chains[e]
                for side, df in (("call", cdf), ("put", pdf)):
                    if df is None or df.empty:
                        continue
                    for _, r0 in df.iterrows():
                        try:
                            oi = int(num(r0.get("openInterest"), 0))
                        except Exception:
                            continue
                        if oi <= 0:
                            continue
                        try:
                            k = float(r0["strike"])
                        except Exception:
                            continue
                        b_, a_ = num(r0.get("bid"), 0), num(r0.get("ask"), 0)
                        mid = round((b_ + a_) / 2.0, 2) if (b_ > 0 and a_ > 0) else None
                        ledger.append({
                            "ticker": t, "type": side, "strike": k, "expiry": e, "dte": dte,
                            "oi": oi, "volume": int(num(r0.get("volume"), 0)),
                            "price": mid, "underlying": round(spot, 2) if spot else None,
                            "symbol": tv_symbol(occ_of(t, e, side, k)),
                            "tv_url": tv_url(occ_of(t, e, side, k)),
                        })
            ok += 1
            print(f"  [{i}/{len(tickers)}] {t:6s} exps={len(exp_list)} "
                  f"callOI={call_oi:>8,} putOI={put_oi:>8,}", file=sys.stderr)
        except Exception as e:
            print(f"  ! {t}: {type(e).__name__} {e}", file=sys.stderr)
            skipped.append(t)

    # Average daily SHARE volume, in ONE batched download.  Needed for the "loading"
    # metric on every board row — including tickers we hold no price history for.
    try:
        import yfinance as yf
        px = yf.download(list(out.keys()), period="1mo", interval="1d",
                         progress=False, auto_adjust=False, threads=True)
        vol = px["Volume"]
        for t in list(out.keys()):
            try:
                s = vol[t].dropna()
                if len(s):
                    out[t]["adv"] = int(float(s.mean()))
            except Exception:
                pass
        got = sum(1 for v in out.values() if v.get("adv"))
        print(f"[options] ADV resolved for {got}/{len(out)} tickers", file=sys.stderr)
    except Exception as e:
        print(f"[options] ADV fetch failed: {type(e).__name__} {e}", file=sys.stderr)

    # ---- cross-ticker leaderboard: top 50 calls + top 50 puts by open interest -------
    # Stored under an underscore key so it rides along in options.json for the browser
    # (the same convention as fundamentals' _sectors) without looking like a ticker.
    # Ranked on INDIVIDUAL contracts, not per-strike sums: an "option" is a specific
    # ticker+expiry+strike+side, and mixing expiries would invent instruments.
    TOP_N = 100
    MIN_PRICE = 0.20

    def _topN(side: str, n: int = TOP_N):
        # funds are excluded so this ranks bets on real companies (SPY/QQQ kept by request)
        # and so are contracts under MIN_PRICE: open interest counts CONTRACTS, so a $0.01
        # strike ties with a $1,344 one on the count while representing almost no money.
        # Rows with no quote at all are dropped too — a price floor can't be verified.
        rows = [r for r in ledger
                if r["type"] == side
                and not is_fund(r["ticker"])
                and r.get("price") is not None
                and r["price"] >= MIN_PRICE]
        # WEIGHT BY CONTRACT VALUE (user, 2026-11-27): "the volume is high however the contract
        # value is low ... lets add a weight for contract value so that we are actually
        # evaluating the amount of money is at risk not just a contract count".
        #
        # notional = contracts x 100 shares x price = the dollars of open interest.  Ranked by
        # this, NVDA's 70,830 x $0.39 ($2.8M) drops out of the top and QQQ's $750 put at
        # $109.53 x 38,526 ($422M) — 13x the money, previously invisible — comes in.
        #
        # CAVEAT carried on every row: a notional ranking favours deep-ITM contracts, which are
        # often synthetic stock rather than a directional bet (the GOOG $75 call case).  So the
        # row keeps `oi` too, and carries `moneyness` = strike / underlying so the UI can show
        # which is which instead of letting the dollar figure imply a conviction it may not be.
        for r in rows:
            r["notional"] = int(round(r["oi"] * 100 * r["price"]))
            u = r.get("underlying")
            r["moneyness"] = round(r["strike"] / u, 4) if (u and u > 0) else None
        rows.sort(key=lambda r: (-r["notional"], r["ticker"], r["strike"]))
        return rows[:n]

    dropped_cheap = sum(1 for r in ledger
                        if not is_fund(r["ticker"])
                        and (r.get("price") is None or r["price"] < MIN_PRICE))
    # Per-ticker NOTIONAL totals, accumulated from the ledger so they use the same price the
    # leaderboard does instead of a second, divergent quote rule.  Feeds the OI board so it can
    # rank by money rather than contract count (user request, 2026-11-27).
    for r in ledger:
        rec = out.get(r["ticker"])
        if not isinstance(rec, dict) or r.get("price") is None:
            continue
        key = "call_notional" if r["type"] == "call" else "put_notional"
        rec[key] = int(rec.get(key, 0)) + int(round(r["oi"] * 100 * r["price"]))
    for k, rec in out.items():
        if not isinstance(rec, dict):
            continue
        cn, pn = int(rec.get("call_notional", 0)), int(rec.get("put_notional", 0))
        rec["total_notional"] = cn + pn
        priced = cn + pn
        rec["notional_priced"] = priced > 0

    calls50, puts50 = _topN("call"), _topN("put")
    funds_seen = sorted({r["ticker"] for r in ledger if is_fund(r["ticker"])})
    n_exp = 10
    out["_top_oi"] = {
        "calls": calls50,
        "puts": puts50,
        "n": TOP_N,
        "min_dte": 30,
        "min_price": MIN_PRICE,
        "expirations": n_exp,
        "universe": len(out),
        "contracts_scanned": len(ledger),
        "dropped_under_min_price": dropped_cheap,
        "companies_only": True,
        "kept_funds": sorted(LEADERBOARD_KEEP),
        "excluded_funds": funds_seen,
    }
    if calls50:
        print(f"[options] leaderboard: {len(ledger):,} contracts scanned, "
              f"{dropped_cheap:,} dropped under ${MIN_PRICE:.2f}, "
              f"top call {calls50[0]['ticker']} ${calls50[0]['strike']:g} {calls50[0]['expiry']} "
              f"OI {calls50[0]['oi']:,} @ ${calls50[0]['price']}; top put {puts50[0]['ticker']} "
              f"${puts50[0]['strike']:g} {puts50[0]['expiry']} OI {puts50[0]['oi']:,} "
              f"@ ${puts50[0]['price']}",
              file=sys.stderr)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"))
    print(f"[options] wrote {a.out} — {ok} tickers with data, no options: {skipped}", file=sys.stderr)

    # Append this run to the open-interest history.  Requested: keep track of the OI on every
    # daily run, for every stock we pull.  Non-fatal -- a history failure must never lose the
    # day's option data, which is what the app actually serves.
    if not getattr(a, "no_history", False):
        try:
            import oi_history_store as hist
            rec = hist.build_record(out)
            p, s = hist.write(rec)
            n_c = sum(len(v["calls"]) for v in rec["tickers"].values())
            n_p = sum(len(v["puts"]) for v in rec["tickers"].values())
            print(f"[options] OI history {rec['date']}: {len(rec['tickers'])} tickers, "
                  f"{n_c} call + {n_p} put contracts -> {p}", file=sys.stderr)
        except Exception as e:
            print(f"[options] OI history FAILED ({type(e).__name__}: {e}) — continuing",
                  file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
