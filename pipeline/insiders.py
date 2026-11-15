#!/usr/bin/env python3
"""Flag politicians who are (or were) an OFFICER or DIRECTOR of a company they traded.

Why this matters: committee oversight catches the politician who *regulates* a company.
It structurally cannot catch the politician who *ran* it.  Sen. Alan Armstrong spent
2011-2025 as CEO of Williams Companies and still files as a Williams director — so his
$5M-$25M Williams sale is the most informed possible seller of that stock.

Method (two stages — the second is essential)
---------------------------------------------
1. EDGAR full-text search for the politician's name across Forms 3/4/5.  Hits give every
   CIK involved, so we keep only hits whose ISSUER is a company we track.
2. **Verify against the actual Form 4 XML.**  Name search alone produces false positives
   (we found a "KEAN THOMAS H" director of UnitedHealth — the congressman's *father*).
   So we fetch the filing and require:
     * rptOwnerName contains the surname and the given name (or its initial)
     * isDirector = 1 or isOfficer = 1
     * generational suffix must agree: a politician named "... Jr" is NOT matched by a
       filing for "KEAN THOMAS H" with no suffix.  That single rule removes the
       father/son collision.

Output: data/insiders.json
  { "Sen. Alan Armstrong": { "WMB": { "company": "WILLIAMS COMPANIES INC",
                                      "role": "Director", "title": null,
                                      "last_filed": "2026-03-09", "forms": ["4"],
                                      "verified_filings": 6 } } }

Usage: python insiders.py [--in data/app_data.json] [--out data/insiders.json]
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

UA = "CapitolFlow research (contact: victor26@fastmail.com)"
FTS = "https://efts.sec.gov/LATEST/search-index?q={q}&forms=3,4,5"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
CACHE = "/tmp/capitol-cik-map.json"
NOISE = {"hon", "sen", "rep", "mr", "mrs", "ms", "dr"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def get_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read()
    if r.headers.get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    return raw


def get(url: str):
    return json.loads(get_bytes(url))


def cik_map() -> dict:
    if os.path.exists(CACHE) and os.path.getsize(CACHE) > 10000:
        return json.load(open(CACHE))
    data = get(TICKERS_URL)
    m = {v["ticker"].upper(): int(v["cik_str"]) for v in data.values()}
    json.dump(m, open(CACHE, "w"))
    return m


def parse_person(politician: str) -> tuple[str, str, str, str]:
    """-> (first, middle, last, suffix) with honorifics and noise stripped."""
    s = re.sub(r"[^a-zA-Z ]", " ", politician or "").lower()
    toks = [w for w in s.split() if w]
    suffix = ""
    if toks and toks[-1] in SUFFIXES:
        suffix = toks[-1]
        toks = toks[:-1]
    toks = [w for w in toks if w not in NOISE]
    if len(toks) < 2:
        return (toks[0] if toks else ""), "", (toks[-1] if toks else ""), ""
    return toks[0], " ".join(toks[1:-1]), toks[-1], suffix


def owner_matches(owner: str, first: str, middle: str, last: str, suffix: str) -> bool:
    """EDGAR writes owners as 'LAST FIRST M' — accept either name order."""
    o = re.sub(r"[^a-z ]", " ", (owner or "").lower())
    toks = [w for w in o.split() if w]
    tokset = set(toks)
    if last not in tokset:
        return False
    if first not in tokset and not any(w == first[:1] for w in toks):
        return False
    # If the politician has a middle name/initial, the filing's middle initial must
    # agree.  This is what separates Rep. David J. Taylor from David S. Taylor, the
    # P&G chief executive who filed the P&G Form 4s.
    if middle:
        want = middle.split()[0][:1]
        o_middle = [w for w in toks if w not in {first, last, suffix} and len(w) == 1]
        if o_middle and want not in o_middle and middle not in tokset:
            return False
    o_suffix = next((w for w in toks if w in SUFFIXES), "")
    if suffix and o_suffix != suffix:
        return False
    return True

FORM4_DIR = "https://www.sec.gov/Archives/edgar/data/{cik}/{adsh}/"


def read_form4(cik_plain: str, adsh_clean: str) -> dict | None:
    """Fetch a Form 4 and pull the reporting owner + relationship."""
    base = FORM4_DIR.format(cik=cik_plain, adsh=adsh_clean)
    try:
        idx = get(base + "index.json")
        names = [f["name"] for f in idx["directory"]["item"] if f["name"].endswith(".xml")]
        names = [n for n in names if "F345" not in n and "primary_doc" not in n] or names
        if not names:
            return None
        xml = get_bytes(base + names[0]).decode("utf-8", "ignore")
    except Exception:
        return None
    def grab(tag):
        m = re.search(rf"<{tag}>(.*?)</{tag}>", xml, re.S | re.I)
        return m.group(1).strip() if m else None
    return {
        "owner": grab("rptOwnerName"),
        "isDirector": grab("isDirector"),
        "isOfficer": grab("isOfficer"),
        "title": grab("officerTitle"),
        "isTenPct": grab("isTenPercentOwner"),
    }


def fts_search(q: str, ciks: str | None = None, max_pages: int = 3) -> list:
    """EDGAR full-text search, paginated (it serves 10 hits per page).

    Retries and SURFACES failures.  An earlier version swallowed the exception and
    returned an empty list, which silently looked like "this person filed nothing"
    and wiped a real result.
    """
    out: list = []
    for p in range(max_pages):
        u = FTS.format(q=urllib.parse.quote_plus(q))
        if ciks:
            u += f"&ciks={ciks}"
        u += f"&from={p * 10}"
        d = None
        for attempt in range(3):
            try:
                d = get(u)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"    ! FTS failed ({type(e).__name__} {e}) for {u}", file=sys.stderr)
                time.sleep(1.0 * (attempt + 1))
        if d is None:
            return out
        h = d.get("hits") or {}
        page = h.get("hits") or []
        total = (h.get("total") or {}).get("value", 0)
        out += page
        if not page or len(page) < 10 or len(out) >= total:
            break
        time.sleep(0.4)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/app_data.json")
    ap.add_argument("--out", default="data/insiders.json")
    ap.add_argument("--max-verify", type=int, default=4,
                    help="how many of the newest candidate filings to verify per pair")
    ap.add_argument("--max-age-years", type=int, default=3,
                    help="a verified insider link must have a filing this recent; a "
                         "decades-old directorship is a name collision, not a signal")
    a = ap.parse_args()

    data = json.load(open(a.inp))
    tickers = sorted((data.get("prices") or {}).keys())
    people = list((data.get("politicians") or {}).keys())
    cmap = cik_map()
    ours = {f"{cmap[t.upper()]:010d}": t for t in tickers if t.upper() in cmap}

    out: dict[str, dict] = {}
    for name in people:
        first, middle, last, suffix = parse_person(name)
        if not first or not last:
            continue
        # Stage 1: broad search to find WHICH of our companies this person filed for.
        broad = fts_search(f"{first} {last}")
        cand_tickers = set()
        for h in broad:
            for c in (h.get("_source") or {}).get("ciks") or []:
                key = str(c).zfill(10)
                if key in ours:
                    cand_tickers.add(ours[key])
        time.sleep(0.35)

        # Stage 2: targeted per-company search (far fewer hits, so pagination reaches
        # the newest filings), then verify against the Form 4 XML.
        for tk in sorted(cand_tickers):
            cik_plain = str(int(cmap[tk.upper()]))
            cik_pad = f"{int(cmap[tk.upper()]):010d}"     # EDGAR's ciks filter needs zero-pad
            hits = fts_search(last, ciks=cik_pad)
            print(f"  · {name} / {tk}: {len(hits)} filings on file", file=sys.stderr)
            hits.sort(key=lambda h: (h.get("_source") or {}).get("file_date") or "",
                      reverse=True)
            verified, n_ok = None, 0
            for h in hits[: a.max_verify]:
                src = h.get("_source") or {}
                f4 = read_form4(cik_plain, (src.get("adsh") or "").replace("-", ""))
                time.sleep(0.3)
                if not f4:
                    continue
                if not owner_matches(f4["owner"], first, middle, last, suffix):
                    continue
                if not (f4["isDirector"] == "1" or f4["isOfficer"] == "1"):
                    continue
                n_ok += 1
                if verified is None:
                    verified = {
                        "company": next((n.split("  (")[0].strip()
                                         for n in (src.get("display_names") or [])
                                         if f"(CIK {cik_plain.zfill(10)})" in n), tk),
                        "role": "Officer" if f4["isOfficer"] == "1" else "Director",
                        "title": f4["title"],
                        "last_filed": src.get("file_date"),
                        "forms": [src.get("form")],
                        "verified_filings": 0,
                    }
                else:
                    verified["forms"] = sorted(set(verified["forms"] + [src.get("form")]))
            if verified:
                # Must be a CURRENT insider.  A decades-old directorship is far more
                # likely a name collision than a signal: Richard David McCormick (WFC
                # director 1983-2010) is not Rep. Richard McCormick.
                try:
                    if (date.today() - date.fromisoformat(verified["last_filed"])).days \
                            > a.max_age_years * 366:
                        print(f"  ~ {name}/{tk}: only historical "
                              f"({verified['last_filed']}) — skipped", file=sys.stderr)
                        continue
                except Exception:
                    continue
                verified["verified_filings"] = n_ok
                out.setdefault(name, {})[tk] = verified
        time.sleep(0.35)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=1)
    print(f"[insiders] VERIFIED officer/director links: "
          f"{json.dumps({k: list(v) for k, v in out.items()})}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
