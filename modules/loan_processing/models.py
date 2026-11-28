from dataclasses import asdict, dataclass
from typing import Any

from core.validation import ValidationIssue


@dataclass
class ExtractedDocument:
    filename: str
    document_type: str
    fields: dict[str, Any]
    extraction_method: str
    warnings: list[str]

    def to_dict(self):
        return asdict(self)
