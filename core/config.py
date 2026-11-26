import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
for directory in (UPLOAD_DIR, KNOWLEDGE_DIR):
    directory.mkdir(parents=True, exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))

APP_MODULE = os.getenv(
    "APP_MODULE",
    "document"
).strip().lower()

SUPPORTED_MODULES = {
    "document",
    "rag",
    "classification",
    "prediction",
    "workflow",
    "code"
}

if APP_MODULE not in SUPPORTED_MODULES:
    raise ValueError(f"Invalid APP_MODULE: {APP_MODULE}")
