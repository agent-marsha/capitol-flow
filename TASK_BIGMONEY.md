# TASK — Add a "where the big money went" visualization to Capitol Flow

You are extending an EXISTING app. Do not redesign it. Match it exactly.

## Context

- Project root: **`/root/capitol-flow`**
- App: `web/index.html`, `web/styles.css`, `web/app.js` (vanilla JS, hash routing, no framework)
- Main data: `web/data/app_data.json` (+ inline fallback `web/data/app_data.js` → `window.__CAPITOL_DATA__`)
- The dashboard currently has four regions in order: the hero, **CLUSTER SIGNALS** ("SAME STOCK.
  MANY HANDS."), **BIG MONEY** ("$100K AND UP" — currently a list of large SELLS and BUYS
  side by side), and **THE FEED**.
- **Design language — match it:** dark near-black canvas, flat elevated cards, hairline borders,
  oversized condensed display numerals, tight uppercase micro-labels with wide letter-spacing,
  green (`#00C805`-ish) = buy, red (`#FF5000`-ish) = sell. Nike × Robinhood. No gradients, no
  glows, no drop shadows, no rounded-everything.

## New data — already in the bundle

`app_data.json` now has a **`big_money`** array (present in the file you must read):

```jsonc
"big_money": [
  { "ticker": "MSFT", "asset": "Microsoft Corporation - Common Stock",
    "buy_est": 270000, "sell_est": 241000, "total_est": 511000, "net_est": 29000,
    "n_buy": 2, "n_sell": 1, "n_politicians": 3,
    "politicians": ["Hon. A", "Hon. B", "Hon. C"],
    "last_date": "2026-10-02" },
  ...
]
```

- Sorted by `total_est` descending already.
- **`*_est` values are ESTIMATES.** Disclosure amounts are only ever reported as ranges
  (e.g. "$500,001 – $1,000,000"), so the pipeline uses the range midpoint. **The UI must say
  the figures are estimated** — never present them as exact.

## What to build

Inside (or immediately after) the existing **BIG MONEY** section, add a visualization:
a **horizontally-scaled bar chart, one row per stock**.

Title it plainly, e.g. **"WHERE THE BIG MONEY WENT"**, with a one-line subtitle like
*"Estimated dollars from trades of $100,000 or more. Sells and buys, by stock."*

### Each row
1. **Ticker** — bold, condensed display type (same treatment as elsewhere).
2. **A single horizontal bar** representing `total_est`, scaled against the largest
   `total_est` in the set (the biggest row spans the full track).
   - The bar is **split**: green segment = `buy_est`, red segment = `sell_est`,
     proportional within that row's own total. Order: buys then sells.
   - If a row has only buys or only sells, the bar is a single solid colour.
3. **The total**, right-aligned in a human-readable form (`$511K`, `$1.2M`, `$25M`).
4. A small **"N buys · M sells"** micro-label under or beside the ticker.

### Behaviour
- Show the **top 15** rows by default; a **"SHOW ALL"** control reveals the rest.
- **Clicking a row opens that stock's detail page** (`#/stock/TICKER`) — same as the
  ticker buttons elsewhere in the app.
- Bars should animate their width in subtly on render (CSS transition, ≤400ms). No bounce.

### Rules that still apply
- **Sells get equal visual weight to buys.** Never let the chart read as "buys only".
  **However — be honest about the real data:** in the current dataset 22 of the 25 large
  BUYS are fixed-income (bonds, treasuries, munis, funds) and have no stock ticker, so this
  *per-stock* chart is legitimately sell-heavy. Do **not** fake balance. Instead add one
  quiet line under the chart, e.g. *"Most large buys by politicians are bonds and funds,
  not single stocks — so this chart is mostly sales."* That observation is itself the point.
- Keep it legible at **390px** wide: ticker + bar + value must fit; if space is tight,
  drop the micro-label rather than shrinking the bar into illegibility.
- Accessible: each row is a real focusable element with an `aria-label` naming the ticker,
  the estimated total, and the buy/sell split. Provide a text fallback for screen readers.

### Notes
- If `big_money` is missing or empty (e.g. an older cached bundle), render nothing and
  **do not throw**.
- Do not change any other section. Existing cluster signals, the big-money lists, the feed,
  the stock pages (chart, trades, news, THE BASICS) must all keep working.

## Definition of done

- `node --check web/app.js` passes.
- Loading the dashboard locally shows the new chart with rows ranked by size, correct
  green/red split, readable values, and the "estimated" caveat visible.
- Clicking a row navigates to that stock's page.
- No console errors; the rest of the dashboard is unchanged at 390px and 1440px.
- Regenerate `web/data/app_data.json` is **not** your job (it is copied in for you); but if
  you touch the inline `web/data/app_data.js`, keep it in sync with the JSON.

Be decisive. Don't ask questions.
