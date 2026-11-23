# TASK — Show the OI history on the stock pages

Extend the EXISTING app. Do not redesign it. Read `web/app.js` and `web/styles.css` first.

## Why
The pipeline now records open interest every day for every ticker (see
`pipeline/oi_history_store.py`). Nothing reads it yet. A stock page shows only TODAY's OI —
a single number with no context. A reader cannot tell whether 1.6 M calls is a lot or a
little, or whether positioning is building or unwinding.

## Data — standalone file, load it LAZILY like oi_lookup

`data/app_data.json` does NOT carry it. The refresh copies a standalone file:

```
web/data/oi_history_summary.json     (and window.__CAPITOL_OI_HISTORY__ fallback)
```

Shape — one row per ticker per day, oldest first:

```jsonc
{"series": {
   "NVDA": [["2026-11-15", 162.85, 2114308, 1846547],
            ["2026-11-16", 155.85, 6047676, 5762625]],
   "AAPL": [["2026-11-15", 356.27, 551368, 552041]]
}}
```

Row = `[date, spot_at_pull, call_oi, put_oi]`.

Load it ON FIRST STOCK-PAGE VIEW using the existing lazy pattern already used for
`oi_lookup` (the `oiLoadedBefore` flag). Do NOT add it to the boot bundle. Guard everything:
missing file, missing ticker, a 1-day series, null spot.

## Build — a compact section on `#/stock/<TICKER>`, near the existing OPTIONS block

1. **A line chart** — two series, call OI and put OI, x = date, y = contracts. Use the
   library ALREADY in the app (TradingView Lightweight Charts is already a dependency for
   the candlesticks). No fills, no glow. An inline SVG sparkline is acceptable if the library
   makes dual-series awkward — match the hand-rolled SVG idiom used elsewhere.

2. **A one-line change summary**, e.g. `Calls 6.05M to 6.36M (+5.2%) over 3 days`.

3. **P/C ratio now vs at the start** of the series.

4. **Render NOTHING** when there are fewer than 2 days for that ticker. No empty chart, no
   flat line, no "0%" change.

## THE CRITICAL RULE — an expiry-set change makes totals non-comparable

Total OI jumps when the captured EXPIRY SET changes, not because positioning moved: the
30-day floor rolls forward and contracts expire. In NVDA's history the total jumped 2.1M to
6.0M when the set went 6 to 10 expiries, and fell 6.36M to 5.23M when an expiry aged out.
Neither was real.

The detailed daily records store `n_exp` per day but the compact summary does NOT, so the
summary alone cannot tell you whether a step is real. Therefore:

- **Label the section with that caveat, in one plain sentence**, e.g. *"Open interest totals
  jump when the set of expirations we track changes — that is a change in what is counted,
  not necessarily a change in positioning."*
- **Do NOT present the change figure as a clean positioning claim.** The delta may be shown,
  but it must sit NEXT TO that caveat, never on its own.

Do not invent a correction or a smoothing. Show it and say what it is.

## Wording rules
- **Open interest is directionless.** Never imply the lines show bullish/bearish, buying or
  selling. Stay consistent with the existing OPTIONS caveat.
- `spot` in the data is the **price at pull time (~09:35 ET), not the close.** If you show
  price anywhere, say so.
- Plain English. No jargon beyond "open interest", "call", "put", "expiration".

## Design rules (non-negotiable)
- Match the app: bold black/white, mono uppercase micro-labels, high contrast, minimal chrome.
- **No glassmorphism, no gradients, no glows.**
- Reuse existing classes/tokens; add new CSS only at the end under a clear comment.
- Responsive: must read well on a narrow phone.

## Definition of done
- A ticker with 3+ days (`NVDA`, `AAPL`) shows the chart, the change line and the caveat.
- A ticker with 1 day renders NO section and throws nothing.
- A ticker absent from the series renders NO section and throws nothing.
- `oi_history_summary` missing entirely → page renders exactly as today, no errors.
- Null `spot` or zero call OI never produces `NaN`, `Infinity` or a divide-by-zero.
- `node --check web/app.js` passes.
- No existing section's behaviour changes.
