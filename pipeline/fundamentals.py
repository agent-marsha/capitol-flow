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
    # for EBITDA (operating income + D&A) and free cash flow (op cash - capex)
    "dna": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
            "DepreciationAmortizationAndAccretionNet", "Depreciation"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment",
              "PaymentsToAcquireProductiveAssets",
              "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets"],
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


def latest_shares(facts: dict):
    """Most recent shares outstanding (dei taxonomy preferred, then us-gaap)."""
    alloc = facts.get("facts", {})
    best = None
    for taxo in ("dei", "us-gaap", "ifrs-full"):
        t = alloc.get(taxo, {})
        node = (t.get("EntityCommonStockSharesOutstanding")
                or t.get("CommonStockSharesOutstanding")
                or t.get("NumberOfSharesOutstanding")
                or t.get("WeightedAverageNumberOfDilutedSharesOutstanding"))
        if not node:
            continue
        for rows in node.get("units", {}).values():
            for r in rows:
                end, val = r.get("end", ""), r.get("val")
                if val and (best is None or end > best[0]):
                    best = (end, float(val))
        if best and best[1] > 0:
            return best[1]
    return None


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


_GENERIC = {"international", "american", "general", "national", "united", "advanced",
            "global", "new", "first", "the", "walt"}


_SUFFIX_RE = re.compile(
    r"[,.]?\s*(Inc|Incorporated|Corp|Corporation|Companies|Company|Co|plc|PLC|Ltd|Limited"
    r"|L\.?L\.?C|N\.?V|S\.?A|P\.?L\.?C)\.?(/\s*[A-Za-z]{2})?\s*$", re.I)


def clean_name(raw: str, ticker: str) -> str:
    """Normalise an SEC entity name for display.

    SEC names are inconsistent: some are ALL CAPS, some carry a stray legal suffix
    ("Wells Fargo & Company/Mn"), some have run-on whitespace. Title-casing blindly
    breaks acronyms ("AT&T" -> "At&T"), so only multi-word all-caps names are
    title-cased, and tokens that are acronym-shaped are left alone.
    """
    n = re.sub(r"\s+", " ", (raw or "").strip())
    # SEC names can stack suffixes ("... COMPANIES INC.") — strip repeatedly.
    for _ in range(3):
        stripped = _SUFFIX_RE.sub("", n).strip(" ,.-/")
        if stripped == n:
            break
        n = stripped
    n = re.sub(r"[\s&]+$", "", n).strip()
    letters = [c for c in n if c.isalpha()]
    if " " in n and letters and sum(c.isupper() for c in letters) / len(letters) >= 0.8:
        n = " ".join(w if ("&" in w or not re.search(r"[AEIOUaeiou]", w)) else w.capitalize()
                     for w in n.split())
    n = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), n)   # Mclennan -> McLennan
    n = re.sub(r"\bO'([a-z])", lambda m: "O'" + m.group(1).upper(), n)   # O'brien -> O'Brien
    return n.strip() or ticker


def short_name(name: str, ticker: str) -> str:
    """A short, kid-friendly name — long names inflate the reading level and read badly."""
    n = re.sub(r"\s*[/.]?\s*(com|corp|co|de)\s*$", "", name, flags=re.I).strip(" ,./")
    n = re.sub(r"\s+", " ", n)
    if len(n) <= 14 and len(n.split()) <= 2:
        return n
    first = n.split()[0]
    if len(first) >= 4 and first.lower() not in _GENERIC:
        return first
    return ticker


def build_cards(name: str, s: dict, val: dict | None = None) -> list[dict]:
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

    # 6) EV/EBITDA — the price of the whole business per $1 of OPERATING earnings.
    # Careful with wording:
    #   * "makes" would imply profit. EBITDA is NOT profit — it ignores the bank
    #     (interest), the tax office, AND the wear on machines (depreciation and
    #     amortisation). Apple's EBITDA is 171.5B vs 132.2B real profit.
    #   * It must name all four exclusions, not just two.
    #   * EV is the company PLUS its bills, not what the shares cost.
    if val and val.get("ev_ebitda"):
        m = val["ev_ebitda"]
        cards.append({
            "id": "ev_ebitda", "emoji": "🏷️", "rank": 2,
            "headline": "What it costs to buy the whole company",
            "text": (f"To buy all of {name} — the company and its bills together — would cost about {money(val['ev'])}. "
                     f"Each year it brings in about {money(val['ebitda'])} before it pays the bank, the tax office, "
                     f"and the wear on its machines. So the price is about ${m:,.0f} for every $1 it brings in. "
                     "That $1 is not profit. After all of that gets paid, less is left."),
            "chart": {"type": "stat", "label": "The price, for each $1 it brings in",
                      "value": f"${m:,.1f}", "sub": "before bank, tax and machine wear"},
        })

    # 7) FCF yield — the cash the BUSINESS MAKES per $100 of value.
    # NOT cash paid to the owner: the company decides whether to keep it, spend it
    # or hand some out. Wording must never imply a payout.
    if val and val.get("fcf_yield") is not None:
        y = val["fcf_yield"]
        mcap = val.get("market_cap")
        if (val.get("fcf") or 0) >= 0:
            text = (f"{name} had {money(val['fcf'])} left in cash after paying for everything. "
                    f"That even counts new machines and buildings. ")
            if mcap:
                text += (f"The whole company costs about {money(mcap)} to buy. So for every $100 "
                         f"it is worth, it makes about ${y:.0f} of cash in a year. ")
            else:
                text += f"So for every $100 it is worth, it makes about ${y:.0f} of cash in a year. "
            text += ("It may keep that cash. It may spend it. It may hand some to its owners. "
                     "You only get cash in your hand if the company hands it out.")
        else:
            text = (f"{name} spent more cash than it brought in, by {money(abs(val['fcf']))}. "
                    "So it has no spare cash to hand out to its owners right now.")
        cards.append({
            "id": "fcf_yield", "emoji": "💵", "rank": 1,
            "headline": "The real cash the company makes",
            "text": text,
            "chart": {"type": "stat", "label": "Cash it makes each year, per $100 it is worth",
                      "value": f"${y:,.1f}", "sub": "per $100 of company value, each year"},
        })

    return cards


def compute_valuation(s: dict, facts: dict, price: float | None) -> dict:
    """EV/EBITDA and free-cash-flow yield, using the live price for market cap.

    EV = market cap + total debt - cash  (the price of the whole business)
    EBITDA = operating income + D&A
    FCF = operating cash flow - capital expenditure
    """
    op = latest(s.get("operating_income", []))
    dna = latest(s.get("dna", []))
    cash = latest(s.get("cash", [])) or 0
    debt = latest(s.get("debt", [])) or 0
    op_cash = latest(s.get("op_cash", []))
    capex = latest(s.get("capex", []))
    shares = latest_shares(facts)
    out: dict = {}
    if not price or not shares:
        return out
    mc = price * shares
    out.update(price=price, shares=shares, market_cap=mc, ev=mc + debt - cash)
    if op is not None and dna is not None:
        ebitda = op + dna
        if ebitda > 0 and out["ev"] > 0:
            mult = out["ev"] / ebitda
            out["ebitda"] = ebitda
            # a multiple above ~100x means it barely earns anything; the ratio is
            # meaningless and would read as a broken number — omit the card.
            if mult <= 100:
                out["ev_ebitda"] = mult
    if op_cash is not None and capex is not None and mc > 0:
        fcf = op_cash - abs(capex)
        out["fcf"] = fcf
        out["fcf_yield"] = fcf / mc * 100.0
    return out


# ------------------------------------------------------------ sector peer stats
def _pctl(vals: list[float], q: float) -> float:
    """Linear-interpolated percentile (q in 0..1) of an ASCENDING list."""
    if not vals:
        return 0.0
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def attach_peers(out: dict, sectors: dict) -> None:
    """Per-sector valuation distributions, so a card can show how a company compares.

    Stored under the reserved `_sectors` key — tickers are always uppercase symbols, so
    there is no collision.  Only companies that actually HAVE a given multiple are
    counted, so n can differ between ev_ebitda and fcf_yield.

    `*_pctile` is the share of sector peers sitting BELOW this company's value.  Note the
    direction differs by metric: a LOW ev_ebitda is cheap, a HIGH fcf_yield is cheap, so
    the renderer has to flip the wording, not the number.
    """
    by_sec: dict[str, dict[str, list[tuple[str, float]]]] = {}
    for t, rec in out.items():
        sec = sectors.get(t)
        if not sec:
            continue
        val = rec.get("valuation") or {}
        for m in ("ev_ebitda", "fcf_yield"):
            v = val.get(m)
            if isinstance(v, (int, float)):
                by_sec.setdefault(sec, {}).setdefault(m, []).append((t, float(v)))

    stats: dict[str, dict] = {}
    for sec, metrics in by_sec.items():
        stats[sec] = {"n": sum(1 for t in out if sectors.get(t) == sec)}
        for m, pairs in metrics.items():
            vals = sorted(v for _, v in pairs)
            stats[sec][m] = {
                "n": len(vals),
                "min": round(vals[0], 2), "p25": round(_pctl(vals, 0.25), 2),
                "median": round(_pctl(vals, 0.5), 2), "p75": round(_pctl(vals, 0.75), 2),
                "max": round(vals[-1], 2),
                "mean": round(sum(vals) / len(vals), 2),
            }

    for t, rec in out.items():
        sec = sectors.get(t)
        if not sec:
            continue
        val = rec.get("valuation") or {}
        peer: dict = {"sector": sec, "sector_n": stats[sec]["n"]}
        for m in ("ev_ebitda", "fcf_yield"):
            v = val.get(m)
            pairs = (by_sec.get(sec) or {}).get(m) or []
            st = (stats.get(sec) or {}).get(m)
            # need a real peer group for a percentile to mean anything
            if isinstance(v, (int, float)) and st and st["n"] >= 4:
                vals = [x for _, x in pairs]
                below = sum(1 for x in vals if x < v) / len(vals)
                peer[m + "_pctile"] = round(below, 3)
                peer[m + "_n"] = st["n"]
                # "cheaper" points a DIFFERENT way for the two metrics — a low
                # EV/EBITDA is cheap, a HIGH FCF yield is cheap.  Normalise here so the
                # renderer never has to know: higher *_cheap always means cheaper.
                peer[m + "_cheap"] = round(1.0 - below if m == "ev_ebitda" else below, 3)
                # The sector figure we lead with: the average of the OTHER companies, so a
                # company never drags the benchmark toward itself.
                others = [x for ot, x in pairs if ot != t]
                if others:
                    peer[m + "_peer_mean"] = round(sum(others) / len(others), 2)
                    peer[m + "_peer_n"] = len(others)
                    if others and abs(sum(others) / len(others)) > 1e-9:
                        pm = sum(others) / len(others)
                        peer[m + "_vs_mean"] = round((v - pm) / abs(pm), 3)
        rec["peer"] = peer

    out["_sectors"] = stats


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
    # last daily close per ticker -> market cap for the valuation cards
    prices: dict[str, float] = {}
    for tk, pv in (data.get("prices") or {}).items():
        daily = pv.get("daily") or []
        if daily:
            prices[tk] = daily[-1]["c"]
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
        name = clean_name(f.get("entityName") or t, t)
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
        val = compute_valuation(s, f, prices.get(t))
        short = short_name(name, t)
        cards = build_cards(short, s, val)
        text_all = " ".join(c["text"] for c in cards)
        out[t] = {
            "name": name, "short_name": short, "cik": cik,
            "years": [str(y) for y, _ in s.get("revenue", [])],
            "series": {k: [{"x": str(y), "y": v} for y, v in vv] for k, vv in s.items()},
            "facts": facts, "valuation": val, "cards": cards,
            "reading_grade": round(reading_grade(text_all), 1) if text_all else None,
        }
        done += 1
        print(f"  [{done}/{len(tickers)}] {t:6s} {name[:28]:28s} cards={len(cards)} grade={out[t]['reading_grade']}",
              file=sys.stderr)
        time.sleep(0.15)

    # sector peer stats — needs data/profiles.json for each ticker's sector
    try:
        _prof = json.load(open("data/profiles.json"))
        _sec = {t: (p or {}).get("sector") for t, p in _prof.items()}
    except Exception:
        _sec = {}
    attach_peers(out, _sec)
    _n = sum(1 for k in out if not k.startswith("_"))
    _ranked = sum(1 for k, v in out.items()
                  if not k.startswith("_")
                  and (v.get("peer") or {}).get("ev_ebitda_pctile") is not None)
    print(f"[fundamentals] peers — {len([s for s in _sec.values() if s])} tickers with a "
          f"sector, {_ranked} companies ranked against it", file=sys.stderr)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"))
    print(f"[fundamentals] wrote {a.out} — {_n} companies, missing CIK: {missing}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
