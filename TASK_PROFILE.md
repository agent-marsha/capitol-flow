# TASK — Add a one-line company profile to each stock page

You are extending an EXISTING app. Do not redesign it. Match it exactly.

## Context

- Project root: **`/root/capitol-flow`**
- `web/app.js` (vanilla JS, hash routing) + `web/styles.css`
- Stock detail page renders at `#/stock/TICKER` via `renderDetail(tk)`.
- Its header currently shows: a signal line, the **ticker** as a huge display heading,
  then the company name in muted text (e.g. `Apple Inc. - Common Stock`), then a price block.

## New data — already in the bundle (`D.sectors`)

```jsonc
"sectors": {
  "AAPL": { "name": "Apple Inc.", "sector": "Technology",
            "sic": "3571", "industry": "Electronic Computers" },
  "LLY":  { "name": "ELI LILLY & Co", "sector": "Healthcare",
            "sic": "2834", "industry": "Pharmaceutical Preparations" },
  "FDX":  { "name": "FedEx Corp", "sector": "Industrials",
            "sic": "4513", "industry": "Air Courier Services" }
}
```

`sector` is one of 11 buckets (`Technology`, `Healthcare`, `Financial Services`,
`Consumer Cyclical`, `Consumer Defensive`, `Industrials`, `Energy`, `Basic Materials`,
`Communication Services`, `Utilities`, `Real Estate`). `industry` is the company's own
SIC description — this IS the "what they sell" label. Both come from SEC filings.

## What to build

On the stock detail page, add a **compact one-line company profile** showing the sector
and what the company sells. Keep it to a single short line — this is a label, not a paragraph.

- Place it **under the company name / near the header**, above the chart. It should read as
  quiet supporting detail, not compete with the ticker or the price.
- Show the **sector** as a small tag/chip in the established micro-label style
  (uppercase, wide letter-spacing, hairline border), and the **`industry`** text beside it
  in the muted body colour. For example:

  > `[ TECHNOLOGY ]` Electronic Computers

  > `[ HEALTHCARE ]` Pharmaceutical Preparations

- If `sector` is missing but `industry` exists, show just the industry text.
- If **both** are missing (a few tickers have no SEC CIK — `BRK.B`, `SPYM`, `WBD`), render
  **nothing at all** for this line. Do not print "Unknown", `null`, or an empty chip.
- Never invent a description. Only ever print the values from `D.sectors`.
- Do **not** add this to the dashboard feed rows — stock pages only.

## Design language (keep it)
Dark near-black canvas, flat cards, hairline borders, tight uppercase micro-labels with wide
letter-spacing, green = buy, red = sell, amber = oversight. Nike × Robinhood. No gradients,
no glows, no shadows. Do not introduce a new colour for this — use the existing neutral/border
palette. Keep the sector chip visually distinct from the amber oversight badge.

## Definition of done
- `node --check web/app.js` passes.
- Local `#/stock/AAPL` shows `TECHNOLOGY · Electronic Computers` (or equivalent) near the header.
- Local `#/stock/LLY` shows `HEALTHCARE · Pharmaceutical Preparations`.
- A ticker with no profile data (e.g. `#/stock/WBD`) shows **no** new line and no errors.
- Correct at 390px and 1440px; nothing else regresses; no console errors.

Be decisive. Don't ask questions.
