
import hashlib
import site
import sys
import json
from pathlib import Path

import streamlit as st

# --------------------------------------------------
# 1. Project Configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _ensure_project_venv(project_root: Path) -> None:
    """Fallback to local .venv site-packages when launched from global Python."""
    if sys.prefix != sys.base_prefix:
        return
    venv_dir = project_root / ".venv"
    if not venv_dir.is_dir():
        return
    cfg = venv_dir / "pyvenv.cfg"
    expected_prefix = f"{sys.version_info.major}.{sys.version_info.minor}."
    if cfg.is_file():
        for line in cfg.read_text(encoding="utf-8", errors="ignore").splitlines():
            key, _, val = line.partition("=")
            if key.strip() == "version" and not val.strip().startswith(expected_prefix):
                return
    candidates = [
        venv_dir / "Lib" / "site-packages",
        venv_dir / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages",
    ]
    for site_packages in candidates:
        if site_packages.is_dir() and str(site_packages) not in sys.path:
            site.addsitedir(str(site_packages))


_ensure_project_venv(PROJECT_ROOT)


def _make_progress_callback(progress_bar):
    """Build a progress callback bound to a Streamlit progress bar."""
    def _callback(done: int, total: int, message: str) -> None:
        ratio = min(max(done / total, 0.0), 1.0) if total > 0 else 0.0
        progress_bar.progress(ratio, text=message)
    return _callback


def _select_pdf_page_range(file_bytes: bytes, filename: str, key_prefix: str) -> tuple[tuple[int, int] | None, bool]:
    """Return (page_range, requires_manual_start) for large scanned PDFs."""
    if not filename.lower().endswith(".pdf"):
        return None, False
    from core.document_loader import get_pdf_page_count, pdf_needs_ocr

    total_pages = get_pdf_page_count(file_bytes)
    if total_pages <= 10 or not pdf_needs_ocr(file_bytes):
        return None, False

    st.caption(
        f"Scanned PDF detected ({total_pages} pages). Choose a page range for fast offline OCR or process all pages."
    )
    mode = st.segmented_control(
        "Pages to process",
        ["Page range", "All pages"],
        default="Page range",
        key=f"{key_prefix}_page_mode",
    )
    if mode == "All pages":
        return None, True

    col1, col2 = st.columns(2)
    start_page = int(
        col1.number_input(
            "Start page",
            min_value=1,
            max_value=total_pages,
            value=1,
            step=1,
            key=f"{key_prefix}_start_page",
        )
    )
    end_key = f"{key_prefix}_end_page"
    if end_key in st.session_state and st.session_state[end_key] < start_page:
        st.session_state[end_key] = start_page
    end_page = int(
        col2.number_input(
            "End page",
            min_value=start_page,
            max_value=total_pages,
            value=min(max(start_page + 9, start_page), total_pages),
            step=1,
            key=end_key,
        )
    )
    return (start_page, end_page), True


from core.config import APP_MODULE


# --------------------------------------------------
# 2. Application Configuration
# --------------------------------------------------

MODULES = {
    "document": "Document Intelligence",
    "rag": "RAG Knowledge Assistant",
    "classification": "Classification & Risk",
    "prediction": "Predictive Analytics",
    "workflow": "Workflow Automation",
    "code": "Code Intelligence",
    "loan": "Loan Document Processing"
}

if APP_MODULE not in MODULES:
    st.error(f"Invalid application module: {APP_MODULE}")
    st.stop()


# --------------------------------------------------
# 3. Streamlit Page Configuration
# --------------------------------------------------

st.set_page_config(
    page_title=MODULES[APP_MODULE],
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

module_keys = list(MODULES.keys())
active_module = st.sidebar.selectbox(
    "Active Module",
    options=module_keys,
    index=module_keys.index(APP_MODULE),
    format_func=lambda key: MODULES[key],
    key="active_module_selector",
)

st.title(f"🧠 {MODULES[active_module]}")
st.caption("Powered by the Reusable GenAI Application Framework")

st.divider()


# ==================================================
# 4. DOCUMENT INTELLIGENCE
# ==================================================

if active_module == "document":

    from core.llm import LLMClient
    from core.document_loader import extract_text
    from engines.document_engine import DocumentEngine

    st.subheader("Document Processing")

    uploaded_file = st.file_uploader(
        "Upload your document",
        type=["pdf", "docx", "txt", "md", "csv", "json"]
    )

    if uploaded_file:
        file_bytes = uploaded_file.getvalue()
        page_range, needs_extract_click = _select_pdf_page_range(
            file_bytes, uploaded_file.name, key_prefix="doc"
        )
        range_label = f"{page_range[0]}-{page_range[1]}" if page_range else "all"
        file_key = f"{uploaded_file.name}:{len(file_bytes)}:{hashlib.sha256(file_bytes).hexdigest()}:{range_label}"
        cached_doc = st.session_state.get("extracted_doc_cache")

        if cached_doc and cached_doc.get("key") == file_key:
            document_text = cached_doc["text"]
        else:
            if needs_extract_click and not st.button("Extract PDF Text", type="primary", key="doc_extract_btn"):
                st.stop()
            progress_bar = st.progress(0.0, text="Extracting document text...")
            document_text = extract_text(
                file_bytes,
                uploaded_file.name,
                progress_callback=_make_progress_callback(progress_bar),
                page_range=page_range,
            )
            progress_bar.empty()
            st.session_state["extracted_doc_cache"] = {
                "key": file_key,
                "text": document_text,
            }

        if not document_text.strip():
            st.warning("No text could be extracted from the document.")
            st.stop()

        preview_limit = 50000
        preview_text = document_text[:preview_limit]
        with st.expander("View extracted document text"):
            st.caption(f"Extracted {len(document_text):,} characters" + (" (showing first 50,000)" if len(document_text) > preview_limit else ""))
            st.text_area(
                "Extracted Content",
                preview_text,
                height=250
            )

        operation = st.radio(
            "Select operation",
            ["Summarize Document", "Extract Structured Information"],
            horizontal=True
        )

        if operation == "Summarize Document":

            if st.button("Generate Summary", type="primary"):

                try:
                    progress_bar = st.progress(0.0, text="Analyzing document...")
                    engine = DocumentEngine()
                    result = engine.summarize(
                        document_text,
                        progress_callback=_make_progress_callback(progress_bar),
                    )
                    progress_bar.empty()

                    st.subheader("Document Summary")
                    st.write(result)

                except Exception as e:
                    st.error(f"Processing error: {e}")

        elif operation == "Extract Structured Information":

            fields = st.text_input(
                "Fields to extract (comma separated)",
                "name, date, amount, reference_number"
            )

            if st.button("Extract Information", type="primary"):

                try:
                    field_list = [
                        field.strip()
                        for field in fields.split(",")
                        if field.strip()
                    ]

                    progress_bar = st.progress(0.0, text="Extracting information...")
                    engine = DocumentEngine()
                    result = engine.extract_fields(
                        document_text,
                        field_list,
                        progress_callback=_make_progress_callback(progress_bar),
                    )
                    progress_bar.empty()

                    st.subheader("Extracted Information")
                    st.json(result)

                except Exception as e:
                    st.error(f"Extraction error: {e}")


# ==================================================
# 5. RAG KNOWLEDGE ASSISTANT
# ==================================================

elif active_module == "rag":

    from engines.rag_engine import RAGEngine

    st.subheader("Knowledge Base Management")

    rag = RAGEngine()

    uploaded_file = st.file_uploader(
        "Upload knowledge document",
        type=["pdf", "docx", "txt", "md", "csv", "json"]
    )

    if uploaded_file:
        rag_file_bytes = uploaded_file.getvalue()
        rag_page_range, _ = _select_pdf_page_range(
            rag_file_bytes, uploaded_file.name, key_prefix="rag"
        )

        if st.button("Index Document", type="primary"):

            try:
                progress_bar = st.progress(0.0, text="Extracting and indexing document...")
                chunks = rag.ingest(
                    uploaded_file.name,
                    rag_file_bytes,
                    progress_callback=_make_progress_callback(progress_bar),
                    page_range=rag_page_range,
                )
                progress_bar.empty()

                st.success(
                    f"Successfully indexed {chunks} text chunks."
                )

            except Exception as e:
                st.error(f"Indexing error: {e}")

    st.divider()

    st.subheader("Ask Your Knowledge Base")

    question = st.text_area(
        "Enter your question",
        placeholder="Ask something about your uploaded documents..."
    )

    if st.button("Search and Generate Answer", type="primary"):

        if not question.strip():
            st.warning("Please enter a question.")

        else:

            try:
                with st.spinner("Searching knowledge sources..."):

                    result = rag.ask(question)

                st.subheader("Answer")
                st.write(result["answer"])

                with st.expander("View retrieved source information"):

                    for source in result["sources"]:

                        st.markdown(
                            f"**Source:** {source['source']}"
                        )

                        st.caption(
                            f"Relevance Score: {source['score']:.3f}"
                        )

                        st.write(source["text"])
                        st.divider()

            except Exception as e:
                st.error(f"Query error: {e}")


# ==================================================
# 6. CLASSIFICATION AND RISK ASSESSMENT
# ==================================================

elif active_module == "classification":

    from engines.classification_engine import ClassificationEngine

    st.subheader("Classification and Risk Assessment")

    case_description = st.text_area(
        "Enter case / incident description",
        height=180,
        placeholder="Describe the incident or business request..."
    )

    categories = st.text_input(
        "Available categories",
        "Technical issue, Compliance, Security, Operational, Customer request"
    )

    if st.button("Classify Case", type="primary"):

        if not case_description.strip():
            st.warning("Please enter a case description.")

        else:

            try:
                category_list = [
                    item.strip()
                    for item in categories.split(",")
                    if item.strip()
                ]

                with st.spinner("Classifying case..."):

                    engine = ClassificationEngine()

                    result = engine.classify(
                        case_description,
                        category_list
                    )

                st.subheader("Classification Result")
                st.write(result["result"])

                st.warning(result["notice"])

            except Exception as e:
                st.error(f"Classification error: {e}")

    st.divider()

    st.subheader("Rule-Based Risk Assessment")

    impact = st.slider("Impact", 0, 5, 2)
    likelihood = st.slider("Likelihood", 0, 5, 2)
    urgency = st.slider("Urgency", 0, 5, 2)

    if st.button("Calculate Risk Score"):

        engine = ClassificationEngine()

        result = engine.rule_score({
            "impact": impact,
            "likelihood": likelihood,
            "urgency": urgency
        })

        st.metric(
            "Risk Score",
            f"{result['score']} / 15",
            f"{result['band']} Risk"
        )

        st.caption(result["disclaimer"])


# ==================================================
# 7. PREDICTIVE ANALYTICS
# ==================================================

elif active_module == "prediction":

    import pandas as pd
    from engines.prediction_engine import PredictionEngine

    st.subheader("Demand Forecasting")

    historical_data = st.text_input(
        "Enter historical numeric values (comma separated)",
        "120, 135, 128, 150, 160, 155"
    )

    forecast_periods = st.number_input(
        "Number of future periods",
        min_value=1,
        max_value=24,
        value=3
    )

    if st.button("Generate Forecast", type="primary"):

        try:
            values = [
                float(value.strip())
                for value in historical_data.split(",")
                if value.strip()
            ]

            engine = PredictionEngine()

            result = engine.forecast(
                values,
                int(forecast_periods)
            )

            st.subheader("Forecast Results")

            st.json(result)

            historical = values
            forecast = result["forecast"]

            chart_data = pd.DataFrame({
                "Historical": historical + [None] * len(forecast),
                "Forecast": [None] * len(historical) + forecast
            })

            st.subheader("Forecast Visualization")
            st.line_chart(chart_data)

            st.info(result["warning"])

        except Exception as e:
            st.error(f"Forecasting error: {e}")


# ==================================================
# 8. WORKFLOW AUTOMATION
# ==================================================

elif active_module == "workflow":

    from engines.workflow_engine import WorkflowEngine

    st.subheader("Workflow Automation Engine")

    initial_input = st.text_area(
        "Initial workflow input",
        "New supplier onboarding request"
    )

    default_workflow = [
        {
            "name": "Validate Input",
            "action": "validate_text",
            "params": {}
        },
        {
            "name": "Count Words",
            "action": "word_count",
            "params": {}
        }
    ]

    workflow_definition = st.text_area(
        "Workflow Definition (JSON)",
        json.dumps(default_workflow, indent=4),
        height=250
    )

    if st.button("Execute Workflow", type="primary"):

        try:
            steps = json.loads(workflow_definition)

            if not isinstance(steps, list):
                raise ValueError(
                    "Workflow definition must be a JSON list."
                )

            with st.spinner("Executing workflow..."):

                engine = WorkflowEngine()

                result = engine.run(
                    initial_input,
                    steps
                )

            st.subheader("Workflow Execution Result")

            st.json(result)

        except Exception as e:
            st.error(f"Workflow execution error: {e}")


# ==================================================
# 9. CODE INTELLIGENCE
# ==================================================

elif active_module == "code":

    from engines.code_engine import CodeIntelligenceEngine

    st.subheader("Python Code Intelligence")

    uploaded_file = st.file_uploader(
        "Upload Python source file",
        type=["py"]
    )

    source_code = st.text_area(
        "Or paste Python source code",
        height=250,
        placeholder="Paste your Python code here..."
    )

    if st.button("Analyze Code", type="primary"):

        try:
            engine = CodeIntelligenceEngine()

            if uploaded_file:

                code = uploaded_file.getvalue().decode(
                    "utf-8",
                    errors="replace"
                )

                result = engine.analyze_python(
                    code,
                    uploaded_file.name
                )

            elif source_code.strip():

                result = engine.analyze_python(
                    source_code
                )

            else:
                st.warning("Please upload or enter Python code.")
                st.stop()

            st.subheader("Code Analysis Result")

            if "error" in result:
                st.error(result["error"])
            else:
                col1, col2 = st.columns(2)

                with col1:
                    st.metric(
                        "Functions",
                        len(result["functions"])
                    )

                with col2:
                    st.metric(
                        "Classes",
                        len(result["classes"])
                    )

                st.markdown("### Functions")
                st.json(result["functions"])

                st.markdown("### Classes")
                st.json(result["classes"])

                st.markdown("### Imports")
                st.json(result["imports"])

        except Exception as e:
            st.error(f"Code analysis error: {e}")


# ==================================================
# 10. LOAN DOCUMENT PROCESSING
# ==================================================

elif active_module == "loan":

    import pandas as pd
    from core.audit import AuditLogger
    from core.privacy import mask_dict_fields
    from modules.loan_processing import (
        load_rules,
        loan_report_pdf,
        process_and_validate_loan_documents,
        re_evaluate_loan_assessment,
        report_json,
    )
    from modules.loan_processing.gemini_extractor import ALLOWED_TYPES

    st.subheader("AI-Driven Loan Application Document Analyzer")
    st.caption(
        "Batch-upload applicant KYC, salary, and loan application documents (PDF, PNG, JPG, WEBP) "
        "to classify documents, highlight key data, detect discrepancies, run credit/identity checks, "
        "apply interactive corrections, and export PDF/JSON reports with audit trails."
    )

    rules = load_rules()
    with st.expander("Configured loan policy rules & required documents"):
        st.json(rules)

    c1, c2, c3 = st.columns(3)
    actor_role = c1.selectbox(
        "Reviewer Role",
        ["Loan Officer", "Underwriter", "Compliance Auditor"],
        key="loan_actor_role",
    )
    use_gemini = c2.toggle(
        "Use Gemini AI extraction",
        value=True,
        key="loan_use_gemini",
        help="Falls back to offline OCR automatically if Gemini is unavailable.",
    )
    mask_pii = c3.toggle(
        "Mask sensitive PII (GDPR / PCI mode)",
        value=False,
        key="loan_mask_pii",
    )
    run_banking_api = st.toggle(
        "Run Banking Credit Bureau & Identity Verification APIs (Simulated)",
        value=True,
        key="loan_run_banking_api",
    )

    uploaded_files = st.file_uploader(
        "Upload loan documents (batch)",
        type=["pdf", "png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key="loan_file_uploader",
    )

    if uploaded_files:
        file_sig = "|".join(
            f"{f.name}:{len(f.getvalue())}:{hashlib.sha256(f.getvalue()).hexdigest()}"
            for f in uploaded_files
        ) + f"|gemini={use_gemini}|banking={run_banking_api}"

        if st.button("Validate Loan Documents", type="primary", key="loan_validate_btn"):
            try:
                audit_logger = AuditLogger(module="loan_processing")
                progress_bar = st.progress(0.0, text="Validating loan documents...")
                report = process_and_validate_loan_documents(
                    uploaded_files,
                    use_gemini=use_gemini,
                    rules=rules,
                    progress_callback=_make_progress_callback(progress_bar),
                    run_banking_api_checks=run_banking_api,
                    actor_role=actor_role,
                    audit_logger=audit_logger,
                )
                progress_bar.empty()
                st.session_state["loan_validation_cache"] = {
                    "key": file_sig,
                    "report": report,
                    "audit_logger": audit_logger,
                    "edit_nonce": 0,
                }
            except Exception as e:
                st.error(f"Loan validation error: {e}")

        cached_loan = st.session_state.get("loan_validation_cache")
        if cached_loan and cached_loan.get("key") == file_sig:
            report = cached_loan["report"]
            audit_logger = cached_loan["audit_logger"]
            docs = report.get("documents", [])
            issues = report.get("mismatch_issues", [])
            missing_docs = report.get("missing_documents", [])
            eligibility = report.get("eligibility", {})
            banking = report.get("banking_checks", {})

            st.divider()
            st.subheader("Validation & Financial Summary")

            overall_status = report.get("overall_status", "REVIEW_REQUIRED")
            if overall_status == "REVIEW_REQUIRED":
                st.warning(f"Overall Status: {overall_status}")
            else:
                st.info(f"Overall Status: {overall_status}")
            st.caption(report.get("notice", ""))

            bureau = banking.get("credit_bureau", {})
            identity = banking.get("identity_verification", {})

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Documents Processed", len(docs))
            m2.metric("Discrepancies / Issues", len(issues))
            m3.metric(
                "Credit Score (Simulated)",
                bureau.get("credit_score") if bureau.get("credit_score") is not None else "N/A",
                bureau.get("risk_band") if bureau.get("credit_score") is not None else None,
            )
            m4.metric("Eligibility Status", eligibility.get("status", "UNKNOWN"))

            if banking:
                b1, b2 = st.columns(2)
                with b1:
                    with st.container(border=True):
                        st.markdown("**Identity Verification API (Simulated)**")
                        st.write(f"Status: `{identity.get('status', 'N/A')}`")
                        st.caption(
                            f"PAN Checked: `{identity.get('pan_checked') or 'None'}` | "
                            f"Aadhaar Last4 Present: `{identity.get('aadhaar_last4_present')}`"
                        )
                with b2:
                    with st.container(border=True):
                        st.markdown("**Credit Bureau Scoring API (Simulated)**")
                        st.write(
                            f"Score: `{bureau.get('credit_score', 'N/A')}` | "
                            f"Band: `{bureau.get('risk_band', 'N/A')}`"
                        )
                        st.caption(
                            f"Delinquencies (12m): `{bureau.get('delinquencies_12m', 'N/A')}` | "
                            f"Active Accounts: `{bureau.get('active_accounts', 'N/A')}`"
                        )

            st.markdown("### Extracted Key Data & Interactive Corrections")
            if mask_pii:
                st.caption("PII masking is active; identity columns are read-only until PII masking is turned off.")

            doc_rows = []
            for doc in docs:
                raw_fields = doc.get("fields") or {}
                shown = mask_dict_fields(raw_fields) if mask_pii else raw_fields
                doc_rows.append({
                    "Filename": doc.get("filename"),
                    "Document Type": doc.get("document_type"),
                    "Method": doc.get("extraction_method"),
                    "Name": shown.get("name") or "",
                    "DOB": shown.get("date_of_birth") or "",
                    "PAN": shown.get("pan_number") or "",
                    "Aadhaar Last4": shown.get("aadhaar_last4") or "",
                    "Net Salary (INR)": float(raw_fields["net_monthly_salary"]) if raw_fields.get("net_monthly_salary") is not None else None,
                    "Existing EMI (INR)": float(raw_fields["existing_emi"]) if raw_fields.get("existing_emi") is not None else None,
                    "Requested Loan (INR)": float(raw_fields["requested_loan_amount"]) if raw_fields.get("requested_loan_amount") is not None else None,
                    "Tenure (Months)": int(raw_fields["requested_tenure_months"]) if raw_fields.get("requested_tenure_months") is not None else None,
                })

            disabled_cols = ["Filename", "Method"]
            if mask_pii:
                disabled_cols.extend(["DOB", "PAN", "Aadhaar Last4"])

            editor_key = f"loan_editor_{cached_loan.get('edit_nonce', 0)}"
            edited_df = st.data_editor(
                pd.DataFrame(doc_rows),
                key=editor_key,
                hide_index=True,
                disabled=disabled_cols,
                column_config={
                    "Document Type": st.column_config.SelectboxColumn("Document Type", options=ALLOWED_TYPES),
                    "Net Salary (INR)": st.column_config.NumberColumn("Net Salary (INR)", min_value=0.0, format="%.2f"),
                    "Existing EMI (INR)": st.column_config.NumberColumn("Existing EMI (INR)", min_value=0.0, format="%.2f"),
                    "Requested Loan (INR)": st.column_config.NumberColumn("Requested Loan (INR)", min_value=0.0, format="%.2f"),
                    "Tenure (Months)": st.column_config.NumberColumn("Tenure (Months)", min_value=1, step=1),
                },
                alt="Editable table of extracted loan document fields for interactive corrections",
            )

            if st.button("Apply Corrections & Re-Validate", key="loan_apply_edits_btn"):
                updated_docs = []
                changed_count = 0
                for idx, doc in enumerate(docs):
                    row = edited_df.iloc[idx]
                    new_fields = dict(doc.get("fields") or {})
                    new_type = str(row["Document Type"])
                    changed_fields = []
                    if new_type != doc.get("document_type"):
                        changed_fields.append("document_type")

                    field_map = {
                        "name": row["Name"] or None,
                        "net_monthly_salary": None if pd.isna(row["Net Salary (INR)"]) else float(row["Net Salary (INR)"]),
                        "existing_emi": None if pd.isna(row["Existing EMI (INR)"]) else float(row["Existing EMI (INR)"]),
                        "requested_loan_amount": None if pd.isna(row["Requested Loan (INR)"]) else float(row["Requested Loan (INR)"]),
                        "requested_tenure_months": None if pd.isna(row["Tenure (Months)"]) else int(row["Tenure (Months)"]),
                    }
                    if not mask_pii:
                        field_map["date_of_birth"] = row["DOB"] or None
                        field_map["pan_number"] = row["PAN"] or None
                        field_map["aadhaar_last4"] = row["Aadhaar Last4"] or None

                    for f_key, f_val in field_map.items():
                        if new_fields.get(f_key) != f_val:
                            new_fields[f_key] = f_val
                            changed_fields.append(f_key)

                    if changed_fields:
                        changed_count += 1
                        audit_logger.record(
                            action="INTERACTIVE_CORRECTION",
                            actor_role=actor_role,
                            target=doc.get("filename", ""),
                            status="UPDATED",
                            details={"fields_modified": changed_fields},
                        )

                    updated_docs.append({
                        **doc,
                        "document_type": new_type,
                        "fields": new_fields,
                        "extraction_method": (
                            f"{doc.get('extraction_method')} (Edited)"
                            if changed_fields and "(Edited)" not in str(doc.get("extraction_method"))
                            else doc.get("extraction_method")
                        ),
                    })

                if changed_count == 0:
                    st.info("No field changes detected.")
                else:
                    re_evaluated = re_evaluate_loan_assessment(
                        documents=updated_docs,
                        rules=rules,
                        run_banking_api_checks=run_banking_api,
                        actor_role=actor_role,
                        audit_logger=audit_logger,
                    )
                    st.session_state["loan_validation_cache"] = {
                        "key": file_sig,
                        "report": re_evaluated,
                        "audit_logger": audit_logger,
                        "edit_nonce": cached_loan.get("edit_nonce", 0) + 1,
                    }
                    st.rerun()

            st.markdown("### Document Completeness & Discrepancy Detection")
            if missing_docs:
                st.warning(f"Missing required document types: {', '.join(missing_docs)}")
            else:
                st.success("All required document types are present.")

            if issues:
                issue_rows = [
                    {
                        "Field": issue.get("field"),
                        "Status": issue.get("status"),
                        "Severity": issue.get("severity"),
                        "Values Across Documents": json.dumps(issue.get("values", {}), ensure_ascii=False),
                        "Message": issue.get("message"),
                    }
                    for issue in issues
                ]
                st.dataframe(
                    pd.DataFrame(issue_rows),
                    hide_index=True,
                    alt="Cross-document discrepancy, format, and banking check issues",
                )
            else:
                st.success("No cross-document discrepancies or validation issues detected.")

            st.markdown("### Indicative Financial Summary & FOIR Visualization")
            with st.container(border=True):
                elig_status = eligibility.get("status")
                if elig_status in {"INSUFFICIENT_DATA", "INVALID_INPUT"}:
                    missing_inputs = eligibility.get("missing_inputs") or []
                    detail = f" Missing inputs: {', '.join(missing_inputs)}." if missing_inputs else ""
                    st.warning(f"Eligibility status: {elig_status}.{detail}")
                else:
                    e1, e2, e3, e4 = st.columns(4)
                    e1.metric("Monthly Net Income (INR)", f"{eligibility.get('monthly_net_income_inr', 0):,.2f}")
                    e2.metric("Proposed EMI (INR)", f"{eligibility.get('proposed_emi_inr', 0):,.2f}")
                    e3.metric(
                        "FOIR (%)",
                        f"{eligibility.get('foir_percent', 0):.2f}%",
                        f"Max {eligibility.get('maximum_foir_percent', 0)}%",
                    )
                    e4.metric(
                        "Indicative Max Loan (INR)",
                        f"{eligibility.get('indicative_max_loan_amount_inr', 0):,.2f}",
                    )

                    chart_df = pd.DataFrame({
                        "Component": ["Net Monthly Income", "Existing EMI", "Proposed EMI", "Available Headroom"],
                        "Amount (INR)": [
                            eligibility.get("monthly_net_income_inr", 0),
                            eligibility.get("existing_emi_inr", 0),
                            eligibility.get("proposed_emi_inr", 0),
                            eligibility.get("available_emi_headroom_inr", 0),
                        ],
                    })
                    st.bar_chart(
                        chart_df,
                        x="Component",
                        y="Amount (INR)",
                        alt="Monthly income versus existing EMI, proposed EMI, and available EMI headroom",
                    )

                    st.caption(
                        f"Rule checks — Income passed: {eligibility.get('income_rule_passed')} | "
                        f"Tenure passed: {eligibility.get('tenure_rule_passed')} | "
                        f"FOIR passed: {eligibility.get('foir_rule_passed')} | "
                        f"Credit Score passed: {eligibility.get('credit_score_rule_passed')}"
                    )
                    if eligibility.get("disclaimer"):
                        st.caption(eligibility["disclaimer"])

            with st.expander("View detailed extracted fields & warnings per document"):
                for doc in docs:
                    fields_view = mask_dict_fields(doc.get("fields") or {}) if mask_pii else (doc.get("fields") or {})
                    st.markdown(f"**{doc.get('filename')}** (`{doc.get('document_type')}` via `{doc.get('extraction_method')}`)")
                    if doc.get("warnings"):
                        for warn in doc["warnings"]:
                            st.warning(warn)
                    st.json(fields_view)

            with st.expander("View processing audit trail"):
                audit_events = report.get("audit_trail", [])
                if audit_events:
                    st.dataframe(
                        pd.DataFrame(audit_events),
                        hide_index=True,
                        alt="Timestamped audit trail of document extraction, banking checks, and corrections",
                    )
                else:
                    st.caption("No audit events recorded yet.")

            with st.container(horizontal=True):
                st.download_button(
                    "Download PDF Report",
                    data=loan_report_pdf(report, mask_pii=mask_pii),
                    file_name="loan_validation_report.pdf",
                    mime="application/pdf",
                    key="loan_download_pdf_btn",
                )
                st.download_button(
                    "Download JSON Report",
                    data=report_json(report, mask_pii=mask_pii),
                    file_name="loan_validation_report.json",
                    mime="application/json",
                    key="loan_download_report_btn",
                )


# ==================================================
# 11. FOOTER
# ==================================================

st.divider()

st.caption(
    f"GenAI Reusable Framework | Active Module: {MODULES[active_module]}"
)
