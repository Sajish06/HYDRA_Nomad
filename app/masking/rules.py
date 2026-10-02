import re
from typing import List, Tuple, Set
from app.masking.vault import LocalSecretVault

# Pre-compiled regex patterns for privacy masking
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b")
CURRENCY_PATTERN = re.compile(r"(?:\$|€|£|USD|EUR|GBP)\s*\d+(?:[.,]\d+)*(?:\s*(?:million|billion|thousand|k|m|b))?\b|\b\d+(?:[.,]\d+)*\s*(?:dollars|euros|pounds)\b", re.IGNORECASE)
PERCENT_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%\b|\b\d+(?:\.\d+)?\s*percent\b", re.IGNORECASE)
IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
URL_PATTERN = re.compile(r"https?://[^\s/$.?#].[^\s]*", re.IGNORECASE)
SECRET_PATTERN = re.compile(r"\b(?:api[_-]?key|secret|token|password|bearer\s+[A-Za-z0-9_.-]+)\b", re.IGNORECASE)

# Sensitive business terms to mask as confidential metrics
SENSITIVE_METRICS = [
    "annual recurring revenue",
    "monthly customer value",
    "average order value",
    "customer concentration",
    "revenue numbers",
    "revenue metric",
    "revenue cards",
    "sales information"
]

class MaskingRulesEngine:
    def __init__(self, vault: LocalSecretVault, known_entities: Set[str] = None):
        self.vault = vault
        self.known_entities = known_entities or set()

    def add_known_entity(self, name: str, category: str = "PERSON") -> None:
        if name and name.strip():
            clean = name.strip()
            self.known_entities.add((clean, category))

    def mask_text(self, text: str) -> Tuple[str, int]:
        """Masks sensitive elements in text and records mappings in vault. Returns (masked_text, count)."""
        if not text:
            return text, 0

        masked = text
        count = 0

        # 1. Emails
        def replace_email(match):
            nonlocal count
            count += 1
            return self.vault.register(match.group(0), "EMAIL")
        masked = EMAIL_PATTERN.sub(replace_email, masked)

        # 2. Phone numbers
        def replace_phone(match):
            nonlocal count
            count += 1
            return self.vault.register(match.group(0), "PHONE")
        masked = PHONE_PATTERN.sub(replace_phone, masked)

        # 3. Currency / Financial amounts
        def replace_currency(match):
            nonlocal count
            count += 1
            return self.vault.register(match.group(0), "CURRENCY")
        masked = CURRENCY_PATTERN.sub(replace_currency, masked)

        # 4. Percentages
        def replace_percent(match):
            nonlocal count
            count += 1
            return self.vault.register(match.group(0), "PERCENT")
        masked = PERCENT_PATTERN.sub(replace_percent, masked)

        # 5. URLs & IP addresses
        def replace_url(match):
            nonlocal count
            count += 1
            return self.vault.register(match.group(0), "URL")
        masked = URL_PATTERN.sub(replace_url, masked)

        def replace_ip(match):
            nonlocal count
            count += 1
            return self.vault.register(match.group(0), "IP")
        masked = IP_PATTERN.sub(replace_ip, masked)

        # 6. Sensitive metrics terms
        for metric in SENSITIVE_METRICS:
            pattern = re.compile(rf"\b{re.escape(metric)}\b", re.IGNORECASE)
            def replace_metric(m):
                nonlocal count
                count += 1
                return self.vault.register(m.group(0), "METRIC")
            masked = pattern.sub(replace_metric, masked)

        # 7. Known entities / Names
        for entity_tuple in sorted(self.known_entities, key=lambda x: len(x[0]), reverse=True):
            ent_name, ent_cat = entity_tuple if isinstance(entity_tuple, tuple) else (entity_tuple, "PERSON")
            if not ent_name or len(ent_name) < 2:
                continue
            pattern = re.compile(rf"\b{re.escape(ent_name)}\b", re.IGNORECASE)
            def replace_entity(m):
                nonlocal count
                count += 1
                return self.vault.register(m.group(0), ent_cat)
            masked = pattern.sub(replace_entity, masked)

        return masked, count
