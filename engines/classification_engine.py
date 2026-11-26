from core.llm import LLMClient
from core.guardrails import validate_input

DEFAULT_CATEGORIES = ["Technical issue", "Compliance", "Security", "Operational", "Customer request"]

class ClassificationEngine:
    def __init__(self, llm=None):
        self.llm = llm or LLMClient()

    def classify(self, text: str, categories=None) -> dict:
        ok, error = validate_input(text)
        if not ok: raise ValueError(error)
        categories = categories or DEFAULT_CATEGORIES
        prompt = (
            f"Classify the case into exactly one category from {categories}. "
            "Estimate severity as Low, Medium, High or Critical. Give a short rationale "
            "and recommended next action. Return JSON with category, severity, rationale, next_action. "
            f"CASE:\n{text}"
        )
        result = self.llm.generate(prompt, "Be conservative. Flag uncertainty and avoid unsupported claims.")
        return {"result": result, "allowed_categories": categories,
                "review_required": True,
                "notice": "AI classification is advisory; a human must verify it."}

    @staticmethod
    def rule_score(factors: dict[str, int]) -> dict:
        score = sum(max(0, min(5, int(v))) for v in factors.values())
        maximum = max(1, 5 * len(factors))
        pct = round(score / maximum * 100)
        band = "Low" if pct < 25 else "Medium" if pct < 50 else "High" if pct < 75 else "Critical"
        return {"score": score, "percentage": pct, "band": band,
                "disclaimer": "Illustrative configurable score; validate domain rules before use."}
