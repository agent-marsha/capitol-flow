# TASK — Graceful fallback when a stock page has no price history

You are extending an EXISTING app. Do not redesign it. Match it exactly.

## Background

`#/stock/TICKER` renders for any ticker that has trades **or** prices. Price history is
only fetched for the top-N tickers by signal score, so a ticker with one small trade can
land on a real page whose **chart is empty**.

Today that looks broken. On a ticker such as `#/stock/DIS` (one trade, not in the charted
set) the chart area shows:

```
NO PRICE DATA
No price history for DIS.
```

…and **THE NEWS** renders as an empty titled section with nothing under it. Everything
else on the page is fine (profile, the trade, the full OPTIONS chain).

This is the fallback half of a fix. The other half (raising the charted set from 60 → 120,
and forcing the biggest option markets in) is already done in the pipeline, so this only
needs to catch the **remaining tail** — roughly 112 traded tickers.

**Test cases:** `#/stock/DIS`, `#/stock/PEP`, `#/stock/UBER`, `#/stock/MA`, `#/stock/GE`
have NO prices → must show the fallback. `#/stock/NVDA`, `#/stock/AAPL`, `#/stock/INTC`
DO have prices → must be unchanged.

## What to build

### 1. Chart slot fallback (`renderDetail`, the `chartEmpty(...)` call around line 1408)
When `hasPrices(tk)` is false, instead of the bare message, render a **useful dead-end-free
panel** in the chart's place containing:
- A short honest line, e.g. *"No price history for this ticker yet."*
- A quieter second line explaining why, e.g. *"This app charts the most-traded names. Chart
  <TICKER> elsewhere:"*
- **Two outbound links**, in the app's existing link style:
  - **`Yahoo Finance ↗`** → `https://finance.yahoo.com/quote/<TICKER>/`
  - **`TradingView ↗`** → `https://www.tradingview.com/symbols/<TICKER>/`
  - Both `target="_blank" rel="noopener"`, with accessible labels
    (*"Open INTC on Yahoo Finance, new tab"*).
- Keep the existing timeframe buttons visible but **disabled** (or hidden) — they do
  nothing without data. Choose whichever looks calmer and say which you picked.
- Do **not** show a fake/empty chart canvas, and do not show "NO PRICE DATA" as a bare
  shout.

### 2. Omit THE NEWS when there is nothing to show
If a ticker has no news items, **do not render the THE NEWS section at all** — no heading,
no empty container. (Same principle the BASICS section already uses: omit rather than show
an empty shell.)

### 3. Keep it consistent
- A ticker that **does** have prices must be completely unchanged.
- The fallback must work at **390px** and **1440px** — nothing overflowing, no sideways
  scroll, links tappable (≥44px touch target).
- No new accent colour. Reuse the existing muted/secondary link treatment.

## Definition of done
- `node --check web/app.js` passes.
- `#/stock/INTC` (no prices) shows the fallback panel with two working outbound links, and
  **no empty NEWS section**.
- `#/stock/AAPL` and `#/stock/NVDA` (have prices) are visually unchanged, with their NEWS
  sections intact.
- Correct at 390px and 1440px; no console errors; nothing else regresses.

Be decisive. Don't ask questions.
