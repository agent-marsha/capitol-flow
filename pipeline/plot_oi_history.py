#!/usr/bin/env python3
"""Plot an open-interest history chart for any ticker from the OI history store.

    python3 pipeline/plot_oi_history.py NVDA AAPL

Reads data/oi_history_summary.json (the compact series), so it is one small read per ticker.

TWO THINGS THE CHART IS CAREFUL ABOUT, because both have bitten this data:

1. Per-ticker totals are NOT comparable across a change in the captured expiration set. The
   30-day floor rolls forward and contracts expire, so total OI can jump purely because
   different expiries are in scope -- an artefact, not positioning. Every change in the
   expiry count is drawn as a dashed line; the flat segments between them are the only
   honestly comparable stretches.

2. `spot` is the price AT PULL TIME, not the close. The refresh runs ~09:35 ET, so on a
   volatile day the recorded spot can sit well away from that day's close.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oi_history_store as hist

BG, FG, MUT = "#0a0a0b", "#e8eaed", "#9aa0a6"
VOLT, PINK, BLUE, PUR = "#d8ff3e", "#ff5c7a", "#6cb6ff", "#8a6cff"


def detail(ticker):
    """Date -> n_exp from the gzipped daily records, to flag expiry-set changes."""
    out = {}
    for p in hist.days():
        try:
            rec = hist.load_day(p)
        except Exception:
            continue
        v = (rec.get("tickers") or {}).get(ticker.upper())
        if v:
            out[rec["date"]] = v.get("n_exp")
    return out


def chart(ticker, outdir="charts"):
    rows = hist.series(ticker)
    if not rows:
        print("no history for %s" % ticker)
        return None
    nexp = detail(ticker)
    xs = [datetime.strptime(r[0], "%Y-%m-%d") for r in rows]
    call = [r[2] / 1e6 for r in rows]
    put = [r[3] / 1e6 for r in rows]
    spot = [r[1] for r in rows]
    exp = [nexp.get(r[0]) for r in rows]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True,
                                   gridspec_kw={"height_ratios": [2, 1]})
    fig.patch.set_facecolor(BG)
    for a in (ax1, ax2):
        a.set_facecolor(BG)
        a.tick_params(colors=MUT, labelsize=9)
        for s in a.spines.values():
            s.set_color("#2a2a2e")
        a.grid(color="#1e1e22", linewidth=0.8)

    ax1.plot(xs, call, color=VOLT, linewidth=2.2, marker="o", ms=5, label="Call OI")
    ax1.plot(xs, put, color=PINK, linewidth=2.2, marker="o", ms=5, label="Put OI")
    ax1.set_ylabel("open interest (millions of contracts)", color=FG, fontsize=10)
    ax1.legend(facecolor="#141416", edgecolor="#2a2a2e", labelcolor=FG, fontsize=9)

    for i in range(1, len(rows)):
        if exp[i] is not None and exp[i] != exp[i - 1]:
            ax1.axvline(xs[i], color=PUR, linestyle="--", linewidth=1.1, alpha=0.85)
            ax1.annotate("expiries %s to %s" % (exp[i - 1], exp[i]), (xs[i], max(call)),
                         color="#b9a6ff", fontsize=8, xytext=(4, -4),
                         textcoords="offset points", va="top")

    pc0 = (put[0] / call[0]) if call[0] else 0
    pc1 = (put[-1] / call[-1]) if call[-1] else 0
    ax1.set_title("%s open interest, one point per refresh day\n"
                  "P/C %0.2f to %0.2f   |   price at pull time %s to %s"
                  % (ticker.upper(), pc0, pc1,
                     ("$%.2f" % spot[0]) if spot[0] else "-",
                     ("$%.2f" % spot[-1]) if spot[-1] else "-"),
                  color="#ffffff", fontsize=13, fontweight="bold", loc="left")

    ax2.plot(xs, spot, color=BLUE, linewidth=2, marker="o", ms=4)
    ax2.set_ylabel("price at pull ($)", color=FG, fontsize=10)
    ax2.text(0.01, 0.06, "price at pull time (~09:35 ET), not the close",
             transform=ax2.transAxes, color=MUT, fontsize=8)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    plt.setp(ax2.get_xticklabels(), color=MUT, fontsize=8.5)
    fig.tight_layout()

    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, "%s_oi_history.png" % ticker.lower())
    fig.savefig(out, dpi=140, facecolor=fig.get_facecolor())
    plt.close(fig)
    print("wrote %s" % out)
    return out


if __name__ == "__main__":
    for t in (sys.argv[1:] or ["NVDA"]):
        chart(t)
