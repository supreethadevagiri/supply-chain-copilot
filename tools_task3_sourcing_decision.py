"""
Task 3 -- Sourcing Decision
Once a disruption is confirmed (Task 2's job), this checks whether
switching to the backup supplier is actually advisable: contract
compliance, the backup origin's deforestation/compliance exposure
(Trase.earth), payment timing, and overall sourcing concentration.
Does NOT suggest or compare backup suppliers -- that's Task 2's job;
this only evaluates the switch once a backup is already on the table.

Independent from Task 1 and Task 2's files by design -- only shares
real_data_sources.py (the external API layer), plus its own Salesforce
connection (systems/task3_salesforce.py).
"""

from real_data_sources import get_trase_deforestation_exposure
from systems.task3_salesforce import get_supplier_contracts, get_purchase_history

SUPPLIER_ORIGIN = {
    "Minas Gerais Cooperative": "Minas Gerais",
    "Sao Paulo Cooperative (backup)": "Sao Paulo",
}



def _find_contract(contracts, supplier_name):
    """Case/whitespace-insensitive match -- the LLM calling this tool
    may not reproduce the exact Salesforce record name verbatim."""
    target = supplier_name.strip().lower()
    for c in contracts:
        if c["supplier"].strip().lower() == target:
            return c
    return None

def check_contract_compliance(current_supplier: str, backup_supplier: str) -> dict:
    contracts = get_supplier_contracts()["contracts"]
    current = _find_contract(contracts, current_supplier)
    backup = _find_contract(contracts, backup_supplier)

    if current is None:
        return {
            "can_switch": None,
            "reasoning": f"No contract on file for '{current_supplier}' -- cannot assess compliance.",
        }

    blockers = []
    if current["exclusivity"]:
        blockers.append("current contract has an exclusivity clause")
    if current["minimum_volume_clause_bags_per_quarter"] > 0:
        blockers.append(
            f"current contract requires a minimum {current['minimum_volume_clause_bags_per_quarter']} "
            f"bags/quarter -- switching away mid-quarter may breach this"
        )

    can_switch = len(blockers) == 0
    reasoning = (
        "No contractual blockers -- free to switch." if can_switch
        else f"Switching may breach the current contract: {'; '.join(blockers)}."
    )

    return {
        "can_switch": can_switch,
        "current_contract": current,
        "backup_contract": backup,
        "reasoning": reasoning,
    }


def check_backup_compliance(backup_supplier: str) -> dict:
    origin = SUPPLIER_ORIGIN.get(backup_supplier)
    if origin is None:
        return {
            "origin_region": None,
            "compliant": None,
            "reasoning": f"No known growing region on file for '{backup_supplier}'.",
        }

    exposure = get_trase_deforestation_exposure(origin)
    flagged = bool(exposure.get("deforestation_risk_flag"))
    return {
        "origin_region": origin,
        "compliant": not flagged,
        "trase_data": exposure,
        "reasoning": (
            f"{origin} is flagged for deforestation exposure -- backup sourcing here "
            f"carries EUDR compliance risk." if flagged else
            f"{origin} shows no deforestation exposure flag -- backup sourcing here "
            f"appears EUDR-compliant."
        ),
    }


def check_payment_timing(backup_supplier: str) -> dict:
    contracts = get_supplier_contracts()["contracts"]
    backup = _find_contract(contracts, backup_supplier)
    if backup is None:
        return {
            "payment_terms": None,
            "requires_upfront_cash": None,
            "reasoning": f"No contract on file for '{backup_supplier}' -- cannot assess payment timing.",
        }

    terms = backup["payment_terms"]
    requires_upfront = "upfront" in terms.lower() if terms else False
    return {
        "payment_terms": terms,
        "requires_upfront_cash": requires_upfront,
        "reasoning": (
            f"Backup supplier's terms ({terms}) require upfront cash -- factor this into "
            f"the switch decision." if requires_upfront else
            f"Backup supplier's terms ({terms}) don't require upfront cash."
        ),
    }


def check_sourcing_concentration() -> dict:
    purchases = get_purchase_history()["purchases"]
    total_bags = sum(p["bags_purchased"] for p in purchases)
    by_region = {}
    for p in purchases:
        by_region[p["origin_region"]] = by_region.get(p["origin_region"], 0) + p["bags_purchased"]

    concentration = {
        region: round(bags / total_bags * 100, 1)
        for region, bags in by_region.items()
    } if total_bags > 0 else {}

    top_region = max(concentration, key=concentration.get) if concentration else None
    top_pct = concentration.get(top_region, 0)
    high_concentration = top_pct >= 70

    if high_concentration:
        note = "a concerning concentration; diversifying beyond a one-time backup switch is worth considering."
    else:
        note = "a reasonably diversified sourcing base."
    reasoning = f"{top_pct}% of purchases come from {top_region} -- {note}"

    return {
        "total_bags_purchased": total_bags,
        "concentration_by_region": concentration,
        "top_region": top_region,
        "top_region_pct": top_pct,
        "high_concentration_risk": high_concentration,
        "reasoning": reasoning,
    }


def get_sourcing_decision(current_supplier: str = "Minas Gerais Cooperative",
                           backup_supplier: str = "Sao Paulo Cooperative (backup)") -> dict:
    contract = check_contract_compliance(current_supplier, backup_supplier)
    compliance = check_backup_compliance(backup_supplier)
    payment = check_payment_timing(backup_supplier)
    concentration = check_sourcing_concentration()

    recommend_switch = bool(
        contract.get("can_switch") and compliance.get("compliant")
    )

    summary = (
        f"Switching from {current_supplier} to {backup_supplier}: "
        f"{'recommended' if recommend_switch else 'NOT recommended without further review'}. "
        f"{contract['reasoning']} {compliance['reasoning']} {payment['reasoning']} {concentration['reasoning']}"
    )

    return {
        "current_supplier": current_supplier,
        "backup_supplier": backup_supplier,
        "contract_compliance": contract,
        "backup_compliance": compliance,
        "payment_timing": payment,
        "sourcing_concentration": concentration,
        "recommend_switch": recommend_switch,
        "summary": summary,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_sourcing_decision(), indent=2, default=str))


def get_sourcing_decision_hypothetical(override_contract_ok: bool = None, override_deforestation_ok: bool = None) -> dict:
    """Answers a 'what if' question about sourcing WITHOUT changing any
    real data -- takes the real current contract and deforestation
    findings, hypothetically overrides ONE or both, and recalculates
    the real recommend_switch rule exactly as get_sourcing_decision()
    does. Nothing is written anywhere."""
    real = get_sourcing_decision()

    hypothetical_can_switch = (
        override_contract_ok if override_contract_ok is not None
        else real["contract_compliance"].get("can_switch")
    )
    hypothetical_compliant = (
        override_deforestation_ok if override_deforestation_ok is not None
        else real["backup_compliance"].get("compliant")
    )
    hypothetical_recommend_switch = bool(hypothetical_can_switch and hypothetical_compliant)

    changes = []
    if override_contract_ok is not None:
        changes.append(f"contract compliance set to {'OK' if override_contract_ok else 'blocking'}")
    if override_deforestation_ok is not None:
        changes.append(f"deforestation compliance set to {'OK' if override_deforestation_ok else 'blocking'}")

    return {
        "scenario": f"Hypothetical: {', '.join(changes) if changes else 'no changes specified'}.",
        "real_current_recommend_switch": real["recommend_switch"],
        "hypothetical_recommend_switch": hypothetical_recommend_switch,
        "hypothetical_can_switch": hypothetical_can_switch,
        "hypothetical_compliant": hypothetical_compliant,
        "note": "This is a hypothetical calculation only -- no real data was changed.",
    }
