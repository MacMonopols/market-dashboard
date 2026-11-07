"""
largest_stocks.py – "Large and in charge" cards on the Long Term Summary:
weight of the largest 1 / 5 / 10 US stocks, the largest 10 at the start of
each decade, and the excess return of stocks after they join the top 10.

Inspired by Dimensional, "Large and in Charge: Giant Firms atop Market Is
Nothing New" (17 Jun 2020), which covers 1927–2019 on CRSP data (paid).

Two layers:
1. DIMENSIONAL_* constants: values READ OFF Dimensional's published charts
   (annual weights ±~0.5 pt, decade top-10 lists with combined shares, the
   three excess-return bars). Ranks 5–10 of the pre-1980 decade lists are
   read from a bump chart and may be a place off. Derived figures only.
2. A reconstruction from free data that extends the series to today:
   - universe = today's holdings of iShares ITOT (S&P Total Market Index,
     ~2,500 US stocks, float-adjusted weights), share classes merged per
     company (Alphabet A+C, ...), top UNIVERSE_N companies by weight;
   - cap_i(t) ∝ weight_i(today) × P_i(t) / P_i(today) (split-adjusted price,
     no dividends) — i.e. constant share count;
   - total market(t) ∝ 100 × VTI(t) / VTI(today) (CRSP US Total Market price);
   - weight of the top N at t = sum of the N largest cap_i(t) / total(t).
   Year-ends from START_YEAR (2009; see there why not earlier), plus today's exact value from the weights.
   Biases: buybacks (past caps of buyback-heavy names understated), issuance
   / IPOs (past total overstated → past weights understated), survivorship
   (firms no longer listed are missing). The 2009–2019 overlap with
   Dimensional's line shows how large the error is.
   Excess return: companies that enter the top 10 at a year-end (not in the
   top 10 at any earlier year-end since START_YEAR), annualized total return
   over the next 3 / 5 / 10 years minus VTI's, equal-weighted average.

The yfinance download (~400 tickers × 20 years monthly) is cached for
CACHE_MAX_AGE_DAYS in largest_stocks_cache.json (git-ignored); today's point
is recomputed from the live holdings every run.
"""

import json
import os
import re
import time
from datetime import datetime

START_YEAR = 2009     # 2005-08 is unusable: banks/AIG diluted massively in 2009, so
                      # constant share counts put Citigroup at ~7 % of the market in 2006
UNIVERSE_N = 400
TOP_NS = (1, 5, 10)
HORIZONS = (3, 5, 10)
MARKET_TICKER = "VTI"
CACHE_MAX_AGE_DAYS = 7
CACHE_SCHEMA_VERSION = 2
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "largest_stocks_cache.json")

DIMENSIONAL_SOURCE = ("Dimensional Fund Advisors, “Large and in Charge: Giant Firms atop "
                      "Market Is Nothing New”, 17 Jun 2020 (CRSP data, 1927–2019)")
DIMENSIONAL_URL = ("https://www.dimensional.com/us-en/insights/"
                   "large-and-in-charge-giant-firms-atop-market-is-nothing-new")

# Year-end weights (%) read off Dimensional's Exhibit 1: [year, top1, top5, top10]
DIMENSIONAL_WEIGHTS = [
    [1927, 6.2, 18.6, 27.5], [1928, 6.2, 18.2, 28.0], [1929, 5.6, 18.0, 27.5],
    [1930, 8.6, 21.0, 31.0], [1931, 11.0, 26.6, 37.8], [1932, 11.0, 25.6, 36.0],
    [1933, 7.8, 24.0, 33.0], [1934, 7.2, 22.6, 31.5], [1935, 7.8, 24.2, 31.8],
    [1936, 7.2, 23.2, 30.5], [1937, 8.6, 24.6, 33.2], [1938, 7.2, 23.6, 31.5],
    [1939, 8.6, 25.8, 33.2], [1940, 9.2, 25.8, 33.5], [1941, 8.4, 24.8, 33.5],
    [1942, 8.0, 25.2, 33.2], [1943, 7.4, 23.8, 31.5], [1944, 7.0, 23.2, 29.5],
    [1945, 6.2, 20.0, 26.5], [1946, 6.0, 19.0, 25.3], [1947, 5.4, 18.8, 26.3],
    [1948, 6.0, 19.6, 27.5], [1949, 5.4, 19.4, 26.7], [1950, 5.2, 20.0, 27.8],
    [1951, 5.2, 20.6, 28.3], [1952, 5.6, 21.6, 29.3], [1953, 6.0, 22.2, 29.8],
    [1954, 5.8, 22.6, 30.3], [1955, 6.8, 25.0, 32.8], [1956, 5.8, 23.6, 32.2],
    [1957, 6.0, 23.4, 32.5], [1958, 6.0, 22.2, 31.8], [1959, 6.2, 21.6, 31.2],
    [1960, 5.6, 21.6, 30.2], [1961, 8.0, 23.4, 31.3], [1962, 8.6, 23.0, 31.2],
    [1963, 8.0, 24.0, 32.3], [1964, 8.4, 23.0, 32.0], [1965, 7.4, 20.0, 29.5],
    [1966, 6.4, 19.4, 27.8], [1967, 5.8, 18.6, 26.0], [1968, 5.8, 17.0, 23.8],
    [1969, 5.2, 18.4, 25.2], [1970, 6.6, 18.4, 25.6], [1971, 5.8, 16.6, 24.0],
    [1972, 5.4, 17.0, 24.2], [1973, 5.4, 15.2, 22.0], [1974, 4.8, 15.8, 21.8],
    [1975, 4.8, 16.2, 21.8], [1976, 4.6, 16.0, 21.0], [1977, 4.8, 15.8, 20.6],
    [1978, 4.6, 15.4, 20.2], [1979, 4.6, 12.4, 17.2], [1980, 3.6, 12.0, 17.4],
    [1981, 2.6, 11.8, 16.6], [1982, 3.6, 12.4, 17.0], [1983, 4.0, 12.2, 16.4],
    [1984, 4.0, 10.6, 15.2], [1985, 4.4, 10.4, 14.5], [1986, 4.4, 9.2, 13.2],
    [1987, 3.2, 9.4, 13.8], [1988, 2.6, 9.0, 13.6], [1989, 2.6, 8.8, 13.4],
    [1990, 1.8, 9.6, 15.6], [1991, 2.2, 9.4, 15.8], [1992, 2.0, 8.8, 13.6],
    [1993, 2.2, 7.8, 12.2], [1994, 2.4, 7.8, 12.6], [1995, 2.4, 8.0, 12.6],
    [1996, 2.4, 8.2, 13.6], [1997, 2.8, 8.4, 13.6], [1998, 3.0, 10.2, 16.4],
    [1999, 3.8, 12.8, 19.8], [2000, 3.2, 11.4, 19.4], [2001, 3.2, 12.4, 20.6],
    [2002, 3.0, 12.0, 19.6], [2003, 2.6, 11.0, 18.4], [2004, 2.6, 10.4, 17.2],
    [2005, 2.6, 9.8, 16.0], [2006, 2.6, 10.2, 15.8], [2007, 3.2, 11.4, 16.2],
    [2008, 4.2, 9.4, 19.2], [2009, 2.6, 9.2, 16.4], [2010, 2.4, 10.6, 15.4],
    [2011, 2.8, 10.4, 16.8], [2012, 3.2, 9.4, 16.4], [2013, 2.4, 9.6, 15.2],
    [2014, 2.8, 10.4, 15.4], [2015, 2.6, 11.0, 16.6], [2016, 2.6, 10.6, 16.6],
    [2017, 3.0, 12.4, 18.4], [2018, 3.4, 14.0, 19.6], [2019, 4.1, 15.2, 21.7],
]

# Exhibit 2, "Big Board": largest 10 at the start of each decade (= previous
# year-end), rank order as read off the chart, with the printed combined share.
DIMENSIONAL_DECADES = [
    {"year": 1930, "sharePct": 26.8, "names": ["AT&T", "General Motors", "General Electric", "Exxon",
        "Marathon Oil", "DuPont", "Con Edison", "Philadelphia Co.", "NY Central RR", "Penn Central"]},
    {"year": 1940, "sharePct": 33.0, "names": ["AT&T", "General Motors", "DuPont", "Exxon",
        "General Electric", "Union Carbide", "Marathon Oil", "Texaco", "Sears", "Coca-Cola"]},
    {"year": 1950, "sharePct": 26.7, "names": ["AT&T", "General Motors", "DuPont", "Exxon",
        "Union Carbide", "General Electric", "Chevron", "Texaco", "Sears", "Gulf Oil"]},
    {"year": 1960, "sharePct": 30.9, "names": ["AT&T", "General Motors", "DuPont", "Exxon",
        "General Electric", "IBM", "Texaco", "Union Carbide", "Kodak", "Gulf Oil"]},
    {"year": 1970, "sharePct": 25.1, "names": ["IBM", "AT&T", "General Motors", "Exxon",
        "Kodak", "Sears", "Texaco", "Xerox", "General Electric", "Gulf Oil"]},
    {"year": 1980, "sharePct": 17.4, "names": ["IBM", "AT&T", "Exxon", "General Motors",
        "Amoco", "Mobil", "General Electric", "Chevron", "Atlantic Richfield", "Shell Oil"]},
    {"year": 1990, "sharePct": 13.4, "names": ["Exxon", "IBM", "General Electric", "AT&T",
        "Altria", "Merck", "Bristol-Myers Squibb", "DuPont", "Amoco", "BellSouth"]},
    {"year": 2000, "sharePct": 19.9, "names": ["Microsoft", "General Electric", "Cisco", "Walmart",
        "Exxon", "Intel", "Lucent", "IBM", "Citigroup", "Time Warner"]},
    {"year": 2010, "sharePct": 16.2, "names": ["Exxon", "Microsoft", "Walmart", "Apple",
        "Johnson & Johnson", "P&G", "IBM", "JP Morgan", "AT&T", "General Electric"]},
    {"year": 2020, "sharePct": 21.7, "names": ["Apple", "Microsoft", "Amazon", "Google",
        "Berkshire Hathaway", "Facebook", "JP Morgan", "Johnson & Johnson", "Walmart", "Visa"]},
]

# Exhibit 3, "Power Down": annualized excess return vs market after first
# joining the top 10, 1927–2019.
DIMENSIONAL_EXCESS = [{"years": 3, "pct": 0.7}, {"years": 5, "pct": -1.1}, {"years": 10, "pct": -1.5}]

NOTE = (
    "1927–2019: values read off Dimensional’s charts (CRSP, full market cap; pre-1980 ranks 5–10 "
    "approximate). From 2009: own reconstruction — today’s ~2,500 US stocks in iShares ITOT "
    "(S&P Total Market, float-adjusted), each company’s cap moved back in time with its own "
    "price (constant share count), divided by the total market moved with VTI. Buybacks, "
    "issuance and delisted firms are ignored, so past weights are approximate; the 2005–2019 "
    "overlap with Dimensional shows the size of the error (reconstruction ~1–2 pt lower). Before "
    "2009 the method breaks down (bank/AIG dilution in 2009), so it starts there. Not an official series."
)

_CLASS_RE = re.compile(r"\s+(CLASS|CL)\s+[A-Z]$|\s+SERIES\s+[A-Z]$", re.I)

# Short display names for the usual suspects (ITOT names are upper case)
_DISPLAY = {
    "APPLE": "Apple", "NVIDIA": "Nvidia", "MICROSOFT": "Microsoft", "AMAZON.COM INC": "Amazon",
    "ALPHABET": "Alphabet", "BROADCOM INC": "Broadcom", "META PLATFORMS": "Meta",
    "ELI LILLY": "Eli Lilly", "BERKSHIRE HATHAWAY INC": "Berkshire Hathaway",
    "TESLA INC": "Tesla", "JPMORGAN CHASE & CO": "JP Morgan", "VISA": "Visa",
    "EXXONMOBIL HOLDINGS CORP": "Exxon", "EXXON MOBIL CORP": "Exxon", "WALMART INC": "Walmart",
    "JOHNSON & JOHNSON": "Johnson & Johnson", "PROCTER & GAMBLE": "P&G",
    "MICRON TECHNOLOGY": "Micron", "GENERAL ELECTRIC": "General Electric", "GE AEROSPACE": "General Electric",
    "INTERNATIONAL BUSINESS MACHINES CO": "IBM", "INTERNATIONAL BUSINESS MACHINES": "IBM",
    "AT&T INC": "AT&T", "VERIZON COMMUNICATIONS INC": "Verizon", "UNITEDHEALTH GROUP INC": "UnitedHealth",
    "BANK OF AMERICA CORP": "Bank of America", "CHEVRON CORP": "Chevron", "PFIZER INC": "Pfizer",
    "CISCO SYSTEMS INC": "Cisco", "INTEL CORPORATION": "Intel", "INTEL CORP": "Intel", "BOEING": "Boeing",
    "UNITEDHEALTH GROUP": "UnitedHealth", "VERIZON COMMUNICATIONS": "Verizon", "AT&T": "AT&T",
}


def _company_key(name):
    return _CLASS_RE.sub("", (name or "").strip().upper())


def _display(key):
    if key in _DISPLAY:
        return _DISPLAY[key]
    s = re.sub(r"\s+(INC|CORP|CO|LTD|PLC|HOLDINGS|GROUP)\.?$", "", key)
    return s.title().replace("&Amp;", "&")


def _yf_symbol(sym):
    return sym.strip().replace(" ", "-").replace(".", "-").replace("/", "-")


def _companies_from_holdings(holdings):
    """Merge share classes into companies. Returns ({key: weight}, {key: [(yfsym, weight)]})."""
    comp_w, comp_cls = {}, {}
    for h in holdings:
        sym = (h.get("symbol") or "").strip()
        if not sym or sym == "-" or h.get("weight_pct") is None:
            continue
        key = _company_key(h.get("name"))
        if not key:
            continue
        comp_w[key] = comp_w.get(key, 0.0) + h["weight_pct"]
        comp_cls.setdefault(key, []).append((_yf_symbol(sym), h["weight_pct"]))
    return comp_w, comp_cls


def _top_share(caps, n, total):
    return round(sum(sorted(caps.values(), reverse=True)[:n]) / total * 100, 2)


def _reconstruct(comp_w, comp_cls, total_weight):
    """Year-end top-N weights, rank lists and excess returns of top-10 entrants."""
    import pandas as pd
    import yfinance as yf

    universe = sorted(comp_w, key=comp_w.get, reverse=True)[:UNIVERSE_N]
    tickers = sorted({s for k in universe for s, _ in comp_cls[k]} | {MARKET_TICKER})
    df = yf.download(tickers, start=f"{START_YEAR}-12-01", interval="1mo", auto_adjust=False,
                     progress=False, group_by="ticker", threads=True)
    lv0 = set(df.columns.get_level_values(0))
    close = pd.DataFrame({t: df[t]["Close"] for t in tickers if t in lv0})
    adj = pd.DataFrame({t: df[t]["Adj Close"] for t in tickers if t in lv0})
    close, adj = close.dropna(how="all"), adj.dropna(how="all")
    if MARKET_TICKER not in close.columns or close.empty:
        raise ValueError("market series missing from download")

    # Year-end rows = December monthly bars of completed years
    this_year = datetime.now().year
    dec = [ts for ts in close.index if ts.month == 12 and START_YEAR <= ts.year < this_year]
    last_px = close.ffill().iloc[-1]
    mkt_today = float(last_px[MARKET_TICKER])

    yearly, ranks = [], {}
    for ts in dec:
        row = close.loc[ts]
        caps = {}
        for k in universe:
            c = 0.0
            for s, w in comp_cls[k]:
                if s in row and pd.notna(row[s]) and pd.notna(last_px.get(s)) and last_px[s]:
                    c += w * float(row[s]) / float(last_px[s])
            if c > 0:
                caps[k] = c
        total = total_weight * float(row[MARKET_TICKER]) / mkt_today
        if len(caps) < 10 or not total:
            continue
        top10 = sorted(caps, key=caps.get, reverse=True)[:10]
        ranks[ts.year] = top10
        yearly.append({"year": ts.year, **{f"top{n}": _top_share(caps, n, total) for n in TOP_NS},
                       "names": [_display(k) for k in top10]})

    # Entrants: in the top 10 at year-end Y, never at an earlier year-end in the window
    def tr(k, y0, y1):
        """Total return of company k (first share class) between two Dec rows."""
        s = comp_cls[k][0][0]
        try:
            a = adj.loc[[t for t in adj.index if t.month == 12 and t.year == y0][0], s]
            b = adj.loc[[t for t in adj.index if t.month == 12 and t.year == y1][0], s]
        except (IndexError, KeyError):
            return None
        return float(b / a) if pd.notna(a) and pd.notna(b) and a else None

    entrants, seen = [], set(ranks.get(START_YEAR, []))
    for y in sorted(ranks):
        if y == START_YEAR:
            continue
        for k in ranks[y]:
            if k in seen:
                continue
            seen.add(k)
            # "First" joining as in Dimensional: skip names already in one of
            # their earlier decade lists (e.g. JP Morgan, top 10 in 2010)
            if any(_display(k) in d["names"] for d in DIMENSIONAL_DECADES if d["year"] <= y):
                continue
            e = {"name": _display(k), "year": y, "rank": ranks[y].index(k) + 1}
            for h in HORIZONS:
                if y + h >= this_year:
                    continue
                rs, rm = tr(k, y, y + h), None
                s0 = [t for t in adj.index if t.month == 12 and t.year == y]
                s1 = [t for t in adj.index if t.month == 12 and t.year == y + h]
                if s0 and s1:
                    rm = float(adj.loc[s1[0], MARKET_TICKER] / adj.loc[s0[0], MARKET_TICKER])
                if rs and rm:
                    e[f"ex{h}"] = round((rs ** (1 / h) - rm ** (1 / h)) * 100, 2)
            entrants.append(e)

    excess = []
    for h in HORIZONS:
        vals = [e[f"ex{h}"] for e in entrants if f"ex{h}" in e]
        if vals:
            srt = sorted(vals)
            med = (srt[len(srt) // 2] if len(srt) % 2 else (srt[len(srt) // 2 - 1] + srt[len(srt) // 2]) / 2)
            excess.append({"years": h, "pct": round(sum(vals) / len(vals), 2),
                           "median": round(med, 2), "n": len(vals)})
    return yearly, entrants, excess


def calc_largest_stocks(fetch_etf_holdings):
    """Build LD.largestStocks. `fetch_etf_holdings` is fetch_data's shared helper."""
    out = {
        "asOf": datetime.now().strftime("%Y-%m-%d"),
        "source": DIMENSIONAL_SOURCE, "sourceUrl": DIMENSIONAL_URL, "note": NOTE,
        "dimensional": {"weights": DIMENSIONAL_WEIGHTS, "decades": DIMENSIONAL_DECADES,
                        "excess": DIMENSIONAL_EXCESS},
        "recon": {"startYear": START_YEAR, "yearly": [], "entrants": [], "excess": [],
                  "today": None, "stale": False},
    }

    data = fetch_etf_holdings("ITOT")
    holdings = data.get("holdings") or []
    if data.get("source") != "ishares" or len(holdings) < 1000:
        holdings = []   # the stockanalysis fallback lists too few names for a market total
    comp_w, comp_cls = _companies_from_holdings(holdings)
    total_weight = sum(comp_w.values())

    if comp_w:
        top = sorted(comp_w, key=comp_w.get, reverse=True)[:10]
        out["recon"]["today"] = {
            "date": out["asOf"],
            **{f"top{n}": round(sum(comp_w[k] for k in top[:n]) / total_weight * 100, 2) for n in TOP_NS},
            "top10List": [{"name": _display(k), "pct": round(comp_w[k] / total_weight * 100, 2)} for k in top],
        }

    cache = None
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        pass
    fresh = (cache and cache.get("schema") == CACHE_SCHEMA_VERSION
             and time.time() - cache.get("ts", 0) < CACHE_MAX_AGE_DAYS * 86400)

    if fresh:
        recon = cache["recon"]
    elif comp_w:
        try:
            yearly, entrants, excess = _reconstruct(comp_w, comp_cls, total_weight)
            recon = {"yearly": yearly, "entrants": entrants, "excess": excess}
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump({"schema": CACHE_SCHEMA_VERSION, "ts": time.time(), "recon": recon}, f)
        except Exception as e:
            print(f"  ⚠ largest stocks reconstruction failed: {e}")
            recon = (cache or {}).get("recon")
            out["recon"]["stale"] = bool(recon)
    else:
        recon = (cache or {}).get("recon")
        out["recon"]["stale"] = bool(recon)

    if recon:
        out["recon"].update({k: recon[k] for k in ("yearly", "entrants", "excess")})
    return out
