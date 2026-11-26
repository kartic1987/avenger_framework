# GenAI Reusable Application Framework

A modular Python + Streamlit starter project for the six reusable solution categories:
1. Document intelligence
2. RAG knowledge assistant
3. Classification and risk assessment
4. Predictive analytics
5. Workflow automation
6. Code intelligence

## Requirements
- Python 3.10 or newer
- Optional: Google Gemini API key

## Setup - Windows
Execute .\run.bat

## Restart (Windows)
Use the project virtual environment so all installed dependencies (such as `pypdf`) are used:
```powershell
.\.venv\Scripts\python.exe -m streamlit run app/Home.py
```
Or activate `.venv` first (`.\.venv\Scripts\Activate.ps1`), then run `streamlit run app/Home.py`.

Add `GEMINI_API_KEY` to `.env` to enable Gemini responses. If no key is configured, the framework runs in demo mode with deterministic local responses. Do not use demo mode for production decisions.

## Modules
- `core/llm.py`: Gemini adapter and safe demo fallback
- `core/guardrails.py`: input checks and output grounding helpers
- `core/document_loader.py`: TXT, MD, PDF (digital text + offline OCR via PyMuPDF and RapidOCR), DOCX, CSV and JSON extraction
- `engines/document_engine.py`: extraction, summarization and structured output
- `engines/rag_engine.py`: local TF-IDF retrieval with source references
- `engines/classification_engine.py`: category/risk scoring and explanation
- `engines/prediction_engine.py`: baseline numeric forecasting and narrative
- `engines/workflow_engine.py`: configurable sequential workflow execution
- `engines/code_engine.py`: Python AST-based code inventory and documentation
- `app/Home.py`: Streamlit user interface

## Important limitations
This is a complete runnable MVP/framework, not a production-certified banking, legal, insurance, medical, or compliance system.
- Risk scores are illustrative rules and must be reviewed by domain experts.
- The prediction module is a simple baseline, not a validated forecasting model.
- RAG uses local TF-IDF retrieval. For large corpora, replace it with a vector database and embeddings.
- PDF extraction runs offline OCR (PyMuPDF + RapidOCR) on pages without embedded text; large scanned books can take a few minutes to process on CPU.
- The code intelligence module parses Python source only. Other languages need language-specific parsers.
- Add authentication, authorization, encryption, secrets management, monitoring, rate limiting, human approval and security testing before deployment.

## Add a knowledge document
Upload documents from the RAG page. They are stored under `data/knowledge/` and indexed locally. Supported formats: TXT, MD, PDF, DOCX, CSV, JSON.

## Run tests
```bash
python -m unittest discover -s tests -v
```


## Common error troubleshoot

`ModuleNotFoundError: No module named 'pypdf'`:
This happens if `streamlit run app/Home.py` runs with your global Python instead of `.venv`. Either install dependencies into `.venv` and run using `.venv`:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app/Home.py
```