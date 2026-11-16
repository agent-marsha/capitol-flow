#!/usr/bin/env python3
"""Company identities + plain descriptions for every stock page.

WHY: 284 tickers have a stock page (any ticker reachable from a trade, the OI board, the
options set, or the price set).  Of those, 119 have no name anywhere in the app and 164
have no sector — because the name was only ever read out of congressional filings, so a
ticker Congress never traded showed a bare symbol with no explanation of what it is.

Sources, in order:
  1. SEC EDGAR   — authoritative legal name + SIC industry.  Free, fast, no key.
  2. yfinance    — `longBusinessSummary`, the actual business description.
  3. Fallback    — an industry line built from the SIC code when no summary exists.

The description is cut to the first couple of sentences on a sentence boundary, so it
never trails off mid-clause.  Resumable and circuit-broken like the other fetchers so a
throttled run can be restarted without losing work.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import warnings

warnings.filterwarnings("ignore")

UA = "capitol-flow research (contact: crawford@cs.ua.edu)"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# Funds that should never be looked up as operating companies.  Note BRK.B is NOT here:
# Berkshire Hathaway is a real company, not a fund, and it was wrongly skipped before.
SKIP = {"SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "SLV", "USO", "HYG", "EEM", "FXI",
        "VXX", "UVXY", "SOXL", "TQQQ", "SQQQ"}

# These have stock pages (they sit on the OI board and the contract leaderboard) but no
# company filing to read, so without an entry their pages render a bare symbol — the exact
# complaint this pipeline exists to fix.  They are a small, famous, stable set, so they are
# described by hand rather than guessed at.  Marked source="curated" so it stays auditable.
FUND_NOTES = {
    "SPY":  ("SPDR S&P 500 ETF Trust", "An exchange-traded fund that tracks the S&P 500, an index of about 500 large US companies. Buying it is a way to own the whole US market at once.", "Index fund", "S&P 500 index"),
    "QQQ":  ("Invesco QQQ Trust", "An exchange-traded fund that tracks the Nasdaq-100, an index of the 100 largest non-financial companies on the Nasdaq. It is heavily weighted toward technology.", "Index fund", "Nasdaq-100 index"),
    "IWM":  ("iShares Russell 2000 ETF", "An exchange-traded fund that tracks the Russell 2000, an index of 2,000 smaller US companies.", "Index fund", "Small-cap US stocks"),
    "DIA":  ("SPDR Dow Jones Industrial Average ETF Trust", "An exchange-traded fund that tracks the Dow Jones Industrial Average, an index of 30 large US companies.", "Index fund", "Dow Jones Industrial Average"),
    "TLT":  ("iShares 20+ Year Treasury Bond ETF", "An exchange-traded fund that holds long-dated US Treasury bonds. It rises when long-term interest rates fall and falls when they rise.", "Bond fund", "US Treasury bonds, 20+ years"),
    "GLD":  ("SPDR Gold Shares", "An exchange-traded fund that holds gold bullion. It tracks the price of gold.", "Commodity fund", "Gold"),
    "SLV":  ("iShares Silver Trust", "An exchange-traded fund that holds silver bullion. It tracks the price of silver.", "Commodity fund", "Silver"),
    "USO":  ("United States Oil Fund", "An exchange-traded fund that tracks the price of crude oil through oil futures contracts.", "Commodity fund", "Crude oil futures"),
    "HYG":  ("iShares iBoxx High Yield Corporate Bond ETF", "An exchange-traded fund that holds lower-rated corporate bonds, often called junk bonds. It pays more interest than safer bonds and carries more risk.", "Bond fund", "High-yield corporate bonds"),
    "EEM":  ("iShares MSCI Emerging Markets ETF", "An exchange-traded fund that holds stocks from emerging-market countries such as China, India, Brazil and Taiwan.", "Index fund", "Emerging-market stocks"),
    "FXI":  ("iShares China Large-Cap ETF", "An exchange-traded fund that holds stock in large Chinese companies listed in Hong Kong.", "Index fund", "Large-cap Chinese stocks"),
    "VXX":  ("iPath Series B S&P 500 VIX Short-Term Futures ETN", "A traded note that tracks short-term VIX futures, which rise when the stock market gets jumpy. It is designed for short holding periods.", "Volatility fund", "VIX futures"),
    "UVXY": ("ProShares Ultra VIX Short-Term Futures ETF", "A fund that aims to move 1.5 times as much as short-term VIX futures. It is intended for very short holding periods.", "Volatility fund", "Leveraged VIX futures"),
    "SOXL": ("Direxion Daily Semiconductor Bull 3X Shares", "A fund that aims to move three times as much as an index of semiconductor stocks, in the same direction.", "Leveraged fund", "3× semiconductors"),
    "TQQQ": ("ProShares UltraPro QQQ", "A fund that aims to move three times as much as the Nasdaq-100, in the same direction.", "Leveraged fund", "3× Nasdaq-100"),
    "SQQQ": ("ProShares UltraPro Short QQQ", "A fund that aims to move three times as much as the Nasdaq-100, in the OPPOSITE direction. It rises when the index falls.", "Leveraged fund", "3× inverse Nasdaq-100"),
}


def lookup_variants(t: str) -> list:
    """Symbol spellings to try, since data providers disagree about dots vs dashes.

    The app writes class shares with a dot (`MOG.A`, `BRK.B`); EDGAR's map and Yahoo both
    use a dash (`MOG-A`, `BRK-B`).  Without this, those tickers fall through both sources
    and the stock page goes back to showing a bare symbol.
    """
    t = (t or "").upper().strip()
    out = [t]
    if "." in t:
        out.append(t.replace(".", "-"))
        out.append(t.replace(".", ""))
    if "-" in t:
        out.append(t.replace("-", "."))
        out.append(t.replace("-", ""))
    seen, uniq = set(), []
    for x in out:
        if x and x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def num(v, d=0):
    try:
        f = float(v)
        return d if math.isnan(f) else f
    except Exception:
        return d


def _get(url: str, timeout: int = 30):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def first_sentences(text: str, max_sentences: int = 2, max_chars: int = 300) -> str:
    """Cut a summary to a couple of whole sentences — never mid-clause."""
    t = re.sub(r"\s+", " ", (text or "")).strip()
    if not t:
        return ""
    # split after . ! ? when followed by a space + capital, or at the end
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", t)
    out = ""
    for p in parts[:max_sentences]:
        cand = (out + " " + p).strip() if out else p
        if len(cand) > max_chars and out:
            break
        out = cand
    if not out:
        out = t[:max_chars].rsplit(" ", 1)[0] + "…"
    if not out.endswith((".", "!", "?", "…")):
        out += "."
    return out


def sic_tickers() -> dict:
    """ticker -> (cik, legal name) from EDGAR's public map.  One request for all of them."""
    try:
        raw = _get(SEC_TICKERS)
    except Exception as e:
        print(f"[companies] SEC ticker map failed: {type(e).__name__} {e}", file=sys.stderr)
        return {}
    out = {}
    for _, row in (raw or {}).items():
        t = str(row.get("ticker") or "").upper().strip()
        if t:
            out[t] = (int(row.get("cik_str") or 0), str(row.get("title") or "").strip())
            # also index the dot form, so a caller passing BRK.B / MOG.A finds the entry
            # that EDGAR publishes as BRK-B / MOG-A
            if "-" in t:
                out.setdefault(t.replace("-", "."), out[t])
    return out


def edgar_industry(cik: int) -> tuple:
    """(sic, sic description) for a CIK, or (None, None)."""
    try:
        sub = _get(SEC_SUBS.format(cik=cik))
        sic = str(sub.get("sic") or "").strip()
        desc = str(sub.get("sicDescription") or "").strip()
        return (sic or None, desc or None)
    except Exception:
        return (None, None)


def yf_profile(t: str) -> dict:
    """Name + business summary from Yahoo.  Best-effort; {} on failure."""
    try:
        import yfinance as yf
        info = yf.Ticker(t).info or {}
    except Exception:
        return {}
    return {
        "name": (info.get("longName") or info.get("shortName") or "").strip(),
        "summary": (info.get("longBusinessSummary") or "").strip(),
        "sector": (info.get("sector") or "").strip(),
        "industry": (info.get("industry") or "").strip(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", default="data/app_data.json")
    ap.add_argument("--options", default="data/options.json")
    ap.add_argument("--profiles", default="data/profiles.json")
    ap.add_argument("--out", default="data/companies.json")
    ap.add_argument("--max", type=int, default=0, help="cap (0 = all)")
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--yahoo", action="store_true", help="also fetch business summaries")
    a = ap.parse_args()

    # universe: anything that can be reached as a stock page
    u = set()
    try:
        d = json.load(open(a.inp))
        u |= {t.get("ticker") for t in (d.get("trades") or []) if t.get("ticker")}
        u |= {r["ticker"] for r in (d.get("oi_board") or []) if r.get("ticker")}
        u |= set((d.get("prices") or {}).keys())
    except Exception as e:
        print(f"[companies] {a.inp}: {type(e).__name__}", file=sys.stderr)
    try:
        u |= {k for k in json.load(open(a.options)) if not k.startswith("_")}
    except Exception:
        pass
    u = sorted(x for x in u if x and (x not in SKIP or x in FUND_NOTES))

    prev = {}
    if os.path.exists(a.out):
        try:
            prev = json.load(open(a.out))
        except Exception:
            prev = {}
    todo = [t for t in u if t not in prev]
    if a.max:
        todo = todo[: a.max]
    print(f"[companies] universe {len(u)} · already done {len(prev)} · to fetch {len(todo)}",
          file=sys.stderr)

    tick = sic_tickers()
    out = dict(prev)
    fails = 0
    t0 = time.time()
    for n, t in enumerate(todo, 1):
        rec = {"ticker": t, "name": None, "description": None, "sector": None,
               "industry": None, "sic": None, "source": None}
        if t in FUND_NOTES:
            # a fund with a stock page: describe it by hand, never invent a company for it
            nm, desc, sec, ind = FUND_NOTES[t]
            out[t] = {"ticker": t, "name": nm, "description": desc, "sector": sec,
                      "industry": ind, "sic": None, "source": "curated",
                      "is_fund": True}
            print(f"  [{n}/{len(todo)}] {t:6s} curated fund note", file=sys.stderr)
            continue
        try:
            # 1) EDGAR: authoritative legal name + SIC.  Try each spelling of the symbol.
            hit = next((tick[v] for v in lookup_variants(t) if v in tick), None)
            if hit:
                cik, title = hit
                rec["source"] = "sec"
                sic, sicd = edgar_industry(cik)
                if sicd:
                    rec["sic"] = sic
                    rec["industry"] = sicd
                if title:
                    rec["name"] = title
            # 2) Yahoo: the actual business description.  Same variants.
            if a.yahoo:
                y = {}
                for v in lookup_variants(t):
                    y = yf_profile(v)
                    if y.get("name") or y.get("summary"):
                        break
                if y.get("name"):
                    rec["name"] = y["name"]          # more natural than the legal title
                if y.get("summary"):
                    rec["description"] = first_sentences(y["summary"])
                if y.get("sector"):
                    rec["sector"] = y["sector"]
                if y.get("industry"):
                    rec["industry"] = y["industry"]
                if y.get("summary") or y.get("name"):
                    rec["source"] = "sec+yahoo" if rec.get("sic") else "yahoo"
            # 3) no summary → say what the industry is, not nothing
            if not rec["description"] and rec.get("industry"):
                rec["description"] = f"Operates in {rec['industry'].lower()}."
                rec["description_from"] = "sic"
            fails = 0
        except Exception as e:
            fails += 1
            print(f"  ! {t}: {type(e).__name__} {e}", file=sys.stderr)
            if fails >= 12:
                print(f"[companies] {fails} consecutive failures — backing off 60s",
                      file=sys.stderr)
                time.sleep(60)
                if fails >= 30:
                    print("[companies] giving up; re-run to resume", file=sys.stderr)
                    json.dump(out, open(a.out, "w"))
                    return 0
                fails = 0
        if rec.get("name") or rec.get("description"):
            out[t] = rec
        time.sleep(a.sleep)
        if n % 25 == 0 or n == len(todo):
            el = time.time() - t0
            rate = el / n
            print(f"  {n}/{len(todo)}  {t:6s}  done={len(out)}  {rate:.2f}s/tkr  "
                  f"eta {rate*(len(todo)-n)/60:.1f}m", file=sys.stderr)
            os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
            json.dump(out, open(a.out, "w"), indent=0)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=0)
    named = sum(1 for v in out.values() if v.get("name"))
    desc = sum(1 for v in out.values() if v.get("description"))
    print(f"[companies] wrote {a.out} — {len(out)} tickers, {named} named, {desc} described",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
