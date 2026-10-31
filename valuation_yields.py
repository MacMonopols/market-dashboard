"""
valuation_yields.py – US equity valuation through three yields on one scale:

  1. FCF yield of the whole US corporate sector (listed + unlisted), rebuilt
     from official macro data with the method of Atkeson, Heathcote & Perri,
     "A Macroeconomic Perspective on Stock Market Valuation Ratios"
     (Minneapolis Fed Staff Report 682 / NBER WP 34748, 2026).  Quarterly, 1952 →.
  2. Shiller cyclically adjusted earnings yield = 1 / CAPE.  Monthly, 1881 →.
  3. US 10-year government bond yield (Shiller long rate before 1953, then the
     10Y constant-maturity Treasury).  Monthly, 1871 →.

FCF yield (AHP, Section 2 + Appendix A):
    FCF = GVA − compensation − (taxes on production & imports − subsidies)
          − business current transfers − taxes on corporate income − investment
    V   = market value of the nonfinancial assets of nonfinancial corporates
          + domestic financial sectors  (Z.1 = equity + FDI equity + liabilities
          − financial assets, i.e. enterprise value)
    yield = FCF (SAAR) / V (end of quarter), no smoothing, as in the paper.

FRED series (one request per series: mixing flow and end-of-period series in
one fredgraph.csv call returns a zip, see CLAUDE.md "FRED fetch quirks"):
    NIPA T1.14, corporate business, $bn SAAR:
        A451RC1Q027SBEA GVA · A442RC1Q027SBEA compensation ·
        W321RC1Q027SBEA taxes on production less subsidies ·
        W323RC1Q027SBEA business current transfers (net) ·
        A054RC1Q027SBEA taxes on corporate income (domestic industries)
    Z.1, $m SAAR:
        BOGZ1FA105019985Q nonfin. corp. gross fixed investment + inventories (IMA)
        FBGFEEQ027S       domestic financial sectors gross fixed investment
    Z.1, $m, end of quarter:
        BOGZ1LM102010405Q nonfin. corp. market value of nonfinancial assets
        BOGZ1LM792010405Q domestic financial sectors, same

Known gaps vs the paper (kept visible in the chart note):
- The paper's exact investment lines (FA105019085 / FA105020005 / FA795013005)
  are not on FRED; the IMA total above is the closest available. Financial
  sector residential investment is not included (small).
- Checked 2026-10-31 against the paper's published figures: 1980Q2–1981Q1
  average 3.11 % (paper 3.10 %), 2021Q4–2022Q3 3.20 % (paper 3.07 %), mean
  since 1952 3.23 % (paper 3.18 %). The recent level is HIGHER than the
  paper's (3.5 % at 2026Q1 vs 2.59 % published), most likely the FDI /
  residence-basis adjustment to V and data vintages. The published 2.59 %
  point is therefore drawn as a marker next to the rebuilt line.

CAPE and long rate: multpl.com monthly tables (Shiller data, updated daily
for the current month). Shiller's own ie_data.xls moves URL on every update
and needs xlrd, hence multpl. On any fetch failure the last good result is
taken from VALUATION_CACHE_PATH (git-ignored) and flagged stale.
"""

import csv
import io
import json
import os
import re
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
MULTPL_CAPE_URL = "https://www.multpl.com/shiller-pe/table/by-month"
MULTPL_10Y_URL = "https://www.multpl.com/10-year-treasury-rate/table/by-month"

NIPA_FLOWS_BN = ["A451RC1Q027SBEA", "A442RC1Q027SBEA", "W321RC1Q027SBEA",
                 "W323RC1Q027SBEA", "A054RC1Q027SBEA"]
Z1_INVEST_M = ["BOGZ1FA105019985Q", "FBGFEEQ027S"]
Z1_VALUE_M = ["BOGZ1LM102010405Q", "BOGZ1LM792010405Q"]

FCF_START = "1952-01-01"      # annual before 1952 on FRED; the paper's quarterly sample starts 1952
CAPE_START = "1881-01"        # first month with 10 full years of earnings in Shiller's data

# Published reference points (AHP, NBER WP 34748 revision)
AHP_PUBLISHED = {"date": "2026-03", "pct": 2.59, "meanPct": 3.18}

VALUATION_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "valuation_yields_cache.json")

VALUATION_METHODOLOGY_NOTE = (
    "FCF yield: free cash flow of the whole US corporate sector (listed and unlisted) over its "
    "enterprise value, rebuilt from BEA NIPA table 1.14 and Fed Z.1 (via FRED) with the method of "
    "Atkeson, Heathcote & Perri (Minneapolis Fed Staff Report 682, 2026): FCF = gross value added − "
    "compensation − production taxes − business transfers − corporate income tax − gross investment; "
    "quarterly, not smoothed. It matches the paper's published averages (1980–81: 3.1 %, 2021–22: "
    "3.1–3.2 %, mean ~3.2 %) but sits above its latest figure (2.59 % at Q1 2026, shown as a dot), "
    "most likely because the paper's FDI/residence adjustment to enterprise value is not replicated. "
    "Treat the last two years of the rebuilt line as indicative. Earnings yield = 1 / Shiller CAPE "
    "(10-year average of real earnings, so a real yield); 10Y = Shiller long rate before 1953, then "
    "the 10-year Treasury (nominal). Sources: FRED, multpl.com (Shiller data)."
)


def _fetch_fred_series(series_id, tries=3):
    """{YYYY-MM-DD: float}. Default requests User-Agent on purpose (a browser UA
    gets tarpitted by FRED, see CLAUDE.md)."""
    last_err = None
    for attempt in range(tries):
        try:
            r = requests.get(FRED_CSV_URL, params={"id": series_id}, timeout=30)
            r.raise_for_status()
            if r.content[:2] == b"PK":
                raise ValueError(f"FRED returned a zip for {series_id}")
            out = {}
            for row in csv.DictReader(io.StringIO(r.text)):
                v = row.get(series_id)
                if v and v != ".":
                    out[row["observation_date"]] = float(v)
            if not out:
                raise ValueError(f"empty FRED series {series_id}")
            return out
        except Exception as e:
            last_err = e
            time.sleep(2 + 3 * attempt)
    raise RuntimeError(f"FRED {series_id}: {last_err}")


_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _fetch_multpl_monthly(url):
    """{YYYY-MM: float} from a multpl.com 'table/by-month' page. The table is
    newest first and its top row is today's value inside the current month,
    which then repeats that month: the first-seen (= latest) value wins."""
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (market-dashboard)"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out = {}
    for tr in soup.select("#datatable tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) < 2:
            continue
        m = re.match(r"([A-Z][a-z]{2}) \d{1,2}, (\d{4})", tds[0])
        val = re.search(r"-?\d+(?:\.\d+)?", tds[1].replace(",", ""))
        if not m or not val:
            continue
        key = f"{m.group(2)}-{_MONTHS[m.group(1)]:02d}"
        out.setdefault(key, float(val.group()))
    if len(out) < 1000:
        raise ValueError(f"multpl table too short ({len(out)} rows): {url}")
    return out


def _quarter_end_month(fred_date):
    """FRED dates a quarter by its first day; Z.1 levels are end of quarter."""
    y, m = int(fred_date[:4]), int(fred_date[5:7])
    return f"{y}-{m + 2:02d}"


def compute_fcf_yield(flows, invest, values):
    """flows / invest / values: {series_id: {date: float}} → [{date, pct}]."""
    out = []
    for d in sorted(flows[NIPA_FLOWS_BN[0]]):
        if d < FCF_START:
            continue
        try:
            gva, comp, tpi, bct, ctax = (flows[s][d] for s in NIPA_FLOWS_BN)
            inv_bn = sum(invest[s][d] for s in Z1_INVEST_M) / 1000
            v_bn = sum(values[s][d] for s in Z1_VALUE_M) / 1000
        except KeyError:
            continue                      # quarter not yet published in every series
        fcf = gva - comp - tpi - bct - ctax - inv_bn
        out.append({"date": _quarter_end_month(d), "pct": round(100 * fcf / v_bn, 3)})
    return out


def _fetch_raw():
    raw = {"fred": {}}
    for sid in NIPA_FLOWS_BN + Z1_INVEST_M + Z1_VALUE_M:
        raw["fred"][sid] = _fetch_fred_series(sid)
        time.sleep(1)                     # FRED blocks bursts
    raw["cape"] = _fetch_multpl_monthly(MULTPL_CAPE_URL)
    raw["tenYear"] = _fetch_multpl_monthly(MULTPL_10Y_URL)
    raw["spPrice"] = _fetch_multpl_monthly(MULTPL_PRICE_URL)
    raw["spDivYield"] = _fetch_multpl_monthly(MULTPL_DIVYIELD_URL)
    for sid in (DEFLATOR_SERIES, EXPINF_SERIES):
        raw["fred"][sid] = _fetch_fred_series(sid)
        time.sleep(1)
    raw["fetchedAt"] = date.today().isoformat()
    return raw


def get_valuation_raw():
    """(raw, stale): live FRED + multpl data, or the last good cache. Shared by
    calc_valuation_yields() and calc_expected_return() so FRED is hit once."""
    try:
        raw = _fetch_raw()
        try:
            with open(VALUATION_CACHE_PATH, "w") as f:
                json.dump(raw, f)
        except OSError as e:
            print(f"  ⚠ could not write valuation cache: {e}")
        return raw, False
    except Exception as e:
        try:
            with open(VALUATION_CACHE_PATH) as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            raise e
        print(f"  ⚠ live valuation data failed ({e}) — using cache from {raw['fetchedAt']}")
        return raw, True


def calc_valuation_yields(raw=None, stale=False):
    if raw is None:
        raw, stale = get_valuation_raw()
    f = raw["fred"]
    fcf = compute_fcf_yield({s: f[s] for s in NIPA_FLOWS_BN},
                            {s: f[s] for s in Z1_INVEST_M},
                            {s: f[s] for s in Z1_VALUE_M})
    ey = [{"date": d, "pct": round(100 / v, 3)}
          for d, v in sorted(raw["cape"].items()) if d >= CAPE_START and v > 0]
    ten = [{"date": d, "pct": v} for d, v in sorted(raw["tenYear"].items()) if d >= CAPE_START]
    fcf_mean = round(sum(r["pct"] for r in fcf) / len(fcf), 2) if fcf else None

    return {
        "asOf": raw["fetchedAt"],
        "stale": stale,
        "fcfYield": fcf,
        "fcfMeanPct": fcf_mean,
        "earningsYield": ey,
        "capeLatest": raw["cape"][max(raw["cape"])],
        "tenYear": ten,
        "ahpPublished": AHP_PUBLISHED,
        "note": VALUATION_METHODOLOGY_NOTE,
    }


# ── Expected return (Gordon) vs realized return ──────────────────────────────
#
#   E[R]_t = Y_t · (1 + g_t) + g_t          (Gordon, D1 = D0·(1+g))
#
#   Dividend version (monthly, 1881 →): Y = S&P 500 trailing-12m dividend
#     yield, g = trailing 10-year CAGR of the nominal dividend per share
#     (D = yield × price). Ex ante: only data known at t.
#   FCF version (quarterly, 1962 →): Y = corporate-sector FCF yield above,
#     g = trailing 10-year CAGR of nominal corporate gross value added (NIPA
#     A451). Aggregate FCF itself is too erratic (and sometimes near zero) to
#     give a usable growth rate; AHP's model keeps FCF/GVA roughly
#     mean-reverting, so GVA growth is the long-run FCF growth.
#   Realized (monthly, 1871 →): S&P 500 nominal total return, dividends
#     reinvested monthly (Shiller method: (P_t + D_t/12) / P_{t-1}),
#     annualized over the NEXT 1, 5 and 10 years, plotted at the start date.

MULTPL_PRICE_URL = "https://www.multpl.com/s-p-500-historical-prices/table/by-month"
# NB: multpl's "S&P 500 Dividend" table is inflation-adjusted; the dividend
# YIELD table is a plain nominal ratio, so nominal D = yield × price.
MULTPL_DIVYIELD_URL = "https://www.multpl.com/s-p-500-dividend-yield/table/by-month"
GVA_SERIES = "A451RC1Q027SBEA"
GROWTH_YEARS = 10
# Smoothed g for a third line: trailing 20y REAL growth of corporate GVA
# (deflated by the GDP deflator) + expected inflation (Cleveland Fed 10-year
# expected inflation from 1982; before that, trailing 10y GDP-deflator
# inflation as an adaptive-expectations proxy). Removes the inflation burst
# of 2021-23 (and the post-2008 trough) from the trailing nominal g.
DEFLATOR_SERIES = "GDPDEF"
EXPINF_SERIES = "EXPINF10YR"
REAL_GROWTH_YEARS = 20
# Multiple-reversion scenarios (GMO / Research Affiliates style): the
# smoothed-g E[R] plus the annualized effect of the Shiller CAPE moving from
# its level at t to a target over the next 10 years:
#   E[R]_scen = (1 + E[R]) · (target / CAPE_t)^(1/10) − 1
SCENARIO_CAPES = (30, 25)
SCENARIO_YEARS = 10
HORIZONS = (1, 5, 10)

EXPECTED_RETURN_METHODOLOGY_NOTE = (
    "Expected return = Gordon growth model, E[R] = yield × (1 + g) + g, using only data known at "
    "each date. Dividend version: S&P 500 trailing dividend yield + trailing 10-year growth of the "
    "nominal dividend (Shiller data via multpl.com). FCF version: US corporate-sector FCF yield "
    "(card above) + trailing 10-year growth of nominal corporate gross value added (BEA, via FRED). "
    "Dashed FCF line: same yield with a smoothed g = trailing 20-year real growth of corporate value "
    "added + expected inflation (Cleveland Fed 10-year, from 1982; trailing 10-year GDP-deflator "
    "inflation before), which strips out inflation bursts and slumps from the trailing nominal g. "
    "Dotted lines: the same smoothed-g expected return if the Shiller CAPE moved from its level at "
    "each date to 30 or 25 over the following 10 years (multiple-reversion scenarios); not a forecast "
    "of the CAPE, a way to show what a given change in valuation does to the 10-year return. "
    "Realized = S&P 500 nominal total return over the NEXT 1, 5 or 10 years (dividends reinvested), "
    "annualized and plotted at the start date, so the line stops h years before today. The gap "
    "between realized and expected is mostly the change in valuation multiples, which Gordon "
    "assumes away: large over 1 year, much smaller over 10. Since the 1980s buybacks have replaced "
    "part of dividends, so the dividend version understates expected returns. Overlapping windows: "
    "since 1881 there are only ~14 independent 10-year periods, so R² values are indicative. "
    "Nominal, in USD; the FCF yield covers all US corporations, the realized return the S&P 500 only."
)


def _shift_month(ym, months):
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) + months
    return f"{t // 12}-{t % 12 + 1:02d}"


def _r2(pairs):
    n = len(pairs)
    if n < 10:
        return None
    mx = sum(a for a, _ in pairs) / n
    my = sum(b for _, b in pairs) / n
    sxy = sum((a - mx) * (b - my) for a, b in pairs)
    sxx = sum((a - mx) ** 2 for a, _ in pairs)
    syy = sum((b - my) ** 2 for _, b in pairs)
    return round(sxy * sxy / (sxx * syy), 3) if sxx and syy else None


def compute_expected_return(price, div_yield, gva, fcf_yield, deflator=None, expinf=None, cape=None):
    """price / div_yield: {YYYY-MM: float} (yield in %), gva: {FRED date: $bn},
    fcf_yield: [{date: YYYY-MM (quarter end), pct}] → dict of series."""
    months = sorted(set(price) & set(div_yield))
    div = {m: div_yield[m] / 100 * price[m] for m in months}

    # Total-return index (monthly reinvestment of 1/12 of trailing dividends)
    tr, level, prev = {}, 1.0, None
    for m in months:
        if prev is not None and _shift_month(prev, 1) == m:
            level *= (price[m] + div[m] / 12) / price[prev]
        tr[m] = level
        prev = m
    last_complete = months[-2] if len(months) > 1 else None   # current month is partial

    realized = {}
    for h in HORIZONS:
        rows = []
        for m in months:
            end = _shift_month(m, 12 * h)
            if end in tr and end <= last_complete:
                rows.append({"date": m, "pct": round(100 * ((tr[end] / tr[m]) ** (1 / h) - 1), 2)})
        realized[str(h)] = rows

    er_div = []
    for m in months:
        base = _shift_month(m, -12 * GROWTH_YEARS)
        if base in div and div[base] > 0 and m >= CAPE_START:
            g = (div[m] / div[base]) ** (1 / GROWTH_YEARS) - 1
            y = div_yield[m] / 100
            er_div.append({"date": m, "pct": round(100 * (y * (1 + g) + g), 2),
                           "yieldPct": round(100 * y, 2), "growthPct": round(100 * g, 2)})

    gva_q = {_quarter_end_month(d): v for d, v in gva.items()}
    er_fcf = []
    for r in fcf_yield:
        base = _shift_month(r["date"], -12 * GROWTH_YEARS)
        if base in gva_q and gva_q[base] > 0:
            g = (gva_q[r["date"]] / gva_q[base]) ** (1 / GROWTH_YEARS) - 1
            y = r["pct"] / 100
            er_fcf.append({"date": r["date"], "pct": round(100 * (y * (1 + g) + g), 2),
                           "yieldPct": round(r["pct"], 2), "growthPct": round(100 * g, 2)})

    er_fcf_smooth = []
    if deflator and expinf:
        defl_q = {_quarter_end_month(d): v for d, v in deflator.items()}
        # monthly expectations, read at the quarter-end month
        exp_m = {d[:7]: v for d, v in expinf.items()}
        for r in fcf_yield:
            q = r["date"]
            b_real = _shift_month(q, -12 * REAL_GROWTH_YEARS)
            b_inf = _shift_month(q, -12 * GROWTH_YEARS)
            if not all(k in gva_q and k in defl_q for k in (q, b_real)) or b_inf not in defl_q:
                continue
            real_g = ((gva_q[q] / defl_q[q]) / (gva_q[b_real] / defl_q[b_real])) ** (1 / REAL_GROWTH_YEARS) - 1
            if q in exp_m:
                infl, src = exp_m[q] / 100, "expected"
            else:
                infl, src = (defl_q[q] / defl_q[b_inf]) ** (1 / GROWTH_YEARS) - 1, "trailing"
            g = (1 + real_g) * (1 + infl) - 1
            y = r["pct"] / 100
            er_fcf_smooth.append({"date": q, "pct": round(100 * (y * (1 + g) + g), 2),
                                  "yieldPct": round(r["pct"], 2), "growthPct": round(100 * g, 2),
                                  "realGrowthPct": round(100 * real_g, 2), "inflPct": round(100 * infl, 2),
                                  "inflSource": src})

    scenarios = {}
    if cape:
        for target in SCENARIO_CAPES:
            rows = []
            for r in er_fcf_smooth:
                c = cape.get(r["date"])
                if not c:
                    continue
                m = (target / c) ** (1 / SCENARIO_YEARS)
                rows.append({"date": r["date"], "pct": round(100 * ((1 + r["pct"] / 100) * m - 1), 2),
                             "capePct": round(100 * (m - 1), 2), "cape": c})
            scenarios[str(target)] = rows

    def fit(expected):
        out = {}
        for h, rows in realized.items():
            real = {r["date"]: r["pct"] for r in rows}
            pairs = [(e["pct"], real[e["date"]]) for e in expected if e["date"] in real]
            gap = [b - a for a, b in pairs]
            out[h] = {"r2": _r2(pairs), "n": len(pairs),
                      "meanGapPct": round(sum(gap) / len(gap), 2) if gap else None}
        return out

    return {
        "expectedDividend": er_div,
        "expectedFcf": er_fcf,
        "expectedFcfSmooth": er_fcf_smooth,
        "realized": realized,
        "fitDividend": fit(er_div),
        "fitFcf": fit(er_fcf),
        "fitFcfSmooth": fit(er_fcf_smooth),
        "scenarios": scenarios,
        "fitScenarios": {k: fit(v) for k, v in scenarios.items()},
        "scenarioYears": SCENARIO_YEARS,
        "realGrowthYears": REAL_GROWTH_YEARS,
        "growthYears": GROWTH_YEARS,
    }


def calc_expected_return(raw=None, stale=False, fcf_yield=None):
    if raw is None:
        raw, stale = get_valuation_raw()
    if "spPrice" not in raw or "spDivYield" not in raw:
        raise ValueError("cache predates the expected-return data (spPrice / spDivYield)")
    if fcf_yield is None:
        fcf_yield = calc_valuation_yields(raw, stale)["fcfYield"]
    res = compute_expected_return(raw["spPrice"], raw["spDivYield"],
                                  raw["fred"][GVA_SERIES], fcf_yield,
                                  raw["fred"].get(DEFLATOR_SERIES), raw["fred"].get(EXPINF_SERIES),
                                  raw.get("cape"))
    res.update({"asOf": raw["fetchedAt"], "stale": stale, "note": EXPECTED_RETURN_METHODOLOGY_NOTE})
    return res


if __name__ == "__main__":
    raw, stale = get_valuation_raw()
    res = calc_valuation_yields(raw, stale)
    print(json.dumps({k: (v[-3:] if isinstance(v, list) else v) for k, v in res.items()
                      if k != "note"}, indent=1))
    er = calc_expected_return(raw, stale, res["fcfYield"])
    print("E[R] div", er["expectedDividend"][-1], "fcf", er["expectedFcf"][-1])
    print("smooth", er["expectedFcfSmooth"][-1])
    print("fit div", er["fitDividend"], "\nfit fcf", er["fitFcf"], "\nfit smooth", er["fitFcfSmooth"])
