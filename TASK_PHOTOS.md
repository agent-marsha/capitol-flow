# TASK — Show a small photo and the state for each politician

You are extending an EXISTING app. Do not redesign it. Match it exactly.

## Context

- Project root: **`/root/capitol-flow`**
- `web/app.js` (vanilla JS, hash routing) + `web/styles.css`
- Every trade row is rendered by **`tradeRow(t, opt)`** and shows a politician name in a
  `who` list, currently like: **Gilbert Cisneros · CA31 · Spouse · filed +13d**
  (built around line ~216: `<b>` politician `</b>`, then state_district, owner, filing lag).
- Politician names also appear in the **cluster signal** cards on the dashboard
  (a muted line listing who traded, e.g. "Lisa McClain, Maria Elvira Salazar, …").
- **Design language (keep it):** dark near-black canvas, flat cards, hairline borders, tight
  uppercase micro-labels with wide letter-spacing, green = buy, red = sell. Nike × Robinhood.
  No gradients, no glows, no drop shadows.

## New data — already in the bundle

`D.politicians` is a map keyed by the **exact** `t.politician` string in the trades:

```jsonc
"politicians": {
  "Hon. Gilbert Cisneros": {
    "bioguide": "C001123",
    "photo": "https://raw.githubusercontent.com/unitedstates/images/gh-pages/congress/225x275/C001123.jpg",
    "state": "CA",                 // 2-letter
    "state_name": "California",
    "party": "Democrat",           // "Republican" | "Democrat" | "Independent"
    "district": 31,                // house only; null/absent for senators
    "chamber": "House",            // "House" | "Senate"
    "official_full": "Gilbert Ray Cisneros, Jr."
  },
  "Sen. Shelley M Capito": { "...": "...", "district": null, "chamber": "Senate" }
}
```

All 53 politicians currently resolve and every one has a `photo`. But **code defensively** —
a politician may be missing from the map, have `photo: null`, or the image may fail to load.

## What to build

### 1. In every trade row (`tradeRow`)
Show, next to the politician's name:
- a **small circular photo** of the politician, and
- the **state they represent**.

Keep it quiet and secondary — this must not become the loudest thing in the row.

- **Photo:** a circle, roughly **26–30px** at desktop, ~24px at 390px. Use
  `object-fit: cover`, `loading="lazy"`, `decoding="async"`, and a fixed width/height so the
  layout never jumps. Give it a hairline ring in the existing border colour.
- **Fallback:** if there is no `photo`, or the image errors (`onerror`), fall back to a
  circle containing the politician's **initials** (first letter of first + last name) — do not
  show a broken-image icon and never let the row collapse.
- **State:** show the **2-letter state** (e.g. `CA`) as a small muted tag next to the name.
  For a representative also keep the district if it already shows (e.g. `CA-31`); for a
  senator just the state (`WV`). Do not duplicate the state twice in one row.
- **Alt text / a11y:** the image needs a meaningful `alt` (e.g. `Photo of Gilbert Cisneros`).
  Prefer `alt=""` + an `aria-label` on the wrapper if the name is already read out next to it,
  so screen readers don't say the name twice.

### 2. In the cluster signal cards (dashboard)
Each cluster lists several politicians in a muted line. Add the **tiny circular photo** before
each name there too (about **18–20px**), with the same initials fallback. The state is
optional here — the photos are the point. If it gets crowded at 390px, show photos for up to
4 names then a `+N` — do not let the card overflow.

### 3. Optional but nice
On the **stock detail page**, the trade rows come from the same `tradeRow`, so they should pick
this up automatically. Confirm they do.

## Rules
- **Performance:** there can be 30+ rows with 30+ images. `loading="lazy"` on every image is
  required. Don't fetch a photo twice for the same politician in the same view if that's easy
  to avoid (e.g. `onerror` should mark it so it isn't retried in a loop).
- **No layout shift:** reserve the circle's space before the image loads.
- **Never throw** if `D.politicians` is missing entirely — just render the row as it is today.
- Do not break: the chart, DAILY/HOURLY toggle, THE TRADES, OPTIONS, THE BASICS, THE NEWS,
  the dashboard, the feed filters, "Stocks only".

## Definition of done
- `node --check web/app.js` passes.
- Local dashboard feed rows show a small round photo + state tag beside the name.
- Local `#/stock/AAPL` trade rows do too.
- Cluster cards show the tiny photos.
- A politician with a broken photo URL falls back to initials, cleanly.
- Correct at 390px and 1440px, no overflow, no console errors.

Be decisive. Don't ask questions.
