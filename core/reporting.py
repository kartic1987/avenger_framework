import io
import json
from typing import Any
from xml.sax.saxutils import escape


def report_to_json(report: Any) -> str:
    """Serialize any assessment/report structure to formatted UTF-8 JSON."""
    return json.dumps(report, indent=2, ensure_ascii=False, default=str)


def build_pdf_report(
    title: str,
    subtitle: str,
    summary_items: list[tuple[str, str]],
    tables: list[tuple[str, list[str], list[list[Any]]]],
    notice: str | None = None,
) -> bytes:
    """Generate a reusable formatted PDF report using ReportLab."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=32, rightMargin=32, topMargin=32, bottomMargin=32)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(escape(title), styles["Title"]),
        Paragraph(escape(subtitle), styles["Normal"]),
        Spacer(1, 10),
    ]

    if summary_items:
        story.append(Paragraph("Summary", styles["Heading2"]))
        kv_rows = [[Paragraph(f"<b>{escape(str(k))}</b>", styles["Normal"]), Paragraph(escape(str(v)), styles["Normal"])]
                   for k, v in summary_items]
        kv_table = Table(kv_rows, colWidths=[170, 350])
        kv_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([kv_table, Spacer(1, 12)])

    for section_title, headers, rows in tables:
        story.append(Paragraph(escape(section_title), styles["Heading2"]))
        if not rows:
            story.append(Paragraph("No records.", styles["Italic"]))
            story.append(Spacer(1, 8))
            continue
        table_data = [[Paragraph(f"<b>{escape(str(h))}</b>", styles["Normal"]) for h in headers]]
        for row in rows:
            table_data.append([Paragraph(escape(str(cell if cell is not None else "")), styles["Normal"]) for cell in row])
        col_width = 520.0 / max(1, len(headers))
        tbl = Table(table_data, colWidths=[col_width] * len(headers), repeatRows=1)
        tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.extend([tbl, Spacer(1, 12)])

    if notice:
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<i>{escape(notice)}</i>", styles["Normal"]))

    doc.build(story)
    return buf.getvalue()
