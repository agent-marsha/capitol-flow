# TASK — Let option-heavy tickers open their own page, even with no congressional trades

You are extending an EXISTING app. Do not redesign it. Match it exactly.

## The goal

The dashboard's **OPTION OPEN INTEREST** board ("Where the options are.") currently splits
its rows by `tracked`:

- `tracked: true`  → `#/stock/TICKER` (this app's own stock page)
- `tracked: false` → the TradingView symbol page, **new tab**

**Change it so every row opens the app's own page.** Even a ticker with **no congressional
trades and no price history** should open a real screen showing its **specific call and put
option strikes** — because that data already exists for it.

## Why this works

Options data covers **130 tickers**; prices cover 120; trades fewer still. So tickers like
**SPY, HYG, EEM, QQQ, TSLA, PLTR** already have full option chains (10 calls + 10 puts, each
with strikes, open interest, prices and expiry) — they simply have no page to show them on.

`#/stock/INTC` proves the pattern works (chart + options). This extends the same page to
tickers with no prices and no trades.

## What to change

### 1. `renderDetail` — the early-return guard (around line 867)
Today:
```js
if (!trades.length && !daily.length) { … "No trades or prices found for TK." … return; }
```
It must also render when the ticker **has options data**. Options arrive via `loadOptions()`
(a promise, see ~line 114) — make sure the render path has them available; the existing
detail page already awaits them for tickers like INTC, so follow that same pattern.

Keep the existing empty state for a ticker with **nothing at all** (no trades, no prices, no
options) — that's still a real case for a bad URL.

### 2. On an options-only page (no trades, no prices)
Render:
- **Header** — ticker + the company profile line when present (SPY/HYG have no sector; omit it rather than printing anything)
- **Chart slot** — the existing no-price fallback panel (already built: *"No price history for this ticker yet."* + `Yahoo Finance ↗` / `TradingView ↗`). Do not invent a chart.
- **THE OPTIONS section** — the full existing component: most-active expiry, call/put OI totals, put/call ratio with its reading, 10 CALLS and 10 PUTS rows with strikes, OI, contract price and their TradingView links.

**Omit** (no heading, no empty shell):
- THE TRADES — there are none
- THE NEWS — there are none
- The BASICS / fundamentals section — none for these
- The hero **stats row** (POLITICIANS / SELLS / BUYS / LAST TRADE). Do not show zeros.
  Instead put **one muted line** in its place, e.g.
  *"No congressional trades disclosed on this ticker in the current window."* — so it's
  obvious *why* the page looks different, not broken.

### 3. The board's row links
In `oiRow(r)` (~line 796), make **every** row link to `'#/stock/' + encodeURIComponent(r.ticker)`.
The `tracked === false` TradingView branch goes away — those outbound links now live on the
destination page's fallback panel, where they belong.

Keep the `aria-label` accurate for the new destination, and keep the existing
`NO CONGRESSIONAL ACTIVITY` muted marker on rows with `n_politicians === 0` — it's still true
and still useful.

## Definition of done
- `node --check web/app.js` passes.
- `#/stock/SPY`, `#/stock/HYG`, `#/stock/EEM` each render: header, the no-price fallback panel,
  and a **full OPTIONS section with 10 calls and 10 puts**. No trades section, no news,
  no zeroed stats row, and the muted "no congressional trades" line.
- `#/stock/NVDA` and `#/stock/INTC` are **completely unchanged**.
- Every row on the options board navigates to `#/stock/TICKER`; no row opens TradingView
  directly any more.
- A nonsense ticker (e.g. `#/stock/ZZZZ`) still shows the old empty state.
- Correct at 390px and 1440px; no console errors; nothing else regresses.

Be decisive. Don't ask questions.
