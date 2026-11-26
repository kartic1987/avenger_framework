import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from core.document_loader import extract_text, get_pdf_page_count, pdf_needs_ocr
from engines.document_engine import DocumentEngine
from engines.rag_engine import RAGEngine


class _StubLLM:
    def __init__(self):
        self.calls = []

    def generate(self, prompt: str, system_instruction: str | None = None) -> str:
        self.calls.append(prompt)
        if "Return valid JSON only" in prompt:
            return json.dumps({"title": "Grammar Guide" if "Grammar" in prompt else None})
        return "Summary chunk"


def _make_scanned_pdf_bytes(text: str) -> bytes:
    """Create a single-page image-only PDF containing rendered text."""
    img = Image.new("RGB", (900, 220), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=42)
    draw.text((40, 80), text, fill="black", font=font)
    png_buf = io.BytesIO()
    img.save(png_buf, format="PNG")

    doc = pymupdf.open()
    page = doc.new_page(width=900, height=220)
    page.insert_image(page.rect, stream=png_buf.getvalue())
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_digital_pdf_bytes(text: str) -> bytes:
    """Create a single-page PDF with embedded digital text."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=14)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class DocumentLoaderAndLargeDocTests(unittest.TestCase):
    def test_digital_pdf_extraction(self):
        pdf_bytes = _make_digital_pdf_bytes("Embedded digital PDF content for testing.")
        extracted = extract_text(pdf_bytes, "digital.pdf")
        self.assertIn("Embedded digital PDF content", extracted)

    def test_scanned_pdf_ocr_and_rag_ingest(self):
        pdf_bytes = _make_scanned_pdf_bytes("OFFLINE OCR TEST 2026")
        events = []
        extracted = extract_text(
            pdf_bytes,
            "scanned.pdf",
            progress_callback=lambda done, total, msg: events.append((done, total, msg)),
            use_cache=False,
        )
        normalized = extracted.replace(" ", "").upper()
        self.assertIn("OFFLINE", normalized)
        self.assertIn("OCR", normalized)
        self.assertIn("2026", normalized)
        self.assertTrue(events)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("core.document_loader._get_ocr_cache_dir", return_value=Path(tmpdir) / "ocr_cache"):
                rag = RAGEngine(directory=Path(tmpdir), llm=_StubLLM())
                chunk_count = rag.ingest("scanned.pdf", pdf_bytes)
                self.assertGreaterEqual(chunk_count, 1)
                hits = rag.retrieve("OFFLINE")
                self.assertGreaterEqual(len(hits), 1)

    def test_pdf_page_range_helpers_and_cache(self):
        doc = pymupdf.open()
        for page_num in range(1, 4):
            page = doc.new_page()
            page.insert_text((72, 72), f"Page {page_num} embedded digital content here.", fontsize=14)
        pdf_bytes = doc.tobytes()
        doc.close()

        self.assertEqual(get_pdf_page_count(pdf_bytes), 3)
        self.assertFalse(pdf_needs_ocr(pdf_bytes))

        with tempfile.TemporaryDirectory() as cache_tmp:
            with patch("core.document_loader._get_ocr_cache_dir", return_value=Path(cache_tmp)):
                page2_only = extract_text(pdf_bytes, "three.pdf", page_range=(2, 2), use_cache=True)
                self.assertIn("Page 2", page2_only)
                self.assertNotIn("Page 1", page2_only)
                self.assertNotIn("Page 3", page2_only)

                events = []
                cached_again = extract_text(
                    pdf_bytes,
                    "three.pdf",
                    page_range=(2, 2),
                    use_cache=True,
                    progress_callback=lambda d, t, m: events.append(m),
                )
                self.assertEqual(cached_again, page2_only)
                self.assertTrue(any("cache" in m.lower() for m in events))

    def test_large_document_chunked_summarize_and_extract(self):
        llm = _StubLLM()
        engine = DocumentEngine(llm=llm)
        large_text = ("English Grammar chapter content.\n" * 4500)
        self.assertGreater(len(large_text), 120000)

        summary = engine.summarize(large_text)
        self.assertTrue(summary)
        self.assertGreaterEqual(len(llm.calls), 2)

        fields = engine.extract_fields(large_text, ["title"])
        self.assertEqual(fields.get("title"), "Grammar Guide")

    def test_llm_client_fallback_on_503(self):
        from core.llm import LLMClient

        class _FakeModels:
            def __init__(self):
                self.tried = []

            def generate_content(self, model, contents, config=None):
                self.tried.append(model)
                if model == "gemini-3.8-flash":
                    raise RuntimeError("503 UNAVAILABLE")
                if model == "gemini-3.6-flash":
                    raise RuntimeError("504 DEADLINE_EXCEEDED")
                return type("Resp", (), {"text": f"ok from {model}"})()

        client = LLMClient.__new__(LLMClient)
        client.model = "gemini-3.8-flash"
        client.client = type("FakeGenAI", (), {"models": _FakeModels()})()
        reply = client.generate("hello")
        self.assertEqual(reply, "ok from gemini-3.1-flash-lite")
        self.assertEqual(client.model, "gemini-3.1-flash-lite")


if __name__ == "__main__":
    unittest.main()
