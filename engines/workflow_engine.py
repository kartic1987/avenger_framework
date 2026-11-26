from dataclasses import dataclass, field
from typing import Any
from core.guardrails import validate_input

@dataclass
class WorkflowStep:
    name: str
    action: str
    params: dict = field(default_factory=dict)

class WorkflowEngine:
    """Small sequential workflow runner. Actions are allow-listed; no arbitrary code execution."""
    def __init__(self):
        self.actions = {
            "validate_text": self._validate_text,
            "uppercase": lambda value, params: str(value).upper(),
            "word_count": lambda value, params: {"word_count": len(str(value).split())},
            "prefix": lambda value, params: str(params.get("prefix", "")) + str(value),
        }

    def run(self, initial_input: Any, steps: list[dict]) -> dict:
        current, history = initial_input, []
        for raw in steps:
            step = WorkflowStep(**raw)
            if step.action not in self.actions:
                raise ValueError(f"Action not allowed: {step.action}")
            current = self.actions[step.action](current, step.params)
            history.append({"step": step.name, "action": step.action, "output": current})
        return {"final_output": current, "history": history}

    @staticmethod
    def _validate_text(value, params):
        ok, error = validate_input(str(value))
        return {"valid": ok, "error": error, "text": value}
