"""
country_returns.py – "Periodic table" of annual returns of the 22 developed
equity markets (2006 to last full year + current year to date), ranked in
each column, in USD (as Dimensional's "Annual returns for developed markets,
ranked (2006–2025)") and in CHF.

Source: MSCI country indices, net dividends reinvested (NETR), in USD and in
CHF, from MSCI's index-data endpoint (getLevelDataForGraph, the same one
regional_expected_return.py uses; automated use OK'd by the user on
2026-10-31 for this personal dashboard). One request per series per run;
raw index levels are never stored or committed — the cache
(country_returns_cache.json, git-ignored) holds only the derived annual
returns, so full years are fetched once and only the YTD is refreshed
(one daily request per country and currency).

MSCI index codes are "9" + ISO 3166 numeric + "00" except Germany (928000,
old West-German code) and Singapore (998100).
"""

import json
import os
import time
from datetime import date

import requests

FIRST_YEAR = 2006

MSCI_URL = ("https://app2.msci.com/products/service/index/indexmaster/getLevelDataForGraph"
            "?currency_symbol={cur}&index_variant=NETR&start_date={start}&end_date={end}"
            "&data_frequency={freq}&baseValue=false&index_codes={code}")
MSCI_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://app2.msci.com/products/index-data-search/"}
CURRENCIES = ("USD", "CHF")

# key, name, MSCI code, background, text colour (palette after Dimensional's chart)
COUNTRIES = [
    ("AUS", "Australia",      "903600", "#2BA6B8", "#fff"),
    ("AUT", "Austria",        "904000", "#4FD6C8", "#000"),
    ("BEL", "Belgium",        "905600", "#D6DE8C", "#000"),
    ("CAN", "Canada",         "912400", "#1F6E80", "#fff"),
    ("DNK", "Denmark",        "920800", "#1E7B6C", "#fff"),
    ("FIN", "Finland",        "924600", "#EDEADF", "#000"),
    ("FRA", "France",         "925000", "#CFCFD2", "#000"),
    ("DEU", "Germany",        "928000", "#D2694B", "#fff"),
    ("HKG", "Hong Kong",      "934400", "#7D9C9C", "#fff"),
    ("IRL", "Ireland",        "937200", "#7B7468", "#fff"),
    ("ITA", "Italy",          "938000", "#A8D49F", "#000"),
    ("JPN", "Japan",          "939200", "#3A3A2C", "#fff"),
    ("NLD", "Netherlands",    "952800", "#DCD6CC", "#000"),
    ("NZL", "New Zealand",    "955400", "#1E3A5C", "#fff"),
    ("NOR", "Norway",         "957800", "#CDBF8E", "#000"),
    ("PRT", "Portugal",       "962000", "#2C3A47", "#fff"),
    ("SGP", "Singapore",      "998100", "#8A1F5E", "#fff"),
    ("ESP", "Spain",          "972400", "#B07445", "#fff"),
    ("SWE", "Sweden",         "975200", "#5C1F2B", "#fff"),
    ("CHE", "Switzerland",    "975600", "#C8C84A", "#000"),
    ("GBR", "United Kingdom", "982600", "#A99E22", "#000"),
    ("USA", "USA",            "984000", "#FFFF33", "#000"),
]

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "country_returns_cache.json")

NOTE = (
    "MSCI country indices (standard: large + mid cap), net dividends reinvested, in US dollars or Swiss "
    "francs, ranked from highest to lowest in each column; the last column is the current year to date. "
    "Same data and layout as Dimensional's \"Annual returns for developed markets, ranked\" chart, extended "
    "with the current year. Annualized figures are geometric means over the full calendar years shown. "
    "Source: MSCI (index levels not redistributed, only derived returns shown). Past performance is not a "
    "guide to future returns."
)


def _levels(code, cur, start, freq):
    url = MSCI_URL.format(cur=cur, start=start, end=date.today().strftime("%Y%m%d"), freq=freq, code=code)
    for attempt in range(3):
        try:
            r = requests.get(url, headers=MSCI_HEADERS, timeout=30)
            r.raise_for_status()
            lv = (r.json().get("indexes") or {}).get("INDEX_LEVELS")
            if not lv:
                raise ValueError(f"MSCI {code} {cur}: no levels")
            return sorted((str(x["calc_date"]), float(x["level_eod"])) for x in lv)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)
        finally:
            time.sleep(0.25)


def _annual(code, cur, last_full):
    """{year: % return} for FIRST_YEAR..last_full from month-end levels."""
    ye = {}
    for d, v in _levels(code, cur, f"{FIRST_YEAR - 1}1201", "END_OF_MONTH"):
        if d[4:6] == "12":
            ye[int(d[:4])] = v
    return {str(y): round((ye[y] / ye[y - 1] - 1) * 100, 2)
            for y in range(FIRST_YEAR, last_full + 1) if y in ye and y - 1 in ye}


def _ytd(code, cur, cur_year):
    lv = _levels(code, cur, f"{cur_year - 1}1224", "DAILY")
    base = [v for d, v in lv if d < f"{cur_year}0101"]
    if not base:
        raise ValueError(f"MSCI {code} {cur}: no year-end level")
    d1, v1 = lv[-1]
    return round((v1 / base[-1] - 1) * 100, 2), f"{d1[:4]}-{d1[4:6]}-{d1[6:]}"


def _load_cache():
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _annualized(vals):
    g = 1.0
    for v in vals:
        g *= 1 + v / 100
    return round((g ** (1 / len(vals)) - 1) * 100, 2)


def calc_country_returns(today=None):
    today = today or date.today()
    cur_year, last_full = today.year, today.year - 1
    years = list(range(FIRST_YEAR, last_full + 1))
    cache = _load_cache() or {}
    annual = cache.get("annual") or {}
    stale = False

    # full calendar years: fetched once, then served from the cache
    need_full = any(str(last_full) not in annual.get(f"{k}_{c}", {})
                    for k, *_ in COUNTRIES for c in CURRENCIES)
    if need_full:
        try:
            annual = {f"{k}_{c}": _annual(code, c, last_full)
                      for k, _, code, *_ in COUNTRIES for c in CURRENCIES}
        except Exception as e:
            if not annual:
                raise
            print(f"  ⚠ MSCI annual returns failed ({e}) — using cached years")
            stale = True

    # current year to date: refreshed every run
    ytd, as_of = {}, None
    try:
        for k, _, code, *_ in COUNTRIES:
            for c in CURRENCIES:
                ytd[f"{k}_{c}"], d = _ytd(code, c, cur_year)
                as_of = min(as_of, d) if as_of else d
    except Exception as e:
        if cache.get("ytdYear") != cur_year:
            raise
        print(f"  ⚠ MSCI YTD failed ({e}) — using cached YTD from {cache.get('asOf')}")
        ytd, as_of, stale = cache["ytd"], cache["asOf"], True

    try:
        with open(CACHE_PATH, "w") as f:
            json.dump({"annual": annual, "ytd": ytd, "ytdYear": cur_year, "asOf": as_of}, f)
    except OSError as e:
        print(f"  ⚠ could not write country returns cache: {e}")

    cols = [{"year": y, "ytd": False} for y in years] + [{"year": cur_year, "ytd": True}]
    countries = []
    for k, name, code, bg, fg in COUNTRIES:
        row = {"key": k, "label": name, "bg": bg, "fg": fg, "ret": {}, "annualized": {}}
        for c in CURRENCIES:
            a = annual.get(f"{k}_{c}", {})
            vals = [a.get(str(y)) for y in years]
            row["ret"][c] = [None if v is None else round(v, 1) for v in vals] + [
                None if ytd.get(f"{k}_{c}") is None else round(ytd[f"{k}_{c}"], 1)]
            row["annualized"][c] = _annualized(vals) if all(v is not None for v in vals) else None
        countries.append(row)
    return {"asOf": as_of, "columns": cols, "currencies": list(CURRENCIES),
            "countries": countries, "note": NOTE, "stale": stale}


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    res = calc_country_returns()
    print("as of", res["asOf"], "stale" if res["stale"] else "")
    for c in CURRENCIES:
        print(f"\n{c}: annualized {res['columns'][0]['year']}-{res['columns'][-2]['year']}, last full year, YTD")
        for r in sorted(res["countries"], key=lambda r: -(r["annualized"][c] or -99)):
            print(f"  {r['key']} {r['label']:15s} {r['annualized'][c]:>6}  {r['ret'][c][-2]:>6}  {r['ret'][c][-1]:>6}")
