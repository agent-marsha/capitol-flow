# TASK — Add a "Fundamentals" section to each stock page in Capitol Flow

You are extending an EXISTING app. Do not redesign it. Match what is there.

## Context

- Project root: **`/root/capitol-flow`**
- Existing app: `web/index.html`, `web/styles.css`, `web/app.js` (vanilla JS + hash routing)
- The stock detail page is route `#/stock/TICKER`, rendered by `app.js`. It already has:
  a header (ticker + price), a candlestick + Bollinger chart with a DAILY/HOURLY toggle,
  "THE TRADES", and "THE NEWS".
- Existing data bundle: `web/data/app_data.json` (+ inline `web/data/app_data.js` fallback)
- **Design language (do not break it):** dark near-black canvas, flat surfaces, hairline
  borders, single green (buy) / red (sell) accents, oversized condensed display numerals,
  tight uppercase micro-labels with wide letter-spacing. Nike × Robinhood. No gradients,
  no glows, no drop shadows.

## New data you must render

A new file: **`data/fundamentals.json`** (a copy will also live at `web/data/fundamentals.json`,
plus an inline fallback `web/data/fundamentals.js` — see "Data loading" below).

Shape:

```jsonc
{
  "AAPL": {
    "name": "Apple",
    "cik": "0000320193",
    "years": ["2023","2024","2025","2026"],
    "series": {                       // chart-ready, ascending by year
      "revenue":     [ {"x":"2023","y":383285000000}, ... ],
      "net_income":  [ ... ], "gross_profit":[ ... ], "assets":[ ... ],
      "liabilities":[ ... ], "cash":[ ... ], "debt":[ ... ], "op_cash":[ ... ]
    },
    "facts": { "revenue": 478834000000, "net_income": 132175000000, ... },
    "cards": [
      { "id":"revenue", "emoji":"🧾", "headline":"How much money it made",
        "text":"Apple sold 478.8 billion worth of things last year. That is up 15 out of 100 from the year before.",
        "chart": { "type":"bars", "label":"Money it made each year", "unit":"money",
                   "points":[ {"x":"2023","y":...}, ... ] } },
      { "id":"margin", ..., "chart": { "type":"split", "label":"...",
                   "points":[{"x":"Kept","y":49.0},{"x":"Cost to make","y":51.0}] } },
      { "id":"owes", ..., "chart": { "type":"bars2", "label":"Owns vs owes",
                   "points":[{"x":"Owns","y":...},{"x":"Owes","y":...},{"x":"Really left","y":...}] } }
    ],
    "reading_grade": 1.5
  }
}
```

Source is SEC EDGAR XBRL (official 10-K figures). Not every company has every field —
**build each card independently and skip any key that is missing.**

## What to build

On the stock detail page (`#/stock/TICKER`), add a section — place it **after the chart and
"THE TRADES", before or after "THE NEWS"** (your call; it should feel like part of the flow).
Title it something plain, e.g. **"THE BASICS"** or **"IN PLAIN ENGLISH"**, with a
one-line subtitle noting it comes from the company's official SEC filings.

For each `card`:
1. **The emoji + headline** as a small label.
2. **The `text` exactly as given** — it is already written at a 4th-grade reading level.
   **Do not rewrite, shorten, or "improve" it.** Display it in a comfortable reading size
   (larger than the micro-labels — this is the point of the feature).
3. **The visualization** described by `chart.type`:

### Visualization specs (keep them SIMPLE — the audience includes kids)

- **`bars`** — a small column chart, one bar per `point`, `x` = year label under each bar,
  `y` = value. Show the value above each bar, formatted human-readable
  (e.g. `$478.8B`, `$132.2B`). Flat single-colour bars (use the accent green at a low
  opacity, or a neutral). No axis clutter, no gridlines, no tooltips needed.
- **`bars2`** — 2–3 labelled bars showing a comparison (Owns vs Owes, Bank vs Owes).
  Each bar labelled on the left with its `x`, value on the right. Colour the
  "good" bar (more) green and the "worse" bar red **only when that reading is
  unambiguous** — otherwise keep them neutral. Ties/near-zero: neutral.
- **`split`** — a single horizontal bar split into two proportional segments
  (e.g. "Kept" vs "Cost to make"), each segment labelled with its `x` and its `y` as a
  percentage. This is a simple 100%-stacked bar, not a donut.

Implement these in **plain CSS/SVG** inside `app.js` — no new chart library. They must be
crisp at 390px wide and must not overflow.

## Data loading

`app.js` currently loads the main bundle. Add a **second** fetch for `data/fundamentals.json`
that:
- resolves to an empty object on any failure, and **never blocks or breaks the page**
  (if it's missing, simply don't render the section — or render a one-line "not available"),
- also supports `window.__CAPITOL_FUNDAMENTALS__` from `data/fundamentals.js` for `file://`,
- is looked up by ticker; if the ticker has no entry, render nothing for this section.

Keep the hash-router behaviour intact: navigating between tickers must re-render this
section correctly (no stale cards from the previous ticker).

## Definition of done

- `node --check web/app.js` passes.
- Loading the site locally and opening `#/stock/AAPL` shows the new section with **5 cards**,
  each with its reading-level sentence and its visualization rendered.
- `#/stock/NVDA` shows NVDA's own numbers (not AAPL's).
- A ticker with no fundamentals entry (e.g. a fund/ETF ticker) renders cleanly with no errors.
- No console errors. Existing sections (chart, trades, news) still work.

## Also do

- Generate `web/data/fundamentals.js` (the inline fallback) and copy `data/fundamentals.json`
  → `web/data/fundamentals.json`.
- Update `.github/workflows/refresh.yml` to run `pipeline/fundamentals.py` and copy the
  outputs into `web/data/` alongside the existing data steps.
- Add a short note to `web/README.md` about the fundamentals section.

Be decisive. Don't ask questions.
