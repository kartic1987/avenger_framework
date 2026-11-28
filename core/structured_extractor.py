import json
import re
from typing import Any, Callable, Iterable


def clean_json_response(text: str) -> dict[str, Any]:
    """Parse JSON from an LLM response, stripping optional markdown fences."""
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(cleaned[start:end])
        raise


def extract_with_gemini_schema(
    document: dict[str, Any],
    prompt: str,
    allowed_types: Iterable[str],
    default_type: str = "UNKNOWN",
) -> dict[str, Any]:
    """Run Gemini multimodal/text structured JSON extraction with fast model failover."""
    from google.genai import types
    from core.llm import LLMClient

    llm = LLMClient()
    if not llm.is_live:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    parts = [types.Part.from_text(text=prompt)]
    if document.get("text"):
        parts.append(types.Part.from_text(text="DOCUMENT TEXT:\n" + document["text"][:60000]))
    else:
        for image_bytes in document.get("images", [])[:8]:
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    last_exc: Exception | None = None
    response = None
    for model_name in llm._candidate_models():
        try:
            try:
                response = llm.client.models.generate_content(
                    model=model_name,
                    contents=parts,
                    config=config,
                )
            except Exception as inner_exc:
                if getattr(inner_exc, "code", None) == 400:
                    response = llm.client.models.generate_content(
                        model=model_name,
                        contents=parts,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0,
                        ),
                    )
                else:
                    raise
            llm.model = model_name
            break
        except Exception as exc:
            last_exc = exc
            if not llm._is_retryable_model_error(exc):
                raise
    if response is None:
        raise last_exc  # type: ignore[misc]

    result = clean_json_response(response.text or "")
    allowed = {t.upper() for t in allowed_types}
    doc_type = str(result.get("document_type", default_type)).upper()
    if allowed and doc_type not in allowed:
        doc_type = default_type
    result["document_type"] = doc_type
    result.setdefault("fields", {})
    result.setdefault("warnings", [])
    return result


def extract_structured_document(
    document: dict[str, Any],
    prompt: str,
    allowed_types: Iterable[str],
    fallback_parser: Callable[[str], tuple[str, dict[str, Any]]],
    ocr_fn: Callable[[dict[str, Any]], str],
    use_gemini: bool = True,
    default_type: str = "UNKNOWN",
) -> dict[str, Any]:
    """Reusable Gemini-first + offline-OCR-fallback structured extractor."""
    warnings: list[str] = []
    if use_gemini:
        try:
            result = extract_with_gemini_schema(
                document=document,
                prompt=prompt,
                allowed_types=allowed_types,
                default_type=default_type,
            )
            return {
                "filename": document["filename"],
                "document_type": result.get("document_type", default_type),
                "fields": result.get("fields", {}),
                "extraction_method": "Gemini",
                "warnings": list(result.get("warnings", [])),
            }
        except Exception as exc:
            warnings.append(f"Gemini extraction unavailable: {type(exc).__name__}: {exc}")

    ocr_text = document.get("text", "") or ocr_fn(document)
    if ocr_text:
        doc_type, fields = fallback_parser(ocr_text)
        fields["ocr_text"] = ocr_text[:30000]
    else:
        doc_type, fields = default_type, {"ocr_text": None}
        warnings.append("OCR returned no readable text. Check image quality.")

    warnings.append("OCR field extraction is best-effort; verify every extracted value against the source.")
    return {
        "filename": document["filename"],
        "document_type": doc_type,
        "fields": fields,
        "extraction_method": "OCR fallback",
        "warnings": warnings,
    }
