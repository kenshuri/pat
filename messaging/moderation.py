import re

_FINANCIAL_PATTERNS = re.compile(
    r'\b(iban|bic|swift|virement|western\s*union|moneygram|paypal\.me|'
    r'[a-z]{2}\d{2}[\s\d]{10,30}|'  # IBAN-like sequences
    r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b)',  # card-like numbers
    re.IGNORECASE,
)

_LINK_PATTERN = re.compile(r'https?://', re.IGNORECASE)


def check_financial_patterns(text: str) -> bool:
    return bool(_FINANCIAL_PATTERNS.search(text))


def check_external_links(text: str) -> bool:
    return bool(_LINK_PATTERN.search(text))
