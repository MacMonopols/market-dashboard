# market-dashboard

## Fixed duplicate/mislabeled CHF bond tickers on YTD Dashboard, set up 2026-09-17

User noticed that sorting the YTD Dashboard by "52W Range" showed several
markets with suspiciously identical figures. Root cause, found by scanning
`MAIN_MARKETS` for duplicate tickers: **`"CHF Bonds"` and `"CHF Corporate
Bonds"` both used `CHCORP.SW`** — the same iShares Core CHF Corporate Bond
ETF — so the two rows were guaranteed to show identical YTD/52W figures
every single day, not a coincidence.

While hunting for a distinct, genuinely-different ticker for "CHF Bonds",
also found a second, related mislabel: **`"Money Market CHF"` used
`CSBGC0.SW`**, which per yfinance is actually the **iShares Swiss Domestic
Government Bond 7–15yr ETF** — a long-duration bond fund, not a cash-like
instrument. That explained its oddly wide 52W swing (-2.39% / +1.68%,
comparable to genuine multi-year bond funds) for a row meant to represent
"money market."

Both fixed using the same iShares Swiss Domestic Government Bond family
(`CSBGC{0,3,7}.SW`, by maturity bucket) already partly in use:

- **`"CHF Bonds"`**: `CHCORP.SW` → `CSBGC7.SW` (3–7yr Swiss government
  bonds) — now a genuine government-bond counterpart to "CHF Corporate
  Bonds", mirroring the same govt-vs-corporate split already used for EUR
  (`"EUR Bonds"` = `IBGE.L` govt vs `"EUR Corporate Bonds"` = `IEAC.AS` corp).
- **`"Money Market CHF"`**: `CSBGC0.SW` (7–15yr) → `CSBGC3.SW` (0–3yr) — the
  shortest-duration fund in the same iShares family, the closest available
  proxy to a cash-like instrument (still not true overnight/T-bill money
  market, since no such CHF-listed ETF was found, but far closer than 7–15yr
  duration).

Changed in both `fetch_data.py`'s `MAIN_MARKETS` and the matching `data.js`
entries (ticker label only, for display). Verified via scratch patch +
browser: "CHF Bonds" now shows -1.2% vs "CHF Corporate Bonds" -0.5%
(previously identical), and "Money Market CHF"'s 52W range tightened from
[-2.39%, +1.68%] to [-0.66%, +0.28%], consistent with an actual short-duration
fund. `LONGTERM_MARKETS`'s `"Swiss Bond Index"` (Long Term Summary tab) still
uses `CHCORP.SW` — out of scope for this fix, not touched.

## Hyperscaler Capex now cached (7-day TTL) instead of re-fetched every run, set up 2026-09-17

`fetch_hyperscaler_capex()` in `hyperscaler_capex.py` was taking ~50s of
every `fetch_data.py` run — it makes ~119 sequential SEC EDGAR requests (7
companies x 17 XBRL tag-variants, deliberately throttled to stay under SEC's
10 req/s limit). But the underlying data is quarterly 10-Q/10-K filings, so
it's unchanged on ~89 of every ~90 days — the daily re-fetch was mostly
wasted work.

Now `fetch_hyperscaler_capex()` checks `hyperscaler_capex_cache.json`
(git-ignored — regenerable, not source of truth) first: if it exists and is
`CACHE_MAX_AGE_DAYS` (7) old, the cached result is returned in ~0s instead of
re-hitting SEC EDGAR. Verified via scratch timing: cold run 49.7s, warm run
0.00s with byte-identical output; also verified a >7-day-old cache is
correctly treated as stale and triggers a live re-fetch. Delete
`hyperscaler_capex_cache.json` any time to force an immediate refresh (e.g.
right after a hyperscaler earnings release, if you don't want to wait up to
7 days for the new filing to show up).

## World Small Cap vs World Cap-Weighted — 3rd Long Term Summary factor module, set up 2026-09-17

`longterm.html` now has a third factor-vs-cap-weighted card, "World Small
Cap vs World Cap-Weighted", alongside "World Value vs World Cap-Weighted"
and "World Quality vs World Cap-Weighted" (both below) — together the three
complete Dimensional's "3 dimensions of expected return" framework (small
cap / value / profitability) as live ratio charts, matching the same trio
already present as a drill-down under "Global Equities" on the YTD
Dashboard (see further below).

Also built on the shared `calc_factor_vs_capweighted()` /
`renderFactorVsCapWeighted()` helpers (see the Quality section just below
for why they're shared) — `calc_world_smallcap_vs_capweighted()` is a third
thin wrapper over the same helper.

- **Small cap leg**: `WSML.L` — iShares MSCI World Small Cap UCITS ETF USD
  (Acc) (ISIN IE00BF4RFH31), tracking the **MSCI World Small Cap Index**, the
  actual small-cap segment of the MSCI World IMI universe. Unlike IWVL/IWQU
  below, this is a genuine size-segment index fund, not a large-cap "factor
  tilt" product — the most direct match to Dimensional's small-cap dimension
  of the three. No SIX-listed version of this fund exists (checked via
  yfinance), so `WSML.L` (LSE) is used instead — same precedent as `EXUS.L`
  elsewhere in this dashboard. Still the same fund provider (BlackRock/
  iShares) and USD share class as `SWDA.SW`, so the ratio isn't muddied by
  an FX/domicile mismatch, only a different exchange than IWVL/IWQU's SIX
  listing.
- **Cap-weighted leg**: `SWDA.SW`, same benchmark as the other two cards.

## World Quality (Profitability proxy) vs World Cap-Weighted — 2nd Long Term Summary factor module, set up 2026-09-17

`longterm.html` also has a second factor-vs-cap-weighted card, "World
Quality vs World Cap-Weighted", alongside "World Value vs World
Cap-Weighted" (see below).

`fetch_data.py`'s `calc_factor_vs_capweighted(factor_ticker,
cap_weighted_ticker, note)` is now the shared helper behind both cards
(refactored out of what was `calc_world_value_vs_capweighted()`) — same
"single source of truth, no silent divergence" pattern as
`get_company_market_cap()` / `fetch_etf_holdings()`. `calc_world_value_vs_
capweighted()` and `calc_world_quality_vs_capweighted()` are now both thin
wrappers over it. `longterm.html`'s `renderFactorVsCapWeighted(data,
idPrefix, factorLabel)` is the equivalent shared render function (was
`renderWorldValue()`), called once per factor with its own DOM id prefix.

- **Quality leg**: `IWQU.SW` — iShares Edge MSCI World Quality Factor UCITS
  ETF (ISIN IE00BP3QZ601), tracking **MSCI World Sector Neutral Quality**
  (three equally-weighted criteria: high ROE, low financial leverage, stable
  earnings growth; sector-neutral vs parent MSCI World). Same fund family as
  IWVL (iShares Edge MSCI World Factor), same October 2014 launch, same
  0.25% TER — chosen for that consistency over Dimensional's own "High
  Profitability" ETFs (`DUHP` for US, `DIHP` for international), which match
  the strict Fama-French Profitability (RMW) definition more closely but are
  US-listed only with no single World-wide fund, so don't fit the SIX-listed
  iShares Edge family the rest of this section uses.
- **Cap-weighted leg**: `SWDA.SW`, same benchmark as the Value card, for the
  same fund-family/listing/share-class consistency reasons.

**Methodology caveat that must stay visible wherever this series is shown**
(`WORLD_QUALITY_METHODOLOGY_NOTE` in `fetch_data.py`, rendered under the
chart): MSCI Quality is used here as a **proxy** for the Fama-French/
Dimensional Profitability factor (RMW), not an exact match — Dimensional
defines profitability on operating profitability alone, while MSCI Quality
also folds in leverage and earnings stability. Never present this chart as
"the" academic profitability factor without that distinction, same spirit as
the Value card's Enhanced-Value-vs-Value-Weighted caveat below.

### Ticker bug found and fixed while verifying IWQU: `IWQU.L` was already in use, mislabeled

While confirming `IWQU.SW` for the Quality card above, verified via
`yfinance` that `IWQU.L` — already hardcoded elsewhere in the dashboard as
"Global Equities Ex-US (MSCI W ex USA)" (`data.js` / `fetch_data.py`'s
`MAIN_MARKETS`) and as "Intl Developed ex US" (`fetch_data.py`'s
`LONGTERM_MARKETS`) — is in fact the **same Quality Factor ETF**, not a
World-ex-US fund. Both of those rows had been silently showing Quality
Factor returns under an unrelated label (confirmed live: the Long Term
Summary's "Intl Developed ex US" row was showing 10 years of Quality
Factor's actual annualized returns). `tickerCcy`/`ccy` was also wrong
(`GBP`, when `IWQU.L`'s real currency is USD per yfinance) — a second,
compounding error in the CHF conversion for those rows.

Fixed by replacing `IWQU.L` with `EXUS.L` (USD) — Xtrackers MSCI World ex
USA UCITS ETF, confirmed via yfinance to be the actual "MSCI World ex USA"
fund — in both `MAIN_MARKETS` and `LONGTERM_MARKETS` in `fetch_data.py`, and
in `data.js`'s `MARKETS`. **Trade-off, decided with the user 2026-09-17**:
`EXUS.L` only launched in 2024, so it has ~2.5 years of history on Yahoo
Finance vs. the ~10 years `IWQU.L` (wrongly) had — the Long Term Summary's
"Intl Developed ex US" row will now show a correct 1-year return but "—" for
the 5/10/15/20-year columns until more history accumulates, rather than
continuing to show a decade of mislabeled Quality Factor data. No Irish/
Swiss-domiciled "World ex-US" UCITS fund with longer history was found
during this search (only US-domiciled alternatives like `IEFA`, which the
existing `LONGTERM_MARKETS` convention already excludes for withholding-tax
reasons) — if one surfaces later, swap it in for deeper history.

**Revised 2026-09-17, same day**: `EXUS.L`'s ~2.5yr history turned out to be
too short in practice (5/10/15/20yr columns all blank) — the user explicitly
asked to switch to `EFA` (iShares MSCI EAFE ETF) instead, accepting the
US-domicile withholding-tax drag (~15% on dividends) that `LONGTERM_MARKETS`
otherwise avoids, in exchange for a 25-year history (since 2001) and the row
actually being useful. This makes `Intl Developed ex US`/`EFA` a **deliberate,
named exception** to the "all ETFs are Irish UCITS" convention documented at
the top of `LONGTERM_MARKETS` in `fetch_data.py` — not an oversight. Also
note EFA tracks **MSCI EAFE** (Europe, Australasia, Far East), which excludes
**Canada** — a small but real difference from "MSCI World ex USA" (which
includes Canada). `EXUS.L` remains in place for `MAIN_MARKETS`/`data.js`
("Global Equities Ex-US (MSCI W ex USA)" on the YTD Dashboard), since that
row only ever needs 1yr + 52-week data, where its short history isn't a
problem — this EFA swap is scoped to the Long Term Summary only.

## Global Equities factor drill-down (Value / Small Cap / Quality) — YTD Dashboard, set up 2026-09-17, revised 2026-09-17

`index.html`'s YTD Dashboard originally listed the Value factor ETF
(`IWVL.SW`) as its own standalone `MAIN_MARKETS` row, and Small Cap
(`IUSN.DE`) as a separate standalone row elsewhere in the list. Both were
moved under the "Global Equities" (`ACWI`) row as a drill-down — same
▼-expand pattern already used for "US Equities (S&P 500)" → Nasdaq 100 /
Russell 2000, "Emerging Market Equities" → country breakdown, etc. — and
**Quality** (`IWQU.SW`) was added as a third item in the same drill-down, so
all three of Dimensional's non-cap-weighted "dimensions of expected return"
(small cap / value / profitability) now sit together under their common
cap-weighted parent instead of competing for space as top-level rows.

Implementation: a new `"Global Equities"` entry in `fetch_data.py`'s
`SUB_MARKETS` dict — `[("Value Factor", "IWVL.SW", "USD"), ("Small Cap",
"IUSN.DE", "EUR"), ("Quality Factor", "IWQU.SW", "USD")]` — flows through
the existing generic `SUB_MARKETS` batch-fetch/`calc_chf_returns()` loop, no
new calc logic needed (same mechanism as every other sub-market group). The
matching `data.js` entry sets `subMarkets` (three items, `weight: null` since
these are alternative style/factor slices, not a weight breakdown that sums
to the parent — same as Nasdaq 100 / Russell 2000 under S&P 500) plus
`subMarketsLabel: "Factor / Style"`, `subMarketsIcon: "📊"`, and
`subMarketsSource` text, so the drill-down header doesn't fall back to the
country-breakdown defaults ("Country" / 🌍 / "MSCI EM Index").

This is purely a display reorganization of the YTD Dashboard — each ETF's
own YTD/52W numbers are unchanged, and it's independent of the *relative*
Value-vs-cap-weighted / Quality-vs-cap-weighted ratio charts on the Long
Term Summary tab (`calc_factor_vs_capweighted()`, see above): those compare
IWVL/IWQU against SWDA over time; this drill-down just reports each ETF's
own performance like any other tracked market, one level down from "Global
Equities" instead of as a top-level row.

## World Value vs World Cap-Weighted — new Long Term Summary module, set up 2026-09-17

`longterm.html` has a new card, "World Value vs World Cap-Weighted", following
the same principle as the Mag7 concentration section (`mag7-block`) and the
SPY top-10 history chart: read what a megacap-adjacent factor/subset is doing
relative to its parent, as one clearly-labeled live line + methodology note,
not a from-scratch reconstruction.

`fetch_data.py`'s `calc_world_value_vs_capweighted()` computes the ratio of
two live ETF prices, monthly, rebased to 100 at the first common month:

- **Value leg**: `IWVL.SW` — iShares Edge MSCI World Value Factor UCITS ETF
  (ISIN IE00BP3QZB59), tracking the **MSCI World Enhanced Value Index**.
- **Cap-weighted leg**: `SWDA.SW` — iShares Core MSCI World UCITS ETF (ISIN
  IE00B4L5Y983), the standard cap-weighted MSCI World benchmark. Picked over
  a generic "any MSCI World ETF" because it's the same fund family
  (BlackRock/iShares), same SIX listing, same USD share class as IWVL.SW —
  avoiding cross-provider tracking noise and any FX/domicile mismatch in the
  ratio.

Unlike `calc_spy_top10_history_approx()`, this needs no reconstruction —
both legs are live ETF prices going back to IWVL's 2015 SIX inception, so the
ratio is exact, not an approximation.

**Methodology caveat that must stay visible wherever this series is shown**
(`WORLD_VALUE_METHODOLOGY_NOTE` in `fetch_data.py`, rendered under the chart
by `longterm.html`'s `renderFactorVsCapWeighted()`, see the Quality section
above for why this is now a shared function): IWVL tracks MSCI World
**Enhanced** Value — a concentrated ~400-name selection out of the ~1,500-name
MSCI World universe, cap-weighted within that selection — which is NOT the
same as MSCI World **Value Weighted** (which re-weights the FULL MSCI World
universe by value score instead of selecting a subset). The two indices can
diverge meaningfully; never present this chart as "the" academic value
factor without that distinction.

## Vol & Options nav link — external app, set up 2026-08-25

The "Vol & Options" nav entry on every page links out to
`https://market-vol-dashboard.streamlit.app`, a Streamlit app that lives in
its own separate repo. It is embedded here only as an external link — no
data, charts, or assets from that repo are pulled into this site.

## SPCX (SpaceX) free float — now modeled via unlock schedule, set up 2026-08-10

`fetch_data.py`'s `SPCX_UNLOCK_SCHEDULE` anchors SpaceX's free float
calculation on a reconstructed IPO lock-up unlock schedule (free float % of
shares outstanding at a series of milestone dates, linearly interpolated by
`spcx_scheduled_float_pct()`), because yfinance's `floatShares` field for
SPCX reports roughly half the real number — the same kind of share-class
undercount bug already found and fixed for `sharesOutstanding` (see
`fetch_live_float_cap()` in `fetch_data.py`).

This replaces the earlier fixed `SPCX_IPO_FLOAT_SHARES` constant
(555,555,555 shares, the IPO offering size), which was always going to go
stale once the 2026-08-04 lock-up expiry started legitimately releasing
more shares into the float — the schedule now models that release over
time instead of freezing free float at the IPO number.

**Caveat**: the schedule's dates/percentages were reconstructed from a
third-party infographic (Boyan Girginov, sourced to SpaceX's SEC prospectus
filed 17 June 2026), not read directly from a primary filing — the source
chart itself calls the figures approximate. Treat it the same way as the
ACWI stockanalysis.com fallback or the SPY top-10 history chart: a
clearly-flagged approximation, not ground truth. If a more authoritative
source (real trading volume, secondary-sale disclosures, an actual SEC
Form 4/144) becomes available, update `SPCX_UNLOCK_SCHEDULE` in
`fetch_data.py` accordingly — especially around Musk's Day-366 stake
unlock (~2027-06-12), the single biggest jump in the schedule.

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
