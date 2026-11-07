"""
periodic_table.py – "Periodic table" of annual returns of the main asset
classes in Swiss francs: the last 10 full calendar years plus the current
year to date, each column ranked from highest to lowest return.

Update of the Hinder Asset Management table "Jahresrenditen der
Hauptanlageklassen in Schweizer Franken (2010-2020)", same 18 asset classes
and colours. The original used paid index data (MSCI, FTSE EPRA/NAREIT,
Barclays, UBS CMCI...); this uses free proxies:
- ETF total returns from Yahoo (auto-adjusted closes, distributions
  reinvested, after fund fees / withholding tax) on the same indices where
  possible;
- Swiss equities = SPI TR (SIX, data/spi_six_tr_monthly.csv), extended after
  the CSV's last month with CHSPI.SW;
- money market = monthly 3-month interbank rates (OECD via FRED), compounded,
  missing recent months carried forward, plus the currency move vs CHF;
- FX = Federal Reserve H.10 noon rates via FRED at each year-end (Yahoo's
  USDCHF=X / EURCHF=X year-end closes were off by up to 1 pt); the YTD end
  point uses Yahoo's latest FX close because H.10 lags about a week.

Checked against the original table on the 2016-2020 overlap: most cells
within +/-1 pt. Swiss bonds use the 7-15y segment (CSBGC0.SW) because no
free all-maturity Swiss government bond series exists; it is 1-2 pt off.

On failure the last good result is served from PERIODIC_TABLE_CACHE_PATH
(git-ignored), flagged stale.
"""

import json
import os
import time
from datetime import date

import pandas as pd

from valuation_yields import _fetch_fred_series

N_YEARS = 10

# key, label, (ticker | special), currency, background, text colour, source
ASSETS = [
    ("GOLD",   "Gold",                      "GC=F",      "USD", "#FFCC00", "#000", "Gold, COMEX front-month future (USD)"),
    ("BD_US",  "US Bonds",                  "GOVT",      "USD", "#00FFFF", "#000", "iShares US Treasury Bond ETF (GOVT)"),
    ("BD_CH",  "Swiss Bonds",               "CSBGC0.SW", "CHF", "#0000FF", "#fff", "iShares Swiss Dom. Govt Bond 7-15 (CSBGC0)"),
    ("RE_US",  "US Real Estate",            "VNQ",       "USD", "#339966", "#fff", "Vanguard Real Estate ETF (VNQ)"),
    ("RE_CH",  "Swiss Real Estate Funds",   "SRECHA.SW", "CHF", "#00FF00", "#000", "UBS SXI Real Estate Funds ETF (SRECHA)"),
    ("BD_EM",  "Emerging Market Bonds",     "EMB",       "USD", "#000080", "#fff", "iShares JPM USD EM Bond ETF (EMB)"),
    ("EQ_US",  "US Equities",               "SPY",       "USD", "#FF6600", "#000", "SPDR S&P 500 ETF (SPY)"),
    ("MM_US",  "Money Market USD",          "fred:IR3TIB01USM156N", "USD", "#808080", "#fff", "3-month USD interbank rate (OECD/FRED)"),
    ("BD_EU",  "European Bonds",            "IEGA.AS",   "EUR", "#B7DFF0", "#000", "iShares Core EUR Govt Bond ETF (IEGA)"),
    ("MM_CH",  "Money Market CHF",          "fred:IR3TIB01CHM156N", "CHF", "#FFFFFF", "#000", "3-month CHF interbank rate (OECD/FRED)"),
    ("MM_EU",  "Money Market EUR",          "fred:IR3TIB01EZM156N", "EUR", "#C0C0C0", "#000", "3-month EUR interbank rate (OECD/FRED)"),
    ("EQ_CH",  "Swiss Equities",            "spi",       "CHF", "#FF0000", "#fff", "SPI Total Return (SIX), CHSPI.SW after the last SIX month"),
    ("CMD",    "Commodities",               "CCUSAS.SW", "USD", "#333333", "#fff", "UBS CMCI Composite SF ETF (CCUSAS)"),
    ("EQ_PAC", "Pacific ex Japan Equities", "EPP",       "USD", "#800080", "#fff", "iShares MSCI Pacific ex Japan ETF (EPP)"),
    ("EQ_JP",  "Japan Equities",            "EWJ",       "USD", "#993366", "#fff", "iShares MSCI Japan ETF (EWJ)"),
    ("RE_EU",  "European Real Estate",      "IPRP.AS",   "EUR", "#99CC00", "#000", "iShares European Property Yield ETF (IPRP)"),
    ("EQ_EU",  "Eurozone Equities",         "EZU",       "USD", "#FF00FF", "#000", "iShares MSCI Eurozone ETF (EZU)"),
    ("EQ_EM",  "Emerging Market Equities",  "EEM",       "USD", "#CC99FF", "#000", "iShares MSCI Emerging Markets ETF (EEM)"),
]

PERIODIC_TABLE_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "periodic_table_cache.json")
SPI_SIX_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "spi_six_tr_monthly.csv")

PERIODIC_TABLE_NOTE = (
    "Total returns in CHF, ranked from highest to lowest in each column; the last column is the current "
    "year to date. Update of the Hinder Asset Management table (2011-2020) with free proxies instead of "
    "the original paid indices: ETF total returns (distributions reinvested, after fund fees and "
    "withholding taxes, so slightly below the indices), SPI TR for Swiss equities, monthly 3-month "
    "interbank rates compounded for money market, FX at year-end (Federal Reserve H.10 via FRED). "
    "Swiss Bonds use the 7-15-year segment as a proxy for the all-maturity index. On 2016-2020 most "
    "figures are within about 1 pt of the original table. Past performance is not a guide to future returns."
)


def _fred_series(sid):
    s = pd.Series(_fetch_fred_series(sid))
    s.index = pd.to_datetime(s.index)
    time.sleep(1)                          # FRED blocks bursts
    return s.sort_index()


def _compute(today=None):
    import yfinance as yf

    today = pd.Timestamp(today or date.today())
    cur = today.year
    years = list(range(cur - N_YEARS, cur))           # full calendar years
    tickers = sorted({a[2] for a in ASSETS if a[2] not in ("spi",) and not a[2].startswith("fred:")}
                     | {"CHSPI.SW", "USDCHF=X", "EURCHF=X"})
    px = yf.download(tickers, start=f"{years[0] - 1}-12-01", end=(today + pd.Timedelta(days=1)).date().isoformat(),
                     auto_adjust=True, progress=False)["Close"].ffill()
    px = px[px.index <= today]
    as_of = px.drop(columns=["USDCHF=X", "EURCHF=X"]).dropna(how="all").index[-1]

    # FX: FRED year-ends, Yahoo for the YTD end point
    usd = _fred_series("DEXSZUS")
    eurusd = _fred_series("DEXUSEU")
    usd_ye = usd.groupby(usd.index.year).last()
    eur_ye = (usd * eurusd).dropna()
    eur_ye = eur_ye.groupby(eur_ye.index.year).last()
    fx_ye = {"USD": usd_ye, "EUR": eur_ye}
    fx_now = {"USD": float(px["USDCHF=X"].dropna().iloc[-1]), "EUR": float(px["EURCHF=X"].dropna().iloc[-1])}

    def fx_at(ccy, y):           # y = year for a year-end, or None for "now"
        if ccy == "CHF":
            return 1.0
        return fx_now[ccy] if y is None else float(fx_ye[ccy].loc[y])

    ye = px.groupby(px.index.year).last()
    now = px.iloc[-1]

    # SPI TR: SIX monthly CSV, chained with CHSPI.SW after its last month
    six = pd.read_csv(SPI_SIX_CSV, index_col=0, parse_dates=True).iloc[:, 0].dropna()
    six_ye = six.groupby(six.index.year).last()
    chspi = px["CHSPI.SW"].dropna()

    def spi_level(y):
        if y is None or y > six.index[-1].year or (y == six.index[-1].year and six.index[-1].month < 12):
            # beyond the CSV: last SIX month-end x CHSPI move since then
            anchor = six.index[-1]
            base = chspi[chspi.index <= anchor + pd.offsets.MonthEnd(0)]
            end = chspi if y is None else chspi[chspi.index.year <= y]
            return float(six.iloc[-1]) * float(end.iloc[-1]) / float(base.iloc[-1])
        return float(six_ye.loc[y])

    rates = {}
    for a in ASSETS:
        if a[2].startswith("fred:"):
            rates[a[0]] = _fred_series(a[2][5:])

    def mm_growth(key, y, upto):
        """Compounded money-market growth over calendar year y up to `upto`."""
        r = rates[key]
        months = pd.date_range(f"{y}-01-01", upto, freq="MS")
        g = 1.0
        for m in months:
            avail = r[r.index <= m]
            if avail.empty:
                return None
            rate = float(avail.iloc[-1])                 # carry the last published rate forward
            month_end = m + pd.offsets.MonthEnd(0)
            frac = 1.0 if upto >= month_end else (upto - m).days / month_end.day
            g *= (1 + rate / 1200) ** frac
        return g

    def ret(asset, y):
        key, _, src, ccy = asset[:4]
        y_end = None if y == cur else y
        try:
            if src.startswith("fred:"):
                upto = as_of if y == cur else pd.Timestamp(f"{y}-12-31")
                g = mm_growth(key, y, upto)
                if g is None:
                    return None
            elif src == "spi":
                g = spi_level(y_end) / spi_level(y - 1)
            else:
                p0 = ye[src].get(y - 1)
                p1 = now[src] if y == cur else ye[src].get(y)
                if pd.isna(p0) or pd.isna(p1):
                    return None
                g = float(p1) / float(p0)
            g *= fx_at(ccy, y_end) / fx_at(ccy, y - 1)
            return round((g - 1) * 100, 1)
        except (KeyError, IndexError):
            return None

    cols = years + [cur]
    assets = [{"key": a[0], "label": a[1], "bg": a[4], "fg": a[5], "source": a[6],
               "ret": [ret(a, y) for y in cols]} for a in ASSETS]
    return {
        "asOf": as_of.date().isoformat(),
        "columns": [{"year": y, "ytd": y == cur} for y in cols],
        "assets": assets,
        "note": PERIODIC_TABLE_NOTE,
        "stale": False,
    }


def calc_periodic_table():
    try:
        res = _compute()
        try:
            with open(PERIODIC_TABLE_CACHE_PATH, "w") as f:
                json.dump(res, f)
        except OSError as e:
            print(f"  ⚠ could not write periodic table cache: {e}")
        return res
    except Exception as e:
        try:
            with open(PERIODIC_TABLE_CACHE_PATH) as f:
                res = json.load(f)
        except (OSError, json.JSONDecodeError):
            raise e
        print(f"  ⚠ live periodic table failed ({e}) — using cache from {res['asOf']}")
        res["stale"] = True
        return res


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    pt = calc_periodic_table()
    print("as of", pt["asOf"])
    hdr = "".join(f"{('YTD' if c['ytd'] else c['year']):>7}" for c in pt["columns"])
    print(f"{'':28s}{hdr}")
    for a in pt["assets"]:
        print(f"{a['label']:28s}" + "".join(f"{'—' if v is None else v:>7}" for v in a["ret"]))
