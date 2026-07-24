# market-dashboard

## SPCX (SpaceX) free float — manual review needed after 2026-08-04

`fetch_data.py`'s `SPCX_IPO_FLOAT_SHARES` constant (555,555,555) anchors
SpaceX's free float calculation on the actual IPO offering size (S-1 filed
2026-05-20, pricing confirmed 2026-06-11 at $135/share), because yfinance's
`floatShares` field for SPCX reports roughly half the real number — the same
kind of share-class undercount bug already found and fixed for
`sharesOutstanding` (see `fetch_live_float_cap()` in `fetch_data.py`).

**TODO — review from 2026-08-05 onward**: SpaceX's IPO lock-up expires
around its 2026-08-04 earnings date. After that, more shares legitimately
join the tradable float and the hardcoded 555,555,555 anchor will go stale
(too low). Check yfinance's `floatShares` against real trading volume /
secondary-sale disclosures at that point, and update or remove
`SPCX_IPO_FLOAT_SHARES` in `fetch_data.py` accordingly.

## ETF holdings-derived weights (MSCI ACWI country weights, S&P 500 top 10) — set up 2026-07-23

`fetch_data.py`'s `fetch_etf_holdings(ticker)` is the shared source of truth
for both features below (same "single utility, no silent divergence"
pattern as `get_company_market_cap()` for the Mag7 tabs). It downloads each
fund's own official daily holdings file, with a fallback if that fails:

- **ACWI** (MSCI ACWI country weights, Long Term Summary tab): primary
  source is iShares' own "Data Download" CSV on the ACWI product page
  (ishares.com), which includes a per-holding `Location` field. Fallback:
  `stockanalysis.com/etf/acwi/holdings/` — this fallback has **no**
  per-holding country field, so in fallback mode country is instead
  inferred per-ticker via yfinance for the top 100 holdings by weight, with
  the remainder bucketed as "Other / unclassified" — a clearly-flagged
  approximation (see `acwiCountryWeights.source` in `live_data.js`: only
  `"ishares"` is the real MSCI methodology, `"stockanalysis"` is the
  degraded fallback).
- **SPY** (S&P 500 top 10, new Long Term Summary module): primary source is
  State Street's own daily holdings xlsx on ssga.com
  (`holdings-daily-us-en-spy.xlsx`). Fallback:
  `stockanalysis.com/etf/spy/holdings/`.

Both replace what used to be hardcoded static tables in `longterm.html`;
weights are now recalculated fresh from live holdings on every run. If
either official source fails or changes format, `fetch_etf_holdings()` logs
a clear `⚠` warning and falls back to stockanalysis.com rather than failing
silently.

**MSCI ACWI country weights measure free-float-adjusted weight per the
official MSCI (index provider) / S&P DJI methodology**, as implemented by
the iShares MSCI ACWI ETF — not an in-house approximation — whenever
sourced from ishares.com (the primary path).

## S&P 500 top-10 "weight evolution over time" chart — reconstructed approximation, set up 2026-07-24

There is no free, authoritative dataset of the S&P 500's actual historical
top-10 combined weight (real constituents and their weights both changed
over time — e.g. NVDA's real weight was ~0% a decade ago). Rather than
either building that from scratch (would take years of our own daily
snapshots to accumulate) or silently faking it, `fetch_data.py`'s
`calc_spy_top10_history_approx()` reconstructs a labeled approximation:
it takes TODAY's top-10 constituents and their known-exact current weights
(from `calc_spy_top10()`) and projects each one backward using that
company's own share price vs. the S&P 500 index (`^GSPC`) over the last
`SPY_TOP10_HISTORY_YEARS` (10) years, monthly, via

```
combined_weight_pct(t) = (GSPC(today)/GSPC(t)) × Σ_i weight_i(today) × Close_i(t)/Close_i(today)
```

This is self-calibrating — the formula is constructed so the unknown S&P
500 divisor and absolute total market cap cancel out algebraically, and it
is exact by construction at t=today. It is **not** the true historical
composition: it silently assumes (a) today's top-10 names were the top-10
the whole way back, and (b) each company's share count and the index
divisor were roughly constant (ignoring buybacks/issuance/reconstitutions,
which understates historical weight for buyback-heavy names like AAPL,
META, GOOGL). Both caveats are surfaced in the dashboard itself via
`spy.historyNote` (== `SPY_TOP10_HISTORY_METHODOLOGY_NOTE` in
`fetch_data.py`), rendered directly under the chart in `longterm.html`'s
`renderSpyTop10History()` — never presented as ground truth. This replaced
an earlier design that appended one row per top-10 symbol per day to
`spy_top10_history.csv` and charted 10 individual lines; that approach was
100% accurate but only had ~2 days of real history and would have taken
years to become chart-worthy, so it was dropped in favor of this
immediately-useful (if approximate) multi-year reconstruction.
