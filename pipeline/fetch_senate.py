#!/usr/bin/env python3
"""Fetch US SENATE stock trades and normalize them to the House schema.

Why not the Senate's own site?  efdsearch.senate.gov sits behind Akamai and
returns HTTP 403 to every automated request (and to headless browsers) from a
datacenter/VPN IP.  The official PDFs are the source of record, but they are
not reachable programmatically from here.

So we use a **public community mirror** that republishes the parsed EFD data
and keeps every report's official source URL:

    https://raw.githubusercontent.com/matr-co/senate-ptr/main/senate_ptrs.json

Shape:  { "updated": ISO, "reports": [
            { "id", "name", "first", "last", "filed", "url", "title",
              "trades": [ { "date","owner","ticker","asset","asset_type",
                            "type","lo","hi" } ] } ] }

Every transaction we emit keeps `source_url` pointing at the official
efdsearch.senate.gov filing, so the app can always link to the primary source.

Output: data/senate_trades.json  (same schema as fetch_house.py)

Usage: python fetch_senate.py [--days 150] [--out data/senate_trades.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta

MIRROR = "https://raw.githubusercontent.com/matr-co/senate-ptr/main/senate_ptrs.json"
UA = "CapitolFlow research (contact: victor26@fastmail.com)"

# mirror strings -> our two-letter codes
TYPE_MAP = {
    "Purchase": "P", "Sale (Full)": "S", "Sale (Partial)": "S",
    "Exchange": "E", "Sale": "S",
}


def amount_label(lo, hi) -> str:
    try:
        lo = int(lo)
        hi = int(hi) if hi is not None else None
    except Exception:
        return ""
    if hi is None:
        return f"Over ${lo:,}"
    if hi >= 50_000_000:
        return f"Over ${lo:,}"
    return f"${lo:,} - ${hi:,}"


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=150)
    ap.add_argument("--out", default="data/senate_trades.json")
    a = ap.parse_args()

    try:
        blob = fetch(MIRROR)
    except Exception as e:
        print(f"[fetch_senate] mirror unavailable: {type(e).__name__} {e}", file=sys.stderr)
        return 1

    reports = blob.get("reports", [])
    cutoff = (date.today() - timedelta(days=a.days)).isoformat()
    txns: list[dict] = []
    for rep in reports:
        filed = rep.get("filed") or ""
        if filed and filed < cutoff:
            continue
        pol = f"Sen. {rep.get('name','').strip()}".strip()
        for t in rep.get("trades", []):
            d = t.get("date")
            if not d or d < cutoff:
                continue
            raw_type = (t.get("type") or "").strip()
            code = TYPE_MAP.get(raw_type, "")
            ticker = (t.get("ticker") or "").strip()
            asset = (t.get("asset") or "").strip()
            if ticker and f"({ticker})" not in asset:
                asset = f"{asset} ({ticker})"
            txns.append({
                "owner": t.get("owner") or "Self",
                "asset_raw": asset,
                "txn_type": code,
                "txn_type_label": raw_type or "Unknown",
                "txn_date": d,
                "notification_date": None,
                "amount_low": int(t["lo"]) if t.get("lo") is not None else None,
                "amount_high": int(t["hi"]) if t.get("hi") is not None else None,
                "amount_label": amount_label(t.get("lo"), t.get("hi")),
                "politician": pol,
                "chamber": "Senate",
                "state_district": None,
                "filed_date": filed or None,
                "doc_id": rep.get("id"),
                "ticker": ticker or None,
                "source_url": rep.get("url"),
                "asset_type": t.get("asset_type"),
            })

    txns.sort(key=lambda r: (r.get("txn_date") or ""), reverse=True)
    result = {
        "generated": datetime.utcnow().isoformat() + "Z",
        "source": "US Senate — Periodic Transaction Reports (via matr-co/senate-ptr mirror of efdsearch.senate.gov)",
        "mirror_updated": blob.get("updated"),
        "count": len(txns),
        "transactions": txns,
    }
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(result, open(a.out, "w"), indent=1)
    senators = len({t["politician"] for t in txns})
    print(f"[fetch_senate] {len(txns)} transactions from {senators} senators "
          f"(mirror updated {blob.get('updated')}) -> {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
