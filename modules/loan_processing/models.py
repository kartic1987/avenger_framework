from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class ExtractedDocument:
    filename: str
    document_type: str
    fields: dict[str, Any]
    extraction_method: str
    warnings: list[str]

    def to_dict(self):
        return asdict(self)

@dataclass
class ValidationIssue:
    field: str
    status: str
    values: dict[str, str]
    message: str
    severity: str = "REVIEW"

    def to_dict(self):
        return asdict(self)
