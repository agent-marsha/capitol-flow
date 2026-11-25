# TASK — Replace the historical OI tracker with a historical put/call ratio tracker

Extend the EXISTING app. Do not redesign it. Read `web/app.js` and `web/styles.css` first.

## What changes
The app currently charts historical OPEN INTEREST (two lines: calls and puts) in two places:
1. the stock page section **THE HISTORY** (`#oih-slot`, `.oih*` classes)
2. the dashboard section **BUILDING OR UNWINDING.** (`#oi-index`, `.oix*` classes)

The request is to REPLACE those with a **historical PUT/CALL RATIO** view, so the change over
time reads as one number rather than two lines whose level is hard to compare.

**Do not remove the data collection.** `data/oi_history_summary.json` stays as-is. It is the
input; this is a presentation change. The per-day records still hold raw call/put OI.

## The ratio
    pc = put_oi / call_oi        (by CONTRACTS, not dollars)

Rows are `[date, spot, call_oi, put_oi, n_exp]` (oldest first). Guard call_oi == 0 -- never
emit Infinity/NaN; skip that day.

## Stock page — replace the chart
- **One line**: the P/C ratio over time. Solid; no second series.
- **A reference line at 1.00**, labelled once (e.g. `1.00 BALANCED`), because the value is
  only meaningful relative to 1. Above 1 means more put contracts open than call contracts.
- Y range from the data (min-0.05 .. max+0.05) but the 1.00 line must ALWAYS be visible, so
  include 1.00 in the range even if the series never crosses it.
- Keep the hover readout and the day-by-day table; lead the table with the ratio and keep the
  raw call/put OI columns after it.
- Base the **change figure** on the ratio: `0.84 to 0.96 (+0.12)` over the comparable window.
  Primary form is CHANGE IN RATIO POINTS. A percent change of a ratio is easy to misread --
  include it only if it does not confuse.

## Dashboard index — replace the rows
- Each row's sparkline becomes the **P/C ratio** sparkline, not the two-line OI sparkline.
- Columns: ticker, ratio sparkline, **current ratio**, **change in ratio points**, days, and
  the comparable window. Keep call/put OI only if it still reads cleanly -- the ratio leads.
- Sorting: by ticker, by current ratio (highest/lowest), by biggest ratio move. Default to
  biggest absolute ratio move so the section surfaces what actually changed.
- Keep the filter box and the "show all" pattern.

## Wording — this is the part most likely to go wrong
- **A high ratio is NOT bearish.** Open interest is directionless: it counts open contracts
  and cannot say whether they were bought or written. A put-heavy book can be hedgers buying
  insurance OR sellers writing puts for income. Do NOT use "bearish", "fearful", "betting
  against", "accumulation", "distribution". Describe the book, not a mood.
- Prefer: "more put contracts than call contracts", "the ratio rose from X to Y".
- Keep the expiry-set caveat, but state the ratio's advantage honestly: because the ratio
  divides one total by the other, a change in how many expirations are tracked moves both
  sides and affects the ratio LESS than the raw total -- it does not make the ratio immune,
  since added expiries can differ in mix. Say it that way, not "the ratio is unaffected".
- `spot` is the price at pull time (~09:35 ET), not the close. Keep saying so if shown.

## Keep working
- Section ids and lazy-loading must keep working (`#oih-slot` on stock pages, `#oi-index` on
  the dashboard). The dashboard may keep prefetching the summary.
- A ticker with fewer than 2 readings renders NO chart and NO change figure (not 0, not a
  flat line).
- Missing summary file -> both sections render nothing, no errors.
- No NaN / Infinity / undefined on screen.

## Design rules (non-negotiable)
- Match the app: bold black/white, mono uppercase micro-labels, high contrast, minimal chrome.
- No glassmorphism, no gradients, no glows. Reuse existing tokens; new CSS at the end of
  styles.css under a clear comment.
- Responsive: rows must stay readable on a narrow phone.
- The ratio line must be clearly distinguishable from the 1.00 reference line by weight
  and/or dash, not by colour alone.

## Definition of done
- Stock page shows one P/C ratio line with a visible 1.00 reference and a ratio-point change.
- Dashboard lists all tickers with a ratio sparkline, current ratio and ratio-point change.
- NVDA and AAPL render correctly; NFLX (one reading) renders no chart and no change.
- `node --check web/app.js` passes.
- The raw OI data files are untouched.
- No existing section's behaviour changes.
