"""
hyperscaler_capex.py – Suit trimestriellement trois métriques d'inquiétude sur
les hyperscalers (Microsoft, Alphabet, Amazon, Meta, Oracle) via l'API SEC
EDGAR XBRL (gratuite, officielle, sans clé) :

  1. Capex / ventes (%), TTM          – intensité capitalistique
  2. Free cash flow / ventes (%), TTM – capacité d'autofinancement restante
  3. Capex vs D&A (écart $), TTM      – "mur de dépréciation" à venir

Appelé depuis fetch_data.py, résultat fusionné dans live_data.js sous la clé
"hyperscalerCapex". Pas de dépendance pandas/Plotly : les graphiques sont
construits en SVG/JS côté navigateur, comme le reste du dashboard.

Deux pièges XBRL à connaître :
- Les 10-Q rapportent des flux de trésorerie CUMULÉS depuis le début de
  l'exercice fiscal (YTD), pas le flux du seul trimestre. quarterize()
  regroupe les faits qui partagent le même "start" (= même cumul d'exercice)
  et retranche le cumul du trimestre précédent pour isoler le flux
  trimestriel standalone.
- Microsoft/Alphabet/Amazon/Meta/Oracle changent parfois de tag XBRL d'un
  exercice à l'autre (ex. Revenues vs
  RevenueFromContractWithCustomerExcludingAssessedTax). FALLBACK_TAGS essaie
  plusieurs tags par ordre de priorité, le premier trouvé gagne.
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
# colorer le graphique du "gap" capex-D&A par profil plutôt que par société,
# car toutes les entreprises ne bâtissent pas du capex pour la même raison.
CAPEX_PROFILE = {
    "Microsoft": "Datacenter / cloud IA",
    "Alphabet":  "Datacenter / cloud IA",
    "Amazon":    "Datacenter / cloud IA",
    "Meta":      "Datacenter / cloud IA",
    "Oracle":    "Datacenter / cloud IA",
    "Apple":     "Capex bas et stable (contre-exemple)",
    "Nvidia":    "Fabless — capex physique porté par TSMC",
}

# Tags XBRL par métrique, par ordre de priorité (le premier trouvé gagne)
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
}

TTM_METRICS = ["revenue", "capex", "operating_cash_flow", "depreciation_amortization"]


def _fetch_concept_raw(cik, tag):
    """Récupère les faits XBRL bruts (10-Q + 10-K) pour un CIK/tag donné."""
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
    resp = requests.get(url, headers=SEC_HEADERS, timeout=30)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    usd = resp.json().get("units", {}).get("USD", [])
    return [r for r in usd if r.get("form") in ("10-Q", "10-K") and r.get("start")]


def _fetch_metric(cik, metric):
    """
    Fusionne TOUS les tags de FALLBACK_TAGS pour cette métrique (et pas
    seulement le premier trouvé) : certaines entreprises (ex. Amazon) migrent
    d'un tag à l'autre à une date donnée sans rétropoler l'historique, donc
    ne garder que le premier tag "gagnant" tronquerait la série. On combine
    tout puis on dédoublonne sur (start,end) en gardant le dépôt le plus
    récent (dates ISO → tri lexical = tri chrono).
    """
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


def _rolling_ttm(sorted_ends, values_by_end):
    """Somme glissante sur les 4 derniers trimestres (lisse la saisonnalité)."""
    ttm = {}
    for i, end in enumerate(sorted_ends):
        if i < 3:
            continue
        window = sorted_ends[i - 3:i + 1]
        ttm[end] = sum(values_by_end[e] for e in window)
    return ttm


def _build_company(name, cik):
    per_metric = {}
    for metric in FALLBACK_TAGS:
        recs = _fetch_metric(cik, metric)
        if not recs:
            print(f"    [!] {name}: aucune donnée pour {metric}")
            return None
        per_metric[metric] = _quarterize(recs)

    common_ends = sorted(set.intersection(*(set(d) for d in per_metric.values())))
    if len(common_ends) < 4:
        print(f"    [!] {name}: historique trimestriel insuffisant ({len(common_ends)} trimestres communs)")
        return None

    ttm = {m: _rolling_ttm(common_ends, per_metric[m]) for m in TTM_METRICS}
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
