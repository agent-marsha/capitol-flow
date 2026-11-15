# TASK — Add an "OPTIONS" section to Capitol Flow stock pages

You are extending an EXISTING app. Do not redesign it. Match it exactly.

## Context

- Project root: **`/root/capitol-flow`**
- App: `web/index.html`, `web/styles.css`, `web/app.js` (vanilla JS, hash routing, no framework)
- Stock detail page = route `#/stock/TICKER`. Current sections in order:
  header (ticker + price) → candlestick+Bollinger chart (DAILY/HOURLY) → **THE TRADES**
  → **THE NEWS** → **THE BASICS** (plain-English fundamentals).
- Data bundles load from `web/data/*.json` with inline `window.__CAPITOL_*__` fallbacks.
- **Design language (keep it):** dark near-black canvas, flat elevated cards, hairline borders,
  oversized condensed display numerals, tight uppercase micro-labels with wide letter-spacing,
  green (#00C805-ish) = calls/buy, red (#FF5000-ish) = puts/sell. Nike × Robinhood. No
  gradients, no glows, no drop shadows.

## New data — already generated

A new file **`data/options.json`** (copied to `web/data/options.json`, plus inline fallback
`web/data/options.js` → `window.__CAPITOL_OPTIONS__`).

```jsonc
{
  "AAPL": {
    "underlying": 356.27,
    "expiry": "2026-11-27",      // the most-active expiry in the window
    "dte": 12,
    "call_oi": 52838,            // total open interest on calls, that expiry
    "put_oi": 46744,
    "pc_ratio": 0.88,            // put/call open-interest ratio
    "top_calls": [
      { "strike": 365.0, "oi": 11578, "volume": 2383, "price": 2.1,
        "bid": 2.05, "ask": 2.15, "iv": 20.2,
        "symbol": "AAPL261127C365.0",
        "tv_url": "https://www.tradingview.com/symbols/OPRA-AAPL261127C365.0/" }
    ],
    "top_puts": [ /* same shape */ ],
    "expiries": ["2026-11-16", "..."]
  }
}
```

Not every ticker has options — **skip the section entirely if the ticker has no entry**
(and never throw).

## What to build

Add an **OPTIONS** section (title it that, with a short subtitle) placed **after THE TRADES
and before THE NEWS** — it reads as part of "market positioning".

### Layout
Two side-by-side columns: **CALLS** (green accent) and **PUTS** (red accent).
Stack them vertically at 390px.

### Per row (one per strike)
1. **Strike** — bold, e.g. `$365`.
2. **A horizontal bar** whose width is `oi` scaled against the **largest `oi` in that same
   column** (so the top strike fills the track). Flat single-colour bar (green for calls,
   red for puts), no gradient.
3. **Open interest** value, human-readable (`11,578` or `11.6K`).
4. **The contract price**, clearly shown as a price — `$2.10` — with a muted label
   (e.g. `last` or `mid`). This is the price of that option contract.
5. **A link to the TradingView chart for that exact contract** — use `tv_url`, open in a new
   tab, `rel="noopener noreferrer"`. Label it plainly, e.g. `TradingView ↗` or `Chart ↗`.
   Must be a real anchor so it's keyboard-accessible.

### Header strip (above the two columns)
- The **expiry date** and **DTE** ("Nov 27 · 12 days").
- **Total call OI vs total put OI**, and the **put/call ratio** shown as a labelled figure.
- One plain sentence in the app's voice explaining the idea, e.g.
  *"Open interest is how many contracts are still open at each strike. Big piles often act
  like walls — prices tend to stall there."*

### Rules
- **Calls and puts get equal visual weight.** Neither column may look like an afterthought.
- Keep it legible at **390px**: strike + bar + OI + price must fit. If needed, drop the
  `volume` and `IV` detail at narrow widths rather than shrinking the bar.
- If `top_calls` / `top_puts` are both empty, render nothing.
- Accessibility: each row readable as one phrase, e.g.
  *"$365 call, open interest 11,578, price $2.10"*; the TradingView link needs a
  descriptive `aria-label` naming the contract.

### Do not break
The chart, DAILY/HOURLY toggle, THE TRADES, THE NEWS, THE BASICS, the dashboard — all must
keep working.

## Definition of done

- `node --check web/app.js` passes.
- Local preview of `#/stock/AAPL` shows the OPTIONS section with a CALLS column and a PUTS
  column, bars scaled by open interest, a price per contract, and working TradingView links.
- `#/stock/NVDA` shows NVDA's own contracts.
- A ticker with no options data renders cleanly.
- No console errors; correct at 390px and 1440px.

Be decisive. Don't ask questions.
