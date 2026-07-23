#!/usr/bin/env python3
"""
fetch_data.py  –  Lädt ALLE Marktdaten (YTD + 52W-Bandbreite) von Yahoo Finance
                  und schreibt live_data.js für das Dashboard.

Aufruf:  python3 fetch_data.py
Bedarf:  pip install yfinance
"""

import yfinance as yf
import json
import os
import csv
import io
import requests
from datetime import datetime, timezone, timedelta
from hyperscaler_capex import fetch_hyperscaler_capex

# ── Konfiguration ────────────────────────────────────────────────────────────

YTD_YEAR = 2026
YTD_START = datetime(YTD_YEAR, 1, 1, tzinfo=timezone.utc)

# FX-Paare (alle → CHF)
FX_TICKERS = {
    "USD": "USDCHF=X",
    "EUR": "EURCHF=X",
    "GBP": "GBPCHF=X",
}

# ── Hauptmärkte: (name, ticker, Währung des ETF) ─────────────────────────────
# Ticker = None → kein ETF verfügbar, Bandbreite wird nicht angezeigt
MAIN_MARKETS = [
    ("Emerging Market Equities",          "EEM",       "USD"),
    ("Japanese Equities",                 "EWJ",       "USD"),
    ("Global Equities – Small Caps",      "IUSN.DE",   "EUR"),
    ("US Equities (S&P 500)",             "SPY",       "USD"),
    ("Magnificent 7",                     "MAGS",      "USD"),
    ("Global Equities",                   "ACWI",      "USD"),
    ("Global Equities Ex-US (MSCI W ex USA)", "IWQU.L", "GBP"),
    ("Pacific ex Japan Equities",         "EPP",       "USD"),
    ("Swiss Equities – Small Caps",       "CSSMIM.SW", "CHF"),
    ("UK Equities",                       "EWU",       "USD"),
    ("Swiss Equities (SPI)",              "CHSPI.SW",  "CHF"),
    ("Eurozone Equities (EURO STOXX 50)", "FEZ",       "USD"),
    ("US Real Estate (Equities)",         "VNQ",       "USD"),
    ("Swiss Real Estate (SXI Broad)",     "SRFCHA.SW", "CHF"),
    ("European Real Estate (Equities)",   "IPRP.AS",   "EUR"),
    ("Asian Real Estate (Equities)",      "RWX",       "USD"),
    ("Commodities (Diversified, unhedged)", "ICOM.L",    "USD"),
    ("Gold Bullion (unhedged)",            "ZGLD.SW",   "CHF"),
    ("CHF Bonds",                         "CHCORP.SW", "CHF"),
    ("EM Bonds Local Currency",           "EMLC",      "USD"),
    ("Global Bonds (CHF hedged)",         "AGGH.SW",   "CHF"),
    ("EUR Bonds",                         "IBGE.L",    "GBP"),
    ("USD Bonds",                         "AGG",       "USD"),
    ("CHF Corporate Bonds",               "CHCORP.SW", "CHF"),
    ("USD Corporate Bonds",               "LQD",       "USD"),
    ("EUR Corporate Bonds",               "IEAC.AS",   "EUR"),
    ("Inflation Linked",                  "TIP",       "USD"),
    ("Money Market CHF",                  "CSBGC0.SW", "CHF"),
    ("Money Market GBP",                  "CSH2.L",    "GBP"),
    ("Money Market USD",                  "BIL",       "USD"),
    ("Money Market EUR",                  "EXVM.DE",   "EUR"),
    ("USD / CHF",                         "USDCHF=X",  "CHF"),
    ("EUR / CHF",                         "EURCHF=X",  "CHF"),
    ("JPY / CHF",                         "JPYCHF=X",  "CHF"),
]

# ── Sub-market breakdowns (parent market name → list of sub-items) ───────────
SUB_MARKETS = {
    "Emerging Market Equities": [
        ("Taiwan",       "EWT",  "USD"),
        ("China",        "MCHI", "USD"),
        ("Korea",        "EWY",  "USD"),
        ("India",        "INDA", "USD"),
        ("South Africa", "EZA",  "USD"),
        ("Brazil",       "EWZ",  "USD"),
        ("Saudi Arabia", "KSA",  "USD"),
        ("Mexico",       "EWW",  "USD"),
        ("UAE",          "UAE",  "USD"),
        ("Indonesia",    "EIDO", "USD"),
        ("Thailand",     "THD",  "USD"),
        ("Malaysia",     "EWM",  "USD"),
    ],
    "US Equities (S&P 500)": [
        ("Nasdaq 100",   "QQQ",      "USD"),
        ("Russell 2000", "IWM",      "USD"),
    ],
    "Magnificent 7": [
        ("Apple",     "AAPL",  "USD"),
        ("Microsoft", "MSFT",  "USD"),
        ("Alphabet",  "GOOGL", "USD"),
        ("Amazon",    "AMZN",  "USD"),
        ("Nvidia",    "NVDA",  "USD"),
        ("Meta",      "META",  "USD"),
        ("Tesla",     "TSLA",  "USD"),
    ],
    "Swiss Equities (SPI)": [
        ("SMI",       "CSSMI.SW",  "CHF"),
        ("SPI Extra", "CSSMIM.SW", "CHF"),
    ],
    "Eurozone Equities (EURO STOXX 50)": [
        ("France",      "EWQ",  "USD"),
        ("Germany",     "EWG",  "USD"),
        ("Netherlands", "EWN",  "USD"),
        ("Spain",       "EWP",  "USD"),
        ("Italy",       "EWI",  "USD"),
        ("Finland",     "EFNL", "USD"),
        ("Belgium",     "EWK",  "USD"),
    ],
}

# ── World Market Capitalisation ──────────────────────────────────────────────
# Baseline: Q1 2026 (31 March 2026) — source: Russell 3000 / MSCI ACWI IMI
# Dollar values are updated dynamically by scaling with ETF performance since baseline.
# This avoids any web-scraping: we already download these ETFs for the main dashboard.
WORLD_MKTCAP_BASELINE = {
    "date":  "2026-03-31",
    "total": 100.9,   # USD trillions
    "regions": [
        {"name": "US Market",             "pct": 63, "trillions": 62.6, "etf": "SPY",  "ccy": "USD", "color": "#003a5c"},
        {"name": "International Developed","pct": 26, "trillions": 26.6, "etf": "EFA",  "ccy": "USD", "color": "#b8922a"},
        {"name": "Emerging Markets",       "pct": 11, "trillions": 11.7, "etf": "EEM",  "ccy": "USD", "color": "#5a7a3a"},
    ],
}
MKTCAP_BASELINE_DATE = datetime(2026, 3, 31, tzinfo=timezone.utc)

# SpaceX (SPCX) IPO offering size — source: S-1 filed 2026-05-20, pricing
# confirmed 2026-06-11 (555,555,555 Class A shares at $135). Used as a stable
# reference for SPCX's free float instead of yfinance's `floatShares`, which
# reports ~281M — suspiciously close to exactly half of this — the same
# share-class undercount bug already found and fixed for `sharesOutstanding`
# (see fetch_live_float_cap()).
#
# TODO — review from 2026-08-05 onward: SpaceX's IPO lock-up expires around
# its 2026-08-04 earnings date, after which more shares legitimately join the
# tradable float and this hardcoded anchor will go stale (too low). Re-check
# yfinance's floatShares against real volume/secondary-sale data at that
# point and update or remove SPCX_IPO_FLOAT_SHARES accordingly. See CLAUDE.md.
SPCX_IPO_FLOAT_SHARES = 555_555_555

# ── MAG7 Market Cap ──────────────────────────────────────────────────────────
# Baseline market caps at Q1 2026 (31 March 2026), in USD trillions.
# Source: Bloomberg / public filings, rounded to 2 decimal places.
# Free float market caps at Q1 2026 baseline (total market cap × free float %).
# Free float % source: MSCI / Bloomberg estimates.
MAG7_BASELINE = [
    {"name": "Apple",     "ticker": "AAPL", "totalT": 3.11,  "freeFloat": 0.995},
    {"name": "Microsoft", "ticker": "MSFT", "totalT": 2.83,  "freeFloat": 0.995},
    {"name": "Nvidia",    "ticker": "NVDA", "totalT": 2.52,  "freeFloat": 0.975},
    {"name": "Amazon",    "ticker": "AMZN", "totalT": 2.07,  "freeFloat": 0.940},
    # Alphabet: yfinance's `marketCap` field is company-wide no matter which
    # class ticker you query (verified live: GOOGL and GOOG both report
    # ~$4.17T) — so only GOOGL is fetched (see get_company_market_cap());
    # a separate GOOG entry would double-count Alphabet. Fallback totalT
    # below combines the old GOOGL (1.98T) + GOOG (1.64T) baseline values.
    {"name": "Alphabet",  "ticker": "GOOGL","totalT": 3.62,  "freeFloat": 0.930},
    {"name": "Meta",      "ticker": "META", "totalT": 1.61,  "freeFloat": 0.860},
    {"name": "Tesla",     "ticker": "TSLA", "totalT": 0.79,  "freeFloat": 0.840},
    # SpaceX (SPCX): Nasdaq IPO 2026-06-12. Too recent for the baseline-scaling
    # method used below (fetch_weekly's 1y/weekly series has <10 closes so far,
    # and there is no pre-IPO price to compare against 31 March 2026 anyway).
    # Instead computed live every run as price × floatShares via
    # fetch_live_float_cap() — floatShares, not sharesOutstanding, because Musk
    # retains ~42% equity / ~85% voting power through multi-class shares, so
    # total shares outstanding materially overstates the public float.
    # totalT/freeFloat here are only the fallback if the live fetch fails.
    {"name": "SpaceX",    "ticker": "SPCX",  "totalT": 2.419, "freeFloat": 0.043, "live_float": True},
]

# ── Long-Term Market Summary config ─────────────────────────────────────────
# All returns will be calculated in CHF, annualized.
# ticker = None → no ETF available; show "—"
LONGTERM_MARKETS = [
    # All ETFs are Irish UCITS (or Swiss-domiciled) to reflect tax-efficient Swiss investor experience.
    # US-domiciled ETFs (SPY, EFA, EEM) excluded: higher withholding tax drag (~15% on dividends).
    #
    # name,                       ticker,        ccy,   group,   index / ETF description
    ("CH Market (SPI)",           "__SPI_SIX__", "CHF", "Stocks", "SPI TR (SIX index) + CHSPI.SW UCITS"),
    ("US Stock Market",           "CSPX.L",      "USD", "Stocks", "iShares Core S&P 500 UCITS ETF (LSE USD, Irish domicile, since 2010)"),
    ("Intl Developed ex US",      "IWQU.L",      "GBP", "Stocks", "iShares MSCI World ex-US UCITS ETF (LSE, Irish domicile, since 2014)"),
    ("Emerging Markets",          "IEEM.SW",     "USD", "Stocks", "iShares MSCI EM UCITS ETF (SIX, Irish domicile, since 2009)"),
    ("Global Real Estate",        "IWDP.L",      "GBP", "Stocks", "iShares Dev. Mkts Property Yield UCITS ETF (LSE, Irish domicile, since 2009, unhedged CHF)"),
    ("Swiss Real Estate",         "SRECHA.SW",   "CHF", "Stocks", "iShares Swiss Real Estate ETF (SIX, since 2011)"),
    ("Swiss Bond Index",          "CHCORP.SW",   "CHF", "Bonds",  "iShares CHF Corp Bond ETF (SIX, UCITS, since 2014)"),
    ("Global Bonds (CHF hedged)", "AGGH.SW",     "CHF", "Bonds",  "iShares Core Gbl Agg Bond CHF Hdgd UCITS ETF (SIX, since 2018)"),
]

# Path to the portfolio-backtest SPI TR cache (already monthly, already in CHF)
SPI_SIX_CSV = os.path.expanduser(
    "~/portfolio-backtest/data/cache/spi_six_merged.csv"
)

LONGTERM_PERIODS = [1, 5, 10, 15, 20]   # years

# ── ETF holdings (MSCI ACWI country weights, S&P 500 top 10) ────────────────
# Set up 2026-07-23. Replaces the static country-weight tables previously
# hardcoded in longterm.html with a daily fetch of each ETF's own holdings
# file, aggregated fresh every run — see fetch_etf_holdings() below.
ETF_HOLDINGS_SOURCES = {
    "ACWI": {
        "primary": "ishares",
        "ishares_url": "https://www.ishares.com/us/products/239600/ishares-msci-acwi-etf/1467271812596.ajax",
        "ishares_params": {"fileType": "csv", "fileName": "ACWI_holdings", "dataType": "fund"},
    },
    "SPY": {
        "primary": "ssga",
        "ssga_url": "https://www.ssga.com/us/en/individual/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx",
    },
}

# MSCI ACWI country weights measure free-float-adjusted weight per the
# official MSCI (index provider, licensed to iShares for the ACWI ETF)
# methodology — not an in-house approximation — when fetched from the
# primary ishares.com source. See calc_acwi_country_weights().
ACWI_METHODOLOGY_NOTE = (
    "Free-float-adjusted country weight per the official MSCI ACWI index "
    "methodology (as implemented by the iShares MSCI ACWI ETF, ticker "
    "ACWI), recomputed every run from ACWI's live daily holdings file — "
    "not a static approximation, when sourced from ishares.com."
)

# How many top-by-weight holdings to classify by country when the primary
# ishares.com source (which has a per-holding Location field) is down and
# we fall back to stockanalysis.com (which doesn't). Keeps the degraded
# path's runtime bounded — see calc_acwi_country_weights().
ACWI_FALLBACK_COUNTRY_TOP_N = 100

SPY_TOP10_HISTORY_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spy_top10_history.csv")
SPY_TOP10_N = 10

# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _build_spi_chf_series():
    """
    Best-quality SPI CH Market monthly series in CHF:
    1. Download CHSPI.SW ETF (clean, reliable, from ~2014)
    2. Prepend SIX TR index data (from backtest cache, 1987–splice)
       normalised to the ETF level at the overlap date.
    This gives accurate 1Y/5Y/10Y from the ETF and valid 15Y/20Y from the index.
    """
    try:
        import pandas as pd

        # --- A) CHSPI.SW ETF (primary, reliable) ---
        etf = fetch_monthly_max("CHSPI.SW")
        if not etf:
            return None
        etf_s = pd.Series({pd.Timestamp.utcfromtimestamp(t): v for t, v in etf})
        etf_s.index = etf_s.index.tz_localize(None)

        # --- B) SIX TR index (long history) ---
        six_raw = load_spi_six_series()
        if not six_raw:
            # Fallback: ETF only
            return etf
        six_s = pd.Series({pd.Timestamp.utcfromtimestamp(t): v for t, v in six_raw})
        six_s.index = six_s.index.tz_localize(None)

        # --- C) Splice: normalise SIX to ETF level at ETF inception ---
        # Find overlap: first month of ETF data
        etf_start = etf_s.index[0]
        # Find closest SIX point at ETF inception
        six_at_start = six_s.asof(etf_start)
        etf_at_start = etf_s.iloc[0]
        if six_at_start is None or pd.isna(six_at_start) or six_at_start == 0:
            return etf
        scale = etf_at_start / six_at_start

        # Keep SIX only for dates BEFORE ETF inception, scaled
        six_pre = six_s[six_s.index < etf_start] * scale

        # Combine: SIX (old, scaled) + ETF (recent, authoritative)
        combined = pd.concat([six_pre, etf_s]).sort_index()
        combined = combined[~combined.index.duplicated(keep='last')]

        return [(int(ts.timestamp()), float(v)) for ts, v in combined.items()]
    except Exception as e:
        print(f"\n  ⚠ SPI splice error: {e}")
        return None

def load_spi_six_series():
    """Load SPI TR monthly series from portfolio-backtest cache. Returns [(ts_int, price)]."""
    try:
        import pandas as pd
        df = pd.read_csv(SPI_SIX_CSV, index_col=0, parse_dates=True)
        s  = df.iloc[:, 0].dropna()
        return [(int(ts.timestamp()), float(v)) for ts, v in s.items()]
    except Exception as e:
        print(f"  ⚠ Could not load SPI SIX CSV: {e}")
        return None

def calc_world_mktcap(fx_weekly, cached_series=None):
    """
    Update World Market Cap dollar values by scaling the Q1-2026 baseline
    forward using each region's ETF price performance (in USD).
    cached_series: dict {ticker: [(ts, price), ...]} — reuses already-downloaded data.
    Percentages are re-derived from the updated dollar values.
    Returns a dict ready for live_data.js.
    """
    baseline_ts = int(MKTCAP_BASELINE_DATE.timestamp())
    results = []
    total_updated = 0.0

    for region in WORLD_MKTCAP_BASELINE["regions"]:
        ticker = region["etf"]
        try:
            # Prefer cached data to avoid duplicate downloads / rate-limit hits
            if cached_series and ticker in cached_series:
                series = cached_series[ticker]
            else:
                series = fetch_monthly_max(ticker)
            if not series or len(series) < 2:
                raise ValueError("no data")

            # Find price at (or nearest to) baseline date
            base_idx = min(range(len(series)), key=lambda i: abs(series[i][0] - baseline_ts))
            base_price = series[base_idx][1]

            # Last completed month-end
            now = datetime.now(timezone.utc)
            cutoff = datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp() - 1
            completed = [(t, v) for t, v in series if t <= cutoff]
            curr_price = completed[-1][1] if completed else series[-1][1]

            growth = curr_price / base_price
            updated_T = round(region["trillions"] * growth, 1)
        except Exception:
            # Fallback to baseline value
            updated_T = region["trillions"]

        results.append({
            "name":      region["name"],
            "trillions": updated_T,
            "color":     region["color"],
        })
        total_updated += updated_T

    # Re-derive percentages
    for r in results:
        r["pct"] = round(r["trillions"] / total_updated * 100)

    # Fix rounding so pcts sum to 100
    diff = 100 - sum(r["pct"] for r in results)
    if diff != 0:
        results[0]["pct"] += diff   # absorb rounding into largest segment

    return {
        "baseline":   WORLD_MKTCAP_BASELINE["date"],
        "updatedTo":  datetime.now(timezone.utc).strftime("%d.%m.%Y"),
        "totalT":     round(total_updated, 1),
        "regions":    results,
    }

def calc_mag7(world_total_t):
    """
    Compute free float market cap for each MAG7+SpaceX company.
    For established listed stocks: live total market cap via
    get_company_market_cap() — the same source calc_mag7_cap_weighted() uses
    on the YTD tab — × each company's free-float % (MSCI/Bloomberg estimate,
    a slow-moving structural figure, not the source of the earlier tab
    divergence). This section's "trillions" is a free-float cap, unlike the
    YTD tab's cap-weighted weights which use full market cap, so the two
    tabs' weights will be close but not bit-identical — that residual gap
    (≲1pt per company) is the intentional free-float discount, not a bug.
    For live_float entries (SpaceX/SPCX, IPO too recent for a Q1-2026
    baseline and whose sharesOutstanding/floatShares both need correction):
    computed directly each run as live price × floatShares via
    fetch_live_float_cap().
    For static entries (no ticker at all): baseline free float cap kept fixed.
    Returns combined free float $ trillions + % of world / % of US market.
    """
    total_ff = 0.0
    stocks_out = []
    for stock in MAG7_BASELINE:
        ticker       = stock["ticker"]
        baseline_ff  = round(stock["totalT"] * stock["freeFloat"], 3)  # free float at baseline
        display_totalT     = stock["totalT"]
        display_freeFloat  = round(stock["freeFloat"] * 100, 1)

        if stock.get("live_float"):
            # No valid pre-IPO baseline price exists (e.g. SpaceX/SPCX) — compute
            # directly from live price × floatShares instead of scaling a baseline.
            live = fetch_live_float_cap(ticker)
            if live:
                updated_ff        = round(live["float_cap_t"], 3)
                display_totalT    = round(live["total_cap_t"], 3)
                display_freeFloat = round(live["free_float_pct"], 1)
                note = "live"
            else:
                updated_ff = baseline_ff
                note = "fallback"
        elif stock.get("static") or not ticker:
            # Private / no ticker: keep free float cap fixed
            updated_ff = baseline_ff
            note = "private"
        else:
            live_cap = get_company_market_cap(ticker)
            if live_cap:
                display_totalT = round(live_cap / 1e12, 3)
                updated_ff = round(display_totalT * stock["freeFloat"], 3)
                note = "live"
            else:
                updated_ff = baseline_ff
                note = "fallback"

        stocks_out.append({
            "name":      stock["name"],
            "ticker":    ticker or "—",
            "trillions": updated_ff,
            "totalT":    display_totalT,
            "freeFloat": display_freeFloat,
            "note":      note,
        })
        total_ff += updated_ff

    total_ff = round(total_ff, 1)
    # US market = ~63% of world total
    us_market_t  = world_total_t * 0.63 if world_total_t else None
    us_pct   = round(total_ff / us_market_t  * 100) if us_market_t  else None
    world_pct = round(total_ff / world_total_t * 100) if world_total_t else None

    return {
        "totalT":    total_ff,
        "worldPct":  world_pct,
        "usPct":     us_pct,
        "stocks":    stocks_out,
    }

def get_company_market_cap(ticker):
    """
    Single source of truth for a Mag7 company's live total market cap.
    Called by BOTH calc_mag7_cap_weighted() (YTD tab) and calc_mag7()
    (Long Term Summary tab) so the two tabs price each company identically.

    Before this was unified, calc_mag7() priced companies from a static
    Q1-2026 baseline scaled forward by price only, while
    calc_mag7_cap_weighted() used live data — the two silently drifted apart
    (e.g. Nvidia showed ~23% weight on one tab, ~16% on the other, purely
    from the stale baseline).

    Reads yfinance's own `marketCap` field directly rather than computing
    price × sharesOutstanding ourselves: `marketCap` is Yahoo's own
    company-level figure and is already correct across multi-class share
    structures (verified live: GOOGL and GOOG both report ~$4.17T for
    Alphabet), whereas the raw `sharesOutstanding` field is exactly what
    silently undercounted SpaceX/SPCX (see fetch_live_float_cap()). Using
    `marketCap` directly sidesteps that whole class of bug instead of
    re-deriving it per caller. The 7 Mag7 tickers have stable, well-covered
    yfinance data, so no further cross-check is needed here.
    """
    try:
        info = yf.Ticker(ticker).info
        cap = info.get("marketCap")
        return float(cap) if cap else None
    except Exception:
        return None

def _parse_ishares_csv(raw_text):
    """
    Parse an iShares 'Data Download' holdings CSV. Layout: several
    disclaimer/metadata lines, then a header row starting with 'Ticker,',
    then one row per holding, then a disclaimer footer. The 'Location'
    column is the per-holding country, which is what makes this format
    suitable for MSCI-style country aggregation (stockanalysis.com's
    holdings table, used as fallback below, has no such column).
    """
    lines = raw_text.splitlines()
    header_idx = next((i for i, l in enumerate(lines) if l.startswith("Ticker,")), None)
    if header_idx is None:
        return None
    reader = csv.DictReader(lines[header_idx:])
    holdings = []
    for row in reader:
        ticker = (row.get("Ticker") or "").strip()
        weight_raw = (row.get("Weight (%)") or "").strip()
        if not ticker or not weight_raw:
            continue
        try:
            weight = float(weight_raw)
        except ValueError:
            continue
        holdings.append({
            "symbol":     ticker,
            "name":       (row.get("Name") or "").strip(),
            "weight_pct": weight,
            "country":    (row.get("Location") or "").strip() or None,
        })
    return holdings or None

def _parse_ssga_xlsx(raw_bytes):
    """
    Parse an SSGA 'holdings-daily-us-en-<ticker>' xlsx file. Layout: 3
    metadata rows, a blank row, a header row (Name/Ticker/.../Weight/...),
    then one row per holding, then blank padding rows. No per-holding
    country/location field is included (SPY doesn't need one — S&P 500
    top 10 is ranked by weight only).
    """
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header_idx = next(
        (i for i, r in enumerate(rows) if r and r[0] == "Name" and "Ticker" in r), None
    )
    if header_idx is None:
        return None
    header = [str(h).strip() if h else "" for h in rows[header_idx]]
    col = {name: idx for idx, name in enumerate(header) if name}
    holdings = []
    for r in rows[header_idx + 1:]:
        if not r or col.get("Ticker") is None or not r[col["Ticker"]]:
            continue
        weight = r[col["Weight"]] if col.get("Weight") is not None else None
        if weight is None:
            continue
        holdings.append({
            "symbol":     str(r[col["Ticker"]]).strip(),
            "name":       str(r[col.get("Name", 0)] or "").strip(),
            "weight_pct": float(weight),
            "country":    None,
        })
    return holdings or None

def _fetch_stockanalysis_holdings(ticker):
    """
    Fallback holdings source: stockanalysis.com's server-rendered holdings
    table (same site already used for the SPCX free-float cross-check).
    Only symbol/name/weight are available here — no per-holding country.
    """
    import pandas as pd
    url = f"https://stockanalysis.com/etf/{ticker.lower()}/holdings/"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    if not tables:
        return None
    df = tables[0]
    holdings = []
    for _, row in df.iterrows():
        symbol = str(row.get("Symbol", "")).strip()
        weight_col = "% Weight" if "% Weight" in df.columns else "Weight"
        try:
            weight = float(str(row.get(weight_col, "")).rstrip("%"))
        except ValueError:
            continue
        if not symbol or symbol.lower() == "nan":
            continue
        holdings.append({
            "symbol":     symbol,
            "name":       str(row.get("Name", "")).strip(),
            "weight_pct": weight,
            "country":    None,
        })
    return holdings or None

def fetch_etf_holdings(ticker):
    """
    Single source of truth for an ETF's current holdings (symbol, name,
    weight %, and — when available — per-holding country/location).
    Called by BOTH calc_acwi_country_weights() and calc_spy_top10() so a
    format change or outage in one data source can't silently diverge the
    two features — same principle as get_company_market_cap() for Mag7.

    Primary: the fund provider's own official daily "Data Download" file
    (iShares CSV for ACWI, State Street/SSGA xlsx for SPY). Fallback:
    stockanalysis.com's holdings table if the primary source is
    unreachable or its format changes — logged as a clear warning rather
    than failing silently, since the fallback lacks per-holding country
    data (see calc_acwi_country_weights for how that gap is handled).
    """
    cfg = ETF_HOLDINGS_SOURCES.get(ticker)
    if not cfg:
        raise ValueError(f"No holdings source configured for {ticker}")

    browser_ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    try:
        if cfg["primary"] == "ishares":
            resp = requests.get(cfg["ishares_url"], params=cfg["ishares_params"],
                                 headers={"User-Agent": browser_ua}, timeout=20)
            resp.raise_for_status()
            stripped = resp.text.lstrip()
            if stripped.startswith("<!DOCTYPE") or stripped.startswith("<html"):
                raise ValueError("ishares.com returned an HTML page instead of the holdings "
                                  "CSV (likely bot-protection or a changed download URL)")
            holdings = _parse_ishares_csv(resp.text)
            if not holdings:
                raise ValueError("ishares.com CSV did not parse into any holdings rows "
                                  "(format may have changed)")
            print(f"  ✓ {ticker} holdings from ishares.com ({len(holdings)} rows)")
            return {"holdings": holdings, "source": "ishares"}

        elif cfg["primary"] == "ssga":
            resp = requests.get(cfg["ssga_url"], headers={"User-Agent": browser_ua}, timeout=20)
            resp.raise_for_status()
            if not resp.content.startswith(b"PK"):
                raise ValueError("ssga.com did not return a valid xlsx file "
                                  "(format may have changed)")
            holdings = _parse_ssga_xlsx(resp.content)
            if not holdings:
                raise ValueError("ssga.com xlsx did not parse into any holdings rows "
                                  "(format may have changed)")
            print(f"  ✓ {ticker} holdings from ssga.com ({len(holdings)} rows)")
            return {"holdings": holdings, "source": "ssga"}
    except Exception as e:
        print(f"  ⚠ {ticker} holdings: official source failed ({e}) — falling back to stockanalysis.com")

    try:
        holdings = _fetch_stockanalysis_holdings(ticker)
        if not holdings:
            raise ValueError("no rows parsed")
        print(f"  ✓ {ticker} holdings from stockanalysis.com fallback ({len(holdings)} rows, no country data)")
        return {"holdings": holdings, "source": "stockanalysis"}
    except Exception as e:
        print(f"  ✗ {ticker} holdings: fallback also failed ({e})")
        return {"holdings": [], "source": None}

_country_lookup_cache = {}

# stockanalysis.com prefixes foreign holdings as "EXCHANGE: LOCALSYMBOL"
# (e.g. "TPE: 2330", "KRX: 005930") instead of a plain Yahoo Finance ticker.
# Without translating these, yfinance can't resolve the symbol at all, so
# every non-US large-cap in the fallback's top holdings (Taiwan Semi,
# Samsung, ASML, ...) would silently fail lookup and get dumped into
# "Other / unclassified" despite the country being obvious from the prefix.
_STOCKANALYSIS_EXCHANGE_TO_YF_SUFFIX = {
    "TPE": ".TW", "KRX": ".KS", "HKG": ".HK", "TYO": ".T", "LON": ".L",
    "PAR": ".PA", "AMS": ".AS", "ETR": ".DE", "FRA": ".F", "SWX": ".SW",
    "ASX": ".AX", "TSE": ".TO", "BSE": ".BO", "NSE": ".NS", "SHA": ".SS",
    "SHE": ".SZ", "SGX": ".SI", "BME": ".MC", "MIL": ".MI", "STO": ".ST",
    "CPH": ".CO", "OSL": ".OL", "HEL": ".HE", "BRU": ".BR", "LIS": ".LS",
    "JSE": ".JO", "MEX": ".MX", "SAO": ".SA", "IDX": ".JK", "SET": ".BK",
    "KLS": ".KL",
}

def _normalize_yf_symbol(symbol):
    """Translate a "EXCHANGE: LOCALSYMBOL" fallback symbol into a plain
    Yahoo Finance ticker (e.g. "TPE: 2330" -> "2330.TW"). Returns the
    symbol unchanged if it doesn't use that format or the exchange isn't
    in the map."""
    if ":" not in symbol:
        return symbol
    exch, _, local = symbol.partition(":")
    suffix = _STOCKANALYSIS_EXCHANGE_TO_YF_SUFFIX.get(exch.strip())
    return f"{local.strip()}{suffix}" if suffix else symbol

def _lookup_country(symbol):
    """Best-effort per-ticker country lookup via yfinance, used only in
    calc_acwi_country_weights()'s degraded fallback path (see there)."""
    if symbol in _country_lookup_cache:
        return _country_lookup_cache[symbol]
    try:
        country = yf.Ticker(_normalize_yf_symbol(symbol)).info.get("country")
    except Exception:
        country = None
    _country_lookup_cache[symbol] = country
    return country

def calc_acwi_country_weights():
    """
    MSCI ACWI country weights, recomputed every run from the iShares ACWI
    ETF's live daily holdings file (fetch_etf_holdings) instead of a
    static table. The file lists individual securities, not countries
    directly, so weights are aggregated here by each holding's Location
    field. See ACWI_METHODOLOGY_NOTE for why this is the real MSCI
    free-float methodology, not an approximation, in the primary
    (ishares.com) path.

    Degraded fallback: if ishares.com is unreachable and fetch_etf_holdings
    falls back to stockanalysis.com, that source has no per-holding
    country field, so country is instead inferred per-ticker via
    yfinance's `country` field for the top ACWI_FALLBACK_COUNTRY_TOP_N
    holdings by weight (covers the large-cap bulk of the index); the
    remaining tail — plus any ticker whose country can't be resolved — is
    bucketed into "Other / unclassified". This is clearly flagged via the
    returned "source" field so callers/UI can label it as an approximation.
    """
    data = fetch_etf_holdings("ACWI")
    holdings = data["holdings"]
    if not holdings:
        return {"asOf": None, "source": None, "countries": [], "note": ACWI_METHODOLOGY_NOTE}

    totals = {}
    if data["source"] == "ishares":
        for h in holdings:
            country = h.get("country") or "Other"
            totals[country] = totals.get(country, 0.0) + h["weight_pct"]
    else:
        ranked = sorted(holdings, key=lambda h: h["weight_pct"], reverse=True)
        top = ranked[:ACWI_FALLBACK_COUNTRY_TOP_N]
        classified_weight = 0.0
        for h in top:
            country = _lookup_country(h["symbol"])
            key = country or "Other / unclassified"
            totals[key] = totals.get(key, 0.0) + h["weight_pct"]
            if country:
                classified_weight += h["weight_pct"]
        tail_weight = sum(h["weight_pct"] for h in ranked[ACWI_FALLBACK_COUNTRY_TOP_N:])
        if tail_weight:
            totals["Other / unclassified"] = totals.get("Other / unclassified", 0.0) + tail_weight
        print(f"  ⚠ ACWI country weights: fallback mode classified {classified_weight:.1f}pt "
              f"across {len(top)} top holdings by weight; rest bucketed as unclassified")

    total_pct = sum(totals.values()) or 1.0
    countries = sorted(
        ({"name": name, "pct": round(w / total_pct * 100, 2)} for name, w in totals.items()),
        key=lambda c: c["pct"], reverse=True,
    )
    return {
        "asOf":      datetime.now().strftime("%Y-%m-%d"),
        "source":    data["source"],
        "countries": countries,
        "note":      ACWI_METHODOLOGY_NOTE,
    }

def _append_spy_top10_history(date_str, top10):
    """
    Reads spy_top10_history.csv (long format: date,rank,symbol,name,
    weight_pct — one row per rank per date, checked into the repo so the
    series persists across runs), removes any existing rows for today (so
    re-running fetch_data.py the same day updates rather than duplicates
    today's snapshot), appends today's top10, writes back, and returns the
    full history for embedding in live_data.js.
    """
    rows = []
    if os.path.exists(SPY_TOP10_HISTORY_CSV):
        with open(SPY_TOP10_HISTORY_CSV, newline="", encoding="utf-8") as f:
            rows = [row for row in csv.DictReader(f) if row["date"] != date_str]

    for entry in top10:
        rows.append({
            "date":       date_str,
            "rank":       str(entry["rank"]),
            "symbol":     entry["symbol"],
            "name":       entry["name"],
            "weight_pct": str(entry["weight_pct"]),
        })
    rows.sort(key=lambda r: (r["date"], int(r["rank"])))

    with open(SPY_TOP10_HISTORY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "rank", "symbol", "name", "weight_pct"])
        writer.writeheader()
        writer.writerows(rows)

    return [
        {"date": r["date"], "rank": int(r["rank"]), "symbol": r["symbol"],
         "name": r["name"], "weight_pct": float(r["weight_pct"])}
        for r in rows
    ]

def calc_spy_top10():
    """
    S&P 500 top 10 holdings by weight, from SPY's live daily holdings file
    (fetch_etf_holdings) instead of a static list. Appends today's
    snapshot to spy_top10_history.csv so the Long Term Summary tab can
    chart how the top 10 composition/weights evolve over time, not just
    show a single instant (same time-series-CSV pattern as the rest of
    this dashboard).
    """
    data = fetch_etf_holdings("SPY")
    holdings = data["holdings"]
    if not holdings:
        return {"asOf": None, "source": None, "top10": [], "history": []}

    ranked = sorted(holdings, key=lambda h: h["weight_pct"], reverse=True)[:SPY_TOP10_N]
    top10 = [
        {"rank": i + 1, "symbol": h["symbol"], "name": h["name"], "weight_pct": round(h["weight_pct"], 2)}
        for i, h in enumerate(ranked)
    ]

    today = datetime.now().strftime("%Y-%m-%d")
    history = _append_spy_top10_history(today, top10)

    return {"asOf": today, "source": data["source"], "top10": top10, "history": history}

def calc_mag7_cap_weighted(member_series, fx_data):
    """
    Cap-weighted Mag7 YTD/52W performance, replacing the MAGS ETF's
    equal-weighting for the primary dashboard metric.

    - Weights = live market cap per member / sum(live market caps), fetched
      fresh every run (not a fixed baseline).
    - Each member's CHF return series is built the same way as
      calc_chf_returns() (return vs. last close before YTD_START, converted
      via the same FX series used elsewhere on the dashboard).
    - The weighted index return at each week = sum(weight_i * return_i).
      Weights are held constant across the lookback window — yfinance
      doesn't expose historical share counts, so this is the standard
      "current-weight" approximation, not a true historically-reconstituted
      cap-weighted index.
    - Does NOT include SpaceX: SpaceX is not a historical Magnificent 7
      constituent (the traditional 7 are Apple, Microsoft, Alphabet, Amazon,
      Nvidia, Meta, Tesla). It stays only in the separate MAG7_BASELINE /
      calc_mag7() world-market-cap section, which is unrelated to this
      YTD-tab metric.

    member_series: dict {ticker: [(ts, price), ...]} in USD, weekly — the
                    same series already fetched for SUB_MARKETS["Magnificent 7"].
    fx_data:       dict {ccy: [(ts, fx), ...] or None} — same as used by
                    calc_chf_returns() elsewhere in this file.
    Returns None if too few members have both price data and a live market cap.
    """
    members = SUB_MARKETS["Magnificent 7"]  # [(name, ticker, ccy), ...]
    cutoff = int(YTD_START.timestamp())

    caps = {}
    for _, ticker, _ in members:
        cap = get_company_market_cap(ticker)
        if cap:
            caps[ticker] = cap
    missing_caps = [t for _, t, _ in members if t not in caps]
    if missing_caps:
        print(f"  ⚠ Mag7 cap-weighted: no live market cap for {missing_caps}, excluding from weights")

    member_returns = []  # (weight, [(ts, ret_pct), ...])
    for _, ticker, ccy in members:
        series = member_series.get(ticker)
        cap = caps.get(ticker)
        if not series or not cap:
            continue
        fx_series = fx_data.get(ccy) if ccy != "CHF" else None
        before = [(t, c) for t, c in series if t < cutoff]
        start_ts, start_px = before[-1] if before else series[0]
        start_fx = closest_fx(fx_series, start_ts) if fx_series else 1.0
        start_chf = start_px * start_fx
        if not start_chf:
            continue
        rets = []
        for ts, px in series:
            fx = closest_fx(fx_series, ts) if fx_series else 1.0
            rets.append((ts, (px * fx / start_chf - 1) * 100))
        member_returns.append((ticker, cap, rets))

    if not member_returns:
        return None

    total_cap = sum(cap for _, cap, _ in member_returns)
    weighted = [(ticker, cap / total_cap, rets) for ticker, cap, rets in member_returns]

    # Combine into one weighted series. All members were batch-downloaded
    # together (single yf.download call per SUB_MARKETS group), so their
    # weekly timestamps line up positionally; align on the shortest series
    # as a safety margin.
    length = min(len(rets) for _, _, rets in weighted)
    combined = []
    for i in range(length):
        ts = weighted[0][2][i][0]
        val = sum(w * rets[i][1] for _, w, rets in weighted)
        combined.append((ts, val))

    ytd     = combined[-1][1]
    w52Low  = min(v for _, v in combined)
    w52High = max(v for _, v in combined)

    curr_ts = combined[-1][0]
    thirty_days_ago = curr_ts - 30 * 24 * 3600
    before_30d = [(t, v) for t, v in combined if t <= thirty_days_ago]
    if before_30d:
        v_30d = before_30d[-1][1]
        l30d = round(((1 + ytd / 100) / (1 + v_30d / 100) - 1) * 100, 2)
    else:
        l30d = None

    return {
        "ytd":     round(ytd, 2),
        "w52Low":  round(w52Low, 2),
        "w52High": round(w52High, 2),
        "l30d":    l30d,
        "weights": {ticker: round(w * 100, 1) for ticker, w, _ in weighted},
    }

def fetch_monthly_max(ticker):
    """Download full available monthly history for long-term return calculations."""
    try:
        df = yf.download(ticker, period="max", interval="1mo",
                         progress=False, auto_adjust=True)
        if df.empty:
            return None
        if hasattr(df.columns, "levels"):
            df.columns = df.columns.get_level_values(0)
        closes = df["Close"].dropna()
        series = [(int(ts.timestamp()), float(c)) for ts, c in closes.items()]
        return series if len(series) >= 12 else None
    except Exception:
        return None

def build_chf_monthly(etf_series, fx_monthly):
    """Zip ETF monthly closes with FX, return list of (ts, chf_price)."""
    if fx_monthly is None:
        return etf_series   # already CHF
    result = []
    for ts, price in etf_series:
        fx = min(fx_monthly, key=lambda x: abs(x[0] - ts))[1]
        result.append((ts, price * fx))
    return result

def annualized_return(chf_series, years):
    """
    Annualized CHF return over the last `years` years.
    Uses the last FULLY COMPLETED month-end to avoid partial-month distortion
    (e.g. if today is June 2, the June bar is excluded and May is used as end point).
    Returns None if insufficient history.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    # Last completed month-end: first day of current month minus 1 second
    last_complete_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp() - 1

    # Find the latest data point that is <= last completed month-end
    completed = [(t, v) for t, v in chf_series if t <= last_complete_month]
    if not completed:
        completed = chf_series  # fallback: use all data
    end_ts, end_price = completed[-1]

    target_ts = end_ts - int(years * 365.25 * 24 * 3600)
    idx = min(range(len(completed)), key=lambda i: abs(completed[i][0] - target_ts))
    actual_years = (end_ts - completed[idx][0]) / (365.25 * 24 * 3600)
    if actual_years < years * 0.95:   # require ≥95% coverage to avoid anchoring to outlier dates
        return None
    start_price = completed[idx][1]
    ann = (end_price / start_price) ** (1 / actual_years) - 1
    return round(ann * 100, 2)

def fetch_weekly(ticker):
    """Lädt 1 Jahr Wochendaten. Gibt Liste [(timestamp_int, close_float)] zurück."""
    try:
        df = yf.download(ticker, period="1y", interval="1wk",
                         progress=False, auto_adjust=True)
        if df.empty:
            return None
        if hasattr(df.columns, "levels"):
            df.columns = df.columns.get_level_values(0)
        closes = df["Close"].dropna()
        result = [(int(ts.timestamp()), float(c)) for ts, c in closes.items()]
        return result if len(result) >= 10 else None
    except Exception:
        return None

def fetch_live_float_cap(ticker):
    """
    Holt Preis + Aktienzahlen direkt via Ticker.info, statt über die Kurshistorie
    zu skalieren. Für sehr frische IPOs (z.B. SPCX), deren 1y/Wochen-Serie noch
    zu wenige Datenpunkte hat (fetch_weekly() verlangt >=10) und die ohnehin
    keinen validen Vor-IPO-Referenzpreis für die Q1-2026-Baseline haben.
    Gibt None zurück, wenn eines der benötigten Felder fehlt.

    SPCX-specific cross-check (added 2026-07-22): yfinance's `sharesOutstanding`
    field undercounts SPCX's real share count (~7.57B vs. the actual ~13.17B
    confirmed against stockanalysis.com/CNBC on 2026-07-22) — SpaceX has
    multiple share classes and this field appears to only tally one of them.
    yfinance's own `marketCap` and `impliedSharesOutstanding` fields are
    computed from the full share count and do match external sources, so we
    cross-check price × sharesOutstanding against the reported marketCap and,
    on a large mismatch, use impliedSharesOutstanding instead — logging a
    warning rather than silently using a number we know is likely wrong. This
    check is intentionally SPCX-only (via the `live_float` baseline flag),
    not applied to the other Mag7 tickers, whose yfinance data has been
    stable for years. Reminder: a lock-up expiring around SpaceX's
    2026-08-04 earnings date will move the real float independently of this
    bug — don't mistake that later, legitimate move for a recurrence of it.

    Same undercount bug also affects `floatShares` (added 2026-07-22): SPCX's
    reported floatShares (~281M) is ~half of the 555,555,555 shares actually
    sold in the IPO (SPCX_IPO_FLOAT_SHARES, see its definition for the TODO
    on reviewing this after the 2026-08-04 lock-up expiry) — so for SPCX we
    anchor on the IPO offering size instead when yfinance's figure diverges
    from it by more than 15%.
    """
    try:
        info = yf.Ticker(ticker).info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        float_shares = info.get("floatShares")
        total_shares = info.get("sharesOutstanding")
        if not price or not float_shares or not total_shares:
            return None

        market_cap_reported = info.get("marketCap")
        if market_cap_reported:
            naive_cap = price * total_shares
            discrepancy = abs(naive_cap - market_cap_reported) / market_cap_reported
            if discrepancy > 0.15:
                implied_shares = info.get("impliedSharesOutstanding") or (market_cap_reported / price)
                print(f"  ⚠ {ticker}: yfinance sharesOutstanding ({total_shares:,}) looks incomplete "
                      f"(price x shares = ${naive_cap/1e12:.2f}T vs. reported marketCap "
                      f"${market_cap_reported/1e12:.2f}T) — using impliedSharesOutstanding "
                      f"({implied_shares:,.0f}) instead.")
                total_shares = implied_shares

        if ticker == "SPCX":
            discrepancy = abs(float_shares - SPCX_IPO_FLOAT_SHARES) / SPCX_IPO_FLOAT_SHARES
            if discrepancy > 0.15:
                print(f"  ⚠ {ticker}: yfinance floatShares ({float_shares:,}) looks incomplete "
                      f"(~{float_shares / SPCX_IPO_FLOAT_SHARES * 100:.0f}% of the "
                      f"{SPCX_IPO_FLOAT_SHARES:,} shares actually sold in the IPO) — using the "
                      f"IPO offering size instead.")
                float_shares = SPCX_IPO_FLOAT_SHARES

        return {
            "float_cap_t":    price * float_shares / 1e12,
            "total_cap_t":    price * total_shares / 1e12,
            "free_float_pct": float_shares / total_shares * 100,
        }
    except Exception:
        return None

def closest_fx(fx_series, ts):
    """Gibt den FX-Kurs zurück, dessen Timestamp am nächsten zu ts liegt."""
    return min(fx_series, key=lambda x: abs(x[0] - ts))[1]

def calc_chf_returns(etf_series, fx_series):
    """
    Berechnet YTD, 52W-Tief und 52W-Hoch in CHF.
    Referenzpunkt: letzter Wochenschluss VOR dem 1. Januar YTD_YEAR.
    fx_series = None bedeutet ETF ist bereits in CHF notiert.
    """
    cutoff = int(YTD_START.timestamp())

    # Letzter Datenpunkt vor Jahresanfang
    before = [(t, c) for t, c in etf_series if t < cutoff]
    if not before:
        before = [etf_series[0]]
    start_ts, start_etf = before[-1]

    start_fx  = closest_fx(fx_series, start_ts) if fx_series else 1.0
    start_chf = start_etf * start_fx

    # Alle wöchentlichen CHF-Renditen (vs. Jahresanfang)
    chf_returns = []
    for ts, etf_price in etf_series:
        fx = closest_fx(fx_series, ts) if fx_series else 1.0
        ret = (etf_price * fx / start_chf - 1) * 100
        chf_returns.append(round(ret, 2))

    curr_ts, curr_etf = etf_series[-1]
    curr_fx = closest_fx(fx_series, curr_ts) if fx_series else 1.0
    curr_chf = curr_etf * curr_fx
    ytd = round((curr_chf / start_chf - 1) * 100, 2)

    # 30-day return: find closest weekly close ~30 days before current
    thirty_days_ago = curr_ts - 30 * 24 * 3600
    before_30d = [(t, c) for t, c in etf_series if t <= thirty_days_ago]
    if before_30d:
        ts_30d, etf_30d = before_30d[-1]
        fx_30d = closest_fx(fx_series, ts_30d) if fx_series else 1.0
        l30d = round((curr_chf / (etf_30d * fx_30d) - 1) * 100, 2)
    else:
        l30d = None

    return {
        "ytd":     ytd,
        "w52Low":  round(min(chf_returns), 2),
        "w52High": round(max(chf_returns), 2),
        "l30d":    l30d,
        "etfProxy": True,
    }

# ── Batch-Download ───────────────────────────────────────────────────────────

def batch_fetch(tickers_ccys):
    """
    Holt alle Ticker in einem yfinance-Download (effizienter als einzeln).
    Gibt dict {ticker: [(ts, close), ...]} zurück.
    """
    unique = list({t for t, _ in tickers_ccys if t})
    if not unique:
        return {}

    print(f"  Lade {len(unique)} Ticker …", end=" ", flush=True)
    try:
        df = yf.download(unique, period="1y", interval="1wk",
                         progress=False, auto_adjust=True, group_by="ticker")
    except Exception as e:
        print(f"Fehler: {e}")
        return {}

    result = {}
    for ticker in unique:
        try:
            if len(unique) == 1:
                sub = df
            else:
                sub = df[ticker] if ticker in df.columns.get_level_values(0) else None
            if sub is None or sub.empty:
                continue
            closes = sub["Close"].dropna()
            series = [(int(ts.timestamp()), float(c)) for ts, c in closes.items()]
            if len(series) >= 10:
                result[ticker] = series
        except Exception:
            pass

    ok  = len(result)
    nok = len(unique) - ok
    print(f"OK {ok}/{len(unique)}" + (f"  ⚠ {nok} fehlgeschlagen" if nok else ""))
    return result

# ── Hauptprogramm ────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print(f"  Market Dashboard – Datenabruf  {datetime.now():%d.%m.%Y %H:%M}")
    print(f"{'='*60}\n")

    # 1) FX-Kurse
    print("[1] Wechselkurse (→ CHF)")
    fx_data = {}
    for ccy, fx_ticker in FX_TICKERS.items():
        print(f"  ↓ {fx_ticker} ({ccy}→CHF) …", end=" ", flush=True)
        series = fetch_weekly(fx_ticker)
        if series:
            fx_data[ccy] = series
            print("OK")
        else:
            print("fehlgeschlagen!")
    fx_data["CHF"] = None   # CHF→CHF = 1, kein Fetch nötig

    missing_ccy = [c for c in ["USD","EUR","GBP"] if c not in fx_data]
    if missing_ccy:
        print(f"\n  ⚠ FX fehlt für: {missing_ccy}  →  betroffene Märkte werden übersprungen.\n")

    # 2) Hauptmärkte
    print("\n[2] Hauptmärkte (Batch-Download)")
    main_tickers = [(t, c) for _, t, c in MAIN_MARKETS if t]
    raw_main = batch_fetch(main_tickers)

    main_results = {}
    for name, ticker, ccy in MAIN_MARKETS:
        if not ticker:
            main_results[name] = {"error": "Kein ETF verfügbar"}
            continue
        if ccy not in fx_data and ccy is not None:
            main_results[name] = {"error": f"FX {ccy}→CHF nicht verfügbar"}
            continue
        series = raw_main.get(ticker)
        if not series:
            main_results[name] = {"error": f"Keine Daten ({ticker})"}
            continue
        try:
            main_results[name] = calc_chf_returns(series, fx_data.get(ccy))
            main_results[name]["ticker"] = ticker
        except Exception as e:
            main_results[name] = {"error": str(e)}

    ok_count = sum(1 for v in main_results.values() if "ytd" in v)
    print(f"  → {ok_count}/{len(MAIN_MARKETS)} Märkte berechnet")

    # 3) Sub-market breakdowns
    sub_results = {}   # { "Emerging Market Equities": {"Taiwan": {...}, ...}, ... }
    sub_raw = {}        # { parent: {ticker: [(ts, price), ...]} } — kept for reuse below (Mag7 cap-weighting)
    for i, (parent, items) in enumerate(SUB_MARKETS.items(), start=3):
        print(f"\n[{i}] {parent} – sub-markets (Batch-Download)")
        tickers_ccys = [(t, c) for _, t, c in items if t]
        raw = batch_fetch(tickers_ccys)
        sub_raw[parent] = raw
        group = {}
        for name, ticker, ccy in items:
            series = raw.get(ticker)
            if not series:
                group[name] = {"error": f"No data ({ticker})"}
                continue
            try:
                group[name] = calc_chf_returns(series, fx_data.get(ccy))
                group[name]["ticker"] = ticker
            except Exception as e:
                group[name] = {"error": str(e)}
        ok = sum(1 for v in group.values() if "ytd" in v)
        print(f"  → {ok}/{len(items)} computed")
        sub_results[parent] = group

    # 3b) Magnificent 7 – switch the main YTD-tab metric from MAGS' equal
    # weighting to cap-weighted (live weights), keeping equal-weight as a
    # secondary breadth indicator. Reuses the per-member series just fetched
    # above for the "Magnificent 7" sub-market breakdown.
    print(f"\n[3b] Magnificent 7 – cap-weighted YTD (live market-cap weights)")
    mag7_capw = calc_mag7_cap_weighted(sub_raw.get("Magnificent 7", {}), fx_data)
    if mag7_capw and "ytd" in main_results.get("Magnificent 7", {}):
        equal_weight = {k: main_results["Magnificent 7"][k] for k in ("ytd", "w52Low", "w52High", "l30d", "ticker")}
        equal_weight["etfProxy"] = True
        main_results["Magnificent 7"].update({
            "ytd":         mag7_capw["ytd"],
            "w52Low":      mag7_capw["w52Low"],
            "w52High":     mag7_capw["w52High"],
            "l30d":        mag7_capw["l30d"],
            "weights":     mag7_capw["weights"],
            "weightMethod":"cap-weighted",
            "ticker":      "MAG7-CAPW",
            "etfProxy":    False,
            "equalWeight": equal_weight,
        })
        print(f"  → cap-weighted YTD {mag7_capw['ytd']:+.2f}%  (equal-weight/MAGS was {equal_weight['ytd']:+.2f}%)")
        print("  weights: " + "  ".join(f"{t}:{w:.1f}%" for t, w in mag7_capw["weights"].items()))
    else:
        print("  ⚠ Cap-weighted Mag7 calc failed — keeping MAGS equal-weight as the primary metric")

    # 4) Long-term Market Summary (monthly, max history)
    next_step = 3 + len(SUB_MARKETS) + 1
    print(f"\n[{next_step}] Long-Term Summary – monthly max history")
    # Fetch monthly FX (max period)
    fx_monthly = {}
    for ccy, fx_ticker in FX_TICKERS.items():
        series = fetch_monthly_max(fx_ticker)
        fx_monthly[ccy] = series
    fx_monthly["CHF"] = None

    # ── SPI CH Market: CHSPI.SW ETF (clean, direct) for 1Y-10Y,
    #                   splice with SIX TR index for 15Y/20Y  ──────────────
    print("  Building SPI CH Market series …", end=" ", flush=True)
    spi_chf_series = _build_spi_chf_series()
    if spi_chf_series:
        print(f"OK ({len(spi_chf_series)} months, spliced)")
    else:
        print("⚠ failed")

    lt_tickers = list({t for _, t, c, _, _ in LONGTERM_MARKETS
                       if t and t != "__SPI_SIX__"})
    print(f"  Downloading {len(lt_tickers)} tickers (monthly, max) …", end=" ", flush=True)
    lt_raw = {}
    for ticker in lt_tickers:
        s = fetch_monthly_max(ticker)
        if s:
            lt_raw[ticker] = s
    print(f"OK {len(lt_raw)}/{len(lt_tickers)}")

    lt_results = []
    for name, ticker, ccy, group, index_desc in LONGTERM_MARKETS:
        entry = {"name": name, "group": group, "index": index_desc,
                 "ticker": "CHSPI.SW + SPI TR (SIX)" if ticker == "__SPI_SIX__" else (ticker or "—")}

        if ticker == "__SPI_SIX__":
            chf_monthly = spi_chf_series
            if not chf_monthly:
                entry["returns"] = {str(y): None for y in LONGTERM_PERIODS}
                lt_results.append(entry)
                continue
        elif not ticker or ticker not in lt_raw:
            entry["returns"] = {str(y): None for y in LONGTERM_PERIODS}
            lt_results.append(entry)
            print(f"  {name:35s}  ⚠ no data")
            continue
        else:
            etf_series  = lt_raw[ticker]
            chf_monthly = build_chf_monthly(etf_series, fx_monthly.get(ccy))

        entry["returns"] = {
            str(y): annualized_return(chf_monthly, y)
            for y in LONGTERM_PERIODS
        }
        lt_results.append(entry)
        avail = sum(1 for v in entry["returns"].values() if v is not None)
        print(f"  {name:35s}  {avail}/{len(LONGTERM_PERIODS)} periods  "
              + "  ".join(f"{y}Y:{entry['returns'][str(y)]:+.1f}%"
                          if entry["returns"][str(y)] is not None else f"{y}Y:—"
                          for y in LONGTERM_PERIODS))

    # 5) World Market Cap (reuses already-downloaded fx_monthly and ETF data)
    next_step2 = next_step + 1
    print(f"\n[{next_step2}] World Market Capitalisation (dynamic, baseline Q1 2026)")
    world_mktcap = calc_world_mktcap(fx_monthly, cached_series=lt_raw)
    for r in world_mktcap["regions"]:
        print(f"  {r['name']:28s}  {r['pct']:2d}%  ${r['trillions']:.1f}T")
    print(f"  Total: ${world_mktcap['totalT']:.1f}T  (baseline {world_mktcap['baseline']}, scaled to {world_mktcap['updatedTo']})")

    # 5b) MAG7
    next_step3 = next_step2 + 1
    print(f"\n[{next_step3}] MAG7 Market Cap (dynamic, baseline Q1 2026)")
    mag7 = calc_mag7(world_mktcap["totalT"])
    print(f"  MAG7 total: ${mag7['totalT']:.1f}T  ({mag7['worldPct']}% of world / {mag7['usPct']}% of US)")
    for s in mag7["stocks"]:
        print(f"    {s['name']:12s}  ${s['trillions']:.2f}T")

    # 5c) Hyperscaler Capex (SEC EDGAR XBRL, quarterly TTM)
    next_step4 = next_step3 + 1
    print(f"\n[{next_step4}] Hyperscaler Capex (SEC EDGAR XBRL)")
    try:
        hyperscaler_capex = fetch_hyperscaler_capex()
        print(f"  → {len(hyperscaler_capex['companies'])}/5 companies computed")
    except Exception as e:
        print(f"  ⚠ Hyperscaler Capex fetch failed: {e}")
        hyperscaler_capex = {"companies": []}

    # 5d) MSCI ACWI Country Weights (live ETF holdings, see fetch_etf_holdings)
    next_step5 = next_step4 + 1
    print(f"\n[{next_step5}] MSCI ACWI Country Weights (live ETF holdings)")
    try:
        acwi_country_weights = calc_acwi_country_weights()
        print(f"  → {len(acwi_country_weights['countries'])} countries, source={acwi_country_weights['source']}")
    except Exception as e:
        print(f"  ⚠ ACWI country weights failed: {e}")
        acwi_country_weights = {"asOf": None, "source": None, "countries": [], "note": ACWI_METHODOLOGY_NOTE}

    # 5e) S&P 500 Top 10 (live ETF holdings, see fetch_etf_holdings)
    next_step6 = next_step5 + 1
    print(f"\n[{next_step6}] S&P 500 Top 10 (live ETF holdings)")
    try:
        spy_top10 = calc_spy_top10()
        print("  → " + ", ".join(f"{e['symbol']}:{e['weight_pct']:.1f}%" for e in spy_top10["top10"]))
    except Exception as e:
        print(f"  ⚠ SPY top10 failed: {e}")
        spy_top10 = {"asOf": None, "source": None, "top10": [], "history": []}

    # 6) Output
    fetched_at = datetime.now().strftime("%d.%m.%Y %H:%M")
    out = {
        "fetchedAt":       fetched_at,
        "ytdYear":         YTD_YEAR,
        "mainMarkets":     main_results,
        "subMarkets":      sub_results,
        "longTermMarkets": lt_results,
        "worldMktCap":     world_mktcap,
        "mag7":            mag7,
        "hyperscalerCapex": hyperscaler_capex,
        "acwiCountryWeights": acwi_country_weights,
        "spyTop10":        spy_top10,
    }

    out_path = os.path.join(os.path.dirname(__file__), "live_data.js")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"// AUTO-GENERATED by fetch_data.py  –  {fetched_at}\n")
        f.write("// Do not edit manually. Re-fetch: python3 fetch_data.py\n\n")
        f.write(f"const LIVE_DATA = {json.dumps(out, ensure_ascii=False, indent=2)};\n")

    total_sub = sum(len(g) for g in sub_results.values())
    print(f"\n{'='*60}")
    print(f"  ✓ live_data.js saved  ({ok_count + total_sub + len(lt_results)} data points)")
    print(f"  Reload browser.")
    print(f"{'='*60}\n")

    # Auto-push to GitHub Pages
    import subprocess
    script_dir = os.path.dirname(os.path.abspath(__file__))
    label = datetime.now().strftime("%Y-%m-%d %H:%M")
    result = subprocess.run(
        ["git", "add", "live_data.js", "spy_top10_history.csv"],
        cwd=script_dir, capture_output=True
    )
    result = subprocess.run(
        ["git", "commit", "-m", f"data: {label}"],
        cwd=script_dir, capture_output=True, text=True
    )
    if result.returncode == 0:
        result = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=script_dir, capture_output=True, text=True
        )
        if result.returncode == 0:
            print("  ✓ Pushed to GitHub Pages.")
        else:
            print(f"  ⚠ Push failed: {result.stderr.strip()}")
    else:
        print(f"  ⚠ Commit failed: {result.stderr.strip()}")

    # Kurze Übersicht
    print("Hauptmärkte:")
    for name, data in main_results.items():
        if "ytd" in data:
            print(f"  {name[:42]:42s}  YTD {data['ytd']:+6.1f}%"
                  f"  52W [{data['w52Low']:+.1f}% … {data['w52High']:+.1f}%]")
        else:
            print(f"  {name[:42]:42s}  ⚠ {data.get('error','?')}")

if __name__ == "__main__":
    main()
