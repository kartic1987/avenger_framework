from datetime import date
import re

from core.validation import (
    ValidationIssue,
    check_required_categories,
    compare_records,
    normalize_date,
    normalize_identifier,
    normalize_text,
)

COMPARABLE_FIELDS = ["name", "date_of_birth", "pan_number"]

normalize_name = normalize_text
normalize_pan = normalize_identifier


def _field_value(doc, field):
    return (doc.fields or {}).get(field)


def compare_documents(documents):
    return compare_records(
        records=documents,
        name_getter=lambda doc: doc.filename,
        fields_getter=lambda doc: doc.fields or {},
        exact_fields=("date_of_birth", "pan_number"),
        fuzzy_fields=("name",),
        fuzzy_threshold=95,
    )


def check_document_completeness(documents, required_types):
    return check_required_categories(
        present_categories=(d.document_type for d in documents),
        required_categories=required_types,
    )


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
