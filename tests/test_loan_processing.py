import io
import tempfile
import unittest
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from core.audit import AuditLogger
from core.privacy import mask_dict_fields, mask_identifier, redact_pii_text
from modules.loan_processing import (
    load_rules,
    loan_report_pdf,
    process_and_validate_loan_documents,
    re_evaluate_loan_assessment,
    report_json,
)


class _DummyUpload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getvalue(self) -> bytes:
        return self._data


def _make_text_pdf(lines: list[str]) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=12)
        y += 22
    data = doc.tobytes()
    doc.close()
    return data


def _make_png_doc(lines: list[str]) -> bytes:
    img = Image.new("RGB", (1000, 320), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=28)
    y = 40
    for line in lines:
        draw.text((40, y), line, fill="black", font=font)
        y += 48
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class LoanProcessingTests(unittest.TestCase):
    def test_load_default_rules(self):
        rules = load_rules()
        self.assertIn("maximum_foir_percent", rules)
        self.assertIn("required_document_types", rules)

    def test_multi_document_validation_pass(self):
        uploads = [
            _DummyUpload(
                "pan.pdf",
                _make_text_pdf([
                    "INCOME TAX DEPARTMENT - PAN CARD",
                    "Name: RAHUL SHARMA",
                    "DOB: 1990-05-14",
                    "PAN: ABCDE1234F",
                ]),
            ),
            _DummyUpload(
                "aadhaar.pdf",
                _make_text_pdf([
                    "AADHAAR CARD",
                    "Name: RAHUL SHARMA",
                    "Date of Birth: 14/05/1990",
                    "Aadhaar: XXXX XXXX 4321",
                ]),
            ),
            _DummyUpload(
                "salary_slip.pdf",
                _make_text_pdf([
                    "SALARY SLIP - OCTOBER 2026",
                    "Employee Name: RAHUL SHARMA",
                    "Employer: ACME TECH PVT LTD",
                    "Gross Monthly Salary: 120000",
                    "Net Monthly Salary: 95000",
                ]),
            ),
            _DummyUpload(
                "loan_application.pdf",
                _make_text_pdf([
                    "LOAN APPLICATION FORM",
                    "Applicant Name: RAHUL SHARMA",
                    "PAN: ABCDE1234F",
                    "Existing EMI: 5000",
                    "Requested Loan Amount: 1000000",
                    "Requested Tenure Months: 48",
                ]),
            ),
        ]

        with tempfile.TemporaryDirectory() as td:
            logger = AuditLogger(module="loan_test", log_path=Path(td) / "audit.jsonl")
            progress_events = []
            report = process_and_validate_loan_documents(
                uploads,
                use_gemini=False,
                progress_callback=lambda d, t, m: progress_events.append((d, t, m)),
                audit_logger=logger,
            )

            self.assertEqual(len(report["documents"]), 4)
            self.assertEqual(report["missing_documents"], [])
            self.assertEqual(report["mismatch_issues"], [])
            self.assertEqual(report["eligibility"]["status"], "WITHIN_CONFIGURED_LIMITS")
            self.assertEqual(report["overall_status"], "ASSESSMENT_REQUIRES_HUMAN_REVIEW")
            self.assertEqual(report["banking_checks"]["identity_verification"]["status"], "VERIFIED")
            self.assertGreaterEqual(report["banking_checks"]["credit_bureau"]["credit_score"], 650)
            self.assertGreaterEqual(len(report["audit_trail"]), 5)
            self.assertTrue((Path(td) / "audit.jsonl").is_file())
            self.assertTrue(progress_events)
            self.assertIn("WITHIN_CONFIGURED_LIMITS", report_json(report))

            pdf_bytes = loan_report_pdf(report, mask_pii=True)
            self.assertTrue(pdf_bytes.startswith(b"%PDF"))

            masked_json = report_json(report, mask_pii=True)
            self.assertNotIn("ABCDE1234F", masked_json)
            self.assertIn("******234F", masked_json)

    def test_multi_document_validation_detects_mismatches_and_missing(self):
        uploads = [
            _DummyUpload(
                "pan_mismatch.pdf",
                _make_text_pdf([
                    "PAN CARD",
                    "Name: RAHUL SHARMA",
                    "DOB: 1990-05-14",
                    "PAN: ABCDE1234F",
                ]),
            ),
            _DummyUpload(
                "aadhaar_other.pdf",
                _make_text_pdf([
                    "AADHAAR",
                    "Name: ROHAN VERMA",
                    "DOB: 1992-01-10",
                ]),
            ),
        ]

        with tempfile.TemporaryDirectory() as td:
            logger = AuditLogger(module="loan_test_mismatch", log_path=Path(td) / "audit.jsonl")
            report = process_and_validate_loan_documents(uploads, use_gemini=False, audit_logger=logger)
            issue_fields = {issue["field"] for issue in report["mismatch_issues"]}
            self.assertIn("name", issue_fields)
            self.assertIn("date_of_birth", issue_fields)
            self.assertIn("SALARY_SLIP", report["missing_documents"])
            self.assertIn("LOAN_APPLICATION", report["missing_documents"])
            self.assertEqual(report["overall_status"], "REVIEW_REQUIRED")

            # Interactive correction fixes name/DOB discrepancy
            edited_docs = list(report["documents"])
            edited_docs[1] = {
                **edited_docs[1],
                "fields": {**edited_docs[1]["fields"], "name": "RAHUL SHARMA", "date_of_birth": "1990-05-14"},
            }
            re_eval = re_evaluate_loan_assessment(edited_docs, audit_logger=logger)
            re_issue_fields = {issue["field"] for issue in re_eval["mismatch_issues"]}
            self.assertNotIn("name", re_issue_fields)
            self.assertNotIn("date_of_birth", re_issue_fields)

    def test_privacy_helpers_and_low_credit_score_flag(self):
        self.assertEqual(mask_identifier("ABCDE1234F"), "******234F")
        masked = mask_dict_fields({"pan_number": "ABCDE1234F", "name": "RAHUL"})
        self.assertEqual(masked["pan_number"], "******234F")
        self.assertEqual(masked["name"], "RAHUL")
        self.assertNotIn("9876543210", redact_pii_text("Call 9876543210 or mail a@b.com"))

        uploads = [
            _DummyUpload("pan.pdf", _make_text_pdf(["PAN CARD", "Name: TEST USER", "DOB: 1991-01-01", "PAN: LOWSC1234A"])),
            _DummyUpload("aadhaar.pdf", _make_text_pdf(["AADHAAR", "Name: TEST USER", "DOB: 1991-01-01", "Aadhaar: XXXX XXXX 1111"])),
            _DummyUpload("salary.pdf", _make_text_pdf(["SALARY SLIP", "Employee Name: TEST USER", "Net Monthly Salary: 80000"])),
            _DummyUpload("app.pdf", _make_text_pdf(["LOAN APPLICATION", "Applicant Name: TEST USER", "PAN: LOWSC1234A", "Requested Loan Amount: 500000", "Requested Tenure Months: 36"])),
        ]
        with tempfile.TemporaryDirectory() as td:
            logger = AuditLogger(module="loan_low_score", log_path=Path(td) / "audit.jsonl")
            report = process_and_validate_loan_documents(uploads, use_gemini=False, audit_logger=logger)
            self.assertEqual(report["banking_checks"]["credit_bureau"]["credit_score"], 595)
            self.assertEqual(report["eligibility"]["status"], "OUTSIDE_CONFIGURED_LIMITS")
            self.assertIn("credit_score", {i["field"] for i in report["mismatch_issues"]})

    def test_image_ocr_fallback_without_tesseract(self):
        png_bytes = _make_png_doc([
            "PAN CARD",
            "Name: ANITA DESAI",
            "PAN: ABCDE1234F",
        ])
        report = process_and_validate_loan_documents(
            [_DummyUpload("pan_scan.png", png_bytes)],
            use_gemini=False,
        )
        doc = report["documents"][0]
        self.assertEqual(doc["extraction_method"], "OCR fallback")
        self.assertTrue(doc["fields"].get("ocr_text"))
        self.assertEqual(doc["fields"].get("pan_number"), "ABCDE1234F")


if __name__ == "__main__":
    unittest.main()
