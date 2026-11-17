"""
sector_rotation.py – Relative Rotation Graph (RRG) of the 11 US sectors and of
the main style factors against the S&P 500 (SPY), for the Market Signal tab.

Idea after Julius de Kempenaer's RRG: each ETF is placed by
  x = RS-Ratio    – its relative strength vs SPY compared with its own trend
  y = RS-Momentum – the rate of change of that RS-Ratio
centred on 100, giving four quadrants that are normally crossed clockwise:
Leading (x>100, y>100) → Weakening (x>100, y<100) → Lagging (x<100, y<100)
→ Improving (x<100, y>100).

The exact JdK formulas are proprietary; this is an OPEN APPROXIMATION on weekly
closes (Friday, from Yahoo daily closes, auto_adjust=True — total return):
  rs        = 100 × ETF / SPY, smoothed by an EMA of `RS_SMOOTH` weeks
  RS-Ratio  = 100 × rs / SMA(rs, `RATIO_WINDOW` weeks)
  RS-Mom    = 100 × RS-Ratio / RS-Ratio `MOM_LAG` weeks earlier
The last point uses the latest daily close (partial week).

Quadrant changes are flagged "unconfirmed" until the ETF has stayed
`CONFIRM_WEEKS` weekly closes in its new quadrant (many rotations abort after
2–3 weeks). Factor ETFs overlap heavily (QUAL and MTUM are both heavy in large
tech), so the factor RRG shows style tilts, not pure long/short factors.

Cache sector_rotation_cache.json (git-ignored), `stale: true` on fallback.
"""

import json
import os
from datetime import date

import numpy as np
import pandas as pd

BENCH = "SPY"
SECTORS = [
    ("XLK", "Technology"), ("XLC", "Communication Services"), ("XLY", "Consumer Discretionary"),
    ("XLF", "Financials"), ("XLI", "Industrials"), ("XLB", "Materials"), ("XLE", "Energy"),
    ("XLV", "Health Care"), ("XLP", "Consumer Staples"), ("XLU", "Utilities"), ("XLRE", "Real Estate"),
]
FACTORS = [
    ("MTUM", "Momentum"), ("USMV", "Min Volatility"), ("QUAL", "Quality"), ("VLUE", "Value (MSCI)"),
    ("IWD", "Value (Russell 1000)"), ("IWF", "Growth (Russell 1000)"), ("IWM", "Small Caps (Russell 2000)"),
    ("RSP", "Equal-Weight S&P 500"),
]
RS_SMOOTH = 4        # EMA span (weeks) on the raw relative strength
RATIO_WINDOW = 26    # trend of the relative strength (weeks)
MOM_LAG = 4          # momentum = change of RS-Ratio over 4 weeks
TAIL_WEEKS = 8       # trail drawn on the graph
HISTORY_WEEKS = 104  # weekly points kept (for the date slider)
CONFIRM_WEEKS = 2    # weekly closes in a new quadrant before a change counts
DATA_START_DAYS = 3 * 365

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sector_rotation_cache.json")

NOTE = (
    "Relative Rotation Graph after Julius de Kempenaer, OPEN APPROXIMATION (the JdK formulas are proprietary): "
    f"weekly total-return closes from Yahoo; relative strength = ETF / SPY smoothed over {RS_SMOOTH} weeks; "
    f"RS-Ratio = relative strength vs its {RATIO_WINDOW}-week average (100 = on trend); RS-Momentum = change of "
    f"the RS-Ratio over {MOM_LAG} weeks (100 = flat). The last point uses the latest close (partial week). "
    f"A quadrant change is shown as unconfirmed until it has held {CONFIRM_WEEKS} weekly closes. Price-based, so "
    "late by construction, and many rotations abort within 2–3 weeks. Factor ETFs overlap (MTUM and QUAL are "
    "both heavy in large tech): read them as style tilts, not pure factors. Not investment advice."
)


def quadrant(x, y):
    if x >= 100:
        return "Leading" if y >= 100 else "Weakening"
    return "Improving" if y >= 100 else "Lagging"


def _weekly(px):
    """Friday closes; the last (possibly partial) week is stamped with its last trading day."""
    w = px.resample("W-FRI").last()
    last_day = px.index[-1]
    idx = list(w.index)
    if idx[-1] > last_day:
        idx[-1] = last_day
    w.index = pd.DatetimeIndex(idx)
    return w.dropna(how="all")


def _rrg(w, ticker):
    rs = (100 * w[ticker] / w[BENCH]).ewm(span=RS_SMOOTH, adjust=False).mean()
    ratio = 100 * rs / rs.rolling(RATIO_WINDOW).mean()
    mom = 100 * ratio / ratio.shift(MOM_LAG)
    return ratio, mom


def _group(w, items):
    out = []
    dates = w.index[-HISTORY_WEEKS:]
    for t, name in items:
        if t not in w.columns or w[t].dropna().empty:
            continue
        ratio, mom = _rrg(w, t)
        ratio, mom = ratio.reindex(dates), mom.reindex(dates)
        quads = [quadrant(x, y) if np.isfinite(x) and np.isfinite(y) else None for x, y in zip(ratio, mom)]
        # confirmed quadrant: switch only after CONFIRM_WEEKS consecutive weeks in a new one
        conf, cur, run, cand = [], None, 0, None
        for q in quads:
            if q is None:
                conf.append(cur)
                continue
            if cur is None:
                cur = q
            elif q != cur:
                run = run + 1 if q == cand else 1
                cand = q
                if run >= CONFIRM_WEEKS:
                    cur, run, cand = q, 0, None
            else:
                run, cand = 0, None
            conf.append(cur)
        # last confirmed change
        last_change, prev_q = None, None
        for i in range(len(conf) - 1, 0, -1):
            if conf[i] is not None and conf[i - 1] is not None and conf[i] != conf[i - 1]:
                last_change, prev_q = dates[i].date().isoformat(), conf[i - 1]
                break
        weeks_in = 0
        for q in reversed(conf):
            if q == conf[-1]:
                weeks_in += 1
            else:
                break
        perf = lambda n: round(float((w[t].iloc[-1] / w[t].iloc[-1 - n]) / (w[BENCH].iloc[-1] / w[BENCH].iloc[-1 - n]) * 100 - 100), 1)
        out.append({
            "ticker": t, "name": name,
            "x": [None if not np.isfinite(v) else round(float(v), 2) for v in ratio],
            "y": [None if not np.isfinite(v) else round(float(v), 2) for v in mom],
            "quadrant": quads[-1], "confirmed": conf[-1],
            "pending": quads[-1] != conf[-1],
            "weeksIn": weeks_in, "lastChange": last_change, "from": prev_q,
            "quadrant4w": conf[-1 - 4] if len(conf) > 4 else None,
            "quadrant8w": conf[-1 - 8] if len(conf) > 8 else None,
            "rel4w": perf(4), "rel13w": perf(13),
        })
    return out


def _compute(today=None):
    import yfinance as yf
    today = pd.Timestamp(today or date.today())
    start = (today - pd.Timedelta(days=DATA_START_DAYS)).date().isoformat()
    end = (today + pd.Timedelta(days=1)).date().isoformat()
    tickers = [BENCH] + [t for t, _ in SECTORS + FACTORS]
    px = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)["Close"]
    px.index = px.index.tz_localize(None) if px.index.tz is not None else px.index
    px = px[px[BENCH].notna()].ffill()
    missing = [t for t in tickers if t not in px.columns or px[t].dropna().empty]
    if BENCH in missing or len(missing) > 3:
        raise RuntimeError(f"no Yahoo data for {missing}")
    w = _weekly(px)
    dates = [d.date().isoformat() for d in w.index[-HISTORY_WEEKS:]]
    return {
        "asOf": px.index[-1].date().isoformat(),
        "dates": dates,
        "params": {"rsSmooth": RS_SMOOTH, "ratioWindow": RATIO_WINDOW, "momLag": MOM_LAG,
                   "tailWeeks": TAIL_WEEKS, "confirmWeeks": CONFIRM_WEEKS, "bench": BENCH},
        "sectors": _group(w, SECTORS),
        "factors": _group(w, FACTORS),
        "missing": missing,
        "note": NOTE,
    }


def calc_sector_rotation():
    try:
        res = _compute()
        try:
            with open(CACHE_PATH, "w") as f:
                json.dump(res, f)
        except OSError as e:
            print(f"  ⚠ could not write sector rotation cache: {e}")
        res["stale"] = False
        return res
    except Exception as e:
        try:
            with open(CACHE_PATH) as f:
                res = json.load(f)
        except (OSError, json.JSONDecodeError):
            raise e
        print(f"  ⚠ sector rotation fetch failed ({e}) — using cache as of {res.get('asOf')}")
        res["stale"] = True
        return res


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    r = calc_sector_rotation()
    print("as of", r["asOf"], "weeks", len(r["dates"]), "missing", r["missing"])
    for g in ("sectors", "factors"):
        print(f"\n{g}")
        for s in r[g]:
            print(f"  {s['ticker']:5} {s['x'][-1]:7.2f} {s['y'][-1]:7.2f} {s['quadrant']:9} conf={s['confirmed']:9} "
                  f"{s['weeksIn']:3}w  last change {s['lastChange']} from {s['from']}  4w:{s['quadrant4w']}  "
                  f"rel4w {s['rel4w']:+.1f} rel13w {s['rel13w']:+.1f}")
    print("json size", len(json.dumps(r)))
