from .document_loader import load_document
from .gemini_extractor import extract_with_gemini
from .ocr_service import ocr_document
from .ocr_parser import parse_ocr_text
from .models import ExtractedDocument

def process_uploaded_file(uploaded_file, use_gemini=True):
    document = load_document(uploaded_file)
    warnings = []

    if use_gemini:
        try:
            result = extract_with_gemini(document)
            return ExtractedDocument(
                filename=document["filename"],
                document_type=result.get("document_type", "UNKNOWN"),
                fields=result.get("fields", {}),
                extraction_method="Gemini",
                warnings=list(result.get("warnings", []))
            )
        except Exception as exc:
            warnings.append(f"Gemini extraction unavailable: {type(exc).__name__}: {exc}")

    # OCR fallback: use selectable PDF text first, otherwise Tesseract OCR.
    ocr_text = document.get("text", "") or ocr_document(document)
    if ocr_text:
        doc_type, fields = parse_ocr_text(ocr_text)
        fields["ocr_text"] = ocr_text[:30000]
    else:
        doc_type, fields = "UNKNOWN", {"ocr_text": None}
        warnings.append("OCR returned no readable text. Check image quality and Tesseract installation.")

    warnings.append("OCR field extraction is best-effort; verify every extracted value against the source.")
    return ExtractedDocument(
        filename=document["filename"],
        document_type=doc_type,
        fields=fields,
        extraction_method="OCR fallback",
        warnings=warnings
    )
