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

## Regenerating the data copies

The `refresh.yml` workflow does this every day. To do it by hand:

```bash
mkdir -p web/data
cp data/app_data.json web/data/app_data.json
{ printf 'window.__CAPITOL_DATA__ = '; cat data/app_data.json; printf ';\n'; } > web/data/app_data.js
```

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
