# TASK — "Look up a ticker" section: top calls & puts by open interest

You are extending an EXISTING app. Do not redesign it. Match it exactly.
`web/app.js` + `web/styles.css`, dashboard (`index.html`). Read them first.

## The ask

A new dashboard section where the user **types a ticker** and gets back that ticker's
**calls and puts with the highest open interest**.

## Data — LAZY LOAD, DO NOT TOUCH THE INITIAL PAGE LOAD

`data/oi_lookup.json` is a NEW file that will exist next to `web/data/app_data.json`.
It covers ~520 tickers (S&P 500 + everything the app already tracks).

**It is ~1 MB. It must NOT be part of the boot fetch.** Fetch it the first time the user
interacts with this section, and only once. Pattern to follow (the app already does this
for options/fundamentals — mirror `loadOptions()`):

```js
var OI = null, oiPromise = null;
function loadOI(){
  if (OI) return Promise.resolve(OI);
  if (oiPromise) return oiPromise;
  oiPromise = fetch('data/oi_lookup.json', {cache:'force-cache'})
    .then(function(r){ return r.ok ? r.json() : {}; })
    .then(function(j){ OI = (j && typeof j === 'object') ? j : {}; return OI; })
    .catch(function(){
      // file:// or a network blip → try the inline fallback, then give up quietly
      return loadInline('__CAPITOL_OI_LOOKUP__').then(function(j){ OI = j || {}; return OI; })
        .catch(function(){ OI = {}; return OI; });
    });
  return oiPromise;
}
```

Shape:

```jsonc
{
  "AAPL": {
    "underlying": 356.27,          // spot at fetch time (may be null)
    "expiry": "2026-12-18",        // MOST ACTIVE expiry (most total OI) — not the nearest
    "dte": 31,                     // days to that expiry
    "call_oi": 123456, "put_oi": 98765,
    "pc_ratio": 0.8,               // put_oi / call_oi (may be null)
    "top_calls": [ { "strike":360.0, "oi":50326, "volume":7413,
                     "price":8.3, "expiry":"2026-12-18" } ],   // exactly 10, sorted OI desc
    "top_puts":  [ /* same shape */ ]
  }
}
```

There is **no `symbol` and no `tv_url`** — build them in the browser:

```js
// OCC symbol: ROOT + YYMMDD + C|P + strike, strike un-padded, min one decimal
function occSymbol(tk, expiry, isCall, strike){
  var ymd = expiry.replace(/-/g,'').slice(2);              // 2026-12-18 -> 261218
  var st = strike.toFixed(3).replace(/0+$/,'');            // 360.000 -> "360."
  if (st.slice(-1) === '.') st += '0';                     // "360." -> "360.0"
  return tk + ymd + (isCall ? 'C' : 'P') + st;
}
function tvUrl(tk, expiry, isCall, strike){
  return 'https://www.tradingview.com/symbols/OPRA-' + occSymbol(tk, expiry, isCall, strike) + '/';
}
// e.g. AAPL + 2026-12-18 + call + 360 -> AAPL261218C360.0
//      -> https://www.tradingview.com/symbols/OPRA-AAPL261218C360.0/
```

## The UI

**Section** `#/` dashboard, near the other option content. Micro-label + big display
heading, same idiom as the rest of the app. Something like:

```
MARKET POSITIONING
LOOK UP YOUR OWN.
Type any ticker. See where the option money is sitting.
[ TICKER ] [ LOOK UP ]        ← input, uppercase, monospace, big
```

**On submit** (button or Enter):
1. `loadOI().then(...)` — show a quiet "Loading…" in the panel the first time.
2. `OI[tk]` → if missing, show: **"No option data for `ZZZZ`. The index covers the S&P 500
   and the tickers this app already tracks."** Keep it calm, never an error red.
3. Found → render:
   - A header row: **ticker** (+ company name from `nameOf` if the app knows it), the **spot**,
     **most-active expiry + DTE**, **P/C ratio** with a plain reading, and total call/put OI.
   - **Two columns: CALLS | PUTS.** Each a list of up to 10 rows sorted by OI descending.
   - Each row: **strike**, **open interest** (the loud number), the contract **price**, the
     row's own **expiry**, and a TradingView link (`target="_blank" rel="noopener
     noreferrer"`, small, muted — match the existing `TRADINGVIEW ↗` treatment).
   - Say what OI is, once, in the app's voice: open interest = contracts still open at that
     strike; big piles often act like walls.
   - **The same "positioning, not a prediction" caveat the options section already carries.**
     Do not imply bought vs sold — OI is directionless. This is a hard rule in this app.

**Interaction details**
- Uppercase and trim the input; accept lowercase.
- Remember the last looked-up ticker in `localStorage` and restore it on load (do NOT
  auto-fetch on boot — only refill the input).
- Empty input → gentle nudge, no fetch.
- Re-submitting the same ticker is fine (no extra fetch — `OI` is cached).
- Result must be reachable by keyboard; the input needs a real `<label>` (visually hidden
  is fine) and the results live in a `role="region"` with `aria-live="polite"`.

## Also add
- The inline fallback file: `web/data/oi_lookup.js` containing
  `window.__CAPITOL_OI_LOOKUP__ = {…};` — but **do not write that file yourself**, I will
  generate it. Just make the loader reference it the same way the app already does for
  options (`loadInline`). Check how `loadOptions()` handles this and copy exactly.

## Design rules (non-negotiable in this app)
- **Nike + Robinhood language**: bold black/white, mono uppercase micro-labels, big condensed
  headlines, high contrast, minimal chrome. One accent only.
- **No glassmorphism, no gradients, no glows** — the user hates them.
- Reuse existing classes and tokens from `styles.css` wherever possible. Only add CSS that
  is genuinely new; keep it at the end of the file under a clear comment.
- Numbers in tabular/mono figures. Strike and OI are the loud elements; price and expiry
  are quiet.

## Definition of done
- Section renders on the dashboard; typing `AAPL` + Enter shows 10 calls and 10 puts with
  TradingView links that match the format above (spot-check one URL by eye).
- `ZZZZ` shows the calm "no data" message.
- **A fresh page load issues NO request for `oi_lookup.json`** (verify in the network panel
  or by watching `performance.getEntriesByType('resource')`) — it is fetched only on first use.
- `node --check web/app.js` passes.
- No changes to any existing section's behaviour.
