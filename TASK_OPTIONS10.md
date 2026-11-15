# TASK — Options section: show the TOP 10 per side, and show each contract's expiration date

You are extending an EXISTING app. Do not redesign it. Match it exactly.

## Context

- Project root: **`/root/capitol-flow`**
- `web/app.js` + `web/styles.css` (vanilla JS), stock page route `#/stock/TICKER`
- The page already has an **OPTIONS** section (titled "OPTIONS" / "MARKET POSITIONING") sitting
  between **THE TRADES** and **THE NEWS**. It renders a header strip (expiry + DTE, call vs
  put open interest, put/call ratio) and two columns, **CALLS** (green) and **PUTS** (red),
  each row showing strike, an OI-scaled bar, the open interest, a price, and a `TRADINGVIEW ↗`
  link. Keep that structure and the design language exactly as-is.

## What changed in the data (`data/options.json`)

**Two changes you must handle:**

1. **Lists are now up to 10 rows per side** (was 4). `top_calls` / `top_puts` may hold **10**
   entries. Do not truncate them.

2. **Open interest is now aggregated BY STRIKE across several expirations**, so each row
   carries **its own expiration date** (the one holding most of that strike's open interest).
   The old single `expiry` at the top level still exists, but it is now only *the most-active
   expiry* used for the header — **rows can and do have different expirations.**

New shape:

```jsonc
{
  "AAPL": {
    "underlying": 356.27,
    "expiry": "2026-12-18",              // most-active expiry (header only)
    "dte": 33,
    "expiries_considered": ["2026-11-23","2026-11-25","2026-11-27","2026-12-04","2026-12-11","2026-12-18"],
    "call_oi": 551368,                   // totals across ALL considered expiries
    "put_oi": 552041,
    "pc_ratio": 1.0,
    "top_calls": [
      { "strike": 360.0, "oi": 50326,          // oi = sum across expirations
        "expiry": "2026-12-18", "dte": 33,     // <-- this row's dominant expiration
        "volume": 1234, "price": 8.30, "price_basis": "last",
        "bid": 8.2, "ask": 8.4, "iv": 21.3,
        "symbol": "AAPL261218C360.0",
        "tv_url": "https://www.tradingview.com/symbols/OPRA-AAPL261218C360.0/",
        "parts": [ {"expiry":"2026-12-18","oi":27858},
                   {"expiry":"2026-11-23","oi":16622},
                   {"expiry":"2026-11-27","oi":2512} ] }   // oi split by expiry,
                                                          // descending
    ],
    "top_puts": [ /* same shape */ ]
  }
}
```

## What to build

### 1. Show up to 10 rows per column
Nothing else changes about a row: strike, OI-scaled bar (still scaled against the largest `oi`
**in that same column**), open interest, price, `TRADINGVIEW ↗` link. Just make sure 10 rows
render and the section stays readable (tighten vertical padding if needed — but do **not**
shrink type below what's already used, and never let the bar become a sliver).

### 2. Show the expiration date on every row
Add the row's **`expiry`** to each row as a small muted date, e.g. `DEC 18`. Format it as a
short human date (`DEC 18`, or `DEC 18 '26` if the year is not the current year).

- It must be clear the date belongs to that contract.
- Keep it visually quiet — a micro-label, not a headline — but present on **every** row.
- The CALLS and PUTS columns must both show it.

### 3. Header strip — minor
- The header's single expiry figure should be labelled so it does not read as if it applies to
  every row. Make it say it is the **most active** expiry, e.g.
  `MOST ACTIVE · DEC 18` (keep the DTE under it).
- Add a short muted line noting the totals cover the nearby expirations, e.g.
  *"Totals cover the next few expirations (NOV 23 – DEC 18). Each row shows its own expiration."*
  Derive the range from `expiries_considered` (min → max), formatted human-readably.
- The existing explanatory sentence about open interest walls should stay.

### 4. Keep working
- Rows are still fine to sort by strike or by OI — leave whatever order is currently used.
- If `expiry` is missing on a row, render the row without a date rather than showing `undefined`.
- Everything else (chart, THE TRADES, THE NEWS, THE BASICS, dashboard) unchanged.
- Accessibility: include the row's expiration in the row's readable phrase, e.g.
  *"$360 call expiring December 18, open interest 50,326, price $8.30"*.

## Definition of done

- `node --check web/app.js` passes.
- Local `#/stock/AAPL` shows **up to 10** call rows and **10** put rows, each with a short
  expiration date, a bar, an OI figure, a price and a TradingView link.
- The header reads as the *most active* expiry, not every row's expiry.
- No console errors; still correct at 390px (columns stacked) and 1440px.

Be decisive. Don't ask questions.
