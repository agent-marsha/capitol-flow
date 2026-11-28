# Unusual Volume in Elder Uptrends — Implementation Plan

> **Status: PLAN ONLY — nothing built. For your review before any code is written.**

**Goal:** Add a dashboard section that flags stocks sitting in an **Elder-confirmed uptrend** that have just printed **unusual volume** — i.e. "the trend is up, and something just changed hands in size."

**Architecture:** One new pipeline module that computes the screen from the OHLCV already in `app_data.prices`, emits a compact result into `app_data`, and one new dashboard section that renders it. No new data source, no new network calls in the happy path.

**Stack:** Python 3 (pandas, already used), vanilla JS matching the existing app, GitHub Pages.

---

## 1. What "Elder's rule" means here — OPEN QUESTION #1

I want your call before building, because "Elder's rule" maps to three different things in his work and the plan changes depending on which you mean.

**Dr. Alexander Elder's relevant tools:**

| Tool | Definition | What it gives you |
|---|---|---|
| **Impulse System** | EMA(13) slope + MACD(12,26,9) histogram slope | A 3-state colour: **Green** = EMA rising AND histogram rising; **Red** = both falling; **Blue** = mixed |
| **Triple Screen** | Screen 1 = **weekly** trend (weekly MACD-H slope) | "Trade only with the larger timeframe" |
| **Force Index** | `(Close − Prior Close) × Volume` | His **volume** tool — combines price change and volume |

**My recommended reading (used as the default throughout this plan):**

> **Uptrend = the daily Impulse System is GREEN** (EMA13 rising AND MACD histogram rising).

Elder's stated rule is *only take longs when the Impulse is green, only shorts when red, treat blue as no signal* — so "in an uptrend by Elder's rule" most naturally means green on the daily.

**Options I'd offer as a stricter variant:** also require **Triple Screen Screen 1** — the weekly EMA(13) rising — so you only flag names where both timeframes agree. Fewer signals, cleaner trend. **Tell me which and I'll set it as the default.**

---

## 2. What "unusual volume" means — OPEN QUESTION #2

**Definition:** Relative Volume (RVOL)

```
RVOL = today's volume / mean(volume of the prior 20 sessions)
```

**Threshold:** RVOL ≥ **2.0×** (configurable). 2× is the common "unusual" bar; 1.5× generates too much noise, 3× is rare.

**Two traps this must avoid, and how:**

1. **The partial-day trap.** Comparing a half-finished session against full-day averages makes volume look *low*, never high. **So the screen runs on COMPLETED daily bars only.** RVOL therefore describes *yesterday's* session — which is the honest framing and must be stated in the UI, not glossed.
2. **The penny-stock trap.** Share volume is meaningless on low-priced names. Add a **dollar-volume floor** (`close × volume ≥ $20M` on the signal day) so the list isn't dominated by $3 stocks trading 40M shares.

**Also surfaced per signal:** the 20-day average volume, the raw volume, and the dollar volume — so a 2.1× on a $50M name is distinguishable from a 2.1× on a $2B name.

---

## 3. The key design decision — volume is directionless

**This is the part I'd get wrong if I weren't careful, and it's worth your sign-off.**

"Unusual volume" on its own says **nothing**. Elder's actual point is that **volume confirms whatever price is doing**:

- **Unusual volume + an UP day in an uptrend** → demand. Someone wanted in.
- **Unusual volume + a DOWN day in an uptrend** → supply. Someone wanted out, *inside the trend* — the classic distribution warning.

Flipping this is the whole value of the screen. So **every row carries the direction of its volume day**, and the section splits or clearly labels the two cases. It must **never** present "unusual volume in an uptrend" as a bullish signal by itself — that would be exactly the overclaim this app avoids elsewhere.

Same discipline as the options and OI sections: **describe the book, never the mood.**

---

## 4. Data — what already exists

Verified in the current `app_data.json`:

```
prices: 120 tickers
  each: { daily: 251 rows, hourly: 414 rows }
  daily row: { t: "2025-11-28", o, h, l, c, v }
```

**So the screen needs no new data source.** Daily volume for a full year across 120 names is already fetched by `enrich.py` every run. RVOL and the Impulse System are pure computation over data in hand.

**Universe — OPEN QUESTION #3:**

| Option | Scope | Cost |
|---|---|---|
| **A (recommended first)** | The existing 120 app tickers | Zero new data, ships fastest |
| **B** | S&P 500 (~500 names) | ~1 extra batched `yf.download`; needs a universe file (the screener at `/root/screens/sp500.csv` already has one) |
| **C** | The 546-ticker OI-lookup universe | Pricier; 546 × 1yr daily is a heavier pull |

I'd start with **A** and treat B as a follow-up once the logic is validated — the screen either works on 120 names or it doesn't.

---

## 5. Signal definition (the precise spec, so it's reviewable)

```
For each ticker, using COMPLETED daily bars:

  EMA13        = 13-period EMA of close
  MACD_H       = histogram of MACD(12,26,9)  = MACD line − signal line
  impulse      = GREEN  if EMA13 rising AND MACD_H rising
                 RED    if EMA13 falling AND MACD_H falling
                 BLUE   otherwise
  avg20_vol    = mean volume of the 20 sessions BEFORE the signal day
  rvol         = signal_day_volume / avg20_vol
  dollar_vol   = signal_day_close × signal_day_volume
  vol_dir      = 'up'   if signal_day_close > signal_day_open else 'down'

  FIRES when:  impulse == GREEN
           and rvol >= 2.0
           and dollar_vol >= $20M
```

**Optional weekly confirmation** (pending OPEN QUESTION #1): `weekly_ema13_rising == True`.

**Ranking:** RVOL descending, so the most anomalous tape sits on top.

---

## 6. Validation — measure it, don't assert it

This app's existing discipline is to show data, not to claim edge. The plan follows that:

**Task V1 — backtest before shipping.** For every historical fire in the 251-day window, compute forward returns at **1, 5, and 20 sessions**, split by `vol_dir` (up-volume vs down-volume). Deliverable: a table, not a claim.

**Task V2 — the honest result gets published.** If up-volume fires outperform and down-volume fires don't, the section says so with the measured numbers and the sample size. If there's no difference, **the section says that too.** A screen with no measured edge is still useful as a "what changed hands" watcher — but it must not be dressed up as a signal.

This is the step that stops the section from being astrology.

---

## 7. Files

**New:**
- `pipeline/unusual_volume.py` — the screen: impulse state, RVOL, dollar-volume floor, forward-return backtest. Pure functions, importable and testable in isolation.
- `TASK_UNUSUALVOL.md` — the Opus 5.5 brief for the UI, same format as the existing TASK_*.md files.

**Modified:**
- `pipeline/enrich.py` — call the screen, add its result to `app_data` under a new key (`unusual_volume`), print a coverage line.
- `web/app.js` — one new section (`#unusual-vol`), following the existing pattern: micro label + `h2.display` + `note`, then rows.
- `web/styles.css` — new classes at the end under a clear comment block.
- `.github/workflows/refresh.yml` — nothing new needed if the screen runs inside `enrich.py` (which already runs daily).

---

## 8. Tasks

### Task 1 — `pipeline/unusual_volume.py` core maths
- EMA13, MACD(12,26,9), histogram, impulse state as pure functions.
- **Verify:** on a known series, EMA13 and MACD match a hand-checked value; impulse returns green/red/blue as expected.
- **Commit.**

### Task 2 — RVOL + floors
- `rvol`, `avg20_vol`, `dollar_vol`, `vol_dir` per day.
- **Verify:** RVOL is 1.0-ish on a flat-volume series; a synthetic 3× day returns ~3.0.
- **Commit.**

### Task 3 — the fire condition + ranking
- Apply the spec in §5. Return the last N fires per ticker with all fields.
- **Verify:** run across all 120 tickers; eyeball that flags are plausible (not 90% of the universe, not zero).
- **Commit.**

### Task 4 — forward-return backtest (Validation V1)
- For each historical fire: forward return at 1/5/20 sessions, split by `vol_dir`.
- **Verify:** sample counts printed; no NaN; a coherent table.
- **Deliverable: the measured table — I'll bring you the actual numbers before any UI work.**
- **Commit.**

### Task 5 — wire into `enrich.py`
- Add `unusual_volume` to `app_data`; print coverage.
- **Verify:** key present in `data/app_data.json` with the expected shape; page still renders.
- **Commit.**

### Task 6 — UI (Opus 5.5)
- Section with: ticker (linked), impulse state, RVOL, volume vs 20d average, dollar volume, **up-day vs down-day label**, and the measured forward-return context.
- Empty state: renders nothing when there are no fires.
- **Verify:** `node --check`; renders with real data; no NaN/undefined; responsive.
- **Commit + deploy.**

---

## 9. Risks and tradeoffs

| Risk | Mitigation |
|---|---|
| **The screen shows yesterday's data, not live** | Say so explicitly in the section. It is a completed-bar screen by design. |
| **Signals look predictive when they aren't** | §6 — measure forward returns, publish the honest result either way. |
| **Unusual volume misread as bullish** | §3 — direction label on every row, no directional claims. |
| **Too many or too few fires** | Thresholds (`2.0×`, `$20M`) are single constants, easy to tune after seeing the real counts. |
| **120-name universe is a small sample** | Option B extends it later; the logic is universe-independent. |
| **Elder's Impulse is mechanical but not magic** | It defines "trend" reproducibly. It is not a claim that green predicts anything. |

---

## 10. DECISIONS — settled 2026-11-27

1. **Elder definition:** DONE — **DAILY IMPULSE GREEN only.** No weekly/Triple Screen requirement.
2. **RVOL threshold:** DONE — **default 2.0×** (the 1.5× suggestion was declined; 2.0× stays as the constant, easy to tune later).
3. **Universe:** DONE — **EXPAND TO THE S&P 500.**
4. **Placement:** DONE — **in/after "WHERE THE BIGGEST BETS SIT."**
5. **Format:** DONE — **a screener-style TABLE of where the volume is.** No prose, no explainers, no backtest table in the UI. Bare and scannable.

### Consequences of #3 + #5 (architecture, not preference)
- The screen needs **daily bars only**, and only for the S&P 500. To keep the deploy small, the
  pipeline **fetches the ~500 daily series, computes the screen, and persists ONLY the flagged
  rows** — the raw 500-name price history is never written into `app_data`.
- The existing hourly series stays at 120 tickers; hourly is not needed for this screen.
- The S&P 500 list must live **in the repo** so CI can read it (`data/sp500.json`).
- The backtest (1/5/20-day forward returns split by volume direction) still runs as an internal
  validation step from the same series. I bring you the numbers; they stay out of the UI.

### Session-length correctness (required, not optional)
- **Drop the final bar when its session is still open.** Otherwise a half-finished day reads as
  ~0.04× RVOL (verified live in this dataset: median 0.04 including the partial bar vs 0.92 on
  completed bars). The 08:35 CT cron runs pre-open so this is normally a no-op, but manual
  afternoon runs must not produce garbage.
- **Exclude market half-days** (day after Thanksgiving, Christmas Eve, July 3) as both signal days
  and as inputs to the 20-day average — Nov 27 closes 1pm ET and naturally prints ~half volume.

---

<details><summary>Original open questions (superseded)</summary>

1. "Elder's rule" — which definition?
2. RVOL threshold — 2.0×, or 1.5× / 3×?
3. Universe — 120 app tickers or S&P 500?
4. Placement — after "WHERE THE BIGGEST BETS SIT." or higher?
5. Backtest table in the UI, or a one-off report?

</details>

---

## 11. Guardrails this app already holds (I'll keep them)

- No overclaiming: "a signal fired", never "this will go up"
- Open interest / volume is directionless unless price direction is stated
- Name the cohort and the direction in any comparative claim
- Research, not investment advice
- 4th-grade-readable descriptions where any prose is user-facing
