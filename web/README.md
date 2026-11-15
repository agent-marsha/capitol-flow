# Capitol Flow — web

Static, no-build web app: cluster signals, a trade feed that puts sales first, and per-stock
candlestick + Bollinger Band charts (Daily/Hourly) with the news for each stock.

## Preview locally

```bash
cd /root/capitol-flow          # repo root
python3 -m http.server 8000
# open http://localhost:8000/web/
```

Or open `web/index.html` straight from disk. On `file://` the app skips `fetch` and loads
`data/app_data.js` (`window.__CAPITOL_DATA__`) instead.

## Files

| File | Purpose |
|---|---|
| `index.html` | Page shell. Loads lightweight-charts from unpkg, then `app.js` |
| `styles.css` | All styling (dark, flat, mobile-first) |
| `app.js` | Data loading, hash routing (`#/stock/TICKER`), rendering, Bollinger maths, charts |
| `data/app_data.json` | Copy of `../data/app_data.json`, loaded with `fetch` |
| `data/app_data.js` | The same data wrapped as `window.__CAPITOL_DATA__ = {...};` for `file://` |
| `data/fundamentals.json` | Copy of `../data/fundamentals.json` (optional; powers "The basics") |
| `data/fundamentals.js` | The same wrapped as `window.__CAPITOL_FUNDAMENTALS__ = {...};` for `file://` |

## Regenerating the data copies

The `refresh.yml` workflow does this every day. To do it by hand:

```bash
mkdir -p web/data
cp data/app_data.json web/data/app_data.json
{ printf 'window.__CAPITOL_DATA__ = '; cat data/app_data.json; printf ';\n'; } > web/data/app_data.js

python3 pipeline/fundamentals.py --out data/fundamentals.json   # SEC EDGAR, ~4 min
cp data/fundamentals.json web/data/fundamentals.json
{ printf 'window.__CAPITOL_FUNDAMENTALS__ = '; cat data/fundamentals.json; printf ';\n'; } > web/data/fundamentals.js
```

## The basics (fundamentals)

Each stock page ends with **THE BASICS**: short cards that explain the company's official
10-K numbers (from SEC EDGAR XBRL) in plain English, at about a 4th-grade reading level.
Each card has a sentence and a small chart drawn with plain CSS (no chart library):

- `bars`: one column per year, showing the last 6 years. The newest year is the lighter bar. A loss is drawn as a dashed bar below the line.
- `bars2`: labelled horizontal bars. Green/red is used only for *Owns / In the bank* vs
  *Owes*, and only when the gap is at least 10%. Anything closer, or any label it doesn't know, stays grey.
- `split`: one bar split into two parts that add up to 100% (e.g. Kept vs Cost to make).

The card sentences are shown exactly as `pipeline/fundamentals.py` writes them. The file loads
separately from the main bundle and never holds up the page. If the file is missing, or a ticker
(ETF, fund, foreign listing) has no entry, the section is left out.

## Notes

- Bollinger Bands are a 20-period SMA ± 2σ (population σ), computed in the browser for each timeframe.
- Hourly bars are shown in US Eastern time.
- Buy and sell are never shown by colour alone. Labels read ▲ BUY / ▼ SELL, and candles are
  hollow when the price closed up and filled when it closed down. This is because the brand
  green and red look the same to people with red-green colour blindness.
- If the chart library can't load (for example, offline), the chart area shows a message and
  the price data table is still available.
- Tickers with no price data in the bundle still open a detail view with their trades and news.
  Trades with no ticker can't be opened.
