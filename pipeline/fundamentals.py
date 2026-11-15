#!/usr/bin/env python3
"""Pull company fundamentals from SEC EDGAR (official XBRL) and write them in
plain, 4th-grade language for the Capitol Flow stock pages.

Source (free, no key, official):
  * ticker -> CIK:  https://www.sec.gov/files/company_tickers.json
  * all reported facts for a company:
        https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json

We take ANNUAL (10-K / FY) figures, keep the last few fiscal years, and write
short, simple sentences a 4th grader can read. Simple bar-chart-ready series
are emitted alongside the words.

Output: data/fundamentals.json
   { "AAPL": { "name": "...", "years": [...],
               "series": {"revenue":[...], "net_income":[...], ...},
               "facts":  { "revenue": 478834000000, ... },
               "cards":  [ {"headline":"...", "text":"...", "chart":"bars", "data":[...]} ],
               "reading_grade": 4.2 } }

Usage: python fundamentals.py [--in data/app_data.json] [--out data/fundamentals.json] [--max 60]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request

UA = "CapitolFlow research (contact: victor26@fastmail.com)"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# concept candidates, in preference order
CONCEPTS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                "Revenue", "RevenueFromContractsWithCustomers"],
    "net_income": ["NetIncomeLoss", "ProfitLoss", "ProfitLossAttributableToOwnersOfParent"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss", "ProfitLossFromOperatingActivities"],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
               "Equity", "EquityAttributableToOwnersOfParent"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
             "CashAndCashEquivalents"],
    "debt": ["LongTermDebtNoncurrent", "LongTermDebt", "DebtLongtermAndShorttermCombinedAmount",
             "Borrowings", "LongtermBorrowings"],
    "op_cash": ["NetCashProvidedByUsedInOperatingActivities",
                "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
                "CashFlowsFromUsedInOperatingActivities"],
}


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def cik_map() -> dict[str, str]:
    d = get_json(TICKERS_URL)
    return {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in d.values()}


def annual_series(facts: dict, concepts: list[str]) -> list[tuple[int, float]]:
    """Last few fiscal years of an annual figure: [(fy, value), ...] ascending.

    Keeps only 10-K annual frames, dedupes per fiscal year (latest filing wins).
    """
    alloc = facts.get("facts", {})
    taxonomies = [alloc.get("us-gaap", {}), alloc.get("ifrs-full", {})]
    # Filers switch tags over time (e.g. Revenues -> RevenueFromContract...), so take
    # the candidate with the most recent fiscal year; preference order breaks ties.
    best: list[tuple[int, float]] = []
    for taxo in taxonomies:
      for c in concepts:
        node = taxo.get(c)
        if not node:
            continue
        unit = "USD" if "USD" in node["units"] else next(iter(node["units"]))
        rows = node["units"][unit]
        by_fy: dict[int, tuple[str, float]] = {}
        for r in rows:
            # foreign private issuers file an annual report on 20-F/40-F, not 10-K
            if r.get("form") not in ("10-K", "20-F", "40-F") or r.get("fp") != "FY":
                continue
            fy = r.get("fy")
            end = r.get("end", "")
            if not fy or not end:
                continue
            # quarterly frames inside a 10-K are common; keep ~annual spans only
            prev = by_fy.get(fy)
            if prev is None or end > prev[0]:
                by_fy[fy] = (end, float(r["val"]))
        # >=1 year: newly spun-off / IPO'd entities have a single annual frame
        if len(by_fy) >= 1:
            ser = sorted((fy, v) for fy, (_, v) in by_fy.items())
            if not best or ser[-1][0] > best[-1][0]:
                best = ser
    return best


def latest(series: list[tuple[int, float]]):
    return series[-1][1] if series else None


def prev(series: list[tuple[int, float]]):
    return series[-2][1] if len(series) >= 2 else None


# ------------------------------------------------------------------ wording
def money(v) -> str:
    """Plain-English money, e.g. 478834000000 -> '478.8 billion'."""
    if v is None:
        return "an amount we could not find"
    a = abs(v)
    if a >= 1e12:
        return f"{a/1e12:.1f} trillion"
    if a >= 1e9:
        return f"{a/1e9:.1f} billion"
    if a >= 1e6:
        return f"{a/1e6:.1f} million"
    return f"{a:,.0f}"


def pct(a, b):
    if not a or not b:
        return None
    return (a - b) / abs(b) * 100.0


def reading_grade(text: str) -> float:
    """Flesch-Kincaid grade level — our check that the words stay simple."""
    sents = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    words = re.findall(r"[A-Za-z']+", text)
    if not sents or not words:
        return 0.0

    def syl(w: str) -> int:
        w = w.lower()
        w = re.sub(r"[^a-z]", "", w)
        if not w:
            return 0
        groups = re.findall(r"[aeiouy]+", w)
        n = len(groups)
        if w.endswith("e") and n > 1:
            n -= 1
        return max(1, n)

    S = len(words) / len(sents)
    W = sum(syl(w) for w in words) / len(words)
    return 0.39 * S + 11.8 * W - 15.59


def build_cards(name: str, s: dict) -> list[dict]:
    """Short, simple cards: headline + plain text + chart-ready data."""
    cards = []
    rev, pv = latest(s.get("revenue", [])), prev(s.get("revenue", []))
    ni = latest(s.get("net_income", []))
    gp = latest(s.get("gross_profit", []))
    ast, lia = latest(s.get("assets", [])), latest(s.get("liabilities", []))
    eq = latest(s.get("equity", []))
    cash, debt = latest(s.get("cash", [])), latest(s.get("debt", []))
    yrs = [str(y) for y, _ in s.get("revenue", [])] or []

    # 1) how much it sold
    if rev:
        grew = pct(rev, pv)
        updown = ""
        if grew is not None:
            if grew >= 1:
                updown = f" That is up {grew:.0f}% from the year before."
            elif grew <= -1:
                updown = f" That is down {abs(grew):.0f}% from the year before."
            else:
                updown = " That is about the same as the year before."
        cards.append({
            "id": "revenue", "emoji": "🧾",
            "headline": "How much money it made",
            "text": f"{name} sold {money(rev)} worth of things last year.{updown}",
            "chart": {"type": "bars", "label": "Money it made each year",
                      "unit": "money", "points": [{"x": str(y), "y": v} for y, v in s["revenue"]]},
        })

    # 2) what it kept
    if ni is not None and rev:
        margin = ni / rev * 100 if rev else None
        if ni > 0:
            text = (f"After it paid for everything, {name} got to keep {money(ni)}. "
                    f"That means out of every $100 it took in, it kept about ${margin:.0f}.")
        else:
            text = (f"After it paid for everything, {name} lost {money(abs(ni))}. "
                    "It spent more than it took in.")
        cards.append({
            "id": "profit", "emoji": "💰",
            "headline": "What was left over",
            "text": text,
            "chart": {"type": "bars", "label": "Money kept each year",
                      "unit": "money", "points": [{"x": str(y), "y": v} for y, v in s["net_income"]]},
        })

    # 3) out of every $100 (margin) — simple two-slice picture
    if gp and rev:
        keep = gp / rev * 100
        cards.append({
            "id": "margin", "emoji": "🍰",
            "headline": "Out of every $100",
            "text": (f"When {name} sells something for $100, about ${keep:.0f} is left after "
                     "paying what it cost to make it. The rest goes to running the company."),
            "chart": {"type": "split", "label": "Out of every $100 it takes in",
                      "points": [{"x": "Kept", "y": round(keep, 1)},
                                 {"x": "Cost to make", "y": round(100 - keep, 1)}]},
        })

    # 4) owns vs owes
    if ast and lia:
        left = ast - lia
        cards.append({
            "id": "owes", "emoji": "⚖️",
            "headline": "What it owns and what it owes",
            "text": (f"{name} owns {money(ast)} worth of stuff. It owes {money(lia)} to other people. "
                     + (f"So what is really left is {money(left)}." if left >= 0 else
                        f"It owes more than it owns, by {money(left)}.")),
            "chart": {"type": "bars2", "label": "Owns vs owes",
                      "points": [{"x": "Owns", "y": ast}, {"x": "Owes", "y": lia},
                                 {"x": "Really left", "y": left}]},
        })

    # 5) cash vs debt
    if cash is not None or debt is not None:
        c, d = cash or 0, debt or 0
        if d <= 0:
            text = f"{name} has {money(c)} in the bank and almost no big bills to pay back."
        elif c >= d:
            text = (f"{name} has {money(c)} in the bank. It owes {money(d)}. "
                    "It has more in the bank than it owes.")
        else:
            text = (f"{name} has {money(c)} in the bank. It owes {money(d)}. "
                    "It owes more than it has in the bank.")
        cards.append({
            "id": "cash", "emoji": "🏦",
            "headline": "Money in the bank",
            "text": text,
            "chart": {"type": "bars2", "label": "In the bank vs owed",
                      "points": [{"x": "In the bank", "y": c}, {"x": "Owes", "y": d}]},
        })

    return cards


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/app_data.json")
    ap.add_argument("--out", default="data/fundamentals.json")
    ap.add_argument("--max", type=int, default=60)
    a = ap.parse_args()

    data = json.load(open(a.inp))
    # use the SAME tickers the app charted (signal-strength selected), not the
    # first N alphabetical — otherwise the sets don't match the stock pages.
    tickers = sorted(data.get("prices", {}).keys())
    if not tickers:
        tickers = sorted({t["ticker"] for t in data["trades"] if t.get("ticker")})
    tickers = tickers[: a.max]
    cmap = cik_map()
    print(f"[fundamentals] {len(tickers)} tickers", file=sys.stderr)

    out, done, missing = {}, 0, []
    for t in tickers:
        cik = cmap.get(t.upper())
        if not cik:
            missing.append(t)
            continue
        try:
            f = get_json(FACTS.format(cik=cik))
        except Exception as e:
            print(f"  ! {t}: {type(e).__name__} {e}", file=sys.stderr)
            missing.append(t)
            time.sleep(0.4)
            continue
        name = (f.get("entityName") or t).strip()
        if name.isupper():
            name = name.title()
        name = re.sub(r"[,.]?\s*(Inc|Incorporated|Corp|Corporation|Co|Company|plc|PLC|Ltd|Limited|LLC|N\.V|S\.A)\.?$",
                      "", name, flags=re.I).strip(" ,.") or t
        s = {k: annual_series(f, v) for k, v in CONCEPTS.items()}
        if not s["revenue"]:
            # some filers only tag revenue under a bank/insurance concept
            s["revenue"] = annual_series(f, ["Revenues", "InterestAndDividendIncomeOperating",
                                             "InterestIncomeOperating"])
        s = {k: v for k, v in s.items() if v}
        # drop stale series (a tag the filer stopped using years ago) so cards never
        # mix this year's numbers with a decade-old one
        newest = max((v[-1][0] for v in s.values()), default=0)
        s = {k: v for k, v in s.items() if v[-1][0] >= newest - 1}
        facts = {k: latest(v) for k, v in s.items()}
        cards = build_cards(name, s)
        text_all = " ".join(c["text"] for c in cards)
        out[t] = {
            "name": name, "cik": cik,
            "years": [str(y) for y, _ in s.get("revenue", [])],
            "series": {k: [{"x": str(y), "y": v} for y, v in vv] for k, vv in s.items()},
            "facts": facts, "cards": cards,
            "reading_grade": round(reading_grade(text_all), 1) if text_all else None,
        }
        done += 1
        print(f"  [{done}/{len(tickers)}] {t:6s} {name[:28]:28s} cards={len(cards)} grade={out[t]['reading_grade']}",
              file=sys.stderr)
        time.sleep(0.15)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"))
    print(f"[fundamentals] wrote {a.out} — {len(out)} companies, missing CIK: {missing}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
