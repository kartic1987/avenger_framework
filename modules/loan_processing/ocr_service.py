import io
import os
from PIL import Image


def _rapidocr_image(image_bytes: bytes) -> str:
    """Offline OCR fallback using the project's shared RapidOCR engine."""
    try:
        import numpy as np
        from core.document_loader import _get_ocr_engine

        image = Image.open(io.BytesIO(image_bytes)).convert("L")
        arr = np.asarray(image)
        ocr = _get_ocr_engine()
        result, _ = ocr(arr)
        if not result:
            return ""
        return "\n".join(item[1] for item in result if len(item) >= 2 and item[1]).strip()
    except Exception:
        return ""


def ocr_image(image_bytes: bytes) -> str:
    """OCR fallback using Tesseract when available, otherwise offline RapidOCR."""
    try:
        import pytesseract
        from dotenv import load_dotenv
        load_dotenv(override=True)
        command = os.getenv("TESSERACT_CMD")
        if command:
            pytesseract.pytesseract.tesseract_cmd = command
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        text = pytesseract.image_to_string(image, config="--psm 6").strip()
        if text:
            return text
    except Exception:
        pass
    return _rapidocr_image(image_bytes)


def ocr_document(document: dict) -> str:
    chunks = []
    for image_bytes in document.get("images", []):
        text = ocr_image(image_bytes)
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip()
