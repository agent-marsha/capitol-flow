#!/usr/bin/env python3
"""Resolve politicians named in the trade data to their state, party and photo.

Source (free, public domain, no key):
  * roster  : https://raw.githubusercontent.com/unitedstates/congress-legislators/main/legislators-current.yaml
  * photos  : https://raw.githubusercontent.com/unitedstates/images/gh-pages/congress/225x275/{bioguide}.jpg

Why a matcher and not a join: the disclosure names are messy —
  "Hon. John J Mr McGuire III", "Sen. A. Mitchell McConnell, Jr.", "Hon. Carol Devine Miller"
while the roster holds "John McGuire", "Mitch McConnell", "Carol Miller". We strip
honorifics and generational suffixes, then match on LAST NAME + CHAMBER, using the
House district's state as a tiebreaker.

Output: data/politicians.json
  { "Hon. Gilbert Cisneros": { "bioguide":"C001123",
                               "photo":"https://…/C001123.jpg",
                               "state":"CA", "state_name":"California",
                               "party":"Democrat", "district":31, "chamber":"House" } }

Usage: python politicians.py [--house data/house_trades.json] [--senate data/senate_trades.json]
                             [--out data/politicians.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request

ROSTER_URL = ("https://raw.githubusercontent.com/unitedstates/congress-legislators/"
              "main/legislators-current.yaml")
PHOTO = ("https://raw.githubusercontent.com/unitedstates/images/gh-pages/"
         "congress/225x275/{bioguide}.jpg")
CACHE = "/tmp/capitol-legislators.yaml"
UA = "CapitolFlow research (contact: victor26@fastmail.com)"

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin",
    "WY": "Wyoming", "DC": "District of Columbia", "AS": "American Samoa", "GU": "Guam",
    "MP": "Northern Mariana Islands", "PR": "Puerto Rico", "VI": "U.S. Virgin Islands",
}

# tokens that are never part of a usable surname
NOISE = {"hon", "sen", "rep", "mr", "mrs", "ms", "dr", "jr", "sr", "ii", "iii", "iv", "v"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z ]", "", (s or "").lower()).strip()


def last_name(politician: str) -> str:
    s = re.sub(r"\(.*?\)", " ", politician or "")
    s = re.sub(r"[.,]", " ", s)
    toks = [w for w in norm(s).split() if w and w not in NOISE]
    return toks[-1] if toks else ""


def chamber_hint(politician: str, chamber: str | None) -> str | None:
    p = (politician or "").lower()
    if p.startswith("sen") or chamber == "Senate":
        return "Senate"
    if p.startswith("hon") or chamber == "House":
        return "House"
    return None


def load_roster() -> list:
    import yaml
    if not os.path.exists(CACHE) or os.path.getsize(CACHE) < 10_000:
        req = urllib.request.Request(ROSTER_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as r:
            open(CACHE, "wb").write(r.read())
    return yaml.safe_load(open(CACHE))


def entry(L: dict, chamber: str | None) -> dict:
    ids, name, terms = L["id"], L["name"], L["terms"]
    # the most recent term of the chamber that matters
    want = "sen" if chamber == "Senate" else ("rep" if chamber == "House" else None)
    t = None
    for term in reversed(terms):
        if want is None or term.get("type") == want:
            t = term
            break
    t = t or terms[-1]
    bio = ids.get("bioguide")
    return {
        "bioguide": bio,
        "photo": PHOTO.format(bioguide=bio) if bio else None,
        "state": t.get("state"),
        "state_name": STATES.get(t.get("state"), t.get("state")),
        "party": t.get("party"),
        "district": t.get("district"),
        "chamber": "Senate" if t.get("type") == "sen" else "House",
        "official_full": name.get("official_full"),
    }


def build_index(roster: list) -> dict:
    idx: dict[str, list] = {}
    for L in roster:
        for k in (L["name"].get("last"), L["name"].get("official_full")):
            if k:
                ln = norm(k).split()[-1] if " " in norm(k) else norm(k)
                idx.setdefault(norm(k), []).append(L)
                idx.setdefault(ln, []).append(L)
    for k in idx:
        seen, uniq = set(), []
        for L in idx[k]:
            b = L["id"].get("bioguide")
            if b not in seen:
                seen.add(b); uniq.append(L)
        idx[k] = uniq
    return idx


def match(politician: str, chamber: str | None, state: str | None, idx: dict) -> dict | None:
    """Resolve one disclosure name to a legislator."""
    cands = idx.get(norm(re.sub(r"^(hon\.|sen\.|rep\.)\s*", "", politician, flags=re.I)), [])
    if len(cands) == 1:
        return entry(cands[0], chamber)
    want = chamber_hint(politician, chamber)
    pool = cands or idx.get(last_name(politician), [])
    if not pool:
        return None
    # narrow by chamber using the legislator's current seat
    def seat(L):
        return "Senate" if L["terms"][-1].get("type") == "sen" else "House"
    narrowed = [L for L in pool if not want or seat(L) == want] or pool
    if state:
        bystate = [L for L in narrowed if L["terms"][-1].get("state") == state]
        if bystate:
            narrowed = bystate
    if len(narrowed) == 1:
        return entry(narrowed[0], want or chamber)
    # still ambiguous: take the one who most recently started a term
    narrowed.sort(key=lambda L: L["terms"][-1].get("start", ""), reverse=True)
    return entry(narrowed[0], want or chamber) if narrowed else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--house", default="data/house_trades.json")
    ap.add_argument("--senate", default="data/senate_trades.json")
    ap.add_argument("--out", default="data/politicians.json")
    a = ap.parse_args()

    people: dict[str, tuple[str | None, str | None]] = {}
    for path, chamber in ((a.house, "House"), (a.senate, "Senate")):
        if not os.path.exists(path):
            continue
        for t in json.load(open(path))["transactions"]:
            p = t.get("politician")
            if p:
                st = (t.get("state_district") or "")[:2] or None
                people.setdefault(p, (chamber, st))

    roster = load_roster()
    idx = build_index(roster)
    out, miss = {}, []
    for p, (chamber, st) in sorted(people.items()):
        m = match(p, chamber, st, idx)
        if m:
            out[p] = m
        else:
            miss.append(p)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=1)
    with_photo = sum(1 for v in out.values() if v.get("photo"))
    print(f"[politicians] matched {len(out)}/{len(people)} "
          f"({with_photo} with photos); unmatched: {miss}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
