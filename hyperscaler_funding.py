"""
hyperscaler_funding.py – Les hyperscalers en concurrence avec le Treasury (et
le reste du marché corporate) pour la même épargne obligataire. Combine les
émissions de dette SEC EDGAR déjà calculées par hyperscaler_capex.py avec
des données de marché gratuites et officielles :

  1. Émission nette hyperscalers / émission nette d'obligations corporate
     non-financières US (Fed Z.1, via FRED)       – poids dans le marché
  2. Émission nette hyperscalers / emprunt net du Treasury (variation de la
     dette détenue par le public, Treasury Fiscal Data API)
                                                  – concurrence pour le financement
  3. Spread OAS ICE BofA par notation (AAA / AA / BBB, via FRED)
                                                  – attractivité relative vs Treasury
  4. Capex / cash-flow opérationnel : directement par société dans
     hyperscaler_capex.py (champ capexToOcfTTM), pas besoin de données de marché.

Choix méthodologiques (à garder visibles dans le dashboard, cf
FUNDING_METHODOLOGY_NOTE / SPREAD_METHODOLOGY_NOTE) :

- Les chiffres BRUTS d'émission US Investment Grade (SIFMA) ne sont
  disponibles que derrière un formulaire d'inscription — pas automatisable.
  On utilise donc le flux NET de la Fed (Z.1, obligations des entreprises
  non-financières, toutes notations) et, par cohérence, l'émission NETTE des
  hyperscalers (émissions − remboursements). Net vs net : un ratio
  brut/net gonflerait artificiellement la part des hyperscalers. Quand le
  flux net du marché est proche de zéro (ex. 2022, où les entreprises
  remboursaient plus qu'elles n'émettaient), le ratio n'a pas de sens : on ne
  le calcule pas sous MIN_DENOMINATOR_USD.
- Les émissions XBRL incluent les obligations en EUR/CHF/GBP/… (converties
  en USD par les sociétés) : c'est l'offre mondiale de chaque hyperscaler,
  pas seulement le marché USD.
- Exercices décalés : Oracle (clôture mai) est rattaché au trimestre civil
  contenant sa fin de trimestre fiscal (fin août → T3) ; décalage ≤ 1 mois.
- Spreads : aucune courbe gratuite de spread PAR ÉMETTEUR n'existe (TRACE /
  Bloomberg sont payants). On utilise les indices ICE BofA par notation
  comme proxy de la notation de chaque hyperscaler (S&P/Moody's) :
  AAA ≈ Microsoft, AA ≈ Alphabet/Amazon/Meta, BBB ≈ Oracle. ICE limite
  FRED aux 3 dernières années d'historique.

FRED bloque les rafales de requêtes (protection anti-bot) : on groupe les
séries en une requête par fréquence (2 au total), avec quelques réessais, puis
on retombe sur le dernier résultat valide en cache disque si FRED reste
indisponible (même approche "ne jamais échouer silencieusement" que
fetch_etf_holdings()).
"""

import csv
import io
import json
import os
import time
from datetime import date

import requests

HYPERSCALERS = ["Microsoft", "Alphabet", "Amazon", "Meta", "Oracle"]

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
# Fed Z.1 : Nonfinancial Corporate Business; Corporate Bonds; Liability,
# Transactions — flux NET trimestriel, en millions USD, taux annualisé (SAAR).
Z1_NONFIN_CORP_BONDS = "BOGZ1FA103163005Q"

# Spreads option-adjusted ICE BofA (en points de %), par notation -> proxies.
SPREAD_SERIES = [
    {"id": "BAMLC0A1CAAA", "rating": "AAA", "proxyFor": ["Microsoft"]},
    {"id": "BAMLC0A2CAA",  "rating": "AA",  "proxyFor": ["Alphabet", "Amazon", "Meta"]},
    {"id": "BAMLC0A4CBBB", "rating": "BBB", "proxyFor": ["Oracle"]},
]

TREASURY_DEBT_URL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
                     "v2/accounting/od/debt_to_penny")

# Sous ce flux net annuel du marché (TTM), le ratio "part des hyperscalers"
# explose ou change de signe sans rien signifier économiquement.
MIN_DENOMINATOR_USD = 100e9

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hyperscaler_funding_cache.json")

FUNDING_METHODOLOGY_NOTE = (
    "Net issuance = bond proceeds − repayments, trailing twelve months, summed over Microsoft, Alphabet, "
    "Amazon, Meta and Oracle (SEC EDGAR cash-flow statements; includes their EUR/CHF/GBP issues). "
    "US corporate market = Fed Z.1 net bond issuance of all US nonfinancial corporations (all ratings) — "
    "gross US IG issuance (SIFMA) is not freely downloadable, so both sides are measured net. "
    "Not shown when the market's net issuance is below $100bn (e.g. 2022, when corporates were net repaying). "
    "Treasury = change in debt held by the public over the same 12 months (Treasury Fiscal Data). "
    "Oracle's fiscal quarters (ending Feb/May/Aug/Nov) are mapped to the calendar quarter they end in."
)

SPREAD_METHODOLOGY_NOTE = (
    "Proxy, not issuer-level spreads: ICE BofA US Corporate option-adjusted spread indices by rating bucket, "
    "matched to each hyperscaler's S&P/Moody's rating (Microsoft AAA/Aaa; Alphabet, Amazon, Meta AA range; "
    "Oracle BBB). Individual bonds trade around their bucket — e.g. a heavy new issuer can price wider than "
    "its rating peers. Source: ICE Data Indices via FRED, which only carries the last 3 years of history."
)


def _calendar_quarter_end(iso):
    """'2026-08-31' -> '2026-09-30' : fin du trimestre civil qui contient la date."""
    y, m = int(iso[:4]), int(iso[5:7])
    qm = ((m - 1) // 3 + 1) * 3
    last_day = {3: 31, 6: 30, 9: 30, 12: 31}[qm]
    return f"{y}-{qm:02d}-{last_day}"


def _fetch_fred(ids, attempts=3):
    """Une seule requête groupée -> {id: {date: float}}. Lève si FRED reste
    indisponible après `attempts` essais (réponse HTML = blocage anti-bot)."""
    last_err = None
    for i in range(attempts):
        try:
            # PAS de User-Agent "navigateur" : FRED (Akamai) laisse pendre
            # indéfiniment les requêtes qui se disent "Mozilla/5.0" sans en
            # avoir l'empreinte TLS ; l'UA par défaut de requests passe.
            resp = requests.get(FRED_CSV_URL, params={"id": ",".join(ids)}, timeout=40)
            resp.raise_for_status()
            if not resp.text.startswith("observation_date"):
                raise ValueError("FRED returned a non-CSV page (rate-limited?)")
            out = {sid: {} for sid in ids}
            for row in csv.DictReader(io.StringIO(resp.text)):
                for sid in ids:
                    v = row.get(sid)
                    if v not in (None, "", "."):
                        out[sid][row["observation_date"]] = float(v)
            return out
        except Exception as e:
            last_err = e
            if i < attempts - 1:
                time.sleep(10 * (i + 1))
    raise RuntimeError(f"FRED unavailable after {attempts} attempts: {last_err}")


def _fetch_treasury_debt_held_by_public(since="2010-01-01"):
    """Dette fédérale détenue par le public, quotidienne -> {date: USD}."""
    out, page = {}, 1
    while True:
        resp = requests.get(TREASURY_DEBT_URL, params={
            "fields": "record_date,debt_held_public_amt",
            "filter": f"record_date:gte:{since}",
            "sort": "record_date",
            "page[size]": 10000,
            "page[number]": page,
        }, timeout=40)
        resp.raise_for_status()
        j = resp.json()
        for r in j["data"]:
            if r["debt_held_public_amt"] not in (None, "null"):
                out[r["record_date"]] = float(r["debt_held_public_amt"])
        if page >= j["meta"]["total-pages"]:
            return out
        page += 1


def _last_on_or_before(series_by_date, iso):
    candidates = [d for d in series_by_date if d <= iso]
    return series_by_date[max(candidates)] if candidates else None


def _load_market_cache():
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _fetch_market_data():
    """FRED + Treasury, avec repli sur le dernier résultat valide en cache."""
    try:
        # Deux requêtes, pas une : mélanger séries trimestrielle et
        # quotidiennes fait renvoyer à FRED un zip au lieu d'un CSV.
        fred = _fetch_fred([Z1_NONFIN_CORP_BONDS])
        fred.update(_fetch_fred([s["id"] for s in SPREAD_SERIES]))
        treasury = _fetch_treasury_debt_held_by_public()
        data = {"fetchedAt": date.today().isoformat(), "fred": fred, "treasury": treasury}
        try:
            with open(CACHE_PATH, "w") as f:
                json.dump(data, f)
        except OSError as e:
            print(f"  ⚠ could not write hyperscaler funding cache: {e}")
        return data, False
    except Exception as e:
        cached = _load_market_cache()
        if cached is None:
            raise
        print(f"  ⚠ live market data failed ({e}) — using cached data from {cached['fetchedAt']}")
        return cached, True


def _hyperscaler_net_issuance_by_quarter(hyperscaler_capex):
    """{fin de trimestre civil: émission nette TTM des 5 hyperscalers}, en
    ne gardant que les trimestres où les 5 sociétés ont une valeur (sinon la
    somme sous-estimerait silencieusement le total)."""
    per_company = {}
    for c in hyperscaler_capex.get("companies", []):
        if c["name"] not in HYPERSCALERS:
            continue
        per_company[c["name"]] = {
            _calendar_quarter_end(q["periodEnd"]): q["netDebtIssuanceTTM"]
            for q in c.get("debtFlows", [])
        }
    if set(per_company) != set(HYPERSCALERS):
        missing = set(HYPERSCALERS) - set(per_company)
        raise ValueError(f"missing hyperscaler issuance data for {sorted(missing)}")
    common = sorted(set.intersection(*(set(d) for d in per_company.values())))
    return {qe: sum(per_company[n][qe] for n in HYPERSCALERS) for qe in common}, per_company


def _weekly(series_by_date):
    """Daily -> dernière observation de chaque semaine ISO (allège le graphique)."""
    by_week = {}
    for d in sorted(series_by_date):
        y, w, _ = date.fromisoformat(d).isocalendar()
        by_week[(y, w)] = d
    return [{"date": d, "bp": round(series_by_date[d] * 100)} for d in sorted(by_week.values())]


def calc_hyperscaler_funding(hyperscaler_capex):
    market, stale = _fetch_market_data()
    fred, treasury = market["fred"], market["treasury"]

    hs_net, per_company = _hyperscaler_net_issuance_by_quarter(hyperscaler_capex)

    # Z.1 : dates FRED = 1er jour du trimestre, valeurs SAAR en millions.
    # Flux d'un trimestre = SAAR / 4 ; TTM = somme des 4 derniers trimestres.
    z1_q = {_calendar_quarter_end(d): v * 1e6 / 4 for d, v in fred[Z1_NONFIN_CORP_BONDS].items()}
    z1_ends = sorted(z1_q)
    z1_ttm = {z1_ends[i]: sum(z1_q[e] for e in z1_ends[i - 3:i + 1]) for i in range(3, len(z1_ends))}

    quarters = []
    for qe, hs in sorted(hs_net.items()):
        y = int(qe[:4])
        prev_qe = f"{y - 1}{qe[4:]}"
        dhp_now, dhp_prev = _last_on_or_before(treasury, qe), _last_on_or_before(treasury, prev_qe)
        treasury_net = dhp_now - dhp_prev if dhp_now is not None and dhp_prev is not None else None
        corp_net = z1_ttm.get(qe)
        quarters.append({
            "quarterEnd": qe,
            "hyperscalerNetIssuanceTTM": round(hs),
            "byCompany": {n: round(per_company[n][qe]) for n in HYPERSCALERS},
            "corpNetIssuanceTTM": round(corp_net) if corp_net is not None else None,
            "treasuryNetBorrowingTTM": round(treasury_net) if treasury_net is not None else None,
            "pctOfCorpNetIssuance": (round(hs / corp_net * 100, 1)
                                     if corp_net is not None and corp_net >= MIN_DENOMINATOR_USD else None),
            "pctOfTreasuryNetBorrowing": (round(hs / treasury_net * 100, 1)
                                          if treasury_net and treasury_net >= MIN_DENOMINATOR_USD else None),
        })

    spreads = [{
        "rating": s["rating"],
        "proxyFor": s["proxyFor"],
        "seriesId": s["id"],
        "history": _weekly(fred[s["id"]]),
    } for s in SPREAD_SERIES]

    return {
        "asOf": market["fetchedAt"],
        "stale": stale,
        "hyperscalers": HYPERSCALERS,
        "quarters": quarters,
        "spreads": spreads,
        "note": FUNDING_METHODOLOGY_NOTE,
        "spreadNote": SPREAD_METHODOLOGY_NOTE,
    }


if __name__ == "__main__":
    from hyperscaler_capex import fetch_hyperscaler_capex
    d = calc_hyperscaler_funding(fetch_hyperscaler_capex())
    for q in d["quarters"]:
        print(q["quarterEnd"], q["hyperscalerNetIssuanceTTM"] / 1e9, q["pctOfCorpNetIssuance"], q["pctOfTreasuryNetBorrowing"])
    for s in d["spreads"]:
        print(s["rating"], s["history"][0], s["history"][-1], len(s["history"]))
