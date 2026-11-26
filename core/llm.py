from typing import Optional
from core.config import GEMINI_API_KEY, GEMINI_MODEL

_FALLBACK_MODELS = ("gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash")


class LLMClient:
    """Small provider adapter. Uses Gemini when configured; otherwise demo mode."""
    def __init__(self):
        self.client = None
        self.model = GEMINI_MODEL
        if GEMINI_API_KEY:
            try:
                from google import genai
                from google.genai import types
                self.client = genai.Client(
                    api_key=GEMINI_API_KEY,
                    http_options=types.HttpOptions(
                        timeout=30000,
                        retry_options=types.HttpRetryOptions(attempts=1),
                    ),
                )
            except Exception as exc:
                raise RuntimeError(f"Could not initialize Gemini client: {exc}") from exc

    @property
    def is_live(self) -> bool:
        return self.client is not None

    def _candidate_models(self) -> list[str]:
        candidates = [self.model]
        for model in _FALLBACK_MODELS:
            if model not in candidates:
                candidates.append(model)
        return candidates

    @staticmethod
    def _is_retryable_model_error(exc: Exception) -> bool:
        code = getattr(exc, "code", None)
        if code in {404, 429, 503, 504}:
            return True
        msg = str(exc).upper()
        return any(
            token in msg
            for token in ("503", "504", "404", "UNAVAILABLE", "DEADLINE_EXCEEDED", "NOT_FOUND", "TIMEOUT")
        )

    @staticmethod
    def _fast_config():
        try:
            from google.genai import types
            return types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            )
        except Exception:
            return None

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        if not self.client:
            return self._demo_response(prompt)
        full_prompt = prompt
        if system_instruction:
            full_prompt = f"System instructions:\n{system_instruction}\n\nUser request:\n{prompt}"

        config = self._fast_config()
        last_exc: Exception | None = None
        for model_name in self._candidate_models():
            try:
                kwargs = {"model": model_name, "contents": full_prompt}
                if config is not None:
                    kwargs["config"] = config
                try:
                    response = self.client.models.generate_content(**kwargs)
                except TypeError:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=full_prompt,
                    )
                except Exception as inner_exc:
                    if config is not None and getattr(inner_exc, "code", None) == 400:
                        response = self.client.models.generate_content(
                            model=model_name,
                            contents=full_prompt,
                        )
                    else:
                        raise
                self.model = model_name
                return response.text or "The model returned an empty response."
            except Exception as exc:
                last_exc = exc
                if not self._is_retryable_model_error(exc):
                    raise
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _demo_response(prompt: str) -> str:
        excerpt = prompt.strip().replace("\n", " ")
        excerpt = excerpt[:700]
        return (
            "DEMO MODE — no Gemini API key is configured.\n\n"
            "This is a local placeholder response, not an AI-generated conclusion. "
            "Configure GEMINI_API_KEY in your .env file to enable model generation.\n\n"
            f"Request preview: {excerpt}"
        )
