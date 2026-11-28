from dataclasses import asdict, dataclass
from datetime import datetime
import re
from typing import Any, Callable, Iterable
from rapidfuzz.fuzz import ratio


@dataclass
class ValidationIssue:
    field: str
    status: str
    values: dict[str, str]
    message: str
    severity: str = "REVIEW"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^A-Z0-9 ]", "", str(value).upper()).strip()


def normalize_date(value: Any) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    return raw.upper()


def normalize_identifier(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").upper())


def compare_records(
    records: Iterable[Any],
    name_getter: Callable[[Any], str],
    fields_getter: Callable[[Any], dict[str, Any]],
    exact_fields: Iterable[str] = ("date_of_birth", "pan_number"),
    fuzzy_fields: Iterable[str] = ("name",),
    fuzzy_threshold: int = 95,
) -> list[ValidationIssue]:
    """Compare extracted fields across multiple documents/records and flag discrepancies."""
    items = list(records)
    issues: list[ValidationIssue] = []

    for field in list(fuzzy_fields) + list(exact_fields):
        values: dict[str, str] = {}
        for item in items:
            raw_val = (fields_getter(item) or {}).get(field)
            if raw_val not in (None, ""):
                values[name_getter(item)] = str(raw_val)
        if len(values) < 2:
            continue

        if field in fuzzy_fields:
            normalized = [normalize_text(v) for v in values.values()]
            scores = [
                ratio(normalized[i], normalized[j])
                for i in range(len(normalized))
                for j in range(i + 1, len(normalized))
            ]
            if scores and min(scores) < fuzzy_threshold:
                issues.append(ValidationIssue(
                    field=field,
                    status="POSSIBLE_MISMATCH",
                    values=values,
                    message=f"{field.replace('_', ' ').title()} values differ (lowest similarity {min(scores):.1f}%). Manual review required.",
                ))
        else:
            if "date" in field:
                normalized = [normalize_date(v) for v in values.values()]
            else:
                normalized = [normalize_identifier(v) for v in values.values()]
            if len(set(normalized)) > 1:
                issues.append(ValidationIssue(
                    field=field,
                    status="MISMATCH",
                    values=values,
                    message=f"{field.replace('_', ' ').title()} differs across documents.",
                ))
    return issues


def check_required_categories(
    present_categories: Iterable[str],
    required_categories: Iterable[str],
) -> list[str]:
    """Return sorted missing required categories."""
    return sorted(set(required_categories) - set(present_categories))
