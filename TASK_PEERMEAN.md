# TASK — Replace the peer strip with a plain "this vs the sector average" comparison

You are extending an EXISTING app. Do not redesign it. Match it exactly.

## Why

The current `peerBlock` on the two VALUATION cards draws a **percentile strip** (a track with
a fixed middle band and a dot). The user finds it **weird and too indirect** — it makes you
decode a dot's position instead of just showing the comparison.

**Replace it with a direct, obvious comparison: this company's figure against the AVERAGE of
the other companies in its sector.**

## Data (already in the pipeline — nothing to add)

`F = fundamentals` (`window.__CAPITOL_FUNDAMENTALS__`). Per company:

```jsonc
F["T"].valuation = { "ev_ebitda": 5.90, "fcf_yield": 13.01, ... }

F["T"].peer = {
  "sector": "Communication Services",
  "ev_ebitda_peer_mean": 15.68,   // mean of the OTHER companies in the sector (T excluded)
  "ev_ebitda_peer_n": 5,
  "ev_ebitda_vs_mean": -0.624,    // (value - peer_mean) / |peer_mean|  → -0.624 = 62% below
  "ev_ebitda_cheap": 1.0,         // normalised: higher = cheaper  (for the colour/tone only)
  "ev_ebitda_n": 6,
  "fcf_yield_peer_mean": 2.28, "fcf_yield_peer_n": 3, "fcf_yield_vs_mean": 4.698,
  "fcf_yield_cheap": 0.75, "fcf_yield_n": 4
}

// sector context, for the median note
F._sectors["Communication Services"].ev_ebitda = { n, min, p25, median, p75, max, mean }
```

### ⚠️ Two rules you must not get wrong
1. **Use `*_peer_mean` — the average of the OTHER companies.** Do not compute a mean from
   any other list, and never include the company itself.
2. **`*_cheap` decides direction, NOT the sign of `*_vs_mean`.** A *low* EV/EBITDA is cheap;
   a *high* FCF yield is cheap. So "62% below average" is **good** for EV/EBITDA but **bad**
   for FCF yield. Use `*_cheap ≥ 0.75` → green/"cheap", `≤ 0.25` → red/"pricey", else neutral.
   **Do not** write per-metric direction logic in the renderer.

## What to build — per valuation card

**1. A two-bar comparison.** Two thin horizontal bars on a SHARED scale so the lengths are
directly comparable:
- row 1: the company's own value — e.g. label `T` (or nothing), value `5.9×`, bar
- row 2: label **`Sector average`**, value **`15.7×`**, bar
- Bars are proportional to their values, scaled against the larger of the two
- The company's bar gets the tone colour (green when `*_cheap ≥ 0.75`, red when `≤ 0.25`,
  muted otherwise); the sector bar stays neutral/muted
- Values right-aligned, tabular figures

**2. One line beneath**, plain language:
> **62% below the sector average** · cheaper than 75% of Communication Services companies

- Lead with the vs-average phrase, built from `*_vs_mean`:
  - `Math.round(Math.abs(vs) * 100) + '% below the sector average'` when negative
  - `… + '% above the sector average'` when positive
  - consider `1.6× the sector average` when `vs > 2` so a big ratio doesn't read as "470% above"
- Then the percentile sentence using `*_cheap` (as today).
- Add the **sector median** as a small muted aside: `median 11.7×` — because a mean can be
  dragged by one outlier, and the median next to it makes that visible.

**3. Omit the whole block** when `*_peer_mean` or `*_vs_mean` is null, or `*_peer_n < 4`.
No zeros, no placeholders. (Basic Materials n=1 → plain card.)

## Design rules
- **Quiet and secondary** — the big numeral stays the hero of the card. Small type, hairline
  bars, no gradients/glows/shadows.
- Reuse existing tokens: `--buy`, `--sell`, muted greys. No new accent colour.
- Bars `aria-hidden`; the sentence carries the meaning and must read naturally.
- Works at **390px** and **1440px**; nothing overflows the card.
- **Delete** the old `.fpeer-strip` / `.fpeer-iqr` / `.fpeer-med` / `.fpeer-dot` markup and
  any now-unused CSS. Do not leave dead code behind.

## Definition of done
- `node --check web/app.js` passes.
- `#/stock/T`: EV/EBITDA card shows `5.9×` vs `Sector average 15.7×` with the company bar much
  SHORTER, and reads *"62% below the sector average"*. Its FCF yield card shows `13.0%` vs
  `Sector average 2.3×`→`2.3%`, company bar much LONGER, reading *"…above the sector average"*.
- `#/stock/AAPL`: company and sector-average bars are close in length, reading roughly
  *"above/below the sector average"* with a small percentage.
- A company with no peer block still shows the old, unadorned card.
- No console errors; nothing else regresses at either width.

Be decisive. Don't ask questions.
