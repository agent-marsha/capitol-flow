#!/usr/bin/env python3
"""Coordinate-based parser for US House PTR (Periodic Transaction Report) PDFs.

House PTR PDFs lay out a table whose columns are fixed in x-space:
    ID | Owner | Asset | Transaction Type | Date | Notification Date | Amount | Cap. Gains

Text extraction mangles it because long asset names wrap across lines and
interleave with the date columns. So we cluster *words by x-coordinate* into
columns, then anchor rows on the Transaction-Type cell (a bare P / S / E),
which is unambiguous and only ever appears in the type column.

Public API:
    parse_ptr_pdf(path_or_bytes) -> list[dict]
"""
from __future__ import annotations

import io
import re
from datetime import datetime

TXN_LABELS = {"P": "Purchase", "S": "Sale", "E": "Exchange"}


def _clean(s: str) -> str:
    return s.replace("\x00", "").strip()


def _iso(d: str) -> str | None:
    try:
        return datetime.strptime(d, "%m/%d/%Y").date().isoformat()
    except Exception:
        return None


def _amount(tokens: list[str]) -> tuple[int | None, int | None, str]:
    """Turn amount-column tokens into (low, high, label)."""
    joined = " ".join(tokens)
    if re.search(r"over\s*\$?5,?000,?000", joined, re.I):
        return 5000001, None, "Over $5,000,000"
    nums = re.findall(r"\$[\d,]+", joined)
    vals = [int(n.replace("$", "").replace(",", "")) for n in nums]
    if len(vals) >= 2:
        lo, hi = min(vals[0], vals[1]), max(vals[0], vals[1])
        return lo, hi, f"${lo:,} - ${hi:,}"
    if len(vals) == 1:
        return vals[0], vals[0], f"${vals[0]:,}"
    return None, None, joined.strip()


def _columns(words: list[dict]) -> dict | None:
    """Derive column x-boundaries from the header row ('Owner','Asset','Transaction',...)."""
    hdr = {}
    for w in words:
        t = _clean(w["text"])
        if t in ("Owner", "Asset", "Transaction", "Date", "Notification", "Amount", "Cap.") \
                and 270 < w["top"] < 300:
            hdr.setdefault(t, w["x0"])
    if "Asset" not in hdr or "Transaction" not in hdr or "Date" not in hdr:
        return None
    a, ty, d, n = hdr["Asset"], hdr["Transaction"], hdr["Date"], hdr.get("Notification", hdr["Date"] + 55)
    amt = hdr.get("Amount", n + 62)
    cap = hdr.get("Cap.", amt + 78)
    return {
        "owner": (hdr.get("Owner", a - 39) - 10, a - 4),
        "asset": (a - 4, ty - 6),
        "type": (ty - 6, d - 4),
        "date": (d - 4, n - 4),
        "notify": (n - 4, amt - 4),
        "amount": (amt - 6, cap - 6),
    }


def _in(rng, x) -> bool:
    return rng[0] <= x < rng[1]


def parse_ptr_pdf(src) -> list[dict]:
    import pdfplumber
    buf = io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src
    out: list[dict] = []
    cols = None
    with pdfplumber.open(buf) as pdf:
        for pg in pdf.pages:
            words = [w for w in pg.extract_words() if _clean(w["text"])]
            for w in words:
                w["text"] = _clean(w["text"])
            if cols is None:
                cols = _columns(words)
                if cols is None:
                    continue
            # anchors: bare P / S / E sitting in the type column
            anchors = [w for w in words
                       if w["text"] in TXN_LABELS and _in(cols["type"], w["x0"])]
            if not anchors:
                continue
            anchors.sort(key=lambda w: w["top"])
            for i, a in enumerate(anchors):
                top = a["top"]
                # asset/amount may wrap to ONE continuation line; cap the band so
                # footer text between transactions can't bleed in.
                nxt = min(anchors[i + 1]["top"] - 1, top + 11) if i + 1 < len(anchors) else top + 11
                def band(word, lo=top - 2.5, hi=None):
                    return lo <= word["top"] <= (hi if hi is not None else nxt)
                date = next((w["text"] for w in words
                             if _in(cols["date"], w["x0"]) and abs(w["top"] - top) < 3), None)
                notify = next((w["text"] for w in words
                               if _in(cols["notify"], w["x0"]) and abs(w["top"] - top) < 3), None)
                asset = " ".join(w["text"] for w in words
                                 if _in(cols["asset"], w["x0"]) and band(w))
                # keep only the leading "Name (TICKER) [TYPE]" run; drop any
                # trailing footer/continuation noise
                _m = re.match(r"^(.*?\([A-Z][A-Z0-9.\-]{0,6}\)\s*(?:\[[A-Z]{1,3}\])?)", asset)
                if _m:
                    asset = _m.group(1)
                amt_toks = [w["text"] for w in words
                            if _in(cols["amount"], w["x0"]) and band(w)]
                owner = next((w["text"] for w in words
                              if _in(cols["owner"], w["x0"]) and abs(w["top"] - top) < 3), "Self")
                lo, hi, label = _amount(amt_toks)
                if not asset or not date:
                    continue
                out.append({
                    "owner": owner or "Self",
                    "asset_raw": re.sub(r"\s+", " ", asset).strip(),
                    "txn_type": a["text"],
                    "txn_type_label": TXN_LABELS[a["text"]],
                    "txn_date": _iso(date),
                    "notification_date": _iso(notify) if notify else None,
                    "amount_low": lo, "amount_high": hi, "amount_label": label,
                })
    return out


if __name__ == "__main__":
    import json
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ptr.pdf"
    print(json.dumps(parse_ptr_pdf(src), indent=1))
