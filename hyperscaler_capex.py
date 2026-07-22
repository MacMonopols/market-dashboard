"""
hyperscaler_capex.py – Suit trimestriellement les métriques d'inquiétude sur
les hyperscalers (Microsoft, Alphabet, Amazon, Meta, Oracle) + deux profils de
contraste (Apple, Nvidia) via l'API SEC EDGAR XBRL (gratuite, officielle, sans
clé) :

  1. Capex / ventes (%), TTM          – intensité capitalistique
  2. Free cash flow / ventes (%), TTM – capacité d'autofinancement restante
  3. Capex vs D&A (écart $), TTM      – "mur de dépréciation" à venir
  4. Dette nette / EBITDA, TTM        – solvabilité
  5. Émissions de dette (TTM)         – comment le trou de cash est financé

Appelé depuis fetch_data.py, résultat fusionné dans live_data.js sous la clé
"hyperscalerCapex". Pas de dépendance pandas/Plotly : les graphiques sont
construits en SVG/JS côté navigateur, comme le reste du dashboard.

Pièges XBRL à connaître :
- Les 10-Q rapportent la plupart des flux de trésorerie CUMULÉS depuis le
  début de l'exercice fiscal (YTD), pas le flux du seul trimestre.
  quarterize() regroupe les faits qui partagent le même "start" (= même
  cumul d'exercice) et retranche le cumul du trimestre précédent pour isoler
  le flux trimestriel standalone. Si une métrique est en réalité déjà
  rapportée trimestre par trimestre (chaque fait a son propre "start"), le
  regroupement par "start" produit des groupes à un seul élément et
  quarterize() renvoie la valeur telle quelle — la fonction est donc
  transparente aux deux conventions, pas besoin de les distinguer à l'avance.
- Microsoft/Alphabet/Amazon/Meta/Oracle changent parfois de tag XBRL d'un
  exercice à l'autre (ex. Revenues vs
  RevenueFromContractWithCustomerExcludingAssessedTax). FALLBACK_TAGS essaie
  plusieurs tags par ordre de priorité ; on fusionne TOUS les tags plutôt que
  de garder seulement le premier qui répond (cf _fetch_metric).
- Les postes de bilan (dette long terme, trésorerie) sont des faits XBRL
  "instant" (une seule date "end", pas de "start" : ce sont des stocks, pas
  des flux). Ils ne doivent PAS passer par quarterize() — on prend
  directement la valeur au "end" de chaque trimestre.
"""

import time
import requests

SEC_HEADERS = {
    # La SEC exige un User-Agent identifiable (nom + email) sous peine de 403.
    "User-Agent": "Oblique Market Dashboard contact@oblique.swiss"
}

# CIK SEC (10 chiffres, zero-pad) des hyperscalers suivis
# Tesla est volontairement exclu : son capex est dominé par les usines/lignes
# de production automobile, pas par l'infrastructure IA/datacenter — inclure
# Tesla brouillerait la comparaison faite par ce module.
COMPANIES = {
    "Microsoft": "0000789019",
    "Alphabet":  "0001652044",
    "Amazon":    "0001018724",
    "Meta":      "0001326801",
    "Oracle":    "0001341439",
    "Apple":     "0000320193",
    "Nvidia":    "0001045810",
}

# Catégorisation du profil de capex de chaque entreprise — utilisée pour
# colorer les graphiques (gap capex-D&A, dette nette/EBITDA) par profil
# plutôt que par société, car toutes les entreprises ne bâtissent pas du
# capex (ni ne s'endettent) pour la même raison.
CAPEX_PROFILE = {
    "Microsoft": "Datacenter / cloud IA",
    "Alphabet":  "Datacenter / cloud IA",
    "Amazon":    "Datacenter / cloud IA",
    "Meta":      "Datacenter / cloud IA",
    "Oracle":    "Datacenter / cloud IA",
    "Apple":     "Capex bas et stable (contre-exemple)",
    "Nvidia":    "Fabless — capex physique porté par TSMC",
}

# Tags XBRL par métrique, par ordre de priorité (on fusionne tous les tags,
# cf _fetch_metric — un seul "premier qui répond" tronquerait l'historique
# des entreprises qui migrent de tag en cours de route, ex. Amazon en 2017).
FALLBACK_TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForCapitalImprovements",
        "PaymentsToAcquireProductiveAssets",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "Depreciation",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
    ],
    "long_term_debt": [
        "LongTermDebtNoncurrent",
        "DebtLongtermAndShorttermCombinedAmount",
        "LongTermDebt",
    ],
    "cash_and_equivalents": [
        "CashAndCashEquivalentsAtCarryingValue",
    ],
    "debt_issuance": [
        "ProceedsFromIssuanceOfLongTermDebt",
    ],
}

# Métriques requises : si l'une d'elles manque, l'entreprise est exclue des
# 3 graphiques historiques (capex%, FCF%, gap). Ce sont des flux "duration".
CORE_METRICS = ["revenue", "capex", "operating_cash_flow", "depreciation_amortization"]

# Métriques de dette : best-effort, ajoutées quand disponibles sans faire
# échouer l'entreprise entière si l'une d'elles manque (ex. une société qui
# n'émet pas de dette certains trimestres n'a tout simplement pas de fait
# XBRL ce trimestre-là, ce n'est pas une erreur).
DEBT_METRICS = ["operating_income", "long_term_debt", "cash_and_equivalents", "debt_issuance"]

# Postes de bilan (faits XBRL "instant" : une seule date "end", pas de flux
# à décumuler) — à distinguer des flux "duration" ci-dessus.
INSTANT_METRICS = {"long_term_debt", "cash_and_equivalents"}


def _fetch_concept_raw(cik, tag, instant=False):
    """Récupère les faits XBRL bruts (10-Q + 10-K) pour un CIK/tag donné.

    Les postes de bilan ("instant") n'ont qu'une date "end" et pas de
    "start" ; les flux ("duration", cash-flow/résultat) ont les deux.
    """
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
    resp = requests.get(url, headers=SEC_HEADERS, timeout=30)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    usd = resp.json().get("units", {}).get("USD", [])
    if instant:
        return [r for r in usd if r.get("form") in ("10-Q", "10-K") and not r.get("start")]
    return [r for r in usd if r.get("form") in ("10-Q", "10-K") and r.get("start")]


def _fetch_metric(cik, metric):
    """
    Pour les flux (duration) : fusionne TOUS les tags de FALLBACK_TAGS pour
    cette métrique (et pas seulement le premier trouvé) : certaines
    entreprises (ex. Amazon) migrent d'un tag à l'autre à une date donnée
    sans rétropoler l'historique, donc ne garder que le premier tag
    "gagnant" tronquerait la série. On combine tout puis on dédoublonne en
    gardant le dépôt le plus récent (dates ISO → tri lexical = tri chrono).

    Pour les postes de bilan (instant) : fusion par PRIORITÉ stricte plutôt
    que "dépôt le plus récent gagne". Contrairement aux flux, deux tags de
    bilan ne sont pas toujours de simples synonymes historiques : ex. pour
    Microsoft, LongTermDebtNoncurrent (dette hors part courante) et
    LongTermDebt (qui peut inclure la part courante) coexistent avec des
    valeurs DIFFÉRENTES au même trimestre. "Dernier déposé gagne"
    mélangerait ces deux définitions d'un trimestre à l'autre. On garde donc
    le premier tag de la liste qui a une valeur pour une date "end" donnée ;
    les tags suivants ne comblent que les dates absentes du premier (utile
    pour Oracle, qui ne rapporte pas LongTermDebtNoncurrent et utilise
    DebtLongtermAndShorttermCombinedAmount).
    """
    if metric in INSTANT_METRICS:
        merged = {}
        for tag in FALLBACK_TAGS[metric]:
            recs = _fetch_concept_raw(cik, tag, instant=True)
            time.sleep(0.15)
            latest_per_end = {}
            for r in recs:
                if r["end"] not in latest_per_end or r["filed"] > latest_per_end[r["end"]]["filed"]:
                    latest_per_end[r["end"]] = r
            for end, r in latest_per_end.items():
                merged.setdefault(end, r)  # premier tag présent gagne, pas le plus récent déposé
        if not merged:
            return None
        return sorted(merged.values(), key=lambda r: r["end"])

    combined = []
    for tag in FALLBACK_TAGS[metric]:
        combined.extend(_fetch_concept_raw(cik, tag))
        time.sleep(0.15)  # rester sous la limite SEC de 10 req/s
    if not combined:
        return None

    latest = {}
    for r in combined:
        key = (r["start"], r["end"])
        if key not in latest or r["filed"] > latest[key]["filed"]:
            latest[key] = r
    return sorted(latest.values(), key=lambda r: r["end"])


def _quarterize(records):
    """
    Convertit une série cumulée YTD en flux trimestriel standalone : les
    lignes qui partagent le même 'start' appartiennent au même cumul
    d'exercice fiscal ; on retranche le cumul du trimestre précédent.
    Retourne {end_date_str: valeur_trimestrielle}.
    """
    by_start = {}
    for r in records:
        by_start.setdefault(r["start"], []).append(r)

    out = {}
    for group in by_start.values():
        group = sorted(group, key=lambda r: r["end"])
        prev = 0
        for r in group:
            out[r["end"]] = r["val"] - prev
            prev = r["val"]
    return out


def _instant_series(records):
    """Poste de bilan : valeur directe au 'end', pas de décumulation."""
    return {r["end"]: r["val"] for r in records}


def _rolling_ttm(sorted_ends, values_by_end):
    """Somme glissante sur les 4 derniers trimestres (lisse la saisonnalité).
    Exige les 4 valeurs présentes (série stricte)."""
    ttm = {}
    for i, end in enumerate(sorted_ends):
        if i < 3:
            continue
        window = sorted_ends[i - 3:i + 1]
        ttm[end] = sum(values_by_end[e] for e in window)
    return ttm


def _rolling_ttm_lenient(common_ends, values_by_end):
    """
    Comme _rolling_ttm mais tolère les trimestres manquants (comptés comme
    0) : utilisé pour les émissions de dette, qui sont "lumpy" — beaucoup
    d'entreprises n'émettent pas de dette chaque trimestre et ne rapportent
    alors tout simplement pas ce fait XBRL (ce n'est pas une donnée
    manquante, c'est un montant nul). La fenêtre glissante reste calée sur
    le calendrier trimestriel commun (common_ends) plutôt que sur les seules
    dates où une émission a eu lieu, pour ne pas agréger à tort deux
    émissions éloignées dans le temps.
    """
    ttm = {}
    for i, end in enumerate(common_ends):
        if i < 3:
            continue
        window = common_ends[i - 3:i + 1]
        ttm[end] = sum(values_by_end.get(e, 0) for e in window)
    return ttm


def _build_company(name, cik):
    per_metric = {}
    for metric in CORE_METRICS:
        recs = _fetch_metric(cik, metric)
        if not recs:
            print(f"    [!] {name}: aucune donnée pour {metric}")
            return None
        per_metric[metric] = _quarterize(recs)

    common_ends = sorted(set.intersection(*(set(d) for d in per_metric.values())))
    if len(common_ends) < 4:
        print(f"    [!] {name}: historique trimestriel insuffisant ({len(common_ends)} trimestres communs)")
        return None

    ttm = {m: _rolling_ttm(common_ends, per_metric[m]) for m in CORE_METRICS}
    ttm_ends = sorted(set.intersection(*(set(d) for d in ttm.values())))

    quarters = []
    for end in ttm_ends:
        rev_ttm   = ttm["revenue"][end]
        capex_ttm = ttm["capex"][end]
        ocf_ttm   = ttm["operating_cash_flow"][end]
        da_ttm    = ttm["depreciation_amortization"][end]
        if not rev_ttm:
            continue
        quarters.append({
            "periodEnd":        end,
            "revenueTTM":       round(rev_ttm),
            "capexTTM":         round(capex_ttm),
            "ocfTTM":           round(ocf_ttm),
            "daTTM":            round(da_ttm),
            "capexPctSalesTTM": round(capex_ttm / rev_ttm * 100, 2),
            "fcfPctSalesTTM":   round((ocf_ttm - capex_ttm) / rev_ttm * 100, 2),
            "capexMinusDaTTM":  round(capex_ttm - da_ttm),
        })

    # ── Dette : ajout best-effort, ne fait pas échouer l'entreprise si
    # une métrique manque ────────────────────────────────────────────────
    op_income_recs = _fetch_metric(cik, "operating_income")
    op_income_q = _quarterize(op_income_recs) if op_income_recs else {}
    # EBITDA a besoin d'operating_income TTM calé sur le MÊME calendrier
    # trimestriel (common_ends) que le reste, sinon la comparaison capex vs
    # EBITDA n'a pas de sens ; série stricte (pas de trimestre = pas d'EBITDA
    # ce trimestre-là, on ne devine pas).
    oi_ttm = _rolling_ttm(common_ends, op_income_q) if op_income_q else {}
    da_ttm_by_end = _rolling_ttm(common_ends, per_metric["depreciation_amortization"])

    debt_issuance_recs = _fetch_metric(cik, "debt_issuance")
    debt_issuance_q = _quarterize(debt_issuance_recs) if debt_issuance_recs else {}
    debt_issuance_ttm = _rolling_ttm_lenient(common_ends, debt_issuance_q) if debt_issuance_recs else {}

    ltd_recs = _fetch_metric(cik, "long_term_debt")
    ltd_by_end = _instant_series(ltd_recs) if ltd_recs else {}

    cash_recs = _fetch_metric(cik, "cash_and_equivalents")
    cash_by_end = _instant_series(cash_recs) if cash_recs else {}

    for q in quarters:
        end = q["periodEnd"]

        if end in oi_ttm and end in da_ttm_by_end:
            ebitda_ttm = oi_ttm[end] + da_ttm_by_end[end]
            q["ebitdaTTM"] = round(ebitda_ttm)
        else:
            ebitda_ttm = None
            q["ebitdaTTM"] = None

        if end in ltd_by_end and end in cash_by_end:
            net_debt = ltd_by_end[end] - cash_by_end[end]
            q["longTermDebt"] = round(ltd_by_end[end])
            q["cashAndEquivalents"] = round(cash_by_end[end])
            q["netDebt"] = round(net_debt)
            q["netDebtToEbitdaTTM"] = round(net_debt / ebitda_ttm, 2) if ebitda_ttm else None
        else:
            q["longTermDebt"] = None
            q["cashAndEquivalents"] = None
            q["netDebt"] = None
            q["netDebtToEbitdaTTM"] = None

        q["debtIssuanceTTM"] = round(debt_issuance_ttm[end]) if end in debt_issuance_ttm else None

    return {"name": name, "profile": CAPEX_PROFILE.get(name), "quarters": quarters}


def fetch_hyperscaler_capex(companies=COMPANIES):
    results = []
    for name, cik in companies.items():
        print(f"  ↓ {name} (SEC EDGAR) …")
        company = _build_company(name, cik)
        if company:
            print(f"    OK ({len(company['quarters'])} trimestres TTM)")
            results.append(company)
    return {"companies": results}


if __name__ == "__main__":
    import json
    data = fetch_hyperscaler_capex()
    print(json.dumps(data, indent=2)[:2000])
