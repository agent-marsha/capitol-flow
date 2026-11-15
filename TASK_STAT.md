# TASK — Render the new "stat" card type and lead with the two valuation cards

You are extending an EXISTING app. Do not redesign it. Match it exactly.

## Context

- Project root: **`/root/capitol-flow`**
- App: `web/index.html`, `web/styles.css`, `web/app.js` (vanilla JS, hash routing)
- The stock detail page (`#/stock/TICKER`) has a **"THE BASICS" / "IN PLAIN ENGLISH"** section
  that renders cards from `data/fundamentals.json`. Each card is
  `{ emoji, headline, text, chart }` and `app.js` already renders three chart types inside
  those cards: **`bars`**, **`bars2`**, and **`split`** (plain CSS/SVG).
- **Design language (keep it):** dark near-black canvas, flat surfaces, hairline borders,
  oversized condensed display numerals, tight uppercase micro-labels with wide letter-spacing,
  green (#00C805-ish) = buy/good, red (#FF5000-ish) = sell/bad. Nike × Robinhood. No gradients,
  no glows, no drop shadows.

## What changed in the data

Each company's `cards` array now includes **two new cards** whose `chart.type` is **`"stat"`**:

```jsonc
{
  "id": "fcf_yield", "emoji": "💵", "rank": 1,
  "headline": "The real cash you get back",
  "text": "After Apple paid for everything — even new machines and buildings — it had 136.1 billion left in cash. If you bought the whole company, you would get about $3 of cash back each year for every $100 you spent.",
  "chart": { "type": "stat", "label": "Cash back each year, for every $100 you spend",
             "value": "$2.6", "sub": "per $100 you spend, each year" }
},
{
  "id": "ev_ebitda", "emoji": "🏷️", "rank": 2,
  "headline": "What it costs to buy the whole company",
  "text": "... So you would pay about $30 for every $1 it makes.",
  "chart": { "type": "stat", "label": "You pay, for each $1 it makes",
             "value": "$30.4", "sub": "per $1 it makes in a year" }
}
```

**These two are the most important cards** — they are the valuation of the company. They must
read as the headline of the section, not as two more rows.

## What to build

### 1. Render `chart.type === "stat"`
A `stat` chart is a **single large figure**, not a chart:
- The `chart.value` rendered in the **big condensed display type** — same treatment as the
  big price/ticker numerals elsewhere in the app (i.e. genuinely large, e.g. ~2.5–4rem at
  desktop, still ≥2rem at 390px).
- The `chart.label` above it as a **micro-label** (uppercase, wide letter-spacing, muted).
- The `chart.sub` below it, smaller and muted.
- No axes, no bars, no extra chrome. The number is the whole visual.
- Make sure a long value like `$30.4` or `-$12.0` never wraps or overflows its card.

### 2. Order the cards so the two valuation cards lead
- Sort each company's cards so `stat` cards come **first**, ordered by their `rank` field
  ascending when present (so `fcf_yield` then `ev_ebitda`), and the remaining cards keep
  their existing relative order after them.
- The two leading cards should be **visually distinct as a pair** — a subtle treatment that
  says "these are the headline valuation" — without breaking the flat design language
  (e.g. a brighter hairline border, or the value tinted with the accent colour, or a small
  "VALUATION" micro-tag above the pair). Your call — keep it restrained.

### 3. Behave
- If a card's `chart.type` is unknown (future-proofing), render the card's text and skip the
  chart — never throw.
- Everything else on the page (the candlestick chart, DAILY/HOURLY toggle, THE TRADES, THE
  NEWS, the other fundamentals cards, the dashboard) must keep working unchanged.

### 4. Accessibility
- Each `stat` should be readable to a screen reader as one idea: label + value + sub
  (e.g. `aria-label="Cash back each year, for every $100 you spend: $2.6 per $100 you spend, each year"`).

## Definition of done

- `node --check web/app.js` passes.
- Local preview of `#/stock/AAPL` shows the two valuation cards FIRST, each with a large
  numeral, and the remaining five cards after them, all still rendering their bar/split charts.
- No console errors. Layout correct at 390px and 1440px, no overflow.

Be decisive. Don't ask questions.
