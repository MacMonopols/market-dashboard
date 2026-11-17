"""
market_signals.py – "When to exit a bubble": four exit signals after Citi's
Willer (user's notes), rebuilt with free Yahoo daily data. PROXIES, not
Citi's indicators, and not investment advice.

1. Generals – the 7 largest S&P 500 stocks (FIXED list `GENERALS`, today's
   names = survivorship / look-ahead bias on history): how many close below
   their `MA_GENERALS`-day moving average; alert at >= `GENERALS_ALERT` of 7.
   Compared with the S&P 500 itself (^GSPC) below its own MA — the Generals
   should break first. `generals.leads` = lead in sessions / calendar days
   between each Generals alert and the S&P's own break.
2. AI overcapacity peak (price proxy) – 6-month (126 sessions) return of
   SMH minus SPY; alert when it is negative again after a lead of at least
   `SEMI_LEAD_PCT` pt in the previous 6 months. Citi uses capex / capacity
   data; this is only the price reflection.
3. PULSE (proxy) – mean of 4 rolling z-scores (S&P distance above its
   50-day MA, RSI(14), 3-month return, minus VIX), re-standardized; alert
   above `PULSE_Z`. Citi's PULSE uses proprietary positioning data. Hit
   rate = share of alerts followed by a >= 5 % drawdown within 21 sessions
   vs the unconditional base rate (all days), so the threshold can be judged.
4. Rotation – XLK / geometric mean(XLU, XLP) below its 100-day MA (the
   geometric mean keeps the MA crossings independent of price levels).

Confirm filter: a signal switches ON only after its raw condition held
`CONFIRM_DAYS` (5) consecutive sessions and OFF only after 5 sessions
without it. History from `HISTORY_START` (2015); data from 2011 for the
warm-up of MAs and rolling z-scores.

Cache market_signals_cache.json (git-ignored), `stale: true` on fallback.
"""

import json
import os
from datetime import date

import numpy as np
import pandas as pd

GENERALS = ["NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "AVGO"]
MA_GENERALS = 200          # MA length for the Generals and the S&P break
GENERALS_ALERT = 4         # alert when >= 4 of 7 are below their MA
LEAD_WINDOW_BEFORE = 63    # S&P break may precede a Generals alert by up to 63 sessions (negative lead)
LEAD_WINDOW_AFTER = 189    # ... or follow it by up to ~9 months
SEMI_WINDOW = 126          # 6-month relative performance
SEMI_LEAD_PCT = 15.0       # "strong lead" = SMH ahead of SPY by >= 15 pt over 6 months ...
SEMI_LOOKBACK = 126        # ... at some point in the previous 6 months
PULSE_Z = 1.5
PULSE_ZWIN = 756           # rolling 3-year z-scores (ex ante)
PULSE_DD = -5.0            # "pullback" = drawdown of >= 5 % ...
PULSE_HORIZON = 21         # ... within one month (21 sessions)
ROT_MA = 100
CONFIRM_DAYS = 5
HISTORY_START = "2015-01-01"
DATA_START = "2011-01-01"

TICKERS = GENERALS + ["^GSPC", "SPY", "SMH", "XLK", "XLU", "XLP", "^VIX"]
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_signals_cache.json")

NOTES = {
    "generals": (
        f"Generals = today's 7 largest S&P 500 stocks ({', '.join(GENERALS)}), a FIXED list: on history this "
        "is survivorship / look-ahead bias (in 2015 NVDA and AVGO were not generals, and the real leaders of "
        "earlier tops — e.g. Exxon, GE, Cisco — are not in the list). Count = how many close below their "
        f"{MA_GENERALS}-day moving average (Yahoo, dividend-adjusted); alert at ≥ {GENERALS_ALERT} of 7, "
        f"S&P break = S&P 500 index below its own {MA_GENERALS}-day MA. Both confirmed by "
        f"{CONFIRM_DAYS} consecutive sessions (on and off). Lead = sessions from a Generals alert to the next "
        f"S&P break starting within {LEAD_WINDOW_BEFORE} sessions before / {LEAD_WINDOW_AFTER} after it "
        "(negative = the S&P broke first). Not investment advice."
    ),
    "semis": (
        f"Proxy for Willer's AI overcapacity peak: 6-month ({SEMI_WINDOW} sessions) total return of the "
        "VanEck Semiconductor ETF (SMH) minus SPY. Alert when the gap is negative again after SMH led by "
        f"≥ {SEMI_LEAD_PCT:.0f} pt at some point in the previous 6 months. Citi works from real capex / "
        "capacity data (exit 6–9 months before the sector's overcapacity peak; the index usually breaks 6–9 "
        "months after the fundamentals peak) — prices only show the market's reaction, usually late. "
        f"{CONFIRM_DAYS}-session confirm filter. Not investment advice."
    ),
    "pulse": (
        "Proxy for Citi's PULSE, which uses proprietary positioning data that is not available here. "
        "Composite = mean of 4 rolling 3-year z-scores — S&P 500 distance above its 50-day MA, RSI(14), "
        "3-month return and minus the VIX (low VIX = complacency) — re-standardized over the same window; "
        f"alert above {PULSE_Z} sd, {CONFIRM_DAYS}-session confirm filter. The threshold is NOT calibrated: "
        f"the hit rate is the share of alerts followed by a drawdown of ≥ {abs(PULSE_DD):.0f} % within "
        f"{PULSE_HORIZON} sessions, against the same share over all days (base rate) — only a hit rate "
        "clearly above the base rate means the signal adds anything. On a simulated market the draft "
        "version did no better than chance (22 % vs 23 %). Not investment advice."
    ),
    "rotation": (
        "Ratio of technology (XLK) to defensives (geometric mean of utilities XLU and consumer staples XLP), "
        f"all SPDR sector ETFs, dividend-adjusted. Alert when the ratio is below its {ROT_MA}-day MA "
        f"({CONFIRM_DAYS}-session confirm filter): tech leads until the top, then money rotates into "
        "utilities and staples. Also fires in ordinary corrections and rate shocks. Not investment advice."
    ),
}


# ── helpers ─────────────────────────────────────────────────────────────────

def confirm(raw, n=CONFIRM_DAYS):
    """Hysteresis filter: ON after n consecutive True, OFF after n consecutive False."""
    out = np.zeros(len(raw), dtype=bool)
    state, run_t, run_f = False, 0, 0
    for i, v in enumerate(raw):
        if v:
            run_t, run_f = run_t + 1, 0
        else:
            run_t, run_f = 0, run_f + 1
        if not state and run_t >= n:
            state = True
        elif state and run_f >= n:
            state = False
        out[i] = state
    return out


def episodes(flag, idx):
    """Contiguous True runs → list of (start_pos, end_pos)."""
    eps, start = [], None
    for i, v in enumerate(flag):
        if v and start is None:
            start = i
        elif not v and start is not None:
            eps.append((start, i - 1))
            start = None
    if start is not None:
        eps.append((start, len(flag) - 1))
    return eps


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def rz(s, win=PULSE_ZWIN):
    return (s - s.rolling(win, min_periods=win // 2).mean()) / s.rolling(win, min_periods=win // 2).std()


def _d(ts):
    return ts.date().isoformat()


def _r(arr, nd=2):
    return [None if (v is None or not np.isfinite(v)) else round(float(v), nd) for v in arr]


def _status(raw, conf):
    """Raw run length (sessions the raw condition has held) and confirmed state today."""
    run = 0
    for v in raw[::-1]:
        if v == raw[-1]:
            run += 1
        else:
            break
    return {"on": bool(conf[-1]), "raw": bool(raw[-1]), "rawRun": run}


# ── main ────────────────────────────────────────────────────────────────────

def _compute(today=None):
    import yfinance as yf
    today = pd.Timestamp(today or date.today())
    end = (today + pd.Timedelta(days=1)).date().isoformat()
    px = yf.download(TICKERS, start=DATA_START, end=end, auto_adjust=True, progress=False)["Close"]
    px.index = px.index.tz_localize(None) if px.index.tz is not None else px.index
    px = px[px["^GSPC"].notna()].ffill()
    missing = [t for t in TICKERS if t not in px.columns or px[t].dropna().empty]
    if missing:
        raise RuntimeError(f"no Yahoo data for {missing}")

    spx = px["^GSPC"]
    # 1. Generals
    below = pd.DataFrame({t: px[t] < px[t].rolling(MA_GENERALS).mean() for t in GENERALS})
    valid = pd.DataFrame({t: px[t].rolling(MA_GENERALS).mean().notna() for t in GENERALS})
    count = (below & valid).sum(axis=1)
    spx_ma = spx.rolling(MA_GENERALS).mean()
    gen_raw = (count >= GENERALS_ALERT).values
    spx_raw = (spx < spx_ma).values
    # 2. Semis vs S&P
    rel = (px["SMH"] / px["SMH"].shift(SEMI_WINDOW) - px["SPY"] / px["SPY"].shift(SEMI_WINDOW)) * 100
    prior_max = rel.rolling(SEMI_LOOKBACK, min_periods=1).max()
    semi_raw = ((rel < 0) & (prior_max >= SEMI_LEAD_PCT)).values
    # 3. PULSE proxy
    comps = {
        "dist50": (spx / spx.rolling(50).mean() - 1) * 100,
        "rsi14": rsi(spx),
        "ret63": (spx / spx.shift(63) - 1) * 100,
        "vix": px["^VIX"],
    }
    zs = pd.DataFrame({"dist50": rz(comps["dist50"]), "rsi14": rz(comps["rsi14"]),
                       "ret63": rz(comps["ret63"]), "vix": -rz(comps["vix"])})
    pulse = rz(zs.mean(axis=1, skipna=False))
    pulse_raw = (pulse > PULSE_Z).values
    # 4. Rotation
    ratio = px["XLK"] / np.sqrt(px["XLU"] * px["XLP"])
    ratio = ratio / ratio[ratio.index >= HISTORY_START].iloc[0] * 100
    rot_ma = ratio.rolling(ROT_MA).mean()
    rot_raw = (ratio < rot_ma).values

    # restrict to history window (filters run on full data, so a state is
    # already established on the first day shown)
    conf = {k: confirm(v) for k, v in
            {"generals": gen_raw, "spx": spx_raw, "semis": semi_raw, "pulse": pulse_raw, "rotation": rot_raw}.items()}
    raws = {"generals": gen_raw, "spx": spx_raw, "semis": semi_raw, "pulse": pulse_raw, "rotation": rot_raw}
    m = (px.index >= HISTORY_START)
    idx = px.index[m]
    pos0 = int(np.argmax(m))
    C = {k: v[m] for k, v in conf.items()}
    R = {k: v[m] for k, v in raws.items()}
    dates = [_d(t) for t in idx]
    ep = {k: episodes(v, idx) for k, v in C.items()}
    ep_dates = {k: [[dates[a], dates[b]] for a, b in v] for k, v in ep.items()}

    # Generals lead vs S&P break
    leads = []
    spx_starts = [a for a, _ in ep["spx"]]
    for a, b in ep["generals"]:
        cand = [s for s in spx_starts if a - LEAD_WINDOW_BEFORE <= s <= a + LEAD_WINDOW_AFTER]
        if cand:
            # prefer the first break at / after the alert, else the latest one before it
            after = [c for c in cand if c >= a]
            s = after[0] if after else max(cand)
            leads.append({"generals": dates[a], "spx": dates[s], "sessions": int(s - a),
                          "days": int((idx[s] - idx[a]).days)})
        else:
            leads.append({"generals": dates[a], "spx": None, "sessions": None, "days": None})
    matched = [l["sessions"] for l in leads if l["sessions"] is not None]
    spx_unwarned = [dates[s] for s in spx_starts
                    if not any(l["spx"] == dates[s] for l in leads)]

    # PULSE hit rate
    close = spx.values
    fwd = np.full(len(close), np.nan)
    for i in range(len(close) - PULSE_HORIZON):
        fwd[i] = (close[i + 1:i + 1 + PULSE_HORIZON].min() / close[i] - 1) * 100
    fwd_m = fwd[m]
    ok = ~np.isnan(fwd_m)
    hit = fwd_m <= PULSE_DD
    base = float(hit[ok].mean() * 100)
    starts = [a for a, _ in ep["pulse"] if ok[a]]
    on_days = C["pulse"] & ok
    hit_rate = {
        "horizon": PULSE_HORIZON, "drawdownPct": PULSE_DD,
        "alerts": len(starts), "hits": int(sum(hit[a] for a in starts)),
        "alertHitPct": round(float(np.mean([hit[a] for a in starts]) * 100), 1) if starts else None,
        "alertDays": int(on_days.sum()),
        "alertDayHitPct": round(float(hit[on_days].mean() * 100), 1) if on_days.any() else None,
        "baseDays": int(ok.sum()), "basePct": round(base, 1),
        "rawDays": int((R["pulse"] & ok).sum()),
        "rawDayHitPct": round(float(hit[R["pulse"] & ok].mean() * 100), 1) if (R["pulse"] & ok).any() else None,
    }

    last = -1
    gl = []
    for t in GENERALS:
        ma = px[t].rolling(MA_GENERALS).mean().iloc[last]
        gl.append({"ticker": t, "close": round(float(px[t].iloc[last]), 2),
                   "ma": round(float(ma), 2), "distPct": round(float((px[t].iloc[last] / ma - 1) * 100), 1),
                   "below": bool(px[t].iloc[last] < ma)})

    return {
        "asOf": dates[-1],
        "historyStart": dates[0],
        "params": {"maGenerals": MA_GENERALS, "generalsAlert": GENERALS_ALERT, "confirmDays": CONFIRM_DAYS,
                   "semiWindow": SEMI_WINDOW, "semiLeadPct": SEMI_LEAD_PCT, "pulseZ": PULSE_Z,
                   "rotMa": ROT_MA, "generals": GENERALS},
        "dates": dates,
        "spx": _r(spx.values[m], 1),
        "spxMa": _r(spx_ma.values[m], 1),
        "generals": {
            "count": [int(v) for v in count.values[m]],
            "status": dict(_status(R["generals"], C["generals"]), count=int(count.iloc[last])),
            "spxStatus": dict(_status(R["spx"], C["spx"]),
                              distPct=round(float((spx.iloc[last] / spx_ma.iloc[last] - 1) * 100), 1)),
            "stocks": gl,
            "episodes": ep_dates["generals"],
            "spxEpisodes": ep_dates["spx"],
            "leads": leads,
            "spxUnwarned": spx_unwarned,
            "leadMedianSessions": float(np.median(matched)) if matched else None,
            "leadPositive": sum(1 for v in matched if v > 0),
            "leadMatched": len(matched),
            "note": NOTES["generals"],
        },
        "semis": {
            "rel": _r(rel.values[m], 1),
            "status": dict(_status(R["semis"], C["semis"]), rel=round(float(rel.iloc[last]), 1),
                           priorMax=round(float(prior_max.iloc[last]), 1)),
            "episodes": ep_dates["semis"],
            "note": NOTES["semis"],
        },
        "pulse": {
            "z": _r(pulse.values[m], 2),
            "status": dict(_status(R["pulse"], C["pulse"]), z=round(float(pulse.iloc[last]), 2),
                           components={k: round(float(zs[k].iloc[last]), 2) for k in zs.columns},
                           values={"dist50": round(float(comps["dist50"].iloc[last]), 1),
                                "rsi14": round(float(comps["rsi14"].iloc[last]), 1),
                                "ret63": round(float(comps["ret63"].iloc[last]), 1),
                                "vix": round(float(comps["vix"].iloc[last]), 1)}),
            "episodes": ep_dates["pulse"],
            "hitRate": hit_rate,
            "note": NOTES["pulse"],
        },
        "rotation": {
            "ratio": _r(ratio.values[m], 2),
            "ma": _r(rot_ma.values[m], 2),
            "status": dict(_status(R["rotation"], C["rotation"]), ratio=round(float(ratio.iloc[last]), 2),
                           distPct=round(float((ratio.iloc[last] / rot_ma.iloc[last] - 1) * 100), 1)),
            "episodes": ep_dates["rotation"],
            "note": NOTES["rotation"],
        },
        "disclaimer": ("Price-based proxies of Citi's (Willer) bubble-exit signals, rebuilt from free Yahoo "
                       "Finance data. Not Citi's indicators, not a forecast, not investment advice."),
    }


def calc_market_signals():
    try:
        res = _compute()
        try:
            with open(CACHE_PATH, "w") as f:
                json.dump(res, f)
        except OSError as e:
            print(f"  ⚠ could not write market signals cache: {e}")
        res["stale"] = False
        return res
    except Exception as e:
        try:
            with open(CACHE_PATH) as f:
                res = json.load(f)
        except (OSError, json.JSONDecodeError):
            raise e
        print(f"  ⚠ market signals fetch failed ({e}) — using cache as of {res.get('asOf')}")
        res["stale"] = True
        return res


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    r = calc_market_signals()
    g = r["generals"]
    print("as of", r["asOf"], "| generals", g["status"], "| spx", g["spxStatus"])
    print("generals episodes", len(g["episodes"]), "spx episodes", len(g["spxEpisodes"]))
    for l in g["leads"]:
        print("  lead", l)
    print("  S&P breaks without Generals alert:", g["spxUnwarned"])
    print("  median lead", g["leadMedianSessions"], "positive", g["leadPositive"], "/", g["leadMatched"])
    print("semis", r["semis"]["status"], len(r["semis"]["episodes"]), r["semis"]["episodes"])
    print("pulse", r["pulse"]["status"], r["pulse"]["hitRate"])
    print("rotation", r["rotation"]["status"], len(r["rotation"]["episodes"]))
    print("json size", len(json.dumps(r)))
