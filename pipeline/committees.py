#!/usr/bin/env python3
"""Committee assignments for members of Congress, plus a sector -> committee map.

Why this matters: a senator dumping pharma stock is one thing. The senator who sits
on the committee that OVERSEES pharma doing it is a different signal entirely. This
module supplies the missing half of that comparison.

Sources (free, no key):
  * committee-membership-current.yaml  — who sits on what (with titles: Chairman, ...)
  * committees-current.yaml            — committee names + jurisdiction

Output: data/committees.json
  { "committees": { "SSAF": {"name": "...", "short": "Senate Agriculture", "type": "senate"} },
    "members":    { "B001236": [ {"code": "SSAF", "title": "Chairman", "rank": 1} ] },
    "sector_committees": { "Technology": ["SSCM","HSIF", ...] } }

Usage: python committees.py [--out data/committees.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request

BASE = ("https://raw.githubusercontent.com/unitedstates/congress-legislators/main/")
MEMBERSHIP = BASE + "committee-membership-current.yaml"
COMMITTEES = BASE + "committees-current.yaml"
UA = "CapitolFlow research (contact: victor26@fastmail.com)"

# Which committees have jurisdiction over which stock sector.  This is a HEURISTIC —
# it drives a "this politician oversees this industry" flag, not a legal opinion.
#
# Deliberately NARROW. We only include committees whose jurisdiction over the sector is
# SUBSTANTIVE (they write the rules for it), not merely tax-related.
#   * Ways and Means / Finance are kept for Healthcare only — they genuinely run
#     Medicare/Medicaid — but NOT for retail or financials, where their only hook is tax.
#     Including them there made the flag fire on ~half of all trades, which is noise.
#   * Agriculture is NOT applied to all of Consumer Defensive: the committee covers food
#     and farming, not cosmetics or discount stores (it was flagging Estée Lauder and
#     Walmart). Consumer-product safety sits with Energy and Commerce / Commerce.
SECTOR_COMMITTEES = {
    "Technology": ["SSCM", "HSIF", "SSJU", "HSJU", "HSSY", "HSZS", "SLIN", "HLIG"],
    "Communication Services": ["SSCM", "HSIF", "SSJU", "HSJU"],
    "Healthcare": ["SSHR", "SSFI", "HSIF", "HSWM", "SPAG"],
    "Financial Services": ["SSBK", "HSBA"],
    "Energy": ["SSEG", "HSIF", "HSII"],
    "Basic Materials": ["SSEG", "HSII", "HSIF"],
    "Industrials": ["SSCM", "HSPW", "SSAS", "HSAS", "SSEV"],
    "Consumer Cyclical": ["SSCM", "HSIF"],
    "Consumer Defensive": ["HSIF", "SSCM"],
    "Utilities": ["SSEG", "HSIF", "SSEV"],
    "Real Estate": ["SSBK", "HSBA"],
}


def fetch_yaml(url: str) -> dict:
    import yaml
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return yaml.safe_load(r.read())


SHORT_OVERRIDES = {
    "SSBK": "Banking",
    "HSBA": "Financial Services",
    "SSHR": "Health, Education, Labor",
    "SSAF": "Agriculture",
    "HSAG": "Agriculture",
    "SSEG": "Energy and Natural Resources",
    "HSII": "Natural Resources",
    "HSZS": "China Competition",
    "HLIG": "Intelligence",
    "SLIN": "Intelligence",
    "SSFI": "Finance",
    "HSWM": "Ways and Means",
    "SSAP": "Appropriations",
    "HSAP": "Appropriations",
    "SSCM": "Commerce, Science, and Transportation",
    "HSIF": "Energy and Commerce",
    "SSJU": "Judiciary",
    "HSJU": "Judiciary",
    "SSAS": "Armed Services",
    "HSAS": "Armed Services",
    "HSPW": "Transportation and Infrastructure",
    "SSEV": "Environment and Public Works",
    "HSSY": "Science, Space, and Technology",
    "SPAG": "Aging",
}


def short_committee_name(full: str, tid: str | None = None) -> str:
    if tid and tid in SHORT_OVERRIDES:
        return SHORT_OVERRIDES[tid]
    n = full
    for pre in ("Senate Select Committee on ", "Senate Special Committee on ",
                "Senate Committee on ", "House Select Committee on ",
                "House Committee on ", "United States "):
        if n.startswith(pre):
            n = n[len(pre):]
            break
    n = n.replace("Permanent Select Committee on ", "")
    n = re.sub(r"\s*\(.*?\)\s*$", "", n)
    n = re.sub(r", and Pensions$|, Nutrition, and Forestry$", "", n)
    if "Intelligence" in full:
        n = "Intelligence"
    return n.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/committees.json")
    a = ap.parse_args()

    try:
        membership = fetch_yaml(MEMBERSHIP)
        defs = fetch_yaml(COMMITTEES)
    except Exception as e:
        print(f"[committees] fetch failed: {type(e).__name__} {e}", file=sys.stderr)
        return 1

    committees = {}
    for c in defs:
        tid = c.get("thomas_id")
        if tid:
            committees[tid] = {
                "name": c.get("name", ""),
                "short": short_committee_name(c.get("name", ""), tid),
                "type": c.get("type", ""),
            }

    members: dict[str, list] = {}
    for code, roster in (membership or {}).items():
        if not isinstance(roster, list):
            continue
        # subcommittee codes are the parent code + digits ("SSAP19" -> "SSAP");
        # fold them onto the parent so the jurisdiction check works.
        parent = code if code in committees else code[:4]
        if parent not in committees:
            continue
        for m in roster:
            bio = m.get("bioguide")
            if not bio:
                continue
            members.setdefault(bio, []).append({
                "code": parent,
                "sub": code if code != parent else None,
                "title": (m.get("title") or "").strip() or None,
                "rank": m.get("rank"),
            })
    for bio in members:
        # One seat per committee (subcommittees fold onto their parent).
        # A subcommittee chairmanship must NOT be reported as a full-committee title:
        # "Chairman" is the loudest claim this feature makes, so it may only come from
        # the full committee's own seat.
        best: dict[str, dict] = {}

        def score(x):
            return (x["sub"] is None,            # full committee beats a subcommittee
                    bool(x.get("title")),         # then a titled seat
                    -(x.get("rank") or 999))      # then the most senior

        for s in members[bio]:
            cur = best.get(s["code"])
            if cur is None or score(s) > score(cur):
                best[s["code"]] = s
        for code, s in best.items():
            if s["sub"] is not None:
                s["title"] = None
        members[bio] = sorted(best.values(), key=lambda x: (x.get("rank") or 999))

    out = {
        "committees": committees,
        "members": members,
        "sector_committees": SECTOR_COMMITTEES,
    }
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=1)
    print(f"[committees] {len(committees)} committees, {len(members)} members with seats, "
          f"{len(SECTOR_COMMITTEES)} sectors mapped -> {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
