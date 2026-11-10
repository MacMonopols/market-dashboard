"""
market_timing.py – "The cost of trying to time the market": growth of 1,000
invested at the start of 2001 in the US stock market, fully invested vs
missing the best consecutive week / month / 3 months / 6 months (5 / 21 / 63
/ 126 trading days held in cash at 0 %), after Dimensional's Quick Take PDF
(Russell 3000 Index total return, 2001–2025, MKT-62880 06/26).

- `DIMENSIONAL` = values hand-transcribed from that PDF (Russell 3000 index
  data is not free).
- Own views, 2001 to the last close: iShares Russell 3000 ETF `IWV` (Yahoo,
  dividends reinvested, `auto_adjust=True`), in USD and in CHF (USD/CHF =
  FRED H.10 `DEXSZUS`, Yahoo `USDCHF=X` for the days after FRED's last
  point). The ETF carries its fees (~0.2 %/yr), so it ends ~3 % below the
  index over 25 years; the best-period end dates come out identical.

Cache market_timing_cache.json (git-ignored), `stale: true` on fallback.
"""

import json
import os
from datetime import date

import numpy as np
import pandas as pd

from valuation_yields import _fetch_fred_series

TICKER = "IWV"
START = "2001-01-01"
PERIODS = [("Week", 5), ("Month", 21), ("3 Months", 63), ("6 Months", 126)]

DIMENSIONAL = {
    "label": "Russell 3000 Index (Dimensional)", "ccy": "USD", "start": "2001-01-01", "end": "2025-12-31",
    "total": 8360,
    "missed": [
        {"label": "Week",     "days": 5,   "value": 6977, "end": "2008-11-28"},
        {"label": "Month",    "days": 21,  "value": 6676, "end": "2020-04-22"},
        {"label": "3 Months", "days": 63,  "value": 5893, "end": "2020-06-22"},
        {"label": "6 Months", "days": 126, "value": 5425, "end": "2009-09-04"},
    ],
    "source": "Dimensional, \"The Cost of Trying to Time the Market\" (Quick Take, 06/26)",
}

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_timing_cache.json")

NOTE = (
    "Hypothetical growth of 1,000 invested at the start of 2001, dividends reinvested, no costs or taxes. "
    "\"Missing the best …\" = sold at the close before the best run of 5 / 21 / 63 / 126 consecutive trading "
    "days, held in cash at 0 % for that run, then reinvested everything (Dimensional's method). "
    "Dimensional view: Russell 3000 Index, values from their PDF. Own views: iShares Russell 3000 ETF (IWV, "
    "Yahoo Finance), net of the fund's fees, so about 3 % below the index over 25 years — on 2001–2025 it "
    "gives {val}, and the same best-period dates. CHF view: the USD series converted at the daily USD/CHF "
    "rate (FRED H.10), cash held in CHF. Past performance is not a guide to future returns."
)


def _missed(levels, dates, total):
    """For each period: value of 1,000 when the best n-day run is skipped."""
    out = []
    for label, n in PERIODS:
        w = levels[n:] / levels[:-n]
        i = int(w.argmax())
        out.append({"label": label, "days": n, "value": round(total / w[i]),
                    "end": dates[i + n - 1], "periodReturn": round((w[i] - 1) * 100, 1)})
    return out


def _view(series, label, ccy, end=None):
    s = series.dropna()
    base = s[s.index < START].iloc[-1]
    s = s[s.index >= START]
    if end:
        s = s[s.index <= end]
    lv = np.concatenate([[base], s.values])
    dates = [d.date().isoformat() for d in s.index]
    total = 1000 * lv[-1] / lv[0]
    years = (s.index[-1] - pd.Timestamp(START)).days / 365.25
    return {"label": label, "ccy": ccy, "start": START, "end": dates[-1], "total": round(total),
            "annualized": round(((total / 1000) ** (1 / years) - 1) * 100, 2),
            "missed": _missed(lv, dates, total)}


def _compute(today=None):
    import yfinance as yf
    today = pd.Timestamp(today or date.today())
    end = (today + pd.Timedelta(days=1)).date().isoformat()
    px = yf.download([TICKER, "USDCHF=X"], start="2000-12-01", end=end, auto_adjust=True, progress=False)["Close"]
    px.index = px.index.tz_localize(None) if px.index.tz is not None else px.index
    usd = px[TICKER].dropna()

    fred = pd.Series(_fetch_fred_series("DEXSZUS"))
    fred.index = pd.to_datetime(fred.index)
    fred = fred.sort_index().astype(float)
    yfx = px["USDCHF=X"].dropna()
    fx = pd.concat([fred, yfx[yfx.index > fred.index[-1]]])
    chf = usd * fx.reindex(usd.index, method="ffill")

    validation = _view(usd, "IWV", "USD", end="2025-12-31")
    views = [
        dict(DIMENSIONAL, key="dim"),
        dict(_view(usd, "Russell 3000 ETF (IWV) in USD", "USD"), key="usd", source=f"Yahoo Finance ({TICKER})"),
        dict(_view(chf, "Russell 3000 ETF (IWV) in CHF", "CHF"), key="chf",
             source=f"Yahoo Finance ({TICKER}), FRED DEXSZUS"),
    ]
    return {"asOf": views[1]["end"], "views": views,
            "validation": validation,
            "note": NOTE.format(val=f"{validation['total']:,} instead of {DIMENSIONAL['total']:,}".replace(",", "'"))}


def calc_market_timing():
    try:
        res = _compute()
        try:
            with open(CACHE_PATH, "w") as f:
                json.dump(res, f)
        except OSError as e:
            print(f"  ⚠ could not write market timing cache: {e}")
        res["stale"] = False
        return res
    except Exception as e:
        try:
            with open(CACHE_PATH) as f:
                res = json.load(f)
        except (OSError, json.JSONDecodeError):
            raise e
        print(f"  ⚠ market timing fetch failed ({e}) — using cache as of {res.get('asOf')}")
        res["stale"] = True
        return res


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    r = calc_market_timing()
    print("as of", r["asOf"], "validation 2001-2025:", r["validation"]["total"],
          [(m["value"], m["end"]) for m in r["validation"]["missed"]])
    for v in r["views"]:
        print(v["key"], v["end"], v["total"], [(m["value"], m["end"]) for m in v["missed"]])
