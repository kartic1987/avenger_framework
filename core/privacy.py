import re
from typing import Any, Iterable

DEFAULT_SENSITIVE_FIELDS = frozenset({
    "pan_number",
    "aadhaar_last4",
    "voter_id",
    "phone_last4",
    "date_of_birth",
    "address",
    "employee_id",
})


def mask_identifier(value: Any, visible_tail: int = 4) -> str:
    """Mask an identifier leaving only the trailing characters visible."""
    if value in (None, ""):
        return ""
    raw = str(value).strip()
    if len(raw) <= visible_tail:
        return "*" * len(raw)
    return ("*" * (len(raw) - visible_tail)) + raw[-visible_tail:]


def mask_dict_fields(
    fields: dict[str, Any],
    sensitive_keys: Iterable[str] = DEFAULT_SENSITIVE_FIELDS,
) -> dict[str, Any]:
    """Return a copy of fields with sensitive values masked for GDPR/PCI-safe display."""
    sensitive = set(sensitive_keys)
    masked: dict[str, Any] = {}
    for key, value in (fields or {}).items():
        if key == "ocr_text" and isinstance(value, str):
            masked[key] = redact_pii_text(value)
        elif key in sensitive and value not in (None, ""):
            if key == "date_of_birth":
                raw = str(value).strip()
                masked[key] = f"****-**-{raw[-2:]}" if len(raw) >= 4 else "****"
            elif key == "address":
                masked[key] = "[REDACTED ADDRESS]"
            else:
                masked[key] = mask_identifier(value, visible_tail=4)
        else:
            masked[key] = value
    return masked


def redact_pii_text(text: str) -> str:
    """Redact common Indian/global PII patterns (Aadhaar, PAN, phone, email) in free text."""
    if not text:
        return ""
    redacted = re.sub(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "XXXX-XXXX-XXXX", text)
    redacted = re.sub(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b", lambda m: mask_identifier(m.group(1), 4), redacted)
    redacted = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]", redacted)
    redacted = re.sub(r"\b(?:\+91[\s-]?)?[6-9]\d{9}\b", "[REDACTED_PHONE]", redacted)
    return redacted
