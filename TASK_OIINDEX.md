# TASK — An OI history browser across every tracked stock

Extend the EXISTING app. Do not redesign it. Read `web/app.js` and `web/styles.css` first.

## What already exists — reuse it, do not rebuild
Historical OI is already recorded and already charted on the individual stock page. On
`#/stock/<TICKER>` there is a **THE HISTORY** section (`#oih-slot`, classes `.oih*`) that
draws a calls/puts chart from a lazily-loaded `data/oi_history_summary.json`. Reuse that code
— factor out what you need rather than copying the chart or the caveat text.

## The gap
The history is only reachable if you already know which ticker you want. There is no way to
see ACROSS the tracked universe — which names' open interest is building, which is unwinding,
which have the most history.

## Build — a new section on the DASHBOARD, id `#oi-index`
Place it after the existing `#top-oi` contract leaderboard.

1. A scannable list of EVERY ticker in the series (~119), one row each:
   - ticker, linked to `#/stock/<TICKER>`
   - a mini inline-SVG sparkline of total OI (calls + puts), ~90x22 px, no axes or labels
   - call OI, put OI (compact, e.g. `5.17M`), and P/C
   - days of history and the change over the comparable window
2. Controls: a search/filter box; sort by ticker / total OI / biggest change; a toggle for
   calls vs puts in the sparkline.
3. ~25 rows by default with a "show all" toggle — match the top-N-then-expand pattern the
   app already uses elsewhere.

## THE RULE — never compare across an expiry-set change
Same trap the stock-page section already guards. It matters MORE here because the section is
about comparing names and changes.

Rows are `[date, spot, call_oi, put_oi, n_exp]`. n_exp = expirations tracked that day. Totals
jump when n_exp changes — a 6-expiry day beside a 10-expiry day reads as +144% that never
happened. Therefore:

- Every change figure is computed only over the stretch where n_exp is constant (walk back
  from the newest reading while it matches). Reuse the existing logic.
- Sort by change must use that comparable figure, never raw first-to-last.
- Rows that cannot form a comparable window show NO change figure — not `0%`, not a `—` that
  pretends zero.
- The section needs one plain sentence stating the caveat, like the stock-page section does.

## Wording rules
- Open interest is directionless. Never imply building/unwinding is bullish/bearish or
  buying/selling. "Building" and "unwinding" are fine; "accumulation" and "distribution" are
  NOT — they imply who is on which side.
- spot is the price at pull time (~09:35 ET), not the close. Say so if shown.
- Plain English, consistent with the rest of the app.

## Design rules (non-negotiable)
- Match the app: bold black/white, mono uppercase micro-labels, high contrast, minimal chrome.
- No glassmorphism, no gradients, no glows.
- Reuse existing classes/tokens; new CSS only at the end of styles.css under a clear comment.
- Distinguish calls from puts by line style as well as colour, like the stock-page chart.
- Responsive: rows stay readable on a narrow phone (collapse columns sensibly).

## Definition of done
- `#oi-index` renders ~119 rows from the real data, every sparkline drawn, no console errors.
- Sort by "biggest change" agrees with the stock-page figure for the same ticker.
- A ticker with one reading shows no sparkline change and renders fine.
- `data/oi_history_summary.json` missing → section renders nothing, page fine.
- No NaN / Infinity / undefined on screen.
- `node --check web/app.js` passes.
- No existing section's behaviour changes.
