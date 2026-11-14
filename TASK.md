# TASK — Build "Capitol Flow": a politician trading-intelligence web app

You are building a **static web app** that surfaces recent stock trades by US politicians
and key government figures, so a user can spot moves that might telegraph future stock
moves. It must run as a **plain static site on GitHub Pages** — no server, no build step,
no API keys at runtime.

## Where things are

- Project root: `/root/capitol-flow`
- **Data bundle (read this, do not invent data):** `/root/capitol-flow/data/app_data.json`
- Your output goes in: `/root/capitol-flow/web/` — entry point must be `web/index.html`

Read `data/app_data.json` FIRST and build the UI around its real shape. Inspect it with
`python3 -c "import json;d=json.load(open('data/app_data.json'));print(list(d));print(d['counts'])"`.

### Data bundle shape (authoritative)

```jsonc
{
  "generated": "ISO8601",
  "source": "US House Clerk — Periodic Transaction Reports (official)",
  "window_days": 14,
  "large_threshold": 100000,
  "very_large_threshold": 500000,
  "counts": { "trades": N, "sales": N, "buys": N, "tickers": N, "clusters": N, "large": N },
  "trades": [            // ALREADY sorted: all sales first (newest→oldest), then buys
    { "id":"T00001", "politician":"Hon. ...", "chamber":"House", "state_district":"TX25",
      "asset_raw":"Apple Inc. (AAPL) [ST]", "ticker":"AAPL",
      "txn_type":"P|S", "txn_type_label":"Purchase|Sale",
      "txn_date":"YYYY-MM-DD", "notification_date":"YYYY-MM-DD",
      "amount_low":1001, "amount_high":15000, "amount_label":"$1,001 - $15,000",
      "direction":"buy|sell", "is_large":true, "is_very_large":false,
      "cluster_ids":["AAPL:3p"], "source_url":"https://disclosures-clerk.house.gov/...pdf" }
  ],
  "clusters": [ { "ticker":"AAPL", "politicians":["Hon. A","Hon. B"], "n_politicians":3,
                  "n_trades":5, "window_start":"...", "window_end":"...",
                  "buys":3, "sells":2, "trades":["T00001","T00007"] } ],
  "prices": { "AAPL": { "daily":[ {"t":"YYYY-MM-DD","o":..,"h":..,"l":..,"c":..,"v":..} ],
                         "hourly":[ {"t":<epoch_seconds>,"o":..,"h":..,"l":..,"c":..,"v":..} ] } },
  "news":   { "AAPL": [ {"title":"...","url":"...","publisher":"...","date":"YYYY-MM-DD"} ] }
}
```

Not every trade has a `ticker` (treasuries, munis, funds). Handle `null` tickers gracefully —
show them in the feed but disable the chart link.

## The 8 hard requirements

1. **Sales are sorted most-recent-first.** The `trades` array already arrives in that order;
   the default view must lead with sales.
2. **Large volume is highlighted.** Visually flag `is_large` (>= $100k) and especially
   `is_very_large` (>= $500k) with a distinct badge/treatment that reads instantly in a feed.
3. **Multi-politician clusters are highlighted.** When >= 2 distinct politicians traded the
   same ticker inside the window, surface it prominently — the cluster list is the app's
   "signal" and should be the most visually loud element on the dashboard.
4. **Large sales carry equal weight to large buys.** Do NOT let buys dominate the layout.
   Sells get the same size, prominence, and highlight treatment as buys.
5. **Per-stock candlestick chart with Bollinger Bands.** Compute Bollinger Bands (SMA-20,
   ±2σ) **client-side** from the OHLC arrays.
6. **Daily AND hourly candlestick timeframes**, with a toggle. Use the `daily` and `hourly`
   arrays (`hourly.t` is epoch seconds; convert appropriately for the chart library).
7. **News around the trade date.** On a stock's detail view, show the `news` articles,
   emphasising ones near the politician's trade date(s). Link out to the source.
8. **Detail view ties it together:** ticker → who traded it, when, how much, and the news
   from around that time.

## Design — inspired by **Nike** and **Robinhood**

This is the most important qualitative bar. Read it twice.

- **Nike:** bold, athletic, high-contrast; oversized condensed numerals for the money and
  dates; tight uppercase micro-labels with wide letter-spacing; generous negative space;
  almost no chrome. The data IS the design.
- **Robinhood:** clean dark-mode fintech; mobile-first cards; green = buy / red = sell used
  consistently and confidently; rounded, calm surfaces; dense but airy; fast to scan.

Concretely:
- **Dark theme.** Near-black canvas (`#0B0B0C`), elevated card surfaces (`#151517`),
  hairline borders (`#242427`), high-contrast text.
- **Accent:** a single confident green for buys (`#00C805`-ish) and red for sells
  (`#FF5000`-ish). These are the only strong colours on the page.
- **Type:** a bold condensed display face for headline numbers (system fallback fine —
  e.g. `-apple-system, "Helvetica Neue", Arial Narrow`), and a clean sans for body.
- **Hierarchy:** the **cluster signals** are the hero. Then the trade feed. Then per-stock detail.
- **No** gradients, no glassmorphism, no glows, no drop-shadow soup, no rounded-everything.
  Flat, sharp, confident. Restraint = the point.
- Mobile-first responsive; must look right at 390px and at 1440px.

**Strip any corporate/university branding** — this is a standalone consumer product.
Pick a clean product name for the header (suggest: **Capitol Flow**).

## Technical constraints

- **Vanilla HTML/CSS/JS only.** No React/Vue, no bundler, no npm install. The site must
  work by opening `index.html` (and identically on GitHub Pages).
- **Charts:** use **lightweight-charts** from a CDN
  (`https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js`).
  It handles candlesticks and timeframes well. Overlay Bollinger Bands as **line series**
  (upper/mid/lower) computed in JS.
- **Data loading:** `fetch('data/app_data.json')`. For local `file://` preview this is
  blocked by CORS, so ALSO support an inline fallback: if fetch fails, read a global
  `window.__CAPITOL_DATA__` that you generate into `web/data/app_data.js`
  (a 1-line `window.__CAPITOL_DATA__ = {...}` copy of the JSON). Reference
  `data/app_data.js` via a `<script>` tag so `file://` works too.
- Relative paths only (`data/...`, `assets/...`) so GitHub Pages subpath hosting works.
- No external API calls at runtime. No keys. No tracking.
- Accessible: real contrast, keyboard-focusable controls, `aria-label`s on icons/buttons.

## Deliverables

1. `web/index.html` — the app (self-contained shell is fine)
2. `web/styles.css` and `web/app.js` (split is preferred and easier to review)
3. `web/data/app_data.js` — the inline data fallback (generate from the JSON)
4. `web/README.md` — how to preview locally

## Definition of done

- `python3 -m http.server` in `/root/capitol-flow`, opening `/web/` shows the dashboard with:
  the cluster signals rendered, the trade feed leading with sales, large trades badged,
  and clicking a ticker opening a candlestick + Bollinger chart with a working
  Daily/Hourly toggle and the news list beneath it.
- Validate the JS parses: `node --check web/app.js` (node is available).
- No console errors on load.

Build it. Be decisive about design; don't ask questions — if something is ambiguous, pick
the choice that best serves "spot politician moves that telegraph future stock moves."
