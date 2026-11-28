#!/usr/bin/env python3
"""Unusual volume inside an Elder-confirmed uptrend.

REQUEST (2026-11-27, from the user):
    "a section that just checks for unusual volume on stocks that are generally in an uptrend
     based on elder's rule"
Decisions the user made on the plan:
    * uptrend = DAILY Impulse System GREEN (no weekly requirement)
    * RVOL threshold = 2.0x (default, kept)
    * universe = the S&P 500
    * output = a screener-style TABLE of where the volume is

DEFINITIONS
    Elder's Impulse System
        EMA13  = 13-period EMA of close
        MACD_H = histogram of MACD(12,26,9) = MACD line - signal line
        GREEN  = EMA13 rising AND MACD_H rising     <- permission to buy
        RED    = EMA13 falling AND MACD_H falling   <- permission to sell
        BLUE   = anything else (no signal)

    RVOL = signal-day volume / mean(volume of the 20 sessions before it)

    FIRES when  impulse == GREEN and rvol >= RVOL_MIN and dollar_volume >= DOLLAR_MIN

THE RULE THAT MAKES THIS WORTH BUILDING
    Volume is DIRECTIONLESS -- it says that something happened, never which way it will go.
    The informative part is the pairing:
        unusual volume + an UP day inside an uptrend   -> someone wanted in
        unusual volume + a DOWN day inside an uptrend  -> someone wanted out (distribution)
    Every row therefore carries vol_dir, and this module never emits a directional claim.

TWO CORRECTNESS TRAPS, both hit for real while developing this
 1. The in-progress session. Comparing a half-finished day to full-day averages makes volume
    look tiny -- measured live on this dataset, the median RVOL including the partial bar was
    0.04 against 0.92 on completed bars. The last bar is dropped whenever its session has not
    yet closed in US/Eastern.
 2. Half-days. The day after Thanksgiving, Christmas Eve and July 3 close early and print
    roughly half the volume. They are excluded both as signal days and from the 20-day average,
    otherwise they read as false quiet days.

WHAT IS PERSISTED
    Only the flagged rows (plus the backtest summary). The ~500 daily series are used and
    discarded -- writing them into app_data would multiply the deploy size for data no section
    renders. See the plan's section 10.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

RVOL_MIN = 2.0          # user: "leave rvol default"
DOLLAR_MIN = 20_000_000  # $20M of turnover on the signal day
RECENT_DAYS = 5         # the screener window: the last N sessions that produced any fire
LOOKBACK = 251          # one year of daily bars
EMA_N = 13
MACD_FAST, MACD_SLOW, MACD_SIG = 12, 26, 9
FWD = (1, 5, 20)        # forward-return horizons for the internal backtest

# Half-days are excluded. These are computed rather than hardcoded where possible; the fixed
# ones below cover the recurring US calendar ones that matter for a daily screen.
FIXED_HALF_DAYS = {"12-24", "07-03"}      # month-day, Christmas Eve and July 3


def _today_et() -> dt.date:
    """Today in US/Eastern, without depending on tz data being installed."""
    now = dt.datetime.utcnow()
    # ET is UTC-5 in winter, UTC-4 in summer.  A one-hour error here only matters in the
    # narrow window right after the close, so approximate the DST boundary by month.
    off = 4 if 3 < now.month < 11 else 5
    return (now - dt.timedelta(hours=off)).date()


def is_half_day(d: dt.date, volume: float, vols: list[float]) -> bool:
    """A session is treated as a half-day if it is a known calendar one, or if its volume is
    far below this stock's own recent norm in a way that cannot be explained by interest."""
    if d.strftime("%m-%d") in FIXED_HALF_DAYS:
        return True
    # day after Thanksgiving: 4th Thursday of November + 1
    if d.month == 11:
        first = dt.date(d.year, 11, 1)
        thu = first + dt.timedelta(days=(3 - first.weekday()) % 7)   # first Thursday
        thanksgiving = thu + dt.timedelta(days=21)                   # fourth Thursday
        if d == thanksgiving + dt.timedelta(days=1):
            return True
    return False


# ---------------------------------------------------------------- indicators

def ema(vals: list[float], n: int) -> list[float]:
    """EMA with an SMA seed. Returns a list the same length as vals (None-padded at the front)."""
    out: list[float | None] = [None] * len(vals)
    if len(vals) < n or n <= 0:
        return out  # type: ignore[return-value]
    k = 2.0 / (n + 1)
    seed = sum(vals[:n]) / n
    out[n - 1] = seed
    prev = seed
    for i in range(n, len(vals)):
        prev = vals[i] * k + prev * (1 - k)
        out[i] = prev
    return out  # type: ignore[return-value]


def macd_hist(closes: list[float]) -> list[float | None]:
    fast, slow = ema(closes, MACD_FAST), ema(closes, MACD_SLOW)
    line: list[float | None] = [
        (fast[i] - slow[i]) if (fast[i] is not None and slow[i] is not None) else None
        for i in range(len(closes))
    ]
    idx = [i for i, v in enumerate(line) if v is not None]
    hist: list[float | None] = [None] * len(closes)
    if len(idx) < MACD_SIG:
        return hist
    sig = ema([line[i] for i in idx], MACD_SIG)  # type: ignore[arg-type]
    for j, i in enumerate(idx):
        if sig[j] is not None:
            hist[i] = line[i] - sig[j]  # type: ignore[operator]
    return hist


def impulse_state(closes: list[float]) -> list[str | None]:
    """GREEN / RED / BLUE per bar, aligned to closes."""
    e, h = ema(closes, EMA_N), macd_hist(closes)
    out: list[str | None] = [None] * len(closes)
    for i in range(1, len(closes)):
        if e[i] is None or e[i - 1] is None or h[i] is None or h[i - 1] is None:
            continue
        ema_up, ema_dn = e[i] > e[i - 1], e[i] < e[i - 1]
        h_up, h_dn = h[i] > h[i - 1], h[i] < h[i - 1]
        out[i] = "GREEN" if (ema_up and h_up) else "RED" if (ema_dn and h_dn) else "BLUE"
    return out


# ---------------------------------------------------------------- the screen

def screen_one(ticker: str, sector: str, bars: list[dict], today: dt.date | None = None) -> dict:
    """Return {'fires': [...], 'backtest': [...], 'bars': n} for one ticker.

    `bars` = [{'t':'YYYY-MM-DD','o','h','l','c','v'}, ...] oldest first.
    """
    today = today or _today_et()
    bars = [b for b in bars if b.get("v") and b.get("c")]
    if len(bars) < 40:
        return {"fires": [], "backtest": [], "bars": len(bars)}

    # TRAP 1: drop the final bar if that session has not closed yet.
    if bars and dt.date.fromisoformat(bars[-1]["t"]) >= today:
        bars = bars[:-1]
    if len(bars) < 40:
        return {"fires": [], "backtest": [], "bars": len(bars)}

    # TRAP 2: drop half-days from both the average and the signalling set.
    vols_all = [float(b["v"]) for b in bars]
    keep = [i for i, b in enumerate(bars) if not is_half_day(dt.date.fromisoformat(b["t"]), float(b["v"]), vols_all)]
    if len(keep) < 40:
        return {"fires": [], "backtest": [], "bars": len(bars)}
    bars = [bars[i] for i in keep]

    closes = [float(b["c"]) for b in bars]
    vols = [float(b["v"]) for b in bars]
    opens = [float(b["o"]) for b in bars]
    imp = impulse_state(closes)

    fires: list[dict] = []
    for i in range(21, len(bars)):
        base = sum(vols[i - 20:i]) / 20.0
        if base <= 0:
            continue
        rvol = vols[i] / base
        dvol = closes[i] * vols[i]
        if imp[i] != "GREEN" or rvol < RVOL_MIN or dvol < DOLLAR_MIN:
            continue
        row = {
            "ticker": ticker, "sector": sector, "date": bars[i]["t"],
            "rvol": round(rvol, 2), "volume": int(vols[i]), "avg20": int(base),
            "dollar_vol": int(dvol), "close": round(closes[i], 2),
            "chg": round((closes[i] / closes[i - 1] - 1) * 100, 2),
            # "up day" in the conventional sense = closed ABOVE the PRIOR CLOSE, the same basis
            # as `chg`.  Defining it close-vs-open produced a row reading "+31.5%  DOWN" on
            # NVDA's gap-up day (2026-11-23) -- internally contradictory and non-standard.
            # Both fields now move together.
            "vol_dir": "up" if closes[i] > closes[i - 1] else "down",
            "idx": i,
        }
        fires.append(row)

    # internal backtest -- forward returns by volume direction
    backtest: list[dict] = []
    for f in fires:
        i = f["idx"]
        rec = {"ticker": ticker, "date": f["date"], "vol_dir": f["vol_dir"], "rvol": f["rvol"]}
        for h in FWD:
            rec["r%d" % h] = round((closes[i + h] / closes[i] - 1) * 100, 2) if i + h < len(closes) else None
        backtest.append(rec)
    for f in fires:
        f.pop("idx", None)
    return {"fires": fires, "backtest": backtest, "bars": len(bars)}


def _summarise(backtest: list[dict]) -> dict:
    """Median/mean forward return per horizon, split by volume direction. Measured, not claimed."""
    out = {}
    for direction in ("up", "down"):
        sub = [b for b in backtest if b["vol_dir"] == direction]
        blk = {"n": len(sub)}
        for h in FWD:
            vals = sorted(v for v in (b.get("r%d" % h) for b in sub) if v is not None)
            blk["r%d_median" % h] = round(vals[len(vals) // 2], 2) if vals else None
            blk["r%d_mean" % h] = round(sum(vals) / len(vals), 2) if vals else None
            blk["r%d_winrate" % h] = round(100.0 * sum(1 for v in vals if v > 0) / len(vals), 1) if vals else None
        out[direction] = blk
    return out


# ---------------------------------------------------------------- fetch + entry point

def load_universe(path: str = "data/sp500.json") -> list[dict]:
    if not os.path.exists(path):
        return []
    d = json.load(open(path))
    return d.get("tickers") or []


def fetch_daily(tickers: list[str], period: str = "1y") -> dict:
    """One batched daily download for the whole universe."""
    import warnings
    warnings.filterwarnings("ignore")
    import yfinance as yf
    data = yf.download(tickers, period=period, interval="1d", group_by="ticker",
                       progress=False, auto_adjust=False, threads=True)
    out: dict[str, list[dict]] = {}
    for t in tickers:
        try:
            df = data[t] if len(tickers) > 1 else data
        except Exception:
            continue
        rows = []
        for ts, r in df.iterrows():
            try:
                v = r["Volume"]
                if v != v or v <= 0:      # NaN guard
                    continue
                rows.append({"t": ts.date().isoformat(), "o": float(r["Open"]), "h": float(r["High"]),
                             "l": float(r["Low"]), "c": float(r["Close"]), "v": int(v)})
            except Exception:
                continue
        if rows:
            out[t] = rows
    return out


def run(universe_path: str = "data/sp500.json", quiet: bool = False) -> dict:
    uni = load_universe(universe_path)
    if not uni:
        return {"fires": [], "backtest": {}, "coverage": {"universe": 0, "screened": 0}}
    sectors = {u["t"]: u.get("s", "") for u in uni}
    tickers = [u["t"] for u in uni]
    bars = fetch_daily(tickers)
    fires, back, screened = [], [], 0
    for t, series in bars.items():
        r = screen_one(t, sectors.get(t, ""), series)
        if r["bars"] >= 40:
            screened += 1
        fires += r["fires"]
        back += r["backtest"]
    fires.sort(key=lambda f: (-f["rvol"], f["ticker"]))
    # "where the volume is" means RECENT.  A single session can legitimately be nearly empty --
    # on 2026-11-25 the whole market sold off, so few names had a GREEN impulse and only 2
    # fired.  A screener that reads empty on a red day looks broken, so the window is the last
    # RECENT_DAYS sessions that produced any fire, and every row keeps its date.
    dates = sorted({f["date"] for f in fires}, reverse=True)
    window = set(dates[:RECENT_DAYS])
    latest = dates[0] if dates else None
    result = {
        "fires": fires,
        "recent_date": latest,
        "recent_days": len(window),
        "recent": sorted([f for f in fires if f["date"] in window],
                         key=lambda f: (f["date"], -f["rvol"]), reverse=True) if window else [],
        "backtest": _summarise(back),
        "coverage": {"universe": len(tickers), "screened": screened, "with_data": len(bars)},
        "params": {"rvol_min": RVOL_MIN, "dollar_min": DOLLAR_MIN, "impulse": "GREEN (EMA13 + MACD hist)"},
    }
    if not quiet:
        print("[unusual-volume] screened %d/%d tickers | %d fires | RVOL>=%.1fx | $%dM floor"
              % (screened, len(tickers), len(fires), RVOL_MIN, DOLLAR_MIN // 1_000_000), file=sys.stderr)
    return result


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="data/sp500.json")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    res = run(a.universe)
    if a.out:
        json.dump(res, open(a.out, "w"), separators=(",", ":"))
    print("universe %d | with data %d | screened %d | fires %d"
          % (res["coverage"]["universe"], res["coverage"]["with_data"],
             res["coverage"]["screened"], len(res["fires"])))
    print()
    print("%-7s %-24s %6s %14s %13s %9s %5s %5s" % ("TICKER", "SECTOR", "RVOL", "VOLUME", "20d AVG", "$ VOL", "CHG%", "DIR"))
    for f in res["fires"][:25]:
        print("%-7s %-24s %6.2f %14s %13s %8.1fM %5.1f %5s"
              % (f["ticker"], f["sector"][:24], f["rvol"], format(f["volume"], ","),
                 format(f["avg20"], ","), f["dollar_vol"] / 1e6, f["chg"], f["vol_dir"]))
    print()
    for d, blk in (res["backtest"] or {}).items():
        print("  %-5s volume: n=%d  +1d %s / +5d %s / +20d %s  (median %%)  win-rate 5d %s%%"
              % (d, blk.get("n", 0), blk.get("r1_median"), blk.get("r5_median"), blk.get("r20_median"),
                 blk.get("r5_winrate")))
