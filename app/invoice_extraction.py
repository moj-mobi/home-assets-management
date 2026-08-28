"""Replaceable, local-only receipt text extraction and conservative field parsing."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re


@dataclass
class InvoiceItem:
    name: str
    price: Decimal | None = None
    confidence: str = "low"


@dataclass
class InvoiceData:
    seller: str | None = None
    purchase_date: date | None = None
    invoice_number: str | None = None
    order_number: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    total: Decimal | None = None
    currency: str | None = None
    warranty_months: int | None = None
    items: list[InvoiceItem] = field(default_factory=list)
    warning: str | None = None


class InvoiceExtractor:
    def extract_text(self, content: bytes, mime_type: str) -> str:
        raise NotImplementedError

    def extract(self, content: bytes, mime_type: str) -> InvoiceData:
        try:
            return parse_invoice_text(self.extract_text(content, mime_type))
        except Exception:
            return InvoiceData(warning="Besedila ni bilo mogoče samodejno prepoznati; nadaljujte z ročnim vnosom.")


class LocalInvoiceExtractor(InvoiceExtractor):
    def extract_text(self, content: bytes, mime_type: str) -> str:
        if mime_type == "application/pdf":
            from pypdf import PdfReader
            return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
        try:
            import pytesseract
            from PIL import Image
            return pytesseract.image_to_string(Image.open(BytesIO(content)), lang="slv+eng")
        except (ImportError, OSError):
            return ""


def parse_invoice_text(text: str) -> InvoiceData:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    data = InvoiceData(seller=lines[0][:200] if lines else None)
    joined = "\n".join(lines)
    patterns = {
        "invoice_number": r"(?i)(?:invoice|račun|racun)\s*(?:no\.?|št\.?|st\.?)?\s*[:#]?\s*([\w\-/]+)",
        "order_number": r"(?i)(?:order|naročil[oa])\s*(?:no\.?|št\.?|st\.?)?\s*[:#]?\s*([\w\-/]+)",
        "serial_number": r"(?i)(?:serial|serijska)\s*(?:no\.?|št\.?|st\.?)?\s*[:#]?\s*([\w\-/]+)",
        "model": r"(?i)model\s*[:#]?\s*([\w .\-/]+)",
    }
    for field_name, pattern in patterns.items():
        match = re.search(pattern, joined)
        if match:
            setattr(data, field_name, match.group(1).strip()[:150])
    dm = re.search(r"(?i)(?:date|datum)\s*:?\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})", joined)
    if dm:
        try: data.purchase_date = date(int(dm[3]), int(dm[2]), int(dm[1]))
        except ValueError: pass
    wm = re.search(r"(?i)(?:warranty|garancij\w*)[^\d]{0,20}(\d{1,3})\s*(?:months?|mesecev|mesec)", joined)
    if wm: data.warranty_months = int(wm[1])
    money = re.compile(r"(?i)(.+?)\s+(\d+[.,]\d{2})\s*(EUR|€|USD|GBP)\s*$")
    for line in lines:
        match = money.match(line)
        if match and not re.search(r"(?i)total|skupaj|subtotal|ddv|tax", match[1]):
            try: data.items.append(InvoiceItem(match[1].strip()[:200], Decimal(match[2].replace(",", ".")), "medium"))
            except InvalidOperation: pass
    total = re.search(r"(?im)(?:total|skupaj)\D{0,20}(\d+[.,]\d{2})\s*(EUR|€|USD|GBP)?", joined)
    if total:
        data.total = Decimal(total[1].replace(",", ".")); data.currency = "EUR" if total[2] in {None, "€"} else total[2].upper()
    if not text.strip(): data.warning = "OCR ni na voljo ali dokument ne vsebuje strojno berljivega besedila. Podatke vnesite ročno."
    return data
