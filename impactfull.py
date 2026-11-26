"""
impactfull.py – "Impactfull vs ACWI & EM IMI" tab: EQUUS IMP Emerging Equity
Trends, share class S EUR (LU3281045396), against the MSCI ACWI net total
return index in EUR.

Fund series (switched to real NAV from launch on 2026-11-26, user's request)
  - 2020-01 .. launch: monthly net returns in EUR HAND-ENTERED from the
    Impactfull monthly teaser (data as of 30.10.2026, "NET MONTHLY
    PERFORMANCE (EUR)" table). The fund was only launched on 30.3.2026
    (FUND_LAUNCH); the months before are the strategy's track record (model
    fees, ACA track-record letter), not fund NAVs.
  - After launch: daily NAV of the S EUR class from Yahoo (Morningstar
    feed, FUND_TICKER). Yahoo's NAV only starts on 11.5.2026, so the
    factsheet still bridges launch -> the first month-end with a NAV (the
    "anchor", 29.5.2026: April and May come from the factsheet); from there
    on every point and monthly return is the NAV. The NAV points inside the
    anchor month (11.5-29.5) are scaled to the factsheet's May month-end.
    Later factsheet months are only a cross-check (`factsheetCheck`).
    Without NAV the factsheet runs to FACTSHEET_LAST_MONTH as before.
  Update: new factsheet months are no longer needed for the fund line; add
  them to FACTSHEET_MONTHLY only for the cross-check.

  Known inconsistency in the factsheet: its monthly table compounds to
  +268.5 % since Jan 2020 (21.0 % p.a.; each "Year" column matches), while
  the headline says ITD +342.0 % / 22.3 % p.a. We use the monthly table.

Benchmark
  MSCI ACWI (892400) NETR in EUR, daily, from MSCI's index-data endpoint
  (getLevelDataForGraph, same as country_returns.py; automated use OK'd by
  the user 2026-10-31). Raw levels are never stored: the cache and
  live_data.js hold only the series rebased to 100. MSCI EUR ITD 2020-01 to
  2026-10 = +120.9 %, same as the factsheet.

Second benchmark (added 2026-11-26, user's request): MSCI Emerging Markets
  IMI (664220) NETR in EUR, same endpoint, same rebasing — the fund invests in
  emerging-market equity trends, so EM IMI (large + mid + small cap, 24 EM
  countries) is the closer peer. Every benchmark gets its own series, monthly
  returns, stats and periods in `benchmarks`; the top-level bench / stats /
  periods keys stay = MSCI ACWI. A failed EM IMI fetch only drops that entry.

Cache impactfull_cache.json (git-ignored), stale: true on fallback.
"""

import json
import math
import os
from datetime import date, datetime

import requests

from country_returns import MSCI_URL, MSCI_HEADERS

FUND_NAME = "EQUUS IMP Emerging Equity Trends – S EUR"
FUND_ISIN = "LU3281045396"
FUND_TICKER = "0P0002D4QT.F"          # Yahoo (Morningstar) NAV, S EUR Acc
FUND_LAUNCH = "2026-03-30"
BENCH_NAME = "MSCI ACWI NR EUR"
BENCH_CODE = "892400"
# (key, short label, full name, MSCI code); the first one drives the fund's
# month-end dates and the top-level keys.
BENCHMARKS = [
    ("acwi", "ACWI", "MSCI ACWI NR EUR", "892400"),
    ("emimi", "EM IMI", "MSCI Emerging Markets IMI NR EUR", "664220"),
]
TRACK_START = "2019-12-31"            # base date of the track (= 100)
FACTSHEET_LABEL = "Impactfull monthly teaser, data as of 30.10.2026"
FACTSHEET_LAST_MONTH = "2026-10"
FACTSHEET_LAST_DATE = "2026-10-30"    # last NAV date the factsheet covers

# Net monthly returns in EUR (%), Jan..Dec, from the factsheet table.
FACTSHEET_MONTHLY = {
    2020: [1.90, -6.13, -13.58, 12.25, 6.85, 3.16, -0.88, 3.94, -1.43, -0.24, 14.26, 3.42],
    2021: [1.06, 3.30, 3.86, 1.81, -0.38, 5.46, -1.18, 3.08, -1.10, 3.75, -1.46, 1.35],
    2022: [-6.34, -1.60, 2.38, -4.80, -3.95, -5.74, 10.86, 0.86, -5.40, 6.34, 3.81, -5.70],
    2023: [9.64, 2.35, 0.53, -0.87, 7.91, 5.37, 4.17, 0.96, -1.80, -2.48, 12.53, 4.32],
    2024: [1.32, 6.89, 4.20, -3.40, 3.69, 1.95, 0.60, -1.45, 1.69, 2.80, 6.69, 0.46],
    2025: [4.10, -0.71, -5.64, -3.33, 9.90, 3.54, 4.56, 3.23, 4.18, 2.61, -2.11, 0.76],
    2026: [7.26, 6.98, -10.05, 12.34, 3.86, -3.06, -3.05, 9.33, 0.89, -5.37],
}
# Headline figures printed on the factsheet (shown for comparison only).
FACTSHEET_HEADLINE = {"itd": 342.0, "annSI": 22.3, "benchItd": 120.9, "benchAnnSI": 12.3,
                      "ytd": 18.13, "benchYtd": 17.0}

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "impactfull_cache.json")

NOTE = (
    "Fund: Jan 2020 – Mar 2026 = the strategy's track record with model fees (ACA track-record letter), "
    "net monthly returns in EUR from the Impactfull monthly teaser (data as of 30.10.2026), not fund NAVs; "
    "the fund was launched on 30.3.2026. After launch: daily NAV of the S EUR class (LU3281045396) from "
    "Yahoo / Morningstar. Yahoo's NAV starts on 11.5.2026, so April and May 2026 still come from the "
    "fact sheet (NAV points from 11.5 scaled to its May month-end); every month from June 2026 is the NAV. The factsheet's monthly table "
    "compounds to a lower figure than its headline (ITD +342.0 % / 22.3 % p.a.); the monthly table is used. "
    "Benchmarks: MSCI ACWI and MSCI Emerging Markets IMI, net total return in EUR (MSCI; levels not "
    "redistributed, rebased to 100). "
    "Statistics use full calendar months, no risk-free rate (Sharpe-like ratio = return / volatility). "
    "Marketing document data, not audited. Past performance is not a guide to future returns."
)


def _ym_end_dates(levels):
    """{YYYY-MM: (date, level)} last point of each month."""
    out = {}
    for d, v in levels:
        out[d[:7]] = (d, v)
    return out


def _fetch_bench(code=BENCH_CODE):
    url = MSCI_URL.format(cur="EUR", start=TRACK_START.replace("-", ""),
                          end=date.today().strftime("%Y%m%d"), freq="DAILY", code=code)
    r = requests.get(url, headers=MSCI_HEADERS, timeout=40)
    r.raise_for_status()
    lv = (r.json().get("indexes") or {}).get("INDEX_LEVELS") or []
    if len(lv) < 1000:
        raise ValueError(f"MSCI {code} EUR: only {len(lv)} levels")
    out = []
    for x in sorted(lv, key=lambda x: x["calc_date"]):
        s = str(x["calc_date"])
        out.append((f"{s[:4]}-{s[4:6]}-{s[6:]}", float(x["level_eod"])))
    return out


def _fetch_nav():
    import yfinance as yf
    h = yf.Ticker(FUND_TICKER).history(period="max", auto_adjust=True)
    if h.empty:
        raise ValueError(f"no NAV for {FUND_TICKER}")
    return [(i.strftime("%Y-%m-%d"), float(v)) for i, v in h["Close"].dropna().items()]


def _stats(f, b):
    """Monthly-return statistics. f, b: lists of % returns (same months)."""
    n = len(f)
    if n < 3:
        return None
    fr = [x / 100 for x in f]
    br = [x / 100 for x in b]
    gf = math.prod(1 + x for x in fr)
    gb = math.prod(1 + x for x in br)
    ann_f = gf ** (12 / n) - 1
    ann_b = gb ** (12 / n) - 1
    mf, mb = sum(fr) / n, sum(br) / n
    vf = math.sqrt(sum((x - mf) ** 2 for x in fr) / (n - 1) * 12)
    vb = math.sqrt(sum((x - mb) ** 2 for x in br) / (n - 1) * 12)
    cov = sum((x - mf) * (y - mb) for x, y in zip(fr, br)) / (n - 1)
    varb = sum((y - mb) ** 2 for y in br) / (n - 1)
    act = [x - y for x, y in zip(fr, br)]
    ma = sum(act) / n
    te = math.sqrt(sum((a - ma) ** 2 for a in act) / (n - 1) * 12)

    def mdd(r):
        g = peak = 1.0
        worst = 0.0
        for x in r:
            g *= 1 + x
            peak = max(peak, g)
            worst = min(worst, g / peak - 1)
        return worst

    up = [(x, y) for x, y in zip(fr, br) if y > 0]
    dn = [(x, y) for x, y in zip(fr, br) if y < 0]

    def capture(pairs):
        if not pairs:
            return None
        k = len(pairs)
        a = math.prod(1 + x for x, _ in pairs) ** (1 / k) - 1
        c = math.prod(1 + y for _, y in pairs) ** (1 / k) - 1
        return round(a / c * 100, 0) if c else None

    r2 = lambda x: round(x * 100, 2)
    corr = cov / math.sqrt(varb * (vf ** 2 / 12)) if varb and vf else None
    return {
        "months": n,
        "cum": r2(gf - 1), "benchCum": r2(gb - 1),
        "ann": r2(ann_f), "benchAnn": r2(ann_b), "excessAnn": r2(ann_f - ann_b),
        "vol": r2(vf), "benchVol": r2(vb),
        "retVol": round(ann_f / vf, 2) if vf else None,
        "benchRetVol": round(ann_b / vb, 2) if vb else None,
        "maxDD": r2(mdd(fr)), "benchMaxDD": r2(mdd(br)),
        "beta": round(cov / varb, 2) if varb else None,
        "corr": round(corr, 2) if corr is not None else None,
        "te": r2(te),
        "ir": round((ann_f - ann_b) / te, 2) if te else None,
        "hitRate": round(sum(1 for a in act if a > 0) / n * 100, 0),
        "upCapture": capture(up), "downCapture": capture(dn),
        "best": r2(max(fr)), "worst": r2(min(fr)),
    }


def _level_at(levels, d):
    """Benchmark level on date d (last level on or before d)."""
    lv = None
    for bd, v in levels:
        if bd > d:
            break
        lv = v
    return lv


def _build(benches, nav, today):
    """benches: {key: [(date, level), ...]}; the first BENCHMARKS key is required."""
    bench = benches[BENCHMARKS[0][0]]
    bench_m = _ym_end_dates(bench)

    # ── fund: factsheet month-ends up to the NAV anchor, then daily NAV ──
    # Anchor = the first fund month (after the launch month) whose month-end
    # already has a NAV: the factsheet covers the months before it (the
    # NAV on Yahoo starts after launch), the real NAV everything after it.
    # Without NAV, the factsheet runs to FACTSHEET_LAST_MONTH as before.
    fs = []                                       # (ym, return %, month-end date)
    for y in sorted(FACTSHEET_MONTHLY):
        for m, r in enumerate(FACTSHEET_MONTHLY[y], start=1):
            ym = f"{y}-{m:02d}"
            if ym > FACTSHEET_LAST_MONTH:
                break
            fs.append((ym, r, FACTSHEET_LAST_DATE if ym == FACTSHEET_LAST_MONTH else bench_m[ym][0]))
    anchor = None                                 # (ym, NAV date, NAV)
    if nav:
        nav_by_m = _ym_end_dates(nav)
        for ym, _, _ in fs:
            if ym > FUND_LAUNCH[:7] and ym in nav_by_m and nav[0][0] < nav_by_m[ym][0]:
                anchor = (ym, *nav_by_m[ym])
                break
    fs_cut = anchor[0] if anchor else FACTSHEET_LAST_MONTH

    dates, fund, monthly = [TRACK_START], [100.0], []
    g = 100.0
    for ym, r, d in fs:
        if ym > fs_cut:
            break
        g *= 1 + r / 100
        monthly.append({"ym": ym, "fund": r, "src": "fund" if ym > FUND_LAUNCH[:7] else "track"})
        if anchor and ym == fs_cut:
            # daily NAV inside the anchor month, scaled so its month-end = factsheet level
            for dn, v in nav:
                if dn[:7] == ym:
                    dates.append(dn)
                    fund.append(g * v / anchor[2])
        else:
            dates.append(d)
            fund.append(g)

    nav_source, fs_check = None, []
    if anchor:
        nav_source = "yahoo"
        base_g, base_nav = fund[-1], anchor[2]
        live = [(d, v) for d, v in nav if d > anchor[1]]
        for d, v in live:
            dates.append(d)
            fund.append(base_g * v / base_nav)
        by_month = {}
        for d, v in zip(dates, fund):
            if d > anchor[1]:
                by_month[d[:7]] = (d, v)
        prev_end = base_g
        fs_ret = {ym: r for ym, r, _ in fs}
        for ym in sorted(by_month):
            d, v = by_month[ym]
            r = round((v / prev_end - 1) * 100, 2)
            partial = ym >= today.strftime("%Y-%m")
            monthly.append({"ym": ym, "fund": r, "src": "nav", "partial": partial})
            if ym in fs_ret and not partial:
                fs_check.append({"ym": ym, "nav": r, "factsheet": fs_ret[ym],
                                 "diff": round(r - fs_ret[ym], 2)})
            prev_end = v

    fund = [round(v, 3) for v in fund]
    last = dates[-1]
    ly = str(int(last[:4]) - 1)
    ytd_start = max(d for d in dates if d[:4] == ly)
    prev_m = max(d for d in dates if d[:7] < last[:7])
    years = (datetime.strptime(last, "%Y-%m-%d") - datetime.strptime(TRACK_START, "%Y-%m-%d")).days / 365.25
    full = [r for r in monthly if not r.get("partial")]

    def versus(levels):
        """Benchmark series on the fund's dates + monthly returns, stats, periods."""
        base = dict(levels).get(TRACK_START, levels[0][1])
        series = [round(_level_at(levels, d) / base * 100, 3) for d in dates]
        ends = {d[:7]: v for d, v in zip(dates, series)}
        prev, mret = 100.0, []
        for row in monthly:
            v = ends[row["ym"]]
            mret.append(round((v / prev - 1) * 100, 2))
            prev = v
        fm = [r["fund"] for r in full]
        bm = mret[:len(full)]
        launch = [k for k, r in enumerate(full) if r["ym"] > FUND_LAUNCH[:7]]
        stats = {
            "si": _stats(fm, bm),
            "launch": _stats([fm[k] for k in launch], [bm[k] for k in launch]),
            "3y": _stats(fm[-36:], bm[-36:]) if len(full) >= 36 else None,
        }

        def period(start_date):
            i = max((k for k, d in enumerate(dates) if d <= start_date), default=0)
            return {"fund": round((fund[-1] / fund[i] - 1) * 100, 2),
                    "bench": round((series[-1] / series[i] - 1) * 100, 2), "from": dates[i]}

        periods = {
            "mtd": period(prev_m),
            "ytd": period(ytd_start),
            # base = end of the launch month (the factsheet's first fund month is April 2026)
            "launch": period(max(d for d in dates if d[:7] <= FUND_LAUNCH[:7])),
            "si": period(TRACK_START),
        }
        periods["si"]["fundAnn"] = round(((fund[-1] / 100) ** (1 / years) - 1) * 100, 2)
        periods["si"]["benchAnn"] = round(((series[-1] / 100) ** (1 / years) - 1) * 100, 2)
        return {"bench": series, "monthly": mret, "stats": stats, "periods": periods,
                "asOf": levels[-1][0]}

    benchmarks = []
    for key, short, name, code in BENCHMARKS:
        if key not in benches:
            continue
        v = versus(benches[key])
        v.update({"key": key, "short": short, "name": name, "code": code})
        benchmarks.append(v)
    main = benchmarks[0]
    for row, r in zip(monthly, main["monthly"]):
        row["bench"] = r
    bench_series, stats, periods = main["bench"], main["stats"], main["periods"]

    last_nav = nav[-1] if nav else None
    return {
        "asOf": last,
        "fundName": FUND_NAME, "isin": FUND_ISIN, "ticker": FUND_TICKER,
        "benchName": BENCH_NAME, "launch": FUND_LAUNCH,
        "factsheet": FACTSHEET_LABEL, "factsheetLastDate": FACTSHEET_LAST_DATE,
        "factsheetHeadline": FACTSHEET_HEADLINE,
        "nav": {"date": last_nav[0], "value": round(last_nav[1], 2)} if last_nav else None,
        "navSource": nav_source,
        # first NAV on Yahoo, and the month-end from which the fund line is NAV only
        "navFrom": nav[0][0] if nav else None,
        "navAnchor": anchor[1] if anchor else None,
        "factsheetCheck": fs_check,
        "benchAsOf": bench[-1][0],
        "dates": dates, "fund": fund, "bench": bench_series,
        "benchmarks": benchmarks,
        "monthly": monthly, "stats": stats, "periods": periods,
        "note": NOTE,
    }


def calc_impactfull(today=None):
    today = today or date.today()
    try:
        benches = {BENCHMARKS[0][0]: _fetch_bench(BENCHMARKS[0][3])}
        for key, short, _, code in BENCHMARKS[1:]:
            try:
                benches[key] = _fetch_bench(code)
            except Exception as e:
                print(f"  ⚠ Impactfull benchmark {short} ({code}) failed: {e} — skipped")
        try:
            nav = _fetch_nav()
        except Exception as e:
            print(f"  ⚠ Impactfull NAV ({FUND_TICKER}) failed: {e} — factsheet track only")
            nav = []
        out = _build(benches, nav, today)
        with open(CACHE_PATH, "w") as f:
            json.dump(out, f)
        return out
    except Exception as e:
        print(f"  ⚠ Impactfull vs ACWI live fetch failed: {e}")
        with open(CACHE_PATH) as f:
            out = json.load(f)
        out["stale"] = True
        return out


if __name__ == "__main__":
    o = calc_impactfull()
    print(o["asOf"], o["nav"], o["periods"])
    for b in o.get("benchmarks", []):
        print(b["short"], b["periods"]["si"], b["stats"]["si"] and b["stats"]["si"]["beta"])
    print(o["monthly"][-4:])
