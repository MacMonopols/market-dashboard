"""
fund_flows.py – Net purchases of corporate equities by US mutual funds and
ETFs, cumulated by calendar year (the shape of BofA/EPFR's "cumulative US
equity fund flows by year" chart, rebuilt from free data).

EPFR (BofA's source) is paid, and ICI's weekly flow files are behind a bot
wall (403 for any script, checked 2026-11-02), so this uses the Fed's
Financial Accounts (Z.1), table F.224, via FRED:
    BOGZ1FA653064100Q  mutual funds; corporate equities; asset, transactions ($m SAAR)
    BOGZ1FA563064100Q  ETFs; corporate equities; asset, transactions ($m SAAR)
    BOGZ1LM893064105Q  all sectors; corporate equities; level ($m, end of quarter)
Quarterly flow = SAAR / 4. The sum of mutual funds and ETFs is the headline:
mutual-fund-to-ETF conversions and the active-to-passive shift show up as a
mutual fund outflow and an ETF inflow, which net out.

Differences from EPFR fund flows (kept visible in the chart note):
- it is what the funds BUY (net), not what investors put in; the two differ
  by cash held and by flows into non-equity holdings;
- it covers equities held by every mutual fund (incl. hybrid funds) and both
  US and foreign equities, not only "US equity funds";
- quarterly, about one quarter behind (Q3 is published in December).

On fetch failure the last good result is taken from FUND_FLOWS_CACHE_PATH
(git-ignored) and flagged stale.
"""

import json
import os
import time
from datetime import date

from valuation_yields import _fetch_fred_series, _quarter_end_month

MF_SERIES = "BOGZ1FA653064100Q"
ETF_SERIES = "BOGZ1FA563064100Q"
MKTCAP_SERIES = "BOGZ1LM893064105Q"
FLOWS_START_YEAR = 1952     # Z.1 quarterly flows before 1952 are interpolated annual data

FUND_FLOWS_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "fund_flows_cache.json")

FUND_FLOWS_METHODOLOGY_NOTE = (
    "Net purchases of corporate equities by US mutual funds and ETFs (Fed Financial Accounts Z.1, "
    "table F.224, via FRED), cumulated within each calendar year; the latest year is year to date. "
    "Not the same measure as BofA/EPFR fund flows: it is what the funds buy, not what investors put "
    "in, covers all mutual funds (incl. hybrid) and foreign as well as US equities, and is quarterly "
    "with about one quarter of lag. Mutual fund outflows and ETF inflows largely reflect the shift from "
    "active funds to ETFs; their sum is the headline. Money leaving mutual funds for collective "
    "investment trusts (401(k) plans) or direct holdings is NOT offset here, which likely explains "
    "negative years such as 2025 (BofA/EPFR show strong inflows). % view = cumulative flow over the market value "
    "of all corporate equities held in the US at the start of the year (Z.1)."
)


def _fetch_raw():
    raw = {"fred": {}}
    for sid in (MF_SERIES, ETF_SERIES, MKTCAP_SERIES):
        raw["fred"][sid] = _fetch_fred_series(sid)
        time.sleep(1)                     # FRED blocks bursts
    raw["fetchedAt"] = date.today().isoformat()
    return raw


def _get_raw():
    try:
        raw = _fetch_raw()
        try:
            with open(FUND_FLOWS_CACHE_PATH, "w") as f:
                json.dump(raw, f)
        except OSError as e:
            print(f"  ⚠ could not write fund flows cache: {e}")
        return raw, False
    except Exception as e:
        try:
            with open(FUND_FLOWS_CACHE_PATH) as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            raise e
        print(f"  ⚠ live fund flows failed ({e}) — using cache from {raw['fetchedAt']}")
        return raw, True


def compute_fund_flows(mf, etf, mktcap):
    """Quarterly rows and per-year cumulative paths, $bn. Inputs are FRED dicts."""
    quarters = []
    for d in sorted(mf):
        if int(d[:4]) < FLOWS_START_YEAR or d not in mktcap:
            continue
        m = mf[d] / 4 / 1000
        e = etf.get(d, 0.0) / 4 / 1000
        quarters.append({"date": _quarter_end_month(d), "mfBn": round(m, 1), "etfBn": round(e, 1),
                         "totalBn": round(m + e, 1), "mktCapBn": round(mktcap[d] / 1000)})

    cap_end = {q["date"]: q["mktCapBn"] for q in quarters}
    years = []
    for y in sorted({int(q["date"][:4]) for q in quarters}):
        qs = [q for q in quarters if int(q["date"][:4]) == y]
        base = cap_end.get(f"{y - 1}-12") or qs[0]["mktCapBn"]   # market value at the start of the year
        cm = ce = 0.0
        path = [{"date": f"{y - 1}-12", "totalBn": 0.0, "mfBn": 0.0, "etfBn": 0.0, "totalPct": 0.0}]
        for q in qs:
            cm += q["mfBn"]
            ce += q["etfBn"]
            path.append({"date": q["date"], "totalBn": round(cm + ce, 1), "mfBn": round(cm, 1),
                         "etfBn": round(ce, 1), "totalPct": round(100 * (cm + ce) / base, 3)})
        n = len(qs)
        years.append({
            "year": y, "quarters": n, "startCapBn": base, "path": path,
            "totalBn": round(cm + ce, 1), "mfBn": round(cm, 1), "etfBn": round(ce, 1),
            "totalPct": round(100 * (cm + ce) / base, 3),
            # partial year: scaled to 12 months, like BofA's "YTD annualized"
            "annualizedBn": round((cm + ce) * 4 / n, 1),
            "annualizedPct": round(100 * (cm + ce) * 4 / n / base, 3),
        })
    return quarters, years


def calc_fund_flows():
    raw, stale = _get_raw()
    f = raw["fred"]
    quarters, years = compute_fund_flows(f[MF_SERIES], f[ETF_SERIES], f[MKTCAP_SERIES])
    full = [y for y in years if y["quarters"] == 4]
    return {
        "asOf": raw["fetchedAt"],
        "stale": stale,
        "lastQuarter": quarters[-1]["date"],
        "quarters": quarters,
        "years": years,
        "recordBn": max(full, key=lambda y: y["totalBn"]) if full else None,
        "recordPct": max(full, key=lambda y: y["totalPct"]) if full else None,
        "note": FUND_FLOWS_METHODOLOGY_NOTE,
    }


if __name__ == "__main__":
    ff = calc_fund_flows()
    for y in ff["years"][-14:]:
        print(f"{y['year']} q{y['quarters']}  total {y['totalBn']:8.1f}bn  (MF {y['mfBn']:8.1f}, ETF {y['etfBn']:7.1f})"
              f"  {y['totalPct']:5.2f}% of cap  ann. {y['annualizedBn']:8.1f}bn / {y['annualizedPct']:5.2f}%")
    for k in ("recordBn", "recordPct"):
        r = ff[k]
        print(k, r["year"], r["totalBn"], r["totalPct"])
