
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
    "code": "Code Intelligence"
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
    initial_sidebar_state="collapsed"
)

st.title(f"🧠 {MODULES[APP_MODULE]}")
st.caption("Powered by the Reusable GenAI Application Framework")

st.divider()


# ==================================================
# 4. DOCUMENT INTELLIGENCE
# ==================================================

if APP_MODULE == "document":

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

elif APP_MODULE == "rag":

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

elif APP_MODULE == "classification":

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

elif APP_MODULE == "prediction":

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

elif APP_MODULE == "workflow":

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

elif APP_MODULE == "code":

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
# 10. FOOTER
# ==================================================

st.divider()

st.caption(
    f"GenAI Reusable Framework | Active Module: {MODULES[APP_MODULE]}"
)
