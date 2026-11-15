#!/usr/bin/env python3
"""Per-ticker company profile: which sector it is in, and what it sells.

Source: SEC EDGAR.  `data.sec.gov/submissions/CIK##########.json` carries the company's
own SIC code and its SIC description — i.e. the classification the company registered
with the regulator.  Free, authoritative, fast (~1s/ticker), and not rate-limited the
way Yahoo's `.info` endpoint is (which is what previously blanked out every sector).

We map the SIC code onto the same coarse sector buckets the committee-jurisdiction
map uses, so this output also drives the committee-oversight flag.

Output: data/profiles.json
  { "AAPL": { "name": "Apple Inc.", "sector": "Technology",
              "sic": "3571", "industry": "Electronic Computers" } }

Usage: python profiles.py [--in data/app_data.json] [--out data/profiles.json] [--max 60]
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
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
CACHE = "/tmp/capitol-cik-map.json"


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read()
    if r.headers.get("Content-Encoding") == "gzip":
        import gzip
        raw = gzip.decompress(raw)
    return json.loads(raw)


def cik_map() -> dict:
    if os.path.exists(CACHE) and os.path.getsize(CACHE) > 10000:
        return json.load(open(CACHE))
    data = get_json(TICKERS_URL)
    m = {v["ticker"].upper(): int(v["cik_str"]) for v in data.values()}
    json.dump(m, open(CACHE, "w"))
    return m


# ---- SIC -> coarse sector -------------------------------------------------------
# Ordered rules, most specific first.  SIC major groups are 2 digits; we override a
# handful of 4-digit codes whose major group would land them in the wrong bucket.
_SIC_RULES = [
    # (lo, hi, sector)
    (2833, 2836, "Healthcare"),          # pharmaceutical preparations
    (2840, 2844, "Consumer Defensive"),  # soap, cleaners, toiletries (P&G, Colgate)
    (3841, 3851, "Healthcare"),          # medical devices & supplies
    (3826, 3827, "Healthcare"),          # lab / analytical instruments (Revvity)
    (6324, 6324, "Healthcare"),          # hospital & medical service plans (UNH, CI, ELV)
    (8000, 8099, "Healthcare"),          # health services
    (7370, 7379, "Technology"),          # computer programming & data processing
    (3570, 3579, "Technology"),          # computer & office equipment
    (3670, 3679, "Technology"),          # electronic components, semiconductors
    (3660, 3669, "Technology"),          # communications equipment
    (3812, 3812, "Industrials"),         # search & navigation (defence-leaning)
    (3820, 3825, "Technology"),          # measuring & controlling devices
    (3829, 3829, "Industrials"),         # measuring/controlling NEC (Rockwell)
    (6500, 6599, "Real Estate"),
    (6000, 6499, "Financial Services"),
    (6700, 6799, "Financial Services"),  # holding & investment offices
    (4800, 4899, "Communication Services"),
    (7810, 7841, "Communication Services"),  # motion pictures / video
    (4900, 4999, "Utilities"),
    (1300, 1389, "Energy"),              # oil & gas extraction
    (2900, 2999, "Energy"),              # petroleum refining
    (1000, 1299, "Basic Materials"),     # metal mining
    (1400, 1499, "Basic Materials"),     # nonmetallic mining
    (2000, 2099, "Consumer Defensive"),  # food & beverages
    (2100, 2199, "Consumer Defensive"),  # tobacco
    (2200, 2399, "Consumer Cyclical"),   # textiles & apparel
    (2400, 2599, "Consumer Cyclical"),   # lumber, furniture
    (2600, 2699, "Basic Materials"),     # paper
    (2700, 2799, "Communication Services"),  # printing & publishing
    (2800, 2899, "Basic Materials"),     # chemicals
    (3000, 3399, "Basic Materials"),     # rubber, plastics, metals
    (3400, 3499, "Industrials"),         # fabricated metal
    (3500, 3569, "Industrials"),         # industrial machinery
    (3580, 3599, "Industrials"),
    (3600, 3669, "Technology"),
    (3680, 3699, "Technology"),
    (3700, 3799, "Industrials"),         # transport equipment
    (3800, 3899, "Technology"),          # instruments
    (3900, 3999, "Consumer Cyclical"),   # misc manufacturing
    (4000, 4799, "Industrials"),         # transportation
    (5000, 5199, "Industrials"),         # wholesale — durables
    (5200, 5999, "Consumer Cyclical"),   # retail
    (7000, 7099, "Consumer Cyclical"),   # hotels
    (7200, 7299, "Consumer Cyclical"),   # personal services
    (7300, 7369, "Industrials"),         # business services
    (7380, 7399, "Industrials"),
    (7400, 7999, "Consumer Cyclical"),
    (8100, 8999, "Industrials"),         # professional / engineering services
    (9100, 9999, "Industrials"),         # public administration
]

# SIC is sometimes actively unhelpful for a specific company. Visa files as
# "Services-Business Services, NEC" (7389), which lands it in Industrials — and that
# would silently drive the WRONG committee-oversight flag. These are explicit,
# documented exceptions rather than a guess:
TICKER_OVERRIDES = {
    "V": "Financial Services", "MA": "Financial Services", "PYPL": "Financial Services",
    "AXP": "Financial Services", "FI": "Financial Services",
    "UNH": "Healthcare", "CI": "Healthcare", "ELV": "Healthcare", "CVS": "Healthcare",
    "HUM": "Healthcare", "CNC": "Healthcare",
    "PG": "Consumer Defensive", "CL": "Consumer Defensive", "KMB": "Consumer Defensive",
    "EL": "Consumer Defensive", "KO": "Consumer Defensive", "PEP": "Consumer Defensive",
    "WMT": "Consumer Defensive", "COST": "Consumer Defensive", "TGT": "Consumer Defensive",
    "ROK": "Industrials", "HON": "Industrials", "GE": "Industrials", "EMR": "Industrials",
    "OKE": "Energy", "WMB": "Energy", "KMI": "Energy", "ET": "Energy",
    "META": "Communication Services", "GOOG": "Communication Services",
    "GOOGL": "Communication Services", "NFLX": "Communication Services",
}


def sic_to_sector(sic: str | None) -> str | None:
    if not sic:
        return None
    m = re.match(r"(\d{3,4})", str(sic))
    if not m:
        return None
    c = int(m.group(1))
    if c < 1000:
        c *= 10  # 3-digit SIC -> pad
    for lo, hi, sector in _SIC_RULES:
        if lo <= c <= hi:
            return sector
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/app_data.json")
    ap.add_argument("--out", default="data/profiles.json")
    ap.add_argument("--max", type=int, default=60)
    a = ap.parse_args()

    try:
        data = json.load(open(a.inp))
        tickers = sorted((data.get("prices") or {}).keys())[: a.max]
    except Exception:
        tickers = []
    # Also profile the high-open-interest option universe, so the dashboard board can
    # show a sector for rows Congress never traded.
    try:
        opts = json.load(open("data/options.json"))
        for t in sorted(opts.keys()):
            if t not in tickers:
                tickers.append(t)
    except Exception:
        pass

    cmap = cik_map()
    out, missing = {}, []
    for i, t in enumerate(tickers, 1):
        cik = cmap.get(t.upper())
        if not cik:
            missing.append(t)
            continue
        try:
            sub = get_json(SUBMISSIONS.format(cik=cik))
            sic = sub.get("sic")
            out[t] = {
                "name": sub.get("name") or t,
                "sector": TICKER_OVERRIDES.get(t.upper()) or sic_to_sector(sic),
                "sic": sic,
                "industry": sub.get("sicDescription"),
            }
        except Exception as e:
            print(f"  ! {t}: {type(e).__name__} {e}", file=sys.stderr)
            missing.append(t)
        time.sleep(0.15)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=0)
    nosector = [t for t, v in out.items() if not v.get("sector")]
    print(f"[profiles] {len(out)} profiles ({len(out)-len(nosector)} with a sector); "
          f"no CIK: {missing}; sector unmapped: {nosector}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
