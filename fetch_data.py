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
from datetime import datetime, timezone, timedelta

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
    ("Global Equities – Small Caps",      "VSS",       "USD"),
    ("US Equities (S&P 500)",             "SPY",       "USD"),
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
        ("South Korea",  "EWY",  "USD"),
        ("India",        "INDA", "USD"),
        ("South Africa", "EZA",  "USD"),
        ("Brazil",       "EWZ",  "USD"),
        ("Saudi Arabia", "KSA",  "USD"),
        ("Mexico",       "EWW",  "USD"),
        ("UAE",          "UAE",  "USD"),
        ("Indonesia",    "EIDO", "USD"),
        ("Thailand",     "THD",  "USD"),
    ],
    "US Equities (S&P 500)": [
        ("Nasdaq 100",   "QQQ",      "USD"),
        ("Russell 2000", "IWM",      "USD"),
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
    for i, (parent, items) in enumerate(SUB_MARKETS.items(), start=3):
        print(f"\n[{i}] {parent} – sub-markets (Batch-Download)")
        tickers_ccys = [(t, c) for _, t, c in items if t]
        raw = batch_fetch(tickers_ccys)
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
    # Pass all already-downloaded monthly series (lt_raw) to avoid re-fetching
    world_mktcap = calc_world_mktcap(fx_monthly, cached_series=lt_raw)
    for r in world_mktcap["regions"]:
        print(f"  {r['name']:28s}  {r['pct']:2d}%  ${r['trillions']:.1f}T")
    print(f"  Total: ${world_mktcap['totalT']:.1f}T  (baseline {world_mktcap['baseline']}, scaled to {world_mktcap['updatedTo']})")

    # 6) Output
    fetched_at = datetime.now().strftime("%d.%m.%Y %H:%M")
    out = {
        "fetchedAt":       fetched_at,
        "ytdYear":         YTD_YEAR,
        "mainMarkets":     main_results,
        "subMarkets":      sub_results,
        "longTermMarkets": lt_results,
        "worldMktCap":     world_mktcap,
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
        ["git", "add", "live_data.js"],
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
