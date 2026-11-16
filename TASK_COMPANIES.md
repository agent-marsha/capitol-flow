# TASK — Put the company's NAME and a plain description on every stock page

Extend the EXISTING app. Do not redesign it. Read `web/app.js` and `web/styles.css` first.

## The problem

Every stock page (`#/stock/<TICKER>`) is reachable from trades, the OI board, the contract
leaderboard and the ticker lookup. **284 tickers have a stock page.** But the company name
was only ever read out of congressional filings — so any ticker Congress never traded shows
**a bare symbol with no indication of what the company actually is.** 119 of 284 have no
name at all, 164 have no sector, and none have a description.

## Data — ALREADY IN THE BOOT BUNDLE, no new fetch

`data/app_data.json` now carries a top-level key **`companies`**, already in the bundle the
app loads at boot. **Do not add a fetch.** Shape:

```jsonc
"companies": {
  "AAPL": { "ticker": "AAPL", "name": "Apple Inc.",
            "description": "Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories.",
            "sector": "Technology", "industry": "Consumer Electronics",
            "sic": "3571", "source": "sec+yahoo" },
  "MO":   { "ticker": "MO", "name": "Altria Group, Inc.",
            "description": "Operates in cigarettes.", 
            "sector": null, "industry": "Cigarettes", "sic": "2111", "source": "sec",
            "description_from": "sic" }
}
```

Notes:
- `name`, `description`, `sector`, `industry` may each be **null or absent** — always guard.
- `description_from: "sic"` means the description is a generic industry fallback
  ("Operates in cigarettes.") rather than a real business summary. Render it, but see the
  wording note below.
- `source` is `"sec"`, `"yahoo"` or `"sec+yahoo"` — do not display it to the user.

Defensive: if `companies` is missing or null, the page must render exactly as it does today
and must not throw.

## What to build

### 1. Name on the stock page
Today the hero shows `nameOf.get(tk)` — which is empty for those 119 tickers. Prefer the
new data:

    name = (companies[tk] && companies[tk].name) || nameOf.get(tk) || ''

So a ticker with a company record always shows a real name; the congressional-filing name
remains the fallback.

### 2. A description block
A short block on the stock page — under the hero, above or beside the existing
sector/industry line — that says what the business is.

```
ABOUT
Apple Inc. designs, manufactures, and markets smartphones, personal computers,
tablets, wearables, and accessories.
```

- Heading uses the app's existing micro-label idiom (`ABOUT` / accent, uppercase, tracked).
- Body is the description at normal reading size. Keep it to ~2 lines on desktop.
- If `sector`/`industry` exist, show them as the existing `profileLine` already does — do
  not duplicate that line, just make sure it's present.
- **If the description is missing entirely**, render the block with the industry line only
  (or nothing if that's missing too). Never render the word "null" or an empty box.

### 3. Make the description available where the page is thin
Some tickers have no fundamentals, no trades and no options — the page is nearly empty. The
name + description is the *only* thing that tells the reader what they're looking at, so
make sure the block renders on those pages too, not only when other sections exist.

## Wording rules (important)

- **Do not add editorial or ratings language.** Describe the business, nothing else. No
  "leading", "innovative", "strong", "undervalued" unless it is literally in the source text
  as part of the company's own name for itself is fine — but do not introduce judgement.
- For `description_from: "sic"` the text is genuinely generic ("Operates in cigarettes.").
  Render it plainly; do NOT dress it up to look like a real description, and do not imply it
  came from a filing.
- No new claims about what a company does beyond the supplied text.

## Design rules (non-negotiable)
- Match the app: bold black/white, mono uppercase micro-labels, high contrast, minimal chrome.
- **No glassmorphism, no gradients, no glows.**
- Reuse existing classes/tokens; add new CSS only at the end under a clear comment.
- Responsive: must read well on a narrow phone.

## Definition of done
- A ticker WITH a company record (e.g. `AAPL`, `MO`) shows the name and an ABOUT block.
- A ticker WITHOUT (`nameOf` only, e.g. a small congressional name) still works via fallback.
- A ticker with **no** company record, no trades, no options renders without throwing and
  without an empty "null" block.
- Removing `companies` from the data changes nothing and throws nothing.
- A null `description` or null `sector` renders cleanly.
- `node --check web/app.js` passes.
- No existing section's behaviour changes.
