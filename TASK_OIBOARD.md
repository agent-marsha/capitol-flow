# TASK — Add an "OPTION OPEN INTEREST" board to the dashboard

You are extending an EXISTING app. Do not redesign it. Match it exactly.

## Context

- Project root: **`/root/capitol-flow`**, `web/app.js` (vanilla JS, hash routing) + `web/styles.css`
- The dashboard (`renderHome`) already has, in order: hero stats, **CLUSTER SIGNALS**
  ("SAME STOCK. MANY HANDS."), **COMMITTEE OVERSIGHT** ("THEY OVERSEE IT."),
  **COMPANY INSIDERS** ("THEY RAN IT."), **BIG MONEY**, **WHERE THE BIG MONEY WENT**, **THE FEED**.
- Add this new section **after "WHERE THE BIG MONEY WENT" and before "THE FEED"**.

## New data — already in the bundle (`D.oi_board`)

An array already sorted by `total_oi` descending, one entry per tracked stock that has
listed options (58 entries):

```jsonc
{
  "ticker": "NVDA",
  "sector": "Technology",
  "call_oi": 1845000,          // open call contracts
  "put_oi": 2115855,           // open put contracts
  "total_oi": 3960855,
  "pc_ratio": 0.87,            // put/call; <1 call-heavy, >1 put-heavy
  "expiry": "2026-12-18",      // most active expiry
  "dte": 33,
  "adv": 172000000,            // 30-day avg daily SHARE volume
  "oi_days_of_volume": 2.3,    // (total_oi * 100) / adv  — open interest expressed as
                               // days of the stock's own typical volume. null if unknown
  "n_trades": 13,              // politician trades on this ticker
  "n_politicians": 7           // distinct politicians who traded it
}
```

## What to build

### Section
- Micro-label: **`OPTION OPEN INTEREST`**
- Heading (display style, like the others): **"WHERE THE OPTIONS ARE."**
- One explanatory sentence, plain: *"How much is still riding on each stock in the options market. The biggest piles often act like price walls."*

### Two ways to sort (the important part)
Add a small two-state control — reuse the existing chip style:
- **`BY SIZE`** (default) — sort by `total_oi` descending
- **`BY LOADING`** — sort by `oi_days_of_volume` descending

**Why:** absolute open interest mostly just measures market cap — Apple and Nvidia are
always the biggest. `oi_days_of_volume` normalises it: how many days of the stock's *own*
trading the open option interest represents. On this data that surfaces **VSAT (7.8 days)**
and **COST (3.3 days)**, which the size ranking buries. Say this in a short muted line under
the control, e.g. *"By size favours the megacaps; by loading shows which stocks are unusually option-heavy for how much they trade."*

### Rows (top ~10, with a "show all N" expander)
Each row shows:
- **Ticker** (clickable → `#/stock/TICKER`) and its sector as muted text
- **Total open interest**, human-readable (`3.9M`, `1.1M`, `729K`)
- A **call/put split bar** — one bar, green segment = calls, red segment = puts,
  proportional to `call_oi` / `put_oi`. Label the ends `▲ calls` / `▼ puts`.
- **Put/call ratio** with a one-word reading: `<0.7` "call-heavy", `0.7–1.3` "balanced",
  `>1.3` "put-heavy"
- **Days of volume** (the loading figure) — if `oi_days_of_volume` is null, show `—`
- **Politician activity badge** when `n_politicians > 0`: e.g.
  `⚑ 7 POLITICIANS · 13 TRADES` — this is the cross-reference that makes the section
  belong in *this* app. If `n_politicians` is 0, show nothing.

Rank the **politician-activity badge** as a meaningful marker — a stock that is both
option-heavy and being traded by Congress is the interesting overlap.

### Honesty
- Open interest is a **positioning** measure, not a prediction. Do not imply it forecasts
  direction.
- State the expiry basis somewhere: e.g. *"Open interest across the next few expirations; each row's ratio uses its most active expiry."*
- Do not invent numbers; if a field is missing, omit it rather than printing 0 or NaN.

## Design language (keep it)
Dark near-black canvas, flat cards, hairline borders, tight uppercase micro-labels with wide
letter-spacing, green = buy/calls, red = sell/puts, amber = committee oversight,
blue = company insiders. Nike × Robinhood. No gradients, no glows, no shadows.
Do not introduce a new accent colour.

## Definition of done
- `node --check web/app.js` passes.
- The dashboard shows the section with 10 rows; `BY SIZE` and `BY LOADING` both re-sort correctly.
- Clicking a row navigates to that stock page.
- The `BY LOADING` order starts with VSAT (or whatever `oi_days_of_volume` ranks first).
- Rows with no politician activity show no badge; null `oi_days_of_volume` shows `—`.
- Correct at 390px and 1440px; nothing else regresses; no console errors.

Be decisive. Don't ask questions.
