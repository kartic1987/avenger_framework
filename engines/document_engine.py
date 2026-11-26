import concurrent.futures
import json
from typing import Callable
from core.llm import LLMClient
from core.guardrails import validate_input

_CHUNK_MAX_CHARS = 120000
_MAX_CHUNK_WORKERS = 4


def _split_text_chunks(text: str, max_chars: int = _CHUNK_MAX_CHARS) -> list[str]:
    """Split long text into bounded chunks without breaking mid-word where possible."""
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + max_chars, length)
        if end < length:
            split_at = text.rfind("\n", start, end)
            if split_at <= start:
                split_at = text.rfind(" ", start, end)
            if split_at > start:
                end = split_at
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks


class DocumentEngine:
    def __init__(self, llm=None):
        self.llm = llm or LLMClient()

    def _summarize_single(self, text: str) -> str:
        ok, error = validate_input(text, max_chars=max(50000, _CHUNK_MAX_CHARS))
        if not ok:
            raise ValueError(error)
        return self.llm.generate(
            f"Summarize this document. Separate facts, dates, entities, risks and missing information. "
            f"Do not invent facts.\n\nDOCUMENT:\n{text}",
            "You are a careful document analyst. Clearly mark uncertainty."
        )

    def summarize(
        self,
        text: str,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> str:
        ok, error = validate_input(text, max_chars=max(50000, len(text) if isinstance(text, str) else 50000))
        if not ok:
            raise ValueError(error)
        if len(text) <= _CHUNK_MAX_CHARS:
            if progress_callback:
                progress_callback(0, 1, "Analyzing document with Gemini...")
            result = self._summarize_single(text)
            if progress_callback:
                progress_callback(1, 1, "Summary complete")
            return result

        chunks = _split_text_chunks(text)
        total_steps = len(chunks) + 1
        partials: list[str] = [""] * len(chunks)
        done_count = 0
        if progress_callback:
            progress_callback(0, total_steps, f"Summarizing {len(chunks)} document sections...")

        workers = min(_MAX_CHUNK_WORKERS, len(chunks))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_idx = {
                executor.submit(self._summarize_single, chunk): idx
                for idx, chunk in enumerate(chunks)
            }
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                partials[idx] = future.result()
                done_count += 1
                if progress_callback:
                    progress_callback(done_count, total_steps, f"Summarized section {done_count}/{len(chunks)}")

        if len(partials) == 1:
            return partials[0]
        combined = "\n\n".join(f"[Part {i}]\n{part}" for i, part in enumerate(partials, start=1))
        if len(combined) <= _CHUNK_MAX_CHARS:
            if progress_callback:
                progress_callback(len(chunks), total_steps, "Combining section summaries...")
            final = self.llm.generate(
                "Combine these section summaries into one cohesive summary. "
                "Separate facts, dates, entities, risks and missing information. Do not invent facts.\n\n"
                f"{combined}",
                "You are a careful document analyst. Clearly mark uncertainty."
            )
            if progress_callback:
                progress_callback(total_steps, total_steps, "Summary complete")
            return final
        return combined

    def _extract_fields_single(self, text: str, fields: list[str]) -> dict:
        ok, error = validate_input(text, max_chars=max(50000, _CHUNK_MAX_CHARS))
        if not ok:
            raise ValueError(error)
        prompt = (
            "Extract the requested fields from the document. Return valid JSON only. "
            "Use null when a value is absent; never infer missing values.\n"
            f"FIELDS: {json.dumps(fields)}\nDOCUMENT:\n{text}"
        )
        result = self.llm.generate(prompt, "Return a JSON object only.")
        try:
            start, end = result.find("{"), result.rfind("}") + 1
            return json.loads(result[start:end])
        except Exception:
            return {"raw_model_response": result, "parse_error": "Response was not valid JSON"}

    def extract_fields(
        self,
        text: str,
        fields: list[str],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> dict:
        ok, error = validate_input(text, max_chars=max(50000, len(text) if isinstance(text, str) else 50000))
        if not ok:
            raise ValueError(error)
        if len(text) <= _CHUNK_MAX_CHARS:
            if progress_callback:
                progress_callback(0, 1, "Extracting structured fields...")
            result = self._extract_fields_single(text, fields)
            if progress_callback:
                progress_callback(1, 1, "Extraction complete")
            return result

        chunks = _split_text_chunks(text)
        partials: list[dict] = [{}] * len(chunks)
        done_count = 0
        if progress_callback:
            progress_callback(0, len(chunks), f"Extracting fields across {len(chunks)} sections...")

        workers = min(_MAX_CHUNK_WORKERS, len(chunks))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_idx = {
                executor.submit(self._extract_fields_single, chunk, fields): idx
                for idx, chunk in enumerate(chunks)
            }
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                partials[idx] = future.result()
                done_count += 1
                if progress_callback:
                    progress_callback(done_count, len(chunks), f"Extracted section {done_count}/{len(chunks)}")

        merged: dict = {field: None for field in fields}
        for partial in partials:
            if "parse_error" in partial and not any(merged.get(f) is not None for f in fields):
                merged = partial
                continue
            for field in fields:
                if merged.get(field) is None and partial.get(field) is not None:
                    merged[field] = partial[field]
        return merged
