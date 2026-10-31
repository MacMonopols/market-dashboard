"""
regional_expected_return.py – "Where do we start from today?" snapshot of
long-run expected equity returns by region (Long Term Summary card).

Why a snapshot and not historical lines (decided 2026-10-31): a Gordon test
per country on the Jordà-Schularick-Taylor database (1870-2020) did not hold
outside the US — trailing dividend growth is too unstable per country (France
−0.3 %, Japan +12 % in 2020), R² vs realized 10y mostly 0.0-0.3, and the Swiss
JST equity series has gaps and implausible years. So, Research-Affiliates
style, for each region:

    E[R] (constant valuation) = dividend yield + real growth + expected inflation
    E[R] (valuation reversion) = (1 + E[R]) · (CAPE_ref / CAPE)^(1/10) − 1

- Dividend yield, live: MSCI index levels, gross vs price return over the last
  12 months (MSCI index-data endpoint, one request per series per run, raw
  levels cached locally and NEVER committed — personal use only). Fallback:
  trailing-12m distributions of a US-listed iShares/SPDR ETF via yfinance.
- Real growth: one prudent assumption for all regions (REAL_GROWTH_PCT), in
  line with long-run real dividend growth in JST outside anomalies.
- Expected inflation: Cleveland Fed 10y expectations for USD regions (FRED
  EXPINF10YR; regions measured in USD take USD inflation, i.e. PPP), a fixed
  assumption for CHF (SNB price stability = 0-2 %).
- CAPE and reference level: entered by hand each quarter in CAPE_SNAPSHOT
  (Siblis Research / Research Affiliates); no free CAPE history by region.
- Local 10y government yields for the equity-premium comparison: FRED.
- JST_REFERENCE: real returns 1960-2020 per country computed once from the
  JST Macrohistory Database R6 (CC BY-NC-SA 4.0; Jordà, Knoll, Kuvshinov,
  Schularick & Taylor (2019), "The Rate of Return on Everything, 1870–2015",
  QJE 134(3); accessed 2026-10-31). Derived statistics only.
"""

import csv
import io
import json
import os
import time
from datetime import date

import requests

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "regional_expected_return_cache.json")

MSCI_URL = ("https://app2.msci.com/products/service/index/indexmaster/getLevelDataForGraph"
            "?currency_symbol={cur}&index_variant={var}&start_date={start}&end_date={end}"
            "&data_frequency=END_OF_MONTH&baseValue=false&index_codes={code}")
MSCI_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://app2.msci.com/products/index-data-search/"}
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

REAL_GROWTH_PCT = 1.5
CHF_INFLATION_PCT = 1.0

REGIONS = [
    # key, label, MSCI code, currency, fallback ETF, inflation source, local 10y (FRED id or "US10Y")
    {"key": "USA", "label": "USA", "msci": "984000", "cur": "USD", "etf": "IVV",
     "infl": "USD", "bond": "US10Y", "bondLabel": "US 10Y"},
    {"key": "WXUS", "label": "World ex USA", "msci": "991000", "cur": "USD", "etf": "EFA",
     "infl": "USD", "bond": "US10Y", "bondLabel": "US 10Y"},
    {"key": "EM", "label": "Emerging Markets", "msci": "891800", "cur": "USD", "etf": "EEM",
     "infl": "USD", "bond": "US10Y", "bondLabel": "US 10Y"},
    {"key": "CHE", "label": "Switzerland (CHF)", "msci": "975600", "cur": "CHF", "etf": "EWL",
     "infl": "CHF", "bond": "IRLTLT01CHM156N", "bondLabel": "CH 10Y"},
]

# Hand-entered each quarter. capeRef = the region's own reference level.
CAPE_SNAPSHOT = {
    "asOf": "2026-09-30",
    "source": "Siblis Research (CAPE, Sept 2026); reference levels: Siblis 20-year average (USA), "
              "Siblis world median since 1980 (World ex USA), Research Affiliates historical median (EM)",
    "regions": {
        "USA":  {"cape": 35.9, "capeRef": 24.1, "refLabel": "20y avg"},
        "WXUS": {"cape": 20.75, "capeRef": 21.6, "refLabel": "world median since 1980"},
        "EM":   {"cape": 19.06, "capeRef": 15.2, "refLabel": "historical median"},
        "CHE":  {"cape": 23.2, "capeRef": None, "refLabel": "no reference available"},
    },
}

JST_REFERENCE = {
    "period": "1960–2020",
    "rows": [
        {"country": "USA", "realReturnPct": 6.1, "inflationPct": 3.5, "avgDivYieldPct": 2.9, "realDivGrowthPct": 2.2},
        {"country": "Switzerland", "realReturnPct": 5.6, "inflationPct": 2.4, "avgDivYieldPct": 2.4, "realDivGrowthPct": None},
        {"country": "United Kingdom", "realReturnPct": 5.5, "inflationPct": 4.8, "avgDivYieldPct": 4.3, "realDivGrowthPct": 0.6},
        {"country": "Germany", "realReturnPct": 4.8, "inflationPct": 2.6, "avgDivYieldPct": 2.8, "realDivGrowthPct": 2.4},
        {"country": "Japan", "realReturnPct": 4.5, "inflationPct": 2.9, "avgDivYieldPct": 1.9, "realDivGrowthPct": 1.7},
        {"country": "France", "realReturnPct": 2.4, "inflationPct": 4.0, "avgDivYieldPct": 3.6, "realDivGrowthPct": -0.8},
    ],
    "attribution": "Jordà-Schularick-Taylor Macrohistory Database R6 (macrohistory.net, CC BY-NC-SA 4.0); "
                   "Jordà, Knoll, Kuvshinov, Schularick & Taylor (2019), QJE 134(3). Accessed 2026-10-31. "
                   "Swiss dividend growth omitted (series gaps).",
}

METHODOLOGY_NOTE = (
    "Snapshot, not a forecast series. Expected return = dividend yield (MSCI, gross vs price return over the "
    "last 12 months) + real growth (" + f"{REAL_GROWTH_PCT}" + " % for every region, a prudent long-run assumption) + "
    "expected inflation (Cleveland Fed 10-year for USD regions; " + f"{CHF_INFLATION_PCT}" + " % assumed for CHF). "
    "The reversion column adds the annual effect of the CAPE moving to the reference level over 10 years "
    "(hand-entered quarterly). Outside the US buybacks are smaller, so the dividend yield captures most of the "
    "cash returned; for the US it understates it — see the FCF-based card above for the US. A Gordon test per "
    "country on 1870-2020 data did not validate well outside the US, hence no historical lines here. "
    "CHF view for USD regions: unhedged = relative PPP (CHF appreciates by the USD-CHF inflation gap); "
    "hedged = minus the cost of a rolling USD→CHF hedge, proxied by the US-CH 10-year yield gap. "
    "Personal use; MSCI data are not redistributed, only derived figures shown."
)


def _msci_levels(code, variant, cur):
    url = MSCI_URL.format(cur=cur, var=variant, start="19970101",
                          end=date.today().strftime("%Y%m%d"), code=code)
    r = requests.get(url, headers=MSCI_HEADERS, timeout=30)
    r.raise_for_status()
    j = r.json()
    lv = (j.get("indexes") or {}).get("INDEX_LEVELS")
    if not lv:
        raise ValueError(f"MSCI {code} {variant}: {str(j)[:120]}")
    return {str(x["calc_date"]): float(x["level_eod"]) for x in lv}


def _msci_dividend_yield(code, cur):
    gr, pr = _msci_levels(code, "GRTR", cur), _msci_levels(code, "STRD", cur)
    dates = sorted(set(gr) & set(pr))
    if len(dates) < 13:
        raise ValueError("not enough MSCI history")
    d1, d0 = dates[-1], dates[-13]
    dy = (gr[d1] / gr[d0]) / (pr[d1] / pr[d0]) - 1
    return round(100 * dy, 2), d1


def _etf_dividend_yield(ticker):
    import yfinance as yf
    t = yf.Ticker(ticker)
    divs = t.dividends
    price = t.history(period="5d")["Close"].iloc[-1]
    if divs is None or divs.empty:
        raise ValueError(f"no dividends for {ticker}")
    cutoff = divs.index[-1] - __import__("pandas").Timedelta(days=365)
    ttm = divs[divs.index > cutoff].sum()
    return round(100 * ttm / price, 2), divs.index[-1].strftime("%Y%m%d")


def _fred_last(series_id):
    r = requests.get(FRED_CSV_URL, params={"id": series_id}, timeout=30)
    r.raise_for_status()
    last = None
    for row in csv.DictReader(io.StringIO(r.text)):
        v = row.get(series_id)
        if v and v != ".":
            last = (row["observation_date"], float(v))
    if last is None:
        raise ValueError(f"empty FRED {series_id}")
    return last


def _load_cache():
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def calc_regional_expected_return(us_expected_inflation=None, us_10y=None, us_fcf=None):
    """us_expected_inflation / us_10y: (date, pct) already fetched elsewhere, optional.
    us_fcf: latest points of the FCF-based US expected return (valuation_yields.py):
      {"smooth": expectedFcfSmooth[-1], "reversion": expectedFcfReversion[-1], "ahp": ahpToday}
    → an extra "USA — FCF basis" row, since buybacks make the US dividend yield
    understate the cash returned."""
    cache = _load_cache()
    new_cache = dict(cache)
    stale = []

    def remember(key, fn):
        try:
            val = fn()
            new_cache[key] = val
            return val, False
        except Exception as e:
            if key in cache:
                stale.append(key)
                return cache[key], True
            print(f"  ⚠ {key}: {e}")
            return None, False

    if us_expected_inflation is None:
        us_expected_inflation, _ = remember("EXPINF10YR", lambda: _fred_last("EXPINF10YR"))
    bonds = {}
    for reg in REGIONS:
        b = reg["bond"]
        if b == "US10Y":
            bonds[b] = us_10y
        elif b not in bonds:
            bonds[b], _ = remember(b, lambda b=b: _fred_last(b))

    # CHF conversion for regions measured in USD (added 2026-10-31):
    #  - unhedged: relative PPP, the CHF appreciates by the inflation gap
    #    E_chf = (1 + E_usd) · (1 + π_chf) / (1 + π_usd) − 1
    #  - hedged: a 10-year rolling hedge costs/earns the expected short-rate
    #    gap, proxied by the 10Y government yield gap (US 10Y − CH 10Y)
    #    E_chf = (1 + E_usd) · (1 + y_ch) / (1 + y_us) − 1
    us_infl_pct = us_expected_inflation[1] if us_expected_inflation else 2.4
    ch_bond = bonds.get("IRLTLT01CHM156N")
    us_bond = bonds.get("US10Y")

    def to_chf(pct, cur, hedged):
        if pct is None:
            return None
        if cur == "CHF":
            return round(pct, 2)
        if hedged:
            if not (ch_bond and us_bond):
                return None
            f = (1 + ch_bond[1] / 100) / (1 + us_bond[1] / 100)
        else:
            f = (1 + CHF_INFLATION_PCT / 100) / (1 + us_infl_pct / 100)
        return round(100 * ((1 + pct / 100) * f - 1), 2)

    rows = []
    for reg in REGIONS:
        source = "MSCI"
        try:
            dy, as_of = _msci_dividend_yield(reg["msci"], reg["cur"])
            new_cache["dy_" + reg["key"]] = [dy, as_of, "MSCI"]
        except Exception as e_msci:
            try:
                dy, as_of = _etf_dividend_yield(reg["etf"])
                source = f"ETF {reg['etf']} (MSCI unavailable)"
                new_cache["dy_" + reg["key"]] = [dy, as_of, source]
            except Exception as e_etf:
                cached = cache.get("dy_" + reg["key"])
                if not cached:
                    print(f"  ⚠ {reg['label']}: no dividend yield ({e_msci}; {e_etf})")
                    continue
                dy, as_of, source = cached
                source += " (cached)"
                stale.append(reg["key"])
        if reg["infl"] == "USD":
            infl = us_expected_inflation[1] if us_expected_inflation else 2.4
            infl_src = "Cleveland Fed 10y expected inflation" if us_expected_inflation else "assumed 2.4 %"
        else:
            infl, infl_src = CHF_INFLATION_PCT, f"assumed {CHF_INFLATION_PCT} % (SNB: price stability 0-2 %)"
        er = dy + REAL_GROWTH_PCT + infl
        cs = CAPE_SNAPSHOT["regions"].get(reg["key"], {})
        adj = er_rev = None
        if cs.get("cape") and cs.get("capeRef"):
            m = (cs["capeRef"] / cs["cape"]) ** (1 / 10)
            adj = round(100 * (m - 1), 2)
            er_rev = round(100 * ((1 + er / 100) * m - 1), 2)
        bond = bonds.get(reg["bond"])
        rows.append({
            "key": reg["key"], "label": reg["label"], "currency": reg["cur"],
            "divYieldPct": dy, "divYieldAsOf": as_of, "divYieldSource": source,
            "realGrowthPct": REAL_GROWTH_PCT, "inflationPct": round(infl, 2), "inflationSource": infl_src,
            "erConstantPct": round(er, 2),
            "cape": cs.get("cape"), "capeRef": cs.get("capeRef"), "capeRefLabel": cs.get("refLabel"),
            "valuationAdjPct": adj, "erReversionPct": er_rev,
            "bondLabel": reg["bondLabel"], "bondPct": bond[1] if bond else None,
            "bondAsOf": bond[0] if bond else None,
            "erChfUnhedgedPct": to_chf(round(er, 2), reg["cur"], False),
            "erRevChfUnhedgedPct": to_chf(er_rev, reg["cur"], False),
            "erChfHedgedPct": to_chf(round(er, 2), reg["cur"], True),
            "erRevChfHedgedPct": to_chf(er_rev, reg["cur"], True),
        })

    if us_fcf and us_fcf.get("smooth"):
        sm, rv, ahp = us_fcf["smooth"], us_fcf.get("reversion") or {}, us_fcf.get("ahp") or {}
        row = {
            "key": "USA_FCF", "label": "USA — FCF basis", "currency": "USD", "basis": "fcf",
            "yieldLabel": "FCF yield",
            "divYieldPct": sm["yieldPct"], "divYieldAsOf": sm["date"],
            "divYieldSource": "US corporate FCF yield (BEA/Fed via FRED), Gordon y·(1+g)+g",
            "realGrowthPct": sm.get("realGrowthPct"), "inflationPct": sm.get("inflPct"),
            "inflationSource": "Cleveland Fed 10y expected inflation",
            "erConstantPct": sm["pct"],
            "cape": None, "capeRef": None,
            "capeRefLabel": (f"FCF yield {rv['yield4qPct']}% vs its mean {rv['meanPct']}%" if rv else None),
            "valuationAdjPct": rv.get("reversionPct"), "erReversionPct": rv.get("pct"),
            "ahpPct": ahp.get("reversionPct"),
            "ahpLabel": (f"with AHP's published FCF yield {ahp.get('yieldPct')}% → {ahp.get('meanPct')}%" if ahp else None),
            "bondLabel": "US 10Y", "bondPct": us_bond[1] if us_bond else None,
            "bondAsOf": us_bond[0] if us_bond else None,
        }
        row["erChfUnhedgedPct"] = to_chf(row["erConstantPct"], "USD", False)
        row["erRevChfUnhedgedPct"] = to_chf(row["erReversionPct"], "USD", False)
        row["erChfHedgedPct"] = to_chf(row["erConstantPct"], "USD", True)
        row["erRevChfHedgedPct"] = to_chf(row["erReversionPct"], "USD", True)
        row["ahpChfUnhedgedPct"] = to_chf(row["ahpPct"], "USD", False)
        row["ahpChfHedgedPct"] = to_chf(row["ahpPct"], "USD", True)
        i = next((k for k, r in enumerate(rows) if r["key"] == "USA"), -1)
        rows.insert(i + 1, row)

    try:
        with open(CACHE_PATH, "w") as f:
            json.dump(new_cache, f)
    except OSError:
        pass

    return {
        "asOf": date.today().isoformat(),
        "stale": stale,
        "regions": rows,
        "capeSnapshot": {"asOf": CAPE_SNAPSHOT["asOf"], "source": CAPE_SNAPSHOT["source"]},
        "chf": {"usInflationPct": round(us_infl_pct, 2), "chInflationPct": CHF_INFLATION_PCT,
                "us10yPct": us_bond[1] if us_bond else None, "ch10yPct": ch_bond[1] if ch_bond else None,
                "ch10yAsOf": ch_bond[0] if ch_bond else None},
        "jstReference": JST_REFERENCE,
        "note": METHODOLOGY_NOTE,
    }


if __name__ == "__main__":
    print(json.dumps(calc_regional_expected_return(), indent=1)[:3000])
