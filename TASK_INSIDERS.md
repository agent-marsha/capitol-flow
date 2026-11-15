# TASK — Add an OFFICER / DIRECTOR tag to Capitol Flow

You are extending an EXISTING app. Do not redesign it. Match it exactly.

## The signal (this is the sharpest one in the app)

Committee oversight catches the politician who **regulates** a company. It structurally
cannot catch the politician who **ran** it.

> **Sen. Alan Armstrong** was CEO of Williams Companies (2011-2025) and still files with
> the SEC as a Williams **director** (most recent Form 4: **2026-03-09**). He is also a
> sitting US Senator. His **$5M–$25M Williams sale** is the most informed sale in the dataset.

The app currently shows that trade as an ordinary $100K+ sale. This change labels it.

## New data — already in the bundle (`D`)

```jsonc
// Per TRADE — present only when the politician is/was an officer or director of the
// traded company. Currently exactly 5 trades, all Sen. Alan Armstrong / WMB.
"insider": { "company": "WILLIAMS COMPANIES, INC.",
             "role": "Director",            // "Director" | "Officer"
             "title": null,                 // e.g. "President & CEO" when they are an officer
             "last_filed": "2026-03-09",    // most recent SEC Form 3/4/5 as an insider
             "forms": ["4"], "verified_filings": 4 },

// Whole map, politician -> { ticker: {...same shape} }
"insiders": { "Sen. Alan Armstrong": { "WMB": { "...": "..." } } }
```

**How this data is derived (say so in the UI copy if useful):** every US public-company
officer/director must file Forms 3/4/5 with the SEC naming themselves as reporting owner.
We search EDGAR full-text for the politician's name, then **verify against the actual
Form 4 XML** — owner name must match (including middle initial and any Jr/Sr suffix), and
`isDirector` or `isOfficer` must be set. It is checked, not guessed.

## What to build

### 1. A distinct INSIDER badge on the trade row (`tradeRow`)
When `t.insider` is set, add a badge that clearly outranks the ordinary ones — this is the
strongest claim the app makes. Render the role and, when present, the title:

- `⚑ DIRECTOR` — when `role == "Director"`
- `⚑ OFFICER · PRESIDENT & CEO` — when `role == "Officer"` and a `title` exists
- `⚑ OFFICER` — when `role == "Officer"` and no title

Use a **different accent colour from both** the amber oversight badge and buy-green/sell-red.
Give it a `title`/tooltip, e.g.
*"Alan Armstrong is a director of Williams Companies (most recent SEC insider filing 2026-03-09)."*

### 2. Dashboard section: "THEY RAN IT."
Add a block after the "THEY OVERSEE IT." oversight block:
- Heading along the lines of **"THEY RAN IT."** with the micro-label `⚑ COMPANY INSIDERS`
- One sentence: *"These trades were made by politicians who are or were an officer or director of the company itself."*
- Rows: photo, name, **role/title in the new accent colour**, ticker, direction, amount, days ago
- Because there are currently very few, render nothing if the list is empty (don't leave an empty block). Still code it to handle 1–N rows.
- Tooltip per row naming the company and the most recent insider filing date.
- A muted footnote: *"Officer/director status verified against SEC Forms 3/4/5. Not a claim of wrongdoing."*

### 3. `#/stock/WMB` note
Above THE TRADES, when any of the stock's trades carry `t.insider`, add a one-line note, e.g.
*"1 of these trades was made by a politician who is a director of this company."*

## Honesty guardrails (important)
- Word it factually: **"is an officer/director of this company"**. Never *insider trading*,
  *conflict*, *wrongdoing*, or any implication of illegality. Being an officer/director and
  trading is not itself improper — Congress members must disclose, and this one did.
- Do **not** claim the person is currently an officer/director unless `last_filed` supports
  it; prefer phrasing like *"is a director (most recent filing 2026-03-09)"*.
- Never invent a title. If `title` is null, show only the role.

## Design language (keep it)
Dark near-black canvas, flat cards, hairline borders, tight uppercase micro-labels, wide
letter-spacing, green = buy, red = sell, amber = committee oversight. Nike × Robinhood.
No gradients, no glows, no shadows. One new accent colour for insiders, used only for that.

## Definition of done
- `node --check web/app.js` passes.
- `#/stock/WMB` shows the insider badge on Armstrong's rows and the summary note.
- The dashboard shows a "THEY RAN IT." block with his trade(s).
- A page with no insider trades shows no block and no badge.
- Correct at 390px and 1440px; nothing else regresses; no console errors.

Be decisive. Don't ask questions.
