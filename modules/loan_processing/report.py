from typing import Any, Callable

from core.audit import AuditLogger
from core.privacy import mask_dict_fields
from core.reporting import build_pdf_report, report_to_json

from .eligibility import assess_eligibility, load_rules
from .extractor import process_uploaded_file
from .integrations import run_banking_checks
from .models import ExtractedDocument
from .validators import (
    check_document_completeness,
    compare_documents,
    validate_document_fields,
)


def _merge_fields_by_priority(documents, preferred_types: tuple[str, ...]) -> dict[str, Any]:
    """Merge non-empty fields, prioritizing preferred document types first."""
    merged: dict[str, Any] = {}
    ordered = sorted(
        documents,
        key=lambda d: (0 if d.document_type in preferred_types else 1),
    )
    for doc in ordered:
        for key, value in (doc.fields or {}).items():
            if key not in merged and value not in (None, ""):
                merged[key] = value
    return merged


def build_assessment(
    documents,
    issues,
    missing_documents,
    eligibility,
    banking_checks: dict[str, Any] | None = None,
    audit_trail: list[dict[str, Any]] | None = None,
):
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
        "banking_checks": banking_checks or {},
        "audit_trail": audit_trail or [],
        "overall_status": (
            "REVIEW_REQUIRED" if issues or missing_documents or eligibility_needs_review
            else "ASSESSMENT_REQUIRES_HUMAN_REVIEW"
        ),
        "notice": (
            "This report is decision support only. It does not authenticate documents "
            "or approve/reject a loan. Verify source documents and apply approved lender policy."
        ),
    }


def _coerce_extracted_doc(item: ExtractedDocument | dict[str, Any]) -> ExtractedDocument:
    if isinstance(item, ExtractedDocument):
        return item
    return ExtractedDocument(
        filename=item["filename"],
        document_type=item["document_type"],
        fields=dict(item.get("fields") or {}),
        extraction_method=item.get("extraction_method", "Manual/Edited"),
        warnings=list(item.get("warnings") or []),
    )


def re_evaluate_loan_assessment(
    documents,
    rules: dict | None = None,
    run_banking_api_checks: bool = True,
    actor_role: str = "Underwriter",
    audit_logger: AuditLogger | None = None,
) -> dict[str, Any]:
    """Re-run validation, banking API checks, and eligibility after extraction or interactive edits."""
    loaded_rules = rules or load_rules()
    required_types = loaded_rules.get(
        "required_document_types",
        ["PAN", "AADHAAR", "SALARY_SLIP", "LOAN_APPLICATION"],
    )
    doc_objects = [_coerce_extracted_doc(d) for d in documents]

    issues = compare_documents(doc_objects) + validate_document_fields(doc_objects)
    missing_documents = check_document_completeness(doc_objects, required_types)

    merged_all = _merge_fields_by_priority(doc_objects, ("LOAN_APPLICATION", "PAN", "AADHAAR", "SALARY_SLIP"))
    application_fields = _merge_fields_by_priority(doc_objects, ("LOAN_APPLICATION",))
    salary_fields = _merge_fields_by_priority(doc_objects, ("SALARY_SLIP",))

    banking_checks: dict[str, Any] = {}
    credit_score = None
    if run_banking_api_checks:
        banking_checks, api_issues = run_banking_checks(
            merged_all,
            minimum_credit_score=int(loaded_rules.get("minimum_credit_score", 650)),
        )
        issues.extend(api_issues)
        credit_score = banking_checks.get("credit_bureau", {}).get("credit_score")
        if audit_logger is not None:
            audit_logger.record(
                action="BANKING_API_CHECKS",
                actor_role=actor_role,
                target=f"{len(doc_objects)} document(s)",
                status="COMPLETED",
                details={
                    "identity_status": banking_checks["identity_verification"]["status"],
                    "credit_score": credit_score,
                },
            )

    eligibility = assess_eligibility(
        application_fields,
        salary_fields,
        loaded_rules,
        credit_score=credit_score,
    )
    if audit_logger is not None:
        audit_logger.record(
            action="VALIDATION_COMPLETED",
            actor_role=actor_role,
            target=f"{len(doc_objects)} document(s)",
            status=eligibility.get("status", "UNKNOWN"),
            details={
                "issue_count": len(issues),
                "missing_documents": missing_documents,
            },
        )

    return build_assessment(
        doc_objects,
        issues,
        missing_documents,
        eligibility,
        banking_checks=banking_checks,
        audit_trail=audit_logger.to_dicts() if audit_logger is not None else [],
    )


def process_and_validate_loan_documents(
    uploaded_files,
    use_gemini: bool = True,
    rules: dict | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    run_banking_api_checks: bool = True,
    actor_role: str = "Loan Officer",
    audit_logger: AuditLogger | None = None,
) -> dict[str, Any]:
    """Process multiple uploaded loan documents and return a full validation assessment."""
    if not uploaded_files:
        raise ValueError("Please upload at least one loan document.")

    logger = audit_logger or AuditLogger(module="loan_processing")
    documents: list[ExtractedDocument] = []
    total = len(uploaded_files)

    for idx, uploaded_file in enumerate(uploaded_files, start=1):
        if progress_callback:
            progress_callback(idx - 1, total, f"Extracting {uploaded_file.name} ({idx}/{total})...")
        doc = process_uploaded_file(uploaded_file, use_gemini=use_gemini)
        documents.append(doc)
        logger.record(
            action="DOCUMENT_EXTRACTED",
            actor_role=actor_role,
            target=uploaded_file.name,
            status=doc.document_type,
            details={"method": doc.extraction_method, "warnings": len(doc.warnings)},
        )
        if progress_callback:
            progress_callback(idx, total, f"Processed {uploaded_file.name} ({idx}/{total})")

    return re_evaluate_loan_assessment(
        documents=documents,
        rules=rules,
        run_banking_api_checks=run_banking_api_checks,
        actor_role=actor_role,
        audit_logger=logger,
    )


def report_json(report: dict[str, Any], mask_pii: bool = False) -> str:
    if not mask_pii:
        return report_to_json(report)
    sanitized = dict(report)
    sanitized["documents"] = [
        {**doc, "fields": mask_dict_fields(doc.get("fields") or {})}
        for doc in report.get("documents", [])
    ]
    return report_to_json(sanitized)


def loan_report_pdf(report: dict[str, Any], mask_pii: bool = False) -> bytes:
    """Export the loan validation assessment as a formatted PDF report."""
    elig = report.get("eligibility", {})
    banking = report.get("banking_checks", {})
    bureau = banking.get("credit_bureau", {})
    identity = banking.get("identity_verification", {})

    summary_items = [
        ("Overall Status", str(report.get("overall_status", ""))),
        ("Documents Processed", str(len(report.get("documents", [])))),
        ("Validation Issues", str(len(report.get("mismatch_issues", [])))),
        ("Missing Documents", ", ".join(report.get("missing_documents", [])) or "None"),
        ("Eligibility Status", str(elig.get("status", "UNKNOWN"))),
        ("FOIR (%)", f"{elig.get('foir_percent', 'N/A')}% (Max {elig.get('maximum_foir_percent', 'N/A')}%)"),
        ("Identity API Status", str(identity.get("status", "Not run"))),
        ("Credit Bureau Score", f"{bureau.get('credit_score', 'N/A')} ({bureau.get('risk_band', 'N/A')})"),
    ]

    doc_rows = []
    for doc in report.get("documents", []):
        fields = mask_dict_fields(doc.get("fields") or {}) if mask_pii else (doc.get("fields") or {})
        doc_rows.append([
            doc.get("filename"),
            doc.get("document_type"),
            doc.get("extraction_method"),
            fields.get("name"),
            fields.get("pan_number"),
            fields.get("net_monthly_salary"),
            fields.get("requested_loan_amount"),
        ])

    issue_rows = [
        [
            issue.get("field"),
            issue.get("status"),
            issue.get("severity"),
            issue.get("message"),
        ]
        for issue in report.get("mismatch_issues", [])
    ]

    return build_pdf_report(
        title="Loan Application Validation Report",
        subtitle="AI-Driven Loan Application Document Analyzer",
        summary_items=summary_items,
        tables=[
            ("Extracted Documents", ["Filename", "Type", "Method", "Name", "PAN", "Net Salary", "Req. Loan"], doc_rows),
            ("Discrepancies & Validation Issues", ["Field", "Status", "Severity", "Details"], issue_rows),
        ],
        notice=report.get("notice"),
    )
