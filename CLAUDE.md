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

## S&P 500 top-10 "weight evolution over time" chart — reconstructed approximation, set up 2026-07-24, revised 2026-07-24

There is no free, authoritative dataset of the S&P 500's actual historical
top-10 combined weight (real constituents and their weights both changed
over time — e.g. NVDA's real weight was ~0% a decade ago). Rather than
either building that from scratch (would take years of our own daily
snapshots to accumulate) or silently faking it, `fetch_data.py`'s
`calc_spy_top10_history_approx()` reconstructs a labeled approximation —
and critically, it lets the top-10 MEMBERSHIP float per date rather than
holding it fixed to today's names (an earlier revision of this feature did
fix it to today's top 10 projected backward; the user explicitly asked for
"pas forcément les top 10 d'aujourd'hui", so it was redesigned):

For each of TODAY's ~500 SPY constituents (all of `fetch_etf_holdings`'s
holdings, not just the top 10), approximate its market cap at a past date
`t` as `weight_i(today) × Close_i(t)/Close_i(today)` — today's known weight
(a proxy for today's market cap) scaled by that company's own price move
since. At each date, rank all ~500 by this approximate cap and sum
whichever `SPY_TOP10_N` (10) come out largest THAT DATE:

```
weight_pct(t) = Σ_{i ∈ top10 at t}[weight_i(today) × Close_i(t)/Close_i(today)]
                 ────────────────────────────────────────────────────────────
                 Σ_{i ∈ all ~500}[weight_i(today) × Close_i(t)/Close_i(today)]
```

The unknown absolute scale (today's total S&P 500 market cap) cancels out
entirely since it's only ever used as a top-10-sum / all-sum ratio — no
divisor or index level is needed at all, unlike the original design. This
is **not** an exact historical reconstruction: (a) the universe is capped
at today's ~500 constituents, so a company since removed from the index
(bankruptcy, M&A, relegation) can't be counted even if it was genuinely
top-10 at some past date (survivorship bias); (b) each company's share
count is assumed roughly constant, ignoring buybacks/issuance, which tends
to understate historical weight for buyback-heavy names like AAPL, META,
GOOGL. Both caveats are surfaced in the dashboard itself via
`spy.historyNote` (== `SPY_TOP10_HISTORY_METHODOLOGY_NOTE` in
`fetch_data.py`), rendered directly under the chart in `longterm.html`'s
`renderSpyTop10History()` — never presented as ground truth.

This superseded two earlier designs: (1) appending one row per top-10
symbol per day to `spy_top10_history.csv` and charting 10 individual
lines — 100% accurate but only had ~2 days of real history and would have
taken years to become chart-worthy; (2) projecting today's fixed top-10
names backward via `Σ_i weight_i(today) × Close_i(t)/Close_i(today) ×
GSPC(today)/GSPC(t)` — simpler (10 tickers instead of ~500) and
self-calibrating exactly at t=today, but silently assumed today's top-10
names were always the top-10, which the user flagged as misleading for a
10-year chart (e.g. it would show NVDA back near its current ~8% weight
a decade ago, when NVDA wasn't even close to top-10 then).
