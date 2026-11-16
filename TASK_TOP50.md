# TASK — New section: top 50 CALL and top 50 PUT contracts by open interest

Extend the EXISTING app. Do not redesign it. Match it exactly.
`web/app.js` + `web/styles.css`. Read both first.

## The ask

A new dashboard section listing **the 50 call contracts and the 50 put contracts with the
highest open interest in the whole market** — not per stock, but across every ticker the
app tracks. This is a **contract-level leaderboard**.

Use the same window rule the options scanner already uses: **at least 1 month out, and the
next 10 expiration dates.** Nothing under 30 DTE may appear.

## Data — ALREADY IN THE BOOT BUNDLE, no new fetch

`data/app_data.json` now carries a top-level key **`top_oi`**. It is already in the bundle
the app loads at boot, so **do not add any fetch**. Shape:

```jsonc
"top_oi": {
  "calls": [ /* exactly 50, sorted by oi desc */ ],
  "puts":  [ /* exactly 50, sorted by oi desc */ ],
  "n": 50,
  "min_dte": 30,          // the floor actually applied
  "expirations": 10,      // expirations scanned per ticker
  "universe": 121,        // tickers covered
  "contracts_scanned": 48213
},
"calls": [
  { "ticker": "NVDA", "type": "call", "strike": 200.0, "expiry": "2027-01-15",
    "dte": 60, "oi": 471992, "volume": 12043, "price": 12.35,
    "underlying": 159.18,
    "symbol": "NVDA270115C200.0",
    "tv_url": "https://www.tradingview.com/symbols/OPRA-NVDA270115C200.0/" }
]
```

`price` may be `null` (no two-sided quote) — render `—`, never invent a number.
`symbol` and `tv_url` are prebuilt; use them as-is.

Defensive: if `top_oi` is missing or null (older data), **render nothing for this section**
and do not throw.

## The UI

A new section on the dashboard, near the other options content (the "WHERE THE OPTIONS
ARE" board is the natural neighbour). Follow the established idiom:

```
◆ CONTRACT LEADERBOARD            (micro label, accent)
WHERE THE BIGGEST BETS SIT.       (big display heading)
The 50 calls and 50 puts with the most open interest, across every
stock this app tracks — one month out or further.
```

**Two columns: CALLS | PUTS.** Each is a ranked list of 50 rows.

**Each row shows:**
- **rank** (01–50, quiet, mono)
- **ticker** (loud, mono, links to `#/stock/<TICKER>` — the app's own stock page)
- **strike** and **expiry** (e.g. `$200 · JAN 15`)
- **open interest** — the hero number on the row, large and tabular
- **volume** (quiet, secondary)
- **price** (quiet; `—` when null)
- a small **`TRADINGVIEW ↗`** link from `tv_url` (`target="_blank" rel="noopener noreferrer"`,
  same treatment as the existing options section)

**Say the caveat once, in the app's voice.** Open interest is **directionless** — it cannot
tell you whether contracts were bought or sold, and a huge pile is as likely to be a written
position as a purchased one. The app already makes this point in its options section; carry
it here. Do **not** label the columns "bets it goes up/down" or imply direction.

**Add one line of context** explaining what makes this different from the section above it:
the board above ranks *stocks* by total open interest; this ranks *individual contracts* —
so it answers "which single bet is the biggest", not "which stock is most optioned".

## Design rules (non-negotiable)
- **Nike + Robinhood**: bold black/white, mono uppercase micro-labels, big condensed
  headlines, high contrast, minimal chrome. One accent only.
- **No glassmorphism, no gradients, no glows.**
- Reuse existing classes/tokens from `styles.css` wherever possible; add new CSS only at
  the end under a clear comment.
- Numbers in tabular/mono figures. OI is the loud element; everything else is quiet.
- 50 rows per side is long — a **"SHOW ALL 50 / SHOW TOP 10"** toggle is welcome (the app
  already does this pattern with "SHOW ALL 30 SIGNALS"), defaulting to a shorter list.
  Do not paginate.
- Responsive: two columns on desktop, stacked on narrow screens.

## Definition of done
- Section renders with 50 calls and 50 puts; ranks 01–50.
- Ticker links go to `#/stock/<TICKER>`; TradingView links open the right contract.
- A null `price` renders `—`.
- **No listing under 30 DTE** appears (assert it in the console once).
- Removing `top_oi` from the data renders nothing and throws nothing.
- `node --check web/app.js` passes.
- No change to any existing section's behaviour.
