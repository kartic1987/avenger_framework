from datetime import date
import json
from pathlib import Path

_DEFAULT_RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "loan_rules.json"


def load_rules(path=None):
    resolved = Path(path) if path is not None else _DEFAULT_RULES_PATH
    return json.loads(resolved.read_text(encoding="utf-8"))

def emi(principal, annual_rate_percent, months):
    if principal <= 0 or months <= 0:
        return 0.0
    monthly_rate = annual_rate_percent / 1200
    if monthly_rate == 0:
        return principal / months
    factor = (1 + monthly_rate) ** months
    return principal * monthly_rate * factor / (factor - 1)

def loan_amount_for_emi(monthly_emi, annual_rate_percent, months):
    if monthly_emi <= 0 or months <= 0:
        return 0.0
    monthly_rate = annual_rate_percent / 1200
    if monthly_rate == 0:
        return monthly_emi * months
    factor = (1 + monthly_rate) ** months
    return monthly_emi * (factor - 1) / (monthly_rate * factor)

def assess_eligibility(application_fields, salary_fields, rules):
    """Indicative FOIR calculation. Missing inputs result in INSUFFICIENT_DATA."""
    income = salary_fields.get("net_monthly_salary")
    existing_emi = application_fields.get("existing_emi", 0) or 0
    requested = application_fields.get("requested_loan_amount")
    tenure = application_fields.get("requested_tenure_months") or rules["maximum_tenure_months"]
    rate = rules["default_annual_interest_rate_percent"]

    missing = []
    if income is None: missing.append("net_monthly_salary")
    if requested is None: missing.append("requested_loan_amount")
    if not tenure: missing.append("requested_tenure_months")
    if missing:
        return {"status": "INSUFFICIENT_DATA", "missing_inputs": missing}

    income, existing_emi, requested, tenure = map(float, (income, existing_emi, requested, tenure))
    if income <= 0 or requested <= 0 or tenure <= 0:
        return {"status": "INVALID_INPUT", "missing_inputs": []}

    max_total_emi = income * rules["maximum_foir_percent"] / 100
    available_emi = max(0, max_total_emi - existing_emi)
    proposed_emi = emi(requested, rate, int(tenure))
    foir = ((existing_emi + proposed_emi) / income) * 100
    indicative_max_loan = loan_amount_for_emi(
        available_emi, rate, int(tenure)
    )
    income_ok = income >= rules["minimum_net_monthly_income"]
    tenure_ok = rules["minimum_tenure_months"] <= tenure <= rules["maximum_tenure_months"]
    foir_ok = foir <= rules["maximum_foir_percent"]
    status = "WITHIN_CONFIGURED_LIMITS" if income_ok and tenure_ok and foir_ok else "OUTSIDE_CONFIGURED_LIMITS"

    return {
        "status": status,
        "monthly_net_income_inr": round(income, 2),
        "existing_emi_inr": round(existing_emi, 2),
        "proposed_emi_inr": round(proposed_emi, 2),
        "foir_percent": round(foir, 2),
        "maximum_foir_percent": rules["maximum_foir_percent"],
        "indicative_max_loan_amount_inr": round(indicative_max_loan, 2),
        "requested_loan_amount_inr": round(requested, 2),
        "income_rule_passed": income_ok,
        "tenure_rule_passed": tenure_ok,
        "foir_rule_passed": foir_ok,
        "disclaimer": "Indicative calculation only; not a credit decision or loan approval."
    }
