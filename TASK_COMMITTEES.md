# TASK — Add committee-oversight signal to Capitol Flow

You are extending an EXISTING app. Do not redesign it. Match it exactly.

## The signal (why this is the most important feature so far)

"A politician sold pharma stock" is mildly interesting.
"**The senator who sits on the committee that oversees pharma** sold pharma stock" is the
actual story. The app can now tell the difference, and this change is about surfacing it.

## New data — already in the bundle (`data/app_data.json` → `D`)

```jsonc
// 1. Per TRADE (t.oversight) — present and non-empty only when the politician's committee
//    has jurisdiction over the traded stock's sector. 70 of 745 trades currently.
"oversight": [ { "code": "HSWM", "title": "Chairman", "rank": 1 } ],

// 2. Committee code -> short display name
"committees": { "HSWM": "Ways and Means", "HSIF": "Energy and Commerce", "SSAS": "Armed Services", ... },

// 3. Which committees each politician sits on (keyed by bioguide)
"member_committees": { "H001082": [ {"code": "HSWM", "title": "Chairman"}, {"code": "HSJU", "title": null} ] },

// 4. Sector per ticker (drives the match)
"sectors": { "AMGN": { "sector": "Healthcare", "industry": "Drug Manufacturers—General" } },

// 5. Existing: politician -> { bioguide, photo, state, state_name, party, chamber, district }
"politicians": { "Hon. Kevin Hern": { "bioguide": "H001082", ... } },
```

`title` is usually `null`, but is `"Chairman"` / `"Ranking Member"` / `"Vice Chairman"` for
senior seats — **that is a big deal and must be visible.**

## What to build

### 1. Oversight badge on trade rows (`tradeRow`)
When `t.oversight` is non-empty, add a **distinct badge** to that row, e.g.
`⚡ WAYS AND MEANS` or, when a title exists, `⚡ CHAIRMAN · WAYS AND MEANS`.

- Style it as **the strongest badge in the row** — it should out-rank the existing
  `$100K+` / `◆ SIGNAL` badges. It is the most meaningful marker in the app.
- Give it a `title`/tooltip attribute explaining it plainly, e.g.
  *"This politician sits on Ways and Means, which has jurisdiction over this stock's sector."*
- If a politician has several matching committees, show the most senior one (lowest `rank`),
  and if there is more than one, append `+N`.
- Rows without oversight render exactly as they do today.

### 2. Dashboard: an "Oversight" filter + a signal strip
- Add an **`⚡ Oversight` chip** to the feed controls, alongside `$100K+ only`, `◆ Signals only`,
  `Stocks only`. When active, the feed shows only trades with `t.oversight`.
- Add a compact **"COMMITTEE OVERSIGHT"** block to the dashboard (place it after CLUSTER
  SIGNALS, before BIG MONEY). It lists the oversight trades — politician, their committee
  (+ title if any), ticker, direction, amount, and how many days ago. Sort by committee
  seniority (titles first) then recency. Keep it to ~6 rows with a "show all" expander if
  there are more. Include one plain sentence explaining what it means, e.g.
  *"These trades were made by politicians whose committee oversees that industry."*
- If there are no oversight trades, render nothing (don't leave an empty block).

### 3. Stock detail page
The per-trade rows come from the same `tradeRow`, so they pick the badge up automatically —
confirm that. Above THE TRADES, if the page's trades include oversight cases, add a short
one-line note, e.g. *"2 of these trades were made by politicians whose committee oversees
this sector."*

### 4. Optional, if clean
When a trade has oversight, the row could reveal the politician's **full committee list**
from `member_committees` (on hover via `title`, or in an expandable). Don't build anything
heavy — a tooltip is fine.

## Honesty requirement (important)

The sector→committee map is a **heuristic, not a legal fact**. Do not overclaim.
- Word it as *"a committee that oversees this industry/sector"*, never *"insider"*,
  *"conflict"*, or *"wrongdoing"*.
- Add a short muted footnote somewhere the oversight block appears, e.g.
  *"Committee jurisdiction is matched by sector and is a guide, not a legal determination."*
- Never imply intent.

## Design language (keep it)
Dark near-black canvas, flat cards, hairline borders, tight uppercase micro-labels, wide
letter-spacing, green = buy, red = sell. Nike × Robinhood. No gradients, no glows, no shadows.
The oversight badge may use **one** new accent colour — pick something that reads as
"attention" without colliding with buy-green/sell-red (e.g. a warm amber/yellow). Use it only
for oversight.

## Definitions of done
- `node --check web/app.js` passes.
- Feed rows with oversight show a top-rank `⚡` badge; rows without are unchanged.
- The `⚡ Oversight` chip filters the feed correctly and composes with the other chips.
- The dashboard oversight block renders on the live data (there are 70 oversight trades).
- `#/stock/KO` (or any stock with an oversight trade) shows the badge.
- Correct at 390px and 1440px; no console errors; nothing else regresses.

Be decisive. Don't ask questions.
