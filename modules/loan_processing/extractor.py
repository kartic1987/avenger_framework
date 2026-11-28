from core.structured_extractor import extract_structured_document

from .document_loader import load_document
from .gemini_extractor import ALLOWED_TYPES, EXTRACTION_PROMPT
from .models import ExtractedDocument
from .ocr_parser import parse_ocr_text
from .ocr_service import ocr_document


def process_uploaded_file(uploaded_file, use_gemini=True):
    document = load_document(uploaded_file)
    result = extract_structured_document(
        document=document,
        prompt=EXTRACTION_PROMPT,
        allowed_types=ALLOWED_TYPES,
        fallback_parser=parse_ocr_text,
        ocr_fn=ocr_document,
        use_gemini=use_gemini,
        default_type="UNKNOWN",
    )
    return ExtractedDocument(
        filename=result["filename"],
        document_type=result["document_type"],
        fields=result["fields"],
        extraction_method=result["extraction_method"],
        warnings=result["warnings"],
    )
