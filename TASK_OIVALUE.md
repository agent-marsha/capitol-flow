# TASK — weight the OI rankings by contract value (money, not contract count)

Extend the EXISTING app. Do not redesign it. Read `web/app.js` and `web/styles.css` first.

## What the user asked, verbatim
> "for OI the volume is high however the contract value is low. lets add a weight for contract
> value so that we are actually evaluating the amount of money is at risk not just a contract count"

## The pipeline is ALREADY DONE — you only change the display
`pipeline/fetch_options.py` and `pipeline/enrich.py` now rank by notional value. **Do not touch
any Python file.**

### Leaderboard — `data/options.json` → `_top_oi.calls[]` / `.puts[]`
Rows are now sorted by **notional descending** and each carries two new fields:
```jsonc
{"ticker":"TSLA","type":"call","strike":5.0,"expiry":"2027-12-17","dte":..., "oi":40487,
 "volume":123, "price":394.98, "underlying":376.2,
 "notional":1599200000,      // NEW: oi x 100 x price, in dollars
 "moneyness":0.0125,         // NEW: strike / underlying. <1 ITM for calls, >1 OTM for calls.
 "symbol":"...","tv_url":"..."}
```

### OI board — `data/app_data.json` → `oi_board[]`
Each row now also carries:
```jsonc
{"ticker":"NVDA","call_oi":3428534,"put_oi":3864571,"total_oi":7293105,
 "call_notional":3289912104, "put_notional":7995951871,
 "total_notional":11285863975,     // NEW: dollars of open interest
 "notional_priced":true,            // NEW: false when nothing in the book quoted
 "pc_ratio":1.13, ...}
```
`oi_board` is now **sorted by `total_notional` descending** (ties by `total_oi`). **Render it in
the order given — do not re-sort client-side.**

## Display changes

### 1. "WHERE THE BIGGEST BETS SIT." (leaderboard, `#top-oi`)
- Add a column **`$ OPEN`** showing `notional` in compact money form (`$1.60B`, `$744.6M`, `$2.8M`).
  Put it **first among the numbers** — it is now the sort key, so it should read as the metric.
- Keep the existing OI column. Both must be visible: the whole point is that a big count and a
  big dollar figure are different facts.
- Add a small **`MONEY`** or **`POS`** column derived from `moneyness`:
  - calls: `DEEP ITM` if moneyness ≤ 0.90, `ITM` if ≤ 0.98, `ATM` if 0.98–1.02, `OTM` if > 1.02
  - puts: mirrored — `DEEP ITM` if ≥ 1.10, `ITM` if ≥ 1.02, `ATM` 0.98–1.02, `OTM` < 0.98
  - Render it in the muted style, lowercase or small caps. It must be **neutral** — this is
    position description, not a judgement.
- If `moneyness` is null, render `—`.
- No forbidden words (see below).

### 2. Where the OI board is rendered
- Add the **`$ OPEN`** column (from `total_notional`, compact money) alongside `total_oi`.
- When `notional_priced` is false, render `—` for `$ OPEN` rather than `$0`.
- Do not re-sort.

## WHY the moneyness column exists — do not remove it
A notional ranking **inherently favours deep-in-the-money contracts**, because a contract with
$385 of intrinsic value is worth ~1000x a $0.39 one. Many deep-ITM positions are **synthetic
stock** (someone replicating a share position without the capital or the dividend), **not** a
directional bet — the app already documents this for the GOOG $75 call.

So the money column exists to stop the dollar figure implying conviction it may not represent:
the top calls by money are 4-of-5 deep ITM (stock substitutes) while the top puts are
near-the-money. **Both facts belong on screen.** Do not hide either behind a tooltip only.

## Wording — non-negotiable
- `$ OPEN` is the **notional value of open contracts, both sides**. It is NOT "money at risk",
  "positioning", "conviction", "bullish" or "bearish". Open interest is **directionless** — it
  cannot say whether contracts were bought or written. Describe the amount, never a view.
- Banned anywhere in these sections: bullish, bearish, accumulation, distribution, buying
  pressure, selling pressure, smart money, strength, weakness, conviction, bet against.
- A one-line `note` addition is allowed if it states plainly that the dollar figure counts
  **contracts × 100 × price across both sides**, and that deep-ITM contracts are often stock
  substitutes.

## Guardrails
- `null`/missing `notional` or `moneyness` → render `—`, never `NaN`/`Infinity`/`undefined`/`$0`
  when the value is unknown.
- No client-side re-sorting of `oi_board`.
- No existing section's behaviour changes.
- `node --check web/app.js` passes.
- Responsive: the new columns must not break the narrow-phone layout; drop `MONEY` below ~760px
  and `$ OPEN` only if unavoidable.

## Definition of done
- Leaderboard shows `$ OPEN` as the leading numeric column, plus OI, plus the neutral
  position column; rows appear in the pipeline's order.
- OI board shows `$ OPEN` and uses the given order.
- Real data renders with no `NaN`/`Infinity`/`undefined`, and no `$0` where a value is unknown.
- No banned word appears in either section (verify it programmatically).
- No Python file is modified.
