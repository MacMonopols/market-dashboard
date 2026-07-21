// ============================================================
//  data.js  –  Statische Konfiguration (Namen, Kategorien, ETF-Ticker)
//  YTD und 52W-Bandbreiten kommen aus live_data.js (fetch_data.py)
//
//  ticker      – Yahoo Finance Ticker für den ETF-Proxy
//  tickerCcy   – Währung des ETF: "CHF" | "USD" | "EUR" | "GBP"
//  cat         – "equity" | "bond" | "re" | "commodity" | "cash"
// ============================================================

const MARKETS = [
  // ── Aktien ───────────────────────────────────────────────────────────────
  {
    name: "Emerging Market Equities",
    cat: "equity", ticker: "EEM",      tickerCcy: "USD",
    // Country breakdown (Weights: iShares Core MSCI EM IMI factsheet, June 2026)
    subMarketsWeightDate: "June 2026",
    subMarkets: [
      { name: "Taiwan",       ticker: "EWT",  flag: "🇹🇼", weight: 27.29, note: "iShares MSCI Taiwan ETF"        },
      { name: "Korea",        ticker: "EWY",  flag: "🇰🇷", weight: 22.44, note: "iShares MSCI South Korea ETF"   },
      { name: "China",        ticker: "MCHI", flag: "🇨🇳", weight: 17.65, note: "iShares MSCI China ETF"         },
      { name: "India",        ticker: "INDA", flag: "🇮🇳", weight: 12.22, note: "iShares MSCI India ETF"         },
      { name: "Brazil",       ticker: "EWZ",  flag: "🇧🇷", weight:  3.27, note: "iShares MSCI Brazil ETF"        },
      { name: "South Africa", ticker: "EZA",  flag: "🇿🇦", weight:  2.98, note: "iShares MSCI South Africa ETF"  },
      { name: "Saudi Arabia", ticker: "KSA",  flag: "🇸🇦", weight:  2.26, note: "iShares MSCI Saudi Arabia ETF"  },
      { name: "Mexico",       ticker: "EWW",  flag: "🇲🇽", weight:  1.65, note: "iShares MSCI Mexico ETF"        },
      { name: "Thailand",     ticker: "THD",  flag: "🇹🇭", weight:  1.13, note: "iShares MSCI Thailand ETF"      },
      { name: "Malaysia",     ticker: "EWM",  flag: "🇲🇾", weight:  1.12, note: "iShares MSCI Malaysia ETF"      },
      { name: "UAE",          ticker: "UAE",  flag: "🇦🇪", weight:  1.07, note: "iShares MSCI UAE ETF"           },
    ],
  },
  { name: "Japanese Equities",               cat: "equity",    ticker: "EWJ",      tickerCcy: "USD" },
  { name: "Global Equities – Small Caps",    cat: "equity",    ticker: "IUSN.DE",  tickerCcy: "EUR" },
  {
    name: "US Equities (S&P 500)", cat: "equity", ticker: "SPY", tickerCcy: "USD",
    subMarkets: [
      { name: "Nasdaq 100",   ticker: "QQQ", flag: "💻", weight: null, note: "Invesco QQQ Trust (Nasdaq-100)" },
      { name: "Russell 2000", ticker: "IWM", flag: "📦", weight: null, note: "iShares Russell 2000 ETF"       },
    ],
  },
  { name: "Global Equities",                 cat: "equity",    ticker: "ACWI",     tickerCcy: "USD" },
  { name: "Global Equities Ex-US (MSCI W ex USA)", cat: "equity", ticker: "IWQU.L", tickerCcy: "GBP" },
  { name: "Pacific ex Japan Equities",       cat: "equity",    ticker: "EPP",      tickerCcy: "USD" },
  { name: "Swiss Equities – Small Caps",     cat: "equity",    ticker: "CSSMIM.SW",tickerCcy: "CHF" },
  { name: "UK Equities",                     cat: "equity",    ticker: "EWU",      tickerCcy: "USD" },
  {
    name: "Swiss Equities (SPI)", cat: "equity", ticker: "CHSPI.SW", tickerCcy: "CHF",
    subMarkets: [
      { name: "SMI",       ticker: "CSSMI.SW",  flag: "🇨🇭", weight: null, note: "iShares SMI ETF (CHF)"       },
      { name: "SPI Extra", ticker: "CSSMIM.SW", flag: "🇨🇭", weight: null, note: "CS SPI Extra ETF (CHF)"      },
    ],
  },
  {
    name: "Eurozone Equities (EURO STOXX 50)", cat: "equity", ticker: "FEZ", tickerCcy: "USD",
    subMarketsWeightDate: "May 2026 (approx.)",
    subMarkets: [
      { name: "France",      ticker: "EWQ",  flag: "🇫🇷", weight: 36.2, note: "iShares MSCI France ETF"      },
      { name: "Germany",     ticker: "EWG",  flag: "🇩🇪", weight: 24.1, note: "iShares MSCI Germany ETF"     },
      { name: "Netherlands", ticker: "EWN",  flag: "🇳🇱", weight: 12.3, note: "iShares MSCI Netherlands ETF" },
      { name: "Spain",       ticker: "EWP",  flag: "🇪🇸", weight:  9.8, note: "iShares MSCI Spain ETF"       },
      { name: "Italy",       ticker: "EWI",  flag: "🇮🇹", weight:  8.4, note: "iShares MSCI Italy ETF"       },
      { name: "Finland",     ticker: "EFNL", flag: "🇫🇮", weight:  4.9, note: "iShares MSCI Finland ETF"     },
      { name: "Belgium",     ticker: "EWK",  flag: "🇧🇪", weight:  3.1, note: "iShares MSCI Belgium ETF"     },
    ],
  },
  // ── Real Estate ──────────────────────────────────────────────────────────
  { name: "US Real Estate (Equities)",       cat: "re",        ticker: "VNQ",      tickerCcy: "USD" },
  { name: "Swiss Real Estate (SXI Broad)",   cat: "re",        ticker: "SRFCHA.SW",tickerCcy: "CHF" },
  { name: "European Real Estate (Equities)", cat: "re",        ticker: "IPRP.AS",  tickerCcy: "EUR" },
  { name: "Asian Real Estate (Equities)",    cat: "re",        ticker: "RWX",      tickerCcy: "USD" },
  // ── Commodities / Gold ───────────────────────────────────────────────────
  { name: "Commodities (Diversified, unhedged)", cat: "commodity", ticker: "ICOM.L", tickerCcy: "USD" },
  { name: "Gold Bullion (unhedged)",          cat: "commodity", ticker: "ZGLD.SW",  tickerCcy: "CHF" },
  // ── Bonds ────────────────────────────────────────────────────────────────
  { name: "CHF Bonds",                       cat: "bond",      ticker: "CHCORP.SW",tickerCcy: "CHF" },
  { name: "EM Bonds Local Currency",         cat: "bond",      ticker: "EMLC",     tickerCcy: "USD" },
  { name: "Global Bonds (CHF hedged)",       cat: "bond",      ticker: "AGGH.SW",  tickerCcy: "CHF" },
  { name: "EUR Bonds",                       cat: "bond",      ticker: "IBGE.L",   tickerCcy: "GBP" },
  { name: "USD Bonds",                       cat: "bond",      ticker: "AGG",      tickerCcy: "USD" },
  { name: "CHF Corporate Bonds",             cat: "bond",      ticker: "CHCORP.SW",tickerCcy: "CHF" },
  { name: "USD Corporate Bonds",             cat: "bond",      ticker: "LQD",      tickerCcy: "USD" },
  { name: "EUR Corporate Bonds",             cat: "bond",      ticker: "IEAC.AS",  tickerCcy: "EUR" },
  { name: "Inflation Linked",                cat: "bond",      ticker: "TIP",      tickerCcy: "USD" },
  // ── Money Market ─────────────────────────────────────────────────────────
  { name: "Money Market CHF",                cat: "cash",      ticker: "CSBGC0.SW",tickerCcy: "CHF" },
  { name: "Money Market GBP",                cat: "cash",      ticker: "CSH2.L",   tickerCcy: "GBP" },
  { name: "Money Market USD",                cat: "cash",      ticker: "BIL",      tickerCcy: "USD" },
  { name: "Money Market EUR",                cat: "cash",      ticker: "EXVM.DE",  tickerCcy: "EUR" },
  // ── FX vs CHF ────────────────────────────────────────────────────────────
  { name: "USD / CHF",                       cat: "fx",        ticker: "USDCHF=X", tickerCcy: "CHF" },
  { name: "EUR / CHF",                       cat: "fx",        ticker: "EURCHF=X", tickerCcy: "CHF" },
  { name: "JPY / CHF",                       cat: "fx",        ticker: "JPYCHF=X", tickerCcy: "CHF" },
];

// Datum der manuell erfassten Hinder AM Daten (Kopfzeile)
const DATA_DATE = "29. Mai 2026";
