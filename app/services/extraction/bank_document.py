import re
from typing import Dict, Any, Optional
from app.services.extraction.base import BaseExtractor

class BankDocumentExtractor(BaseExtractor):
    """
    Extractor for Bank Statements, Deposit Slips, and Financial Records.
    """

    def extract(self, text: str, layout: Optional[Any] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        fields: Dict[str, Any] = {
            "bank_name": None,
            "account_number": None,
            "iban": None,
            "swift_bic": None,
            "statement_period": None,
            "balance": None,
            "currency": None
        }

        if not text:
            return fields

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # 1. Bank Name: Top line or keywords
        for l in lines[:4]:
            if any(kw in l.lower() for kw in ["bank", "بنك", "مصرف", "al ahly", "cib", "qnb", "misr"]):
                fields["bank_name"] = l
                break

        # 2. IBAN
        iban_match = re.search(r'\b([A-Z]{2}\d{2}[A-Z0-9]{11,30})\b', text.replace(" ", ""))
        if iban_match:
            fields["iban"] = iban_match.group(1)

        # 3. Account Number
        acc_match = re.search(r'(?:account\s*(?:no|number)|رقم\s*الحساب)\s*[:=]?\s*([0-9-]{8,20})', text, re.IGNORECASE)
        if acc_match:
            fields["account_number"] = acc_match.group(1).strip()

        # 4. SWIFT / BIC
        swift_match = re.search(r'(?:swift|bic)\s*(?:code)?\s*[:=]?\s*([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)', text, re.IGNORECASE)
        if swift_match:
            fields["swift_bic"] = swift_match.group(1).strip()

        # 5. Balance
        bal_match = re.search(r'(?:balance|closing\s*balance|الرصيد|الرصيد\s*الختامي|الرصيد\s*الحالي)\s*[:=]?\s*([\d,]+(?:\.\d{1,2})?)', text, re.IGNORECASE)
        if bal_match:
            fields["balance"] = bal_match.group(1).replace(",", "")

        # 6. Currency
        curr_match = re.search(r'\b(EGP|USD|EUR|GBP|SAR|AED|ج\.م|جنيه|دولار|ريال)\b', text, re.IGNORECASE)
        if curr_match:
            fields["currency"] = curr_match.group(1).upper()

        return {k: v for k, v in fields.items() if v is not None}
