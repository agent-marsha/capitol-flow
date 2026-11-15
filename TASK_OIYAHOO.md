# TASK — Add a Yahoo Finance link to each row of the OPTION OPEN INTEREST board

You are extending an EXISTING app. Do not redesign it. Match it exactly.

## Context

- Project root: **`/root/capitol-flow`**, files `web/app.js` + `web/styles.css`
- The dashboard section is **"Where the options are."** (`#oi-rows`), rendered by
  `oiRows()` and `oiRow(r)` in `app.js` (~lines 738–820).
- `oiRow(r)` currently returns `'<li><a class="oi-row" href=…>…</a></li>'` — the whole row
  **is an anchor**, and its destination depends on `r.tracked`:
  - `tracked === true` → `#/stock/TICKER` (this app's own stock page)
  - `tracked === false` → the TradingView symbol page, new tab

## ⚠️ The HTML constraint that makes this non-trivial

**You cannot nest an `<a>` inside the row's existing `<a>` — that is invalid HTML and
browsers will break the markup or the click behaviour.** So `oiRow` must be restructured so
the Yahoo Finance link is a **sibling** of the row link (e.g. wrap the `<li>` contents in a
positioned container and place the Yahoo anchor alongside it), not a descendant.

Whatever you choose, verify in the browser that:
- the row still navigates correctly to its existing destination
- the Yahoo link navigates to Yahoo and does **not** trigger the row's navigation
- the markup is not nested-anchor invalid

## What to add

A **Yahoo Finance** link on every row, pointing at:

```
https://finance.yahoo.com/quote/<TICKER>/
```

(Include the trailing slash. Ticker is `r.ticker`, URL-encoded.)

Open it in a **new tab** with `rel="noopener"` and an accessible label such as
*"Open SPY on Yahoo Finance, new tab"*.

### Why an https link and not a custom scheme
**Do not use `yfinance://` or `yahoo-finance://`.** Those custom schemes are undocumented
and unreliable across app versions. Yahoo registers the `finance.yahoo.com` domain for
**Universal Links (iOS) / App Links (Android)**, so this https URL **opens the Yahoo
Finance app automatically on a phone with the app installed**, and falls back to the web
page everywhere else. That is the correct, robust way to "route to the Yahoo Finance app".

### Design
- Keep it consistent with the app's existing small link treatment (see how the OPTIONS
  section on the stock page renders its `TRADINGVIEW ↗` links — match that language).
- Visually secondary — it must not compete with the ticker, the OI figure, or the
  politician badge. No new accent colour, no gradients/glows/shadows.
- On mobile (390px) the row already stacks; make sure the Yahoo link still fits calmly and
  doesn't collide with the badge or the split bar. No sideways scroll.
- Keep the existing screen-reader `aria-label` on the row describing its own figures; the
  Yahoo link gets its own separate label.

## Definition of done
- `node --check web/app.js` passes.
- Every row shows a working Yahoo Finance link → `https://finance.yahoo.com/quote/<TICKER>/`.
- Clicking a Yahoo link does **not** also fire the row's own navigation.
- A `tracked: true` row (NVDA) still goes to `#/stock/NVDA`; a `tracked: false` row (SPY)
  still goes to TradingView.
- No nested-anchor markup; no console errors.
- Correct at 390px and 1440px; nothing else regresses.

Be decisive. Don't ask questions.
