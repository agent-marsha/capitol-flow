#!/usr/bin/env python3
"""Plot the NVDA open-interest series reconstructed from committed options.json snapshots."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

rows = json.load(open("/tmp/nvda_oi_hist.json"))
rows = [r for r in rows if r["n_exp"] >= 6]          # drop the pre-schema snapshot
xs = [datetime.strptime(r["when"], "%Y-%m-%d %H:%M") for r in rows]
call = [r["call_oi"] / 1e6 for r in rows]
put = [r["put_oi"] / 1e6 for r in rows]
spot = [r["spot"] for r in rows]
exp = [r["n_exp"] for r in rows]

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True,
                               gridspec_kw={"height_ratios": [2, 1]})
fig.patch.set_facecolor("#0a0a0b")
for a in (ax1, ax2):
    a.set_facecolor("#0a0a0b")
    a.tick_params(colors="#9aa0a6", labelsize=9)
    for s in a.spines.values():
        s.set_color("#2a2a2e")
    a.grid(color="#1e1e22", linewidth=0.8)

ax1.plot(xs, call, color="#d8ff3e", linewidth=2.2, marker="o", ms=4, label="Call OI")
ax1.plot(xs, put, color="#ff5c7a", linewidth=2.2, marker="o", ms=4, label="Put OI")
ax1.set_ylabel("open interest (millions of contracts)", color="#e8eaed", fontsize=10)
ax1.set_title("NVDA open interest, reconstructed from committed snapshots\n"
              "each point = one committed options.json",
              color="#ffffff", fontsize=13, fontweight="bold", loc="left")
ax1.legend(facecolor="#141416", edgecolor="#2a2a2e", labelcolor="#e8eaed", fontsize=9)

# mark where the captured expiration set changed -- totals are not comparable across these
for i in range(1, len(rows)):
    if exp[i] != exp[i - 1]:
        ax1.axvline(xs[i], color="#8a6cff", linestyle="--", linewidth=1.1, alpha=0.85)
        ax1.annotate("expiry set %d to %d" % (exp[i - 1], exp[i]),
                     (xs[i], max(call)), color="#b9a6ff", fontsize=8,
                     xytext=(4, -6), textcoords="offset points", va="top")

ax1.annotate("Nov 20 monthly OPEX",
             (xs[-1], call[-1]), color="#ffb4c2", fontsize=8,
             xytext=(-120, 22), textcoords="offset points",
             arrowprops=dict(arrowstyle="->", color="#ffb4c2", lw=1))

ax2.plot(xs, spot, color="#6cb6ff", linewidth=2, marker="o", ms=3.5)
ax2.set_ylabel("NVDA price ($)", color="#e8eaed", fontsize=10)
ax2.text(0.01, 0.06, "price over the same snapshots", transform=ax2.transAxes,
         color="#9aa0a6", fontsize=8)

ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
plt.setp(ax2.get_xticklabels(), color="#9aa0a6", fontsize=8.5)
fig.tight_layout()
out = "/root/capitol-flow/web/nvda_oi_history.png"
fig.savefig(out, dpi=140, facecolor=fig.get_facecolor())
print("wrote", out)
print()
for r in rows:
    print("  %-17s exps %2d  call %10s  put %10s  spot %.2f" %
          (r["when"], r["n_exp"], format(int(r["call_oi"]), ","),
           format(int(r["put_oi"]), ","), r["spot"] or 0))
