import re

def _find(pattern, text, flags=re.IGNORECASE):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None

def _amount(pattern, text):
    value = _find(pattern, text)
    if not value:
        return None
    try:
        return float(value.replace(",", "").replace("₹", "").strip())
    except ValueError:
        return None

def parse_ocr_text(text):
    """Best-effort label-based parser for OCR fallback; never treats output as verified."""
    upper = text.upper()
    if "LOAN APPLICATION" in upper or "REQUESTED LOAN" in upper:
        kind = "LOAN_APPLICATION"
    elif "SALARY" in upper or "PAYSLIP" in upper or "PAY SLIP" in upper:
        kind = "SALARY_SLIP"
    elif "AADHAAR" in upper or "AADHAR" in upper:
        kind = "AADHAAR"
    elif re.search(r"\bPAN\b", upper) and re.search(r"[A-Z]{5}[0-9]{4}[A-Z]", upper):
        kind = "PAN"
    elif "VOTER" in upper or "EPIC" in upper:
        kind = "VOTER_ID"
    else:
        kind = "UNKNOWN"

    fields = {
        "name": _find(r"(?:Applicant\s+Name|Employee\s+Name|Name)\s*[:\-]\s*([A-Z][A-Z .'-]+)", text),
        "date_of_birth": _find(r"(?:Date\s+of\s+Birth|DOB)\s*[:\-]\s*([0-9./-]+)", text),
        "pan_number": _find(r"\bPAN(?:\s*(?:No\.?|Number))?\s*[:\-]?\s*([A-Z]{5}[0-9]{4}[A-Z])\b", text),
        "aadhaar_last4": _find(r"(?:XXXX|X{4})\s*X{0,4}\s*X{0,4}\s*([0-9]{4})", text),
        "voter_id": _find(r"(?:EPIC|Voter\s*ID)\s*[:\-]\s*([A-Z0-9]+)", text),
        "father_or_spouse_name": _find(r"(?:Father'?s?\s+Name|Spouse\s+Name)\s*[:\-]\s*([A-Z .'-]+)", text),
        "address": _find(r"Address\s*[:\-]\s*(.+)", text),
        "employer_name": _find(r"(?:Employer|Company)\s*[:\-]\s*(.+)", text),
        "employee_id": _find(r"Employee\s*ID\s*[:\-]\s*([A-Z0-9-]+)", text),
        "salary_month": _find(r"Salary\s+Month\s*[:\-]\s*(.+)", text),
        "gross_monthly_salary": _amount(r"Gross(?:\s+Monthly)?\s+Salary\s*[:\-]\s*₹?\s*([0-9,]+(?:\.[0-9]{1,2})?)", text),
        "net_monthly_salary": _amount(r"Net(?:\s+Monthly)?\s+Salary\s*[:\-]\s*₹?\s*([0-9,]+(?:\.[0-9]{1,2})?)", text),
        "monthly_deductions": _amount(r"(?:Monthly\s+)?Deductions?\s*[:\-]\s*₹?\s*([0-9,]+(?:\.[0-9]{1,2})?)", text),
        "existing_emi": _amount(r"Existing\s+EMI\s*[:\-]\s*₹?\s*([0-9,]+(?:\.[0-9]{1,2})?)", text),
        "requested_loan_amount": _amount(r"(?:Requested\s+Loan\s+Amount|Loan\s+Amount)\s*[:\-]\s*₹?\s*([0-9,]+(?:\.[0-9]{1,2})?)", text),
        "requested_tenure_months": _amount(r"(?:Requested\s+)?Tenure(?:\s+Months?)?\s*[:\-]\s*([0-9]+)", text),
        "employment_type": _find(r"Employment\s+Type\s*[:\-]\s*([A-Z -]+)", text),
    }
    return kind, {k: v for k, v in fields.items() if v not in (None, "")}
