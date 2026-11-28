import re
from datetime import date, datetime
from rapidfuzz.fuzz import ratio
from .models import ValidationIssue

COMPARABLE_FIELDS = ["name", "date_of_birth", "pan_number"]

def normalize_name(value):
    if value is None:
        return ""
    return re.sub(r"[^A-Z0-9 ]", "", str(value).upper()).strip()

def normalize_date(value):
    if value is None:
        return ""
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    return raw.upper()

def normalize_pan(value):
    return re.sub(r"\s+", "", str(value or "").upper())

def _field_value(doc, field):
    return (doc.fields or {}).get(field)

def compare_documents(documents):
    issues = []
    for field in COMPARABLE_FIELDS:
        values = {}
        for doc in documents:
            value = _field_value(doc, field)
            if value not in (None, ""):
                values[doc.filename] = str(value)
        if len(values) < 2:
            continue

        normalized = []
        for value in values.values():
            if field == "name":
                normalized.append(normalize_name(value))
            elif field == "date_of_birth":
                normalized.append(normalize_date(value))
            else:
                normalized.append(normalize_pan(value))

        if field == "name":
            scores = [ratio(normalized[i], normalized[j])
                      for i in range(len(normalized)) for j in range(i + 1, len(normalized))]
            if scores and min(scores) < 95:
                issues.append(ValidationIssue(
                    field, "POSSIBLE_MISMATCH", values,
                    f"Name values differ (lowest similarity {min(scores)}%). Manual review required."
                ))
        elif len(set(normalized)) > 1:
            issues.append(ValidationIssue(
                field, "MISMATCH", values,
                f"{field.replace('_', ' ').title()} differs across documents."
            ))
    return issues

def check_document_completeness(documents, required_types):
    present = {d.document_type for d in documents}
    return sorted(set(required_types) - present)

def validate_pan_format(pan):
    if not pan:
        return None
    return bool(re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", normalize_pan(pan)))

def parse_date(value):
    normalized = normalize_date(value)
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        return None


def validate_document_fields(documents):
    """Validate extracted field formats (PAN, DOB) across uploaded documents."""
    issues = []
    invalid_pans = {}
    invalid_dobs = {}

    for doc in documents:
        pan = _field_value(doc, "pan_number")
        if pan not in (None, "") and validate_pan_format(pan) is False:
            invalid_pans[doc.filename] = str(pan)

        dob = _field_value(doc, "date_of_birth")
        if dob not in (None, "") and parse_date(dob) is None:
            invalid_dobs[doc.filename] = str(dob)

    if invalid_pans:
        issues.append(ValidationIssue(
            "pan_number",
            "INVALID_FORMAT",
            invalid_pans,
            "PAN number does not match expected format (AAAAA9999A).",
        ))
    if invalid_dobs:
        issues.append(ValidationIssue(
            "date_of_birth",
            "INVALID_FORMAT",
            invalid_dobs,
            "Date of birth could not be parsed cleanly. Verify against source document.",
        ))
    return issues
