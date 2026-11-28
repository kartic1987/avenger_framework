import json
from typing import Callable

from .eligibility import assess_eligibility, load_rules
from .extractor import process_uploaded_file
from .validators import (
    check_document_completeness,
    compare_documents,
    validate_document_fields,
)


def _merge_fields_by_priority(documents, preferred_types: tuple[str, ...]) -> dict:
    """Merge non-empty fields, prioritizing preferred document types first."""
    merged: dict = {}
    ordered = sorted(
        documents,
        key=lambda d: (0 if d.document_type in preferred_types else 1),
    )
    for doc in ordered:
        for key, value in (doc.fields or {}).items():
            if key not in merged and value not in (None, ""):
                merged[key] = value
    return merged


def build_assessment(documents, issues, missing_documents, eligibility):
    eligibility_needs_review = eligibility.get("status") in {
        "INSUFFICIENT_DATA",
        "INVALID_INPUT",
        "OUTSIDE_CONFIGURED_LIMITS",
    }
    return {
        "documents": [d.to_dict() for d in documents],
        "mismatch_issues": [i.to_dict() for i in issues],
        "missing_documents": missing_documents,
        "eligibility": eligibility,
        "overall_status": (
            "REVIEW_REQUIRED" if issues or missing_documents or eligibility_needs_review
            else "ASSESSMENT_REQUIRES_HUMAN_REVIEW"
        ),
        "notice": (
            "This report is decision support only. It does not authenticate documents "
            "or approve/reject a loan. Verify source documents and apply approved lender policy."
        )
    }


def process_and_validate_loan_documents(
    uploaded_files,
    use_gemini: bool = True,
    rules: dict | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict:
    """Process multiple uploaded loan documents and return a full validation assessment."""
    if not uploaded_files:
        raise ValueError("Please upload at least one loan document.")

    loaded_rules = rules or load_rules()
    required_types = loaded_rules.get(
        "required_document_types",
        ["PAN", "AADHAAR", "SALARY_SLIP", "LOAN_APPLICATION"],
    )

    documents = []
    total = len(uploaded_files)
    for idx, uploaded_file in enumerate(uploaded_files, start=1):
        if progress_callback:
            progress_callback(idx - 1, total, f"Extracting {uploaded_file.name} ({idx}/{total})...")
        documents.append(process_uploaded_file(uploaded_file, use_gemini=use_gemini))
        if progress_callback:
            progress_callback(idx, total, f"Processed {uploaded_file.name} ({idx}/{total})")

    issues = compare_documents(documents) + validate_document_fields(documents)
    missing_documents = check_document_completeness(documents, required_types)

    application_fields = _merge_fields_by_priority(documents, ("LOAN_APPLICATION",))
    salary_fields = _merge_fields_by_priority(documents, ("SALARY_SLIP",))
    eligibility = assess_eligibility(application_fields, salary_fields, loaded_rules)

    return build_assessment(documents, issues, missing_documents, eligibility)


def report_json(report):
    return json.dumps(report, indent=2, ensure_ascii=False, default=str)
