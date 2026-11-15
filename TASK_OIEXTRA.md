# TASK — Let the OPTION OPEN INTEREST board show stocks Congress never traded

You are extending an EXISTING app. Do not redesign it. Match it exactly.

## What changed in the data

`D.oi_board` used to contain only tickers Congress had traded (58 rows, every one with a
politician badge). It now contains the **full high-open-interest universe** — index ETFs
(SPY, QQQ, IWM…), mega caps, and retail favourites (TSLA, PLTR, GME, SOFI…) — whether or
not Congress touched them.

Two new/changed fields per row:

```jsonc
{
  "ticker": "SPY",
  "sector": null,            // may be null for tickers with no SEC SIC match
  "call_oi": 4821000, "put_oi": 7112000, "total_oi": 11933000,
  "pc_ratio": 1.48,
  "expiry": "2026-12-18", "dte": 33,
  "adv": 78000000,
  "oi_days_of_volume": 15.3,
  "n_trades": 0,             // 0 for stocks Congress never traded
  "n_politicians": 0,
  "tracked": false           // NEW. true = this app has a stock page for it
}
```

`tracked` is `true` when the app has a full stock page (price history, trades, options,
fundamentals). `false` means **there is no `#/stock/TICKER` page** — the app holds no price
history or trades for it.

## What to build

**1. Row links must respect `tracked`.** This is the important fix. A `tracked: false` row
must NOT link to `#/stock/TICKER` — that page would be empty and look broken.

- `tracked: true` → link to `#/stock/TICKER`, exactly as now
- `tracked: false` → link to the underlying's TradingView page
  (`https://www.tradingview.com/symbols/TICKER/`), opening in a new tab with
  `rel="noopener"` and an accessible label like
  *"Open SPY on TradingView, new tab"*

**2. Distinguish the two kinds of row, quietly.** A row with no congressional activity
should be visibly *not* part of the political signal — but must not look disabled or broken:
- Rows with `n_politicians > 0`: unchanged — show the existing politician badge
- Rows with `n_politicians == 0`: no politician badge; instead show a small muted
  marker, e.g. `NO CONGRESSIONAL ACTIVITY`, in the same muted style as the sector text.
  Keep it understated — these rows are still fully readable and clickable.

**3. Sort is unchanged** — `BY SIZE` uses `total_oi`, `BY LOADING` uses
`oi_days_of_volume`, both descending. Confirm both still work with the larger set, and
that rows whose `oi_days_of_volume` is null still sink below the sorted ones rather than
appearing as `0`.

**4. Handle `sector: null`** by omitting the sector text (don't print "null" or "Unknown").
Same for any other missing field.

**5. Update the section's explanatory line** so it's accurate now, e.g.
*"How much is still riding on each stock in the options market — including the biggest
option markets Congress hasn't touched."* Keep the existing note that open interest is
positioning, not a direction forecast.

## Design language (keep it)
Dark near-black canvas, flat cards, hairline borders, tight uppercase micro-labels with wide
letter-spacing, green = calls, red = puts, amber = committee oversight, blue = company
insiders. Nike × Robinhood. No gradients, no glows, no shadows. No new accent colour.

## Definition of done
- `node --check web/app.js` passes.
- `BY SIZE` and `BY LOADING` both re-sort correctly across the bigger set.
- A `tracked: true` row (e.g. NVDA) navigates to its stock page.
- A `tracked: false` row (e.g. SPY) opens TradingView in a new tab and does NOT navigate
  to an empty stock page.
- Rows with no congressional activity show the muted marker and no politician badge.
- Correct at 390px and 1440px; nothing else regresses; no console errors.

Be decisive. Don't ask questions.
