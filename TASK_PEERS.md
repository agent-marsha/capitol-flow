# TASK — Show how each valuation compares with sector peers

You are extending an EXISTING app. Do not redesign it. Match it exactly.

## Where
The two **VALUATION** cards that lead "THE BASICS" on each stock page — the `stat` cards
(**EV/EBITDA** = *"What it costs to buy the whole company"* and **FCF yield** = *"The real
cash the company makes"*). They are rendered by `vizStat` / `fundCard` in `web/app.js`
(~lines 1142–1240) and carry `chart.type === 'stat'`.

**Add a peer-comparison block to each of those two cards.** Leave everything else alone.

## The data is already there

`F = fundamentals` (the `window.__CAPITOL_FUNDAMENTALS__` / `data/fundamentals.json` object).
The pipeline now attaches a peer block per company and a sector-stats map:

```jsonc
// F["AAPL"]
{
  "valuation": { "ev_ebitda": 30.38, "fcf_yield": 2.63, ... },
  "peer": {
    "sector": "Technology",
    "sector_n": 14,                 // companies we cover in this sector
    "ev_ebitda_pctile": 0.545,      // share of peers BELOW this value
    "ev_ebitda_n": 11,              // peers that actually have the metric
    "ev_ebitda_cheap": 0.455,       // NORMALISED: higher = cheaper
    "fcf_yield_pctile": 0.429,
    "fcf_yield_n": 14,
    "fcf_yield_cheap": 0.429
  }
}

// F._sectors["Technology"]
{ "n": 14,
  "ev_ebitda": { "n": 11, "min": 7.8, "p25": 20.5, "median": 29.43, "p75": 36.2, "max": 65.5 },
  "fcf_yield": { "n": 14, "min": -1.6, "p25": 2.5, "median": 2.78, "p75": 3.9, "max": 13.0 } }
```

### ⚠️ Read `*_cheap`, never re-derive the direction
**A LOW EV/EBITDA is cheap; a HIGH FCF yield is cheap.** The pipeline already normalised
this: **`*_cheap` is always 0…1 where higher = cheaper.** Use it directly for any
cheap/pricey wording. Do **not** recompute cheapness from the raw multiple — that is the
exact bug this field exists to prevent.  Show the RAW value (`F[tk].valuation.ev_ebitda`)
as the number being positioned; use `*_cheap` only for the verdict.

## What to build — per card

**1. A distribution strip.** A slim horizontal band representing the sector's range:
- Track spans `min` → `max`
- **The interquartile band (`p25` → `p75`) drawn darker** — that's where the middle half of peers sit
- **A marker at this company's value**, in the app's existing accent for the card
- A small tick at the **sector median**
- Position everything by linear interpolation across `min…max`

**2. One line of plain text** beneath, e.g.
> **Cheaper than 55% of Technology companies** · sector median 29.4x

Use `*_cheap` for the percentage (`Math.round(cheap * 100)`), the sector name, and the
relevant `median`. For FCF yield show it as a percentage (`2.8%`), for EV/EBITDA as a
multiple (`29.4x`).

**3. A verdict word** driven by `*_cheap`:
- `≥ 0.75` → *among the cheapest*
- `≤ 0.25` → *among the priciest*
- otherwise → *mid-pack*

**4. Omit cleanly when there's nothing to say.** If `F[tk].peer` is missing, or the metric's
`*_cheap` is null, or `*_n < 4` — render the card **exactly as it is today**, with no strip
and no peer line. No zeros, no "n/a", no empty band. (Basic Materials currently has n=1, so
its cards must stay plain.)

## Design rules
- Keep it **quiet and secondary** — these cards lead the section and the big numeral stays
  the hero. Small type, hairline track, no gradients/glows/shadows.
- Reuse existing tokens: `--buy` (green), `--sell` (red), the amber/blue accents, the muted
  label colour. No new accent colour.
- The strip must be **decorative for screen readers** (`aria-hidden`), with the meaning
  carried by the text line, which should read naturally as one sentence.
- Works at **390px** and **1440px**; the strip must not overflow its card.

## Definition of done
- `node --check web/app.js` passes.
- `#/stock/AAPL` shows both strips with the marker placed sensibly (AAPL EV/EBITDA 30.4 is
  just above the Technology median 29.4 → marker slightly right of the median tick).
- `#/stock/T` (Communication Services, EV/EBITDA 5.9 — the cheapest peer) puts the marker
  at/near the far LEFT of the EV/EBITDA track, and its verdict reads *among the cheapest*.
- `#/stock/INTC` (EV/EBITDA 40.6, `cheap` 0.182) reads *among the priciest* on that card.
- A company with no peer block (e.g. `LLY`, which has no valuation) shows the old,
  unadorned card.
- No console errors; nothing else regresses at either width.

Be decisive. Don't ask questions.
