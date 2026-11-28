import hashlib
from typing import Any

from core.privacy import mask_identifier
from core.validation import ValidationIssue
from .validators import normalize_pan, validate_pan_format


def verify_identity(
    pan_number: str | None,
    aadhaar_last4: str | None,
    applicant_name: str | None,
    date_of_birth: str | None,
) -> dict[str, Any]:
    """Simulated NSDL PAN & UIDAI eKYC verification adapter for banking prototype."""
    pan_valid = validate_pan_format(pan_number)
    has_aadhaar = bool(aadhaar_last4 and str(aadhaar_last4).strip().isdigit() and len(str(aadhaar_last4).strip()) == 4)
    has_name = bool(applicant_name and str(applicant_name).strip())

    if pan_valid is False:
        status = "FAILED_INVALID_PAN"
        verified = False
    elif pan_valid and has_aadhaar and has_name:
        status = "VERIFIED"
        verified = True
    elif (pan_valid or has_aadhaar) and has_name:
        status = "PARTIAL_KYC"
        verified = False
    else:
        status = "INSUFFICIENT_KYC"
        verified = False

    return {
        "service": "Identity Verification API (Simulated)",
        "mode": "SIMULATED_SANDBOX_API",
        "status": status,
        "verified": verified,
        "pan_checked": mask_identifier(normalize_pan(pan_number), 4) if pan_number else None,
        "aadhaar_last4_present": has_aadhaar,
        "dob_present": bool(date_of_birth),
    }


def fetch_credit_bureau_score(
    pan_number: str | None,
    applicant_name: str | None = None,
) -> dict[str, Any]:
    """Simulated CIBIL/Experian credit bureau scoring adapter for banking prototype."""
    norm_pan = normalize_pan(pan_number)
    if not norm_pan or validate_pan_format(norm_pan) is False:
        return {
            "service": "Credit Bureau API (Simulated)",
            "mode": "SIMULATED_SANDBOX_API",
            "status": "UNAVAILABLE",
            "credit_score": None,
            "risk_band": "UNKNOWN",
            "delinquencies_12m": None,
            "active_accounts": None,
        }

    # Deterministic synthetic score (600-840) unless PAN starts with 'LOWSC' for testing risk flows.
    if norm_pan.startswith("LOWSC"):
        score = 595
        delinquencies = 2
    else:
        digest = int(hashlib.sha256(f"{norm_pan}:{(applicant_name or '').strip().upper()}".encode("utf-8")).hexdigest()[:8], 16)
        score = 680 + (digest % 161)
        delinquencies = 0

    if score >= 750:
        band = "PRIME"
    elif score >= 650:
        band = "NEAR_PRIME"
    else:
        band = "SUBPRIME"

    return {
        "service": "Credit Bureau API (Simulated)",
        "mode": "SIMULATED_SANDBOX_API",
        "status": "RETRIEVED",
        "credit_score": score,
        "risk_band": band,
        "delinquencies_12m": delinquencies,
        "active_accounts": 1 + (score % 4),
    }


def run_banking_checks(
    merged_fields: dict[str, Any],
    minimum_credit_score: int = 650,
) -> tuple[dict[str, Any], list[ValidationIssue]]:
    """Run identity verification and credit bureau checks and return issues if any."""
    pan = merged_fields.get("pan_number")
    aadhaar_last4 = merged_fields.get("aadhaar_last4")
    name = merged_fields.get("name")
    dob = merged_fields.get("date_of_birth")

    identity = verify_identity(pan, aadhaar_last4, name, dob)
    bureau = fetch_credit_bureau_score(pan, name)

    issues: list[ValidationIssue] = []
    if identity["status"] == "FAILED_INVALID_PAN":
        issues.append(ValidationIssue(
            field="identity_verification",
            status="FAILED",
            values={"pan": str(pan or "")},
            message="Identity verification failed due to invalid PAN format.",
            severity="HIGH",
        ))
    score = bureau.get("credit_score")
    if score is not None and score < minimum_credit_score:
        issues.append(ValidationIssue(
            field="credit_score",
            status="BELOW_THRESHOLD",
            values={"credit_score": str(score), "minimum_required": str(minimum_credit_score)},
            message=f"Credit score ({score}) is below configured minimum ({minimum_credit_score}).",
            severity="HIGH",
        ))

    return {"identity_verification": identity, "credit_bureau": bureau}, issues
