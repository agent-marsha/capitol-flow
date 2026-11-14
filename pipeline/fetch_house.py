#!/usr/bin/env python3
"""Fetch + parse US House financial-disclosure PTRs (Periodic Transaction Reports).

Source (official, free, no API key):
  * Index:  https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{YEAR}FD.zip
            -> {YEAR}FD.txt  (tab-delimited: Prefix,Last,First,Suffix,FilingType,...,DocID)
            FilingType "P" == Periodic Transaction Report (the trades we want).
  * PTR PDF: https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{YEAR}/{DocID}.pdf

Outputs normalized transactions to stdout as JSON (or writes to data/house_trades.json).

Usage: python fetch_house.py [--days 90] [--limit 80] [--out PATH]
"""
import argparse
import io
import json
import os
import re
import sys
import time
import zipfile
from datetime import date, datetime, timedelta

import requests

from parse_ptr import parse_ptr_pdf

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
BASE = "https://disclosures-clerk.house.gov"
INDEX = BASE + "/public_disc/financial-pdfs/{year}FD.zip"
PTR = BASE + "/public_disc/ptr-pdfs/{year}/{doc}.pdf"

AMOUNTS = [
    (1, 1000, "$1 - $1,000"), (1001, 15000, "$1,001 - $15,000"),
    (15001, 50000, "$15,001 - $50,000"), (50001, 100000, "$50,001 - $100,000"),
    (100001, 250000, "$100,001 - $250,000"), (250001, 500000, "$250,001 - $500,000"),
    (500001, 1000000, "$500,001 - $1,000,000"), (1000001, 5000000, "$1,000,001 - $5,000,000"),
]
TXN_TYPES = {"P": "Purchase", "S": "Sale", "S (partial)": "Sale (Partial)",
             "E": "Exchange", "I": "Income"}


def clean(txt: str) -> str:
    """Strip PDF NUL padding and collapse whitespace, keeping line structure."""
    txt = txt.replace("\x00", "")
    txt = re.sub(r"[ \t]+", " ", txt)
    return txt


def amount_bucket(text: str):
    """Parse a disclosure amount string into (low, high, label)."""
    t = text.replace(",", "")
    m = re.search(r"\$?([0-9]{1,3}(?:[0-9]{3})*|\d+)\s*-\s*\$?([0-9,]+)", text.replace(",", ""))
    if m:
        lo, hi = int(m.group(1)), int(m.group(2).replace(",", ""))
        return lo, hi, f"${lo:,} - ${hi:,}"
    if re.search(r"over\s*\$?5,?000,?000", text, re.I):
        return 5000001, None, "Over $5,000,000"
    return None, None, text.strip()


def parse_ptr_text(txt: str) -> list[dict]:
    """Parse the transactions table out of a PTR PDF's extracted text.

    Rows look like:
      <Asset> <Type> <TxnDate> <NotifyDate> <Amount range>
    e.g. 'Apple Inc. (AAPL) [ST] S 06/12/2026 06/20/2026 $50,001 - $100,000'
    """
    txt = clean(txt)
    out = []
    # date pattern MM/DD/YYYY
    dpat = r"(\d{1,2}/\d{1,2}/\d{4})"
    # transaction line: ... <type letter> <date> <date> <amount>
    row = re.compile(
        r"(?P<asset>.+?)\s+(?P<type>P|S|E|S \(partial\))\s+"
        + dpat + r"\s+" + dpat + r"\s+"
        r"(?P<amt>\$[\d,]+\s*-\s*\$[\d,]+|Over \$5,000,000)",
        re.S,
    )
    for m in row.finditer(txt):
        lo, hi, label = amount_bucket(m.group("amt"))
        out.append({
            "asset_raw": re.sub(r"\s+", " ", m.group("asset")).strip()[-160:],
            "txn_type": m.group("type").strip()[:1],
            "txn_type_label": TXN_TYPES.get(m.group("type").strip(), m.group("type").strip()),
            "txn_date": _iso(m.group(3)),
            "notification_date": _iso(m.group(4)),
            "amount_low": lo,
            "amount_high": hi,
            "amount_label": label,
        })
    return out


def _iso(d: str) -> str | None:
    try:
        return datetime.strptime(d, "%m/%d/%Y").date().isoformat()
    except Exception:
        return None


TICKER_PAT = re.compile(r"\(([A-Z][A-Z0-9.]{0,5})\)")


def guess_ticker(asset: str) -> str | None:
    m = TICKER_PAT.search(asset)
    return m.group(1) if m else None


def fetch_index(year: int) -> list[dict]:
    r = requests.get(INDEX.format(year=year), headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    name = next(n for n in z.namelist() if n.endswith(".txt"))
    raw = z.read(name).decode("latin-1")
    rows = []
    for i, line in enumerate(raw.splitlines()):
        if i == 0 or not line.strip():
            continue
        p = line.split("\t")
        if len(p) < 9 or p[4] != "P":
            continue
        rows.append({
            "prefix": p[0], "last": p[1], "first": p[2], "suffix": p[3],
            "filing_type": p[4], "state_dst": p[5], "year": p[6],
            "filing_date": _iso(p[7]), "doc_id": p[8].strip(),
        })
    return rows


def fetch_ptr(year: int, doc: str) -> str:
    r = requests.get(PTR.format(year=year, doc=doc), headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    return r.content


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120, help="only filings within N days")
    ap.add_argument("--limit", type=int, default=80, help="max PTRs to fetch")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    year = date.today().year
    cutoff = date.today() - timedelta(days=a.days)
    idx = [r for r in fetch_index(year)
           if r["filing_date"] and datetime.fromisoformat(r["filing_date"]).date() >= cutoff]
    idx.sort(key=lambda r: r["filing_date"], reverse=True)
    idx = idx[: a.limit]
    print(f"[fetch_house] {len(idx)} PTRs within {a.days}d (year {year})", file=sys.stderr)

    try:
        import pdfplumber
    except ImportError:
        print("need pdfplumber: pip install pdfplumber", file=sys.stderr)
        return 2

    txns = []
    for i, f in enumerate(idx, 1):
        url = PTR.format(year=year, doc=f["doc_id"])
        try:
            pdf_bytes = fetch_ptr(year, f["doc_id"])
            recs = parse_ptr_pdf(pdf_bytes)
        except Exception as e:
            print(f"  ! {f['doc_id']} {f['last']}: {type(e).__name__} {e}", file=sys.stderr)
            continue
        pol = " ".join(x for x in [f["prefix"], f["first"], f["last"], f["suffix"]] if x).strip()
        for r in recs:
            r.update({
                "politician": pol, "chamber": "House", "state_district": f["state_dst"],
                "filed_date": f["filing_date"], "doc_id": f["doc_id"],
                "ticker": guess_ticker(r["asset_raw"]),
                "source_url": url,
            })
            txns.append(r)
        print(f"  [{i}/{len(idx)}] {pol:32s} {len(recs):3d} txns", file=sys.stderr)
        time.sleep(0.25)

    txns.sort(key=lambda r: (r.get("txn_date") or ""), reverse=True)
    result = {"generated": datetime.utcnow().isoformat() + "Z",
              "source": "US House Clerk — Periodic Transaction Reports (official)",
              "count": len(txns), "transactions": txns}
    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        json.dump(result, open(a.out, "w"), indent=1)
        print(f"[fetch_house] wrote {len(txns)} txns -> {a.out}", file=sys.stderr)
    else:
        print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
