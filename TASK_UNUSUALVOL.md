# TASK — "WHERE THE VOLUME IS." — screener table for unusual volume in Elder uptrends

Extend the EXISTING app. Do not redesign it. Read `web/app.js` and `web/styles.css` first.

## What the user asked for, verbatim
> "a section that just checks for unusual volume on stocks that are generally in an uptrend
> based on elder's rule"
> "where the biggest bets sit, just give me a table in the style of a screener of where the
> volume is"

**So: a screener-style TABLE. Bare and scannable. No prose, no explainers, no charts.** The
only prose allowed is the single one-line `note` that every other section in this app carries,
plus column headers.

## Data — already in app_data, do NOT fetch anything
`data/app_data.json` now carries a top-level key **`unusual_volume`**:

```jsonc
"unusual_volume": {
  "recent_date": "2026-11-25",          // the latest session that produced fires
  "recent": [                            // THE TABLE: fires from that session, RVOL desc
    {"ticker":"MRNA","sector":"Health Care","date":"2026-11-25",
     "rvol":6.57,"volume":99499900,"avg20":15142380,
     "dollar_vol":13265300000,"close":133.28,"chg":-23.6,
     "vol_dir":"down"}
  ],
  "fires": [ ... ],                      // all fires over the past year (not rendered)
  "backtest": { ... },                    // internal validation — DO NOT render in the UI
  "coverage": {"universe":503,"screened":503,"with_data":503},
  "params": {"rvol_min":2.0,"dollar_min":20000000,"impulse":"GREEN (EMA13 + MACD hist)"}
}
```

Render **`recent`** only. Guard hard: the key may be `null`, `recent` may be missing or empty —
in any of those cases render **NOTHING AT ALL** (no heading, no empty table).

## The section
- Section id: **`#unusual-vol`**
- **Placement: immediately after the existing "WHERE THE BIGGEST BETS SIT." section** (`#top-oi`).
- Heading style must match the app: `micro` label + `h2.display`. Suggested:
  - micro: `Unusual volume · Elder uptrend`
  - display: **`WHERE THE VOLUME IS.`**
- **One `note` line**, max two short sentences. It must state: (a) these are stocks whose
  **daily Elder Impulse is GREEN** — EMA13 rising and MACD histogram rising — that traded
  **at least 2× their 20-day average volume** with at least $20M of turnover, and (b) the
  session being shown. Read the threshold and date from `params` / `recent_date` rather than
  hardcoding, so the copy can't drift from the data.

## The table — screener style
Columns, in this order. Numeric columns right-aligned, tabular numerals, tabular font-variant.

| Column | Source | Format |
|---|---|---|
| **TICKER** | `ticker` | linked to `#/stock/<TICKER>`, bold |
| **SECTOR** | `sector` | plain, truncate/wrap sensibly on narrow |
| **RVOL** | `rvol` | **one decimal**, e.g. `6.6×` — this is the sort column and the star of the row |
| **VOLUME** | `volume` | compact: `99.5M` |
| **20D AVG** | `avg20` | compact: `15.1M` |
| **$ VOLUME** | `dollar_vol` | compact with unit: `$13.3B` |
| **CHG** | `chg` | `%` with sign, e.g. `−23.6%` |
| **DAY** | `vol_dir` | `UP` / `DOWN` — see wording rule below |

**No sorting UI, no filters, no expander.** The list is already sorted by RVOL descending.
If it is long, render the top 25 and add a single "show all N" toggle matching the pattern the
app already uses elsewhere — that pattern is fine, invented controls are not.

## THE WORDING RULE — volume is directionless
This is the part most likely to go wrong, and it matters more than the layout.

**Volume tells you that something happened, never which way it will go.** The informative part
is the pairing: unusual volume on an **up day** means someone wanted in; on a **down day**,
someone wanted out *inside an uptrend*.

Therefore:
- The `vol_dir` column renders as **`UP` / `DOWN`** — describing **the price on that day**, not
  a mood.
- **Never** use "bullish", "bearish", "accumulation", "distribution", "buying pressure",
  "selling pressure", "smart money", "strength", "weakness" or any word implying a forecast.
- Do **not** colour the rows green/red to imply good/bad. A neutral, monochrome table is
  correct. If you want one accent, use it on the RVOL figure only (it is the sort key), and
  keep both directions in the same neutral treatment.
- The section must not imply these names are recommendations. It is a description of where
  trading activity was abnormal.

## Formatting helpers
- Numbers: `99.5M`, `$13.3B`, `6.6×`, `−23.6%`. Use the minus sign (−) not a hyphen for
  negatives, matching the rest of the app.
- **Never** print `NaN`, `Infinity`, `undefined`, or `0.0×` for a missing value — omit the cell
  content or show `—`.

## Design rules (non-negotiable)
- Match the app: bold black/white, mono uppercase micro-labels, high contrast, minimal chrome.
- **No glassmorphism, no gradients, no glows.**
- Reuse existing classes and tokens. New CSS only at the end of `styles.css` under a clear
  comment, prefixed `uv-`.
- **A dense table is the point.** Do not add cards, tiles, badges, or icons.
- Responsive: on a narrow phone, drop the SECTOR column and keep TICKER / RVOL / CHG / DAY.
  The row must remain scannable, not wrap into a paragraph.

## Definition of done
- With real data: the table renders after `#top-oi` with one row per entry in `recent`.
- With `unusual_volume` null, or `recent` empty/missing: **nothing renders**, no errors.
- No `NaN`/`Infinity`/`undefined`/`0.0×` on screen for any row.
- Ticker links go to `#/stock/<TICKER>` and open in the same tab (existing behaviour).
- No forbidden word appears anywhere in the section (check programmatically).
- `node --check web/app.js` passes.
- No existing section's behaviour changes.
