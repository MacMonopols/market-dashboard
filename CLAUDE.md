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
