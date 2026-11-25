# Capitol Flow — Trading Rules (current strategy)

> **This is the live strategy.** When Chris says *"remind me of our current trading strategy"*,
> recite these five rules verbatim. The Capitol Flow app renders the same rules in its
> **STRATEGY** section (source: `data/strategy.json`).

Stored 2026-11-25 · Owner: Dr. Chris Crawford · App: Capitol Flow

---

## The five rules

**1. Buy underpriced options, bet on the trend when prices are low.**
Look for Call or Put options that are very underpriced. The premium should be cheap relative to
the move you expect. Enter when prices are low, not after a run.

**2. Trade the trend on the 4h or Daily chart.**
Always follow the trend on the 4h or Daily chart. Do **not** get distracted by intraday moves —
intraday noise is only a reason to *enter or exit* on a **violation** of the 4h or Daily trend.

**3. Price target under $200; under $150 is ideal.**
Prefer underlyings under $200. Under $150 is the sweet spot. (Applies to the underlying's price.)

**4. Follow Open Interest and volume.**
Always follow the OI and volume indicators. Only consider contracts inside the **top 25 OI** for a
name. Do not get distracted by contracts outside the top 25 OI.

**5. Identify trends with the major swing level method.**
Trend is read from **major swing highs and lows** on the higher timeframe (see the reference video
below). An uptrend is a sequence of higher highs and higher lows; a downtrend is lower highs and
lower lows. A close through the most recent major swing level is the **violation** that ends the
trend and is the only intraday move worth acting on.

**Reference:** *major swing level method* — https://youtu.be/2h5ryPi6ZYo?si=GGu_3tOh22NHBu7r

---

## How the app applies the rules

The daily scanner (`pipeline/strategy.py`) reads `data/app_data.json` (prices + top-OI board) and
`data/options.json`, then for every tracked name:

1. **Trend (rules 2 & 5).** Finds major swing highs/lows on the **daily** bars (pivot lookback = 5)
   and on **4h** bars (hourly resampled to 4h). A name is *up* on higher highs + higher lows, *down*
   on lower highs + lower lows, else *range*. Daily leads; 4h is shown as confirmation. A close
   through the last major swing level is flagged as a **VIOLATION**.
2. **Direction (rules 1 & 2).** Uptrend → **calls**; downtrend → **puts**. Range names are skipped.
3. **Universe (rule 4).** Only the **top 25 OI** contracts for that name (OI-sorted, from the option
   chain), and only those with volume > 0.
4. **Underpriced filter (rule 1).** Prefer cheap premium (low price / low price-to-spot) with high
   OI and fresh volume, and a strike within a modest band of spot so it still tracks the trend.
5. **Price filter (rule 3).** Underlying under $200, with a bonus under $150.

Each survivor is scored and ranked; the top rows appear in the app's **STRATEGY** section and are
posted to Discord daily.

---

*Informational only — not investment advice. Disclosures are filed up to 45 days after a trade.*
