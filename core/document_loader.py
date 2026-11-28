import concurrent.futures
import csv
import hashlib
import io
import json
import os
from pathlib import Path
from typing import Callable

SUPPORTED = {".txt", ".md", ".pdf", ".docx", ".csv", ".json"}
_MIN_DIGITAL_PAGE_CHARS = 20
_DEFAULT_OCR_DPI = 120
_OCR_BATCH_SIZE = 8
_OCR_ENGINE = None


def _get_ocr_cache_dir() -> Path:
    from core.config import DATA_DIR
    cache_dir = DATA_DIR / "ocr_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _get_ocr_engine():
    """Return a lazily initialized, speed-tuned offline RapidOCR engine instance."""
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Missing dependency 'rapidocr-onnxruntime' for scanned PDF OCR. "
                "Install requirements or run with the project .venv."
            ) from exc
        _OCR_ENGINE = RapidOCR(
            use_angle_cls=False,
            det_model_path=None,
            det_use_dilation=False,
            rec_model_path=None,
            rec_batch_num=16,
        )
    return _OCR_ENGINE


def _normalize_page_range(total_pages: int, page_range: tuple[int, int] | None) -> tuple[int, int]:
    """Convert 1-based inclusive page_range to clamped 0-based (start, end_exclusive) indices."""
    if total_pages <= 0:
        return 0, 0
    if page_range is None:
        return 0, total_pages
    start_1b, end_1b = page_range
    start_idx = max(0, min(start_1b - 1, total_pages - 1))
    end_idx = max(start_idx + 1, min(end_1b, total_pages))
    return start_idx, end_idx


def get_pdf_page_count(data: bytes) -> int:
    """Return total page count of a PDF byte buffer."""
    try:
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return len(doc)
    except ModuleNotFoundError:
        from pypdf import PdfReader
        return len(PdfReader(io.BytesIO(data)).pages)


def pdf_needs_ocr(data: bytes, page_range: tuple[int, int] | None = None) -> bool:
    """Return True if any page in range lacks sufficient embedded digital text."""
    try:
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            start_idx, end_idx = _normalize_page_range(len(doc), page_range)
            return any(
                len((doc[idx].get_text("text") or "").strip()) < _MIN_DIGITAL_PAGE_CHARS
                for idx in range(start_idx, end_idx)
            )
    except ModuleNotFoundError:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        start_idx, end_idx = _normalize_page_range(len(reader.pages), page_range)
        return any(
            len((reader.pages[idx].extract_text() or "").strip()) < _MIN_DIGITAL_PAGE_CHARS
            for idx in range(start_idx, end_idx)
        )


def _ocr_pixmap_array(page, ocr_dpi: int):
    """Render a PyMuPDF page directly to a contiguous grayscale NumPy array."""
    import numpy as np
    import pymupdf
    pix = page.get_pixmap(dpi=ocr_dpi, colorspace=pymupdf.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()


def _run_ocr_on_array(arr) -> str:
    ocr = _get_ocr_engine()
    result, _ = ocr(arr)
    if not result:
        return ""
    return "\n".join(item[1] for item in result if len(item) >= 2 and item[1])


def _extract_pdf_text(
    data: bytes,
    progress_callback: Callable[[int, int, str], None] | None = None,
    ocr_dpi: int = _DEFAULT_OCR_DPI,
    page_range: tuple[int, int] | None = None,
    use_cache: bool = True,
) -> str:
    """Extract PDF text via single-pass PyMuPDF, parallel offline OCR, and disk caching."""
    range_tag = f"{page_range[0]}-{page_range[1]}" if page_range else "all"
    cache_path = None
    if use_cache:
        digest = hashlib.sha256(data).hexdigest()
        cache_path = _get_ocr_cache_dir() / f"{digest}_{ocr_dpi}_{range_tag}.txt"
        if cache_path.is_file():
            if progress_callback:
                progress_callback(1, 1, "Loaded extracted text from cache")
            return cache_path.read_text(encoding="utf-8")

    try:
        import pymupdf
    except ModuleNotFoundError as exc:
        try:
            from pypdf import PdfReader
        except ModuleNotFoundError as pypdf_exc:
            raise ModuleNotFoundError(
                "Missing dependency 'pypdf' or 'pymupdf'. Install requirements or run with the project .venv."
            ) from pypdf_exc
        reader = PdfReader(io.BytesIO(data))
        start_idx, end_idx = _normalize_page_range(len(reader.pages), page_range)
        pages_text = [(reader.pages[i].extract_text() or "") for i in range(start_idx, end_idx)]
        if any(len(t.strip()) < _MIN_DIGITAL_PAGE_CHARS for t in pages_text) and not any(t.strip() for t in pages_text):
            raise ModuleNotFoundError(
                "Missing dependency 'pymupdf' for scanned PDF OCR. "
                "Install requirements or run with the project .venv."
            ) from exc
        return "\n".join(pages_text)

    with pymupdf.open(stream=data, filetype="pdf") as doc:
        total_pages = len(doc)
        start_idx, end_idx = _normalize_page_range(total_pages, page_range)
        selected_indices = list(range(start_idx, end_idx))
        pages_text: dict[int, str] = {}
        pages_needing_ocr: list[int] = []

        for page_idx in selected_indices:
            native_text = (doc[page_idx].get_text("text") or "").strip()
            if len(native_text) >= _MIN_DIGITAL_PAGE_CHARS:
                pages_text[page_idx] = native_text
            else:
                pages_text[page_idx] = native_text
                pages_needing_ocr.append(page_idx)

        if not pages_needing_ocr:
            if progress_callback:
                progress_callback(len(selected_indices), len(selected_indices), "Extracted embedded PDF text")
            combined = "\n".join(pages_text[i] for i in selected_indices)
            if cache_path is not None and combined.strip():
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(combined, encoding="utf-8")
            return combined

        _get_ocr_engine()
        total_to_ocr = len(pages_needing_ocr)
        workers = min(4, max(1, os.cpu_count() or 2), total_to_ocr)
        completed = 0

        if progress_callback:
            progress_callback(0, total_to_ocr, f"Running offline OCR on {total_to_ocr} scanned pages ({workers} threads)...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            for batch_start in range(0, total_to_ocr, _OCR_BATCH_SIZE):
                batch_indices = pages_needing_ocr[batch_start:batch_start + _OCR_BATCH_SIZE]
                rendered = [(idx, _ocr_pixmap_array(doc[idx], ocr_dpi)) for idx in batch_indices]

                future_to_idx = {
                    executor.submit(_run_ocr_on_array, arr): idx
                    for idx, arr in rendered
                }
                for future in concurrent.futures.as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    ocr_text = future.result()
                    if ocr_text.strip():
                        pages_text[idx] = ocr_text
                    completed += 1
                    if progress_callback:
                        progress_callback(
                            completed,
                            total_to_ocr,
                            f"Offline OCR completed {completed}/{total_to_ocr} scanned pages (page {idx + 1}/{total_pages})",
                        )

        combined = "\n".join(pages_text[i] for i in selected_indices)
        if cache_path is not None and combined.strip():
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(combined, encoding="utf-8")
        return combined


def extract_text(
    path_or_bytes,
    filename: str | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    ocr_dpi: int = _DEFAULT_OCR_DPI,
    page_range: tuple[int, int] | None = None,
    use_cache: bool = True,
) -> str:
    if isinstance(path_or_bytes, (str, Path)):
        path = Path(path_or_bytes)
        filename = filename or path.name
        data = path.read_bytes()
    else:
        data = path_or_bytes
    ext = Path(filename or "").suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"Unsupported file type: {ext or 'unknown'}")
    if ext in {".txt", ".md"}:
        return data.decode("utf-8", errors="replace")
    if ext == ".pdf":
        return _extract_pdf_text(
            data,
            progress_callback=progress_callback,
            ocr_dpi=ocr_dpi,
            page_range=page_range,
            use_cache=use_cache,
        )
    if ext == ".docx":
        try:
            from docx import Document
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Missing dependency 'python-docx'. Install requirements or run with the project .venv."
            ) from exc
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    if ext == ".csv":
        text = data.decode("utf-8", errors="replace")
        return "\n".join(" | ".join(row) for row in csv.reader(io.StringIO(text)))
    if ext == ".json":
        return json.dumps(json.loads(data.decode("utf-8")), indent=2, ensure_ascii=False)
    return ""


def load_visual_document(filename: str, data: bytes, render_scale: float = 1.5) -> dict:
    """Load a PDF or image into selectable text + rendered PNG page images for multimodal/OCR flows."""
    ext = Path(filename or "").suffix.lower()
    if ext == ".pdf":
        import pymupdf

        texts, images = [], []
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            matrix = pymupdf.Matrix(render_scale, render_scale)
            for page in doc:
                page_text = (page.get_text("text") or "").strip()
                if page_text:
                    texts.append(page_text)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                images.append(pix.tobytes("png"))
        return {
            "filename": filename,
            "text": "\n".join(texts).strip(),
            "images": images,
            "mime_type": "application/pdf",
            "raw_bytes": data,
        }

    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        from PIL import Image

        image = Image.open(io.BytesIO(data)).convert("RGB")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return {
            "filename": filename,
            "text": "",
            "images": [buf.getvalue()],
            "mime_type": "image/png",
            "raw_bytes": data,
        }

    raise ValueError(f"Unsupported visual document type: {ext or 'unknown'}")
