import re
from typing import List, Tuple, Dict, Pattern
from app.masking.vault import EntityVault
from app.masking.models import AuditEntry

# ==============================================================================
# 1. ALLOWLIST (Safe Technical Patterns)
# ==============================================================================
TECHNICAL_ALLOWLIST: List[Pattern] = [
    # HTTP status codes
    re.compile(r'\b(?:(?:HTTP|status|code)\s*)?(?:403|404|200|500|401|400|502)(?:\s*(?:state|error|response|status))?\b', re.IGNORECASE),
    # Ports
    re.compile(r'\b(?:port)\s*(?:80|443|8080|5432|27017|6379|3000|695001)\b', re.IGNORECASE),
    # Standard numbers in technical requirements (e.g. 10,000 concurrent users)
    re.compile(r'\b\d+(?:,\d+)*\s*(?:concurrent|requests|users|rps|qps|connections|capacity)\b', re.IGNORECASE),
    # Common tech stack terms that might look like names or sensitive
    re.compile(r'\b(?:React|FastAPI|Postgres|MongoDB|Redis|OAuth 2\.0|JWT|Node)\b', re.IGNORECASE),
]

# ==============================================================================
# 2. CREDENTIALS, KEYS & SECRETS DETECTORS
# ==============================================================================
CREDENTIAL_PATTERNS: List[Tuple[Pattern, str]] = [
    # AWS Access Key ID (AKIA...)
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'), "AWS_ACCESS_KEY"),
    # Generic API Keys
    (re.compile(r'\b(?:sk-[a-zA-Z0-9_\-]{20,}|sk-ant-[a-zA-Z0-9-_]{20,}|AIza[0-9A-Za-z-_]{35}|gh[pousr]_[A-Za-z0-9_]{36,})\b'), "API_KEY"),
    # JWT Tokens (eyJhbGciOi...)
    (re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b'), "JWT_TOKEN"),
    # Database Connection URIs (postgres://, mysql://, mongodb://, redis://)
    (re.compile(r'\b(?:postgres|postgresql|mysql|mongodb|redis):\/\/[a-zA-Z0-9_:\.\-\@\%\/]+(?:\?[a-zA-Z0-9_=&]*)?\b'), "DB_CONNECTION_URI"),
    # Generic password assignments (password = "...", secret: '...')
    (re.compile(r'(?i)\b(?:password|passwd|secret|api_key|access_token|webhook_secret)\s*[:=]\s*["\']([^"\']{4,})["\']'), "PASSWORD_SECRET"),
    # Private Key Headers
    (re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'), "PRIVATE_KEY_HEADER"),
    # Generic Bearer Tokens
    (re.compile(r'\bBearer\s+([a-zA-Z0-9_\-\.]{20,})\b', re.IGNORECASE), "BEARER_TOKEN"),
    # Cloud service URLs containing credentials
    (re.compile(r'\bhttps?:\/\/[a-zA-Z0-9_]+:[a-zA-Z0-9_]+@[a-zA-Z0-9_\-\.]+\b'), "URL_WITH_CREDENTIALS"),
]

# ==============================================================================
# 3. PII & INDIA-SPECIFIC PII DETECTORS
# ==============================================================================
PII_PATTERNS: List[Tuple[Pattern, str]] = [
    # Aadhaar (XXXX XXXX XXXX)
    (re.compile(r'\b\d{4}\s\d{4}\s\d{4}\b'), "AADHAAR"),
    # PAN (5 letters, 4 digits, 1 letter)
    (re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b'), "PAN_CARD"),
    # GSTIN
    (re.compile(r'\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b'), "GSTIN"),
    # IFSC
    (re.compile(r'\b[A-Z]{4}0[A-Z0-9]{6}\b'), "IFSC_CODE"),
    # Email Addresses
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'), "EMAIL"),
    # UPI ID
    (re.compile(r'\b[a-zA-Z0-9.\-_]{2,64}@[a-zA-Z]{2,64}\b'), "UPI_ID"),
    # Indian Vehicle Registration
    (re.compile(r'\b[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}\b'), "VEHICLE_REGISTRATION"),
    # Contextual Indian PIN code
    (re.compile(r'(?:PIN|Pincode|Postal)\s*[:\-]?\s*\b([1-9][0-9]{5})\b', re.IGNORECASE), "PIN_CODE"),
    # Indian Mobile/Landline (Continuous, spaced, or hyphenated)
    (re.compile(r'(?:\+91[\-\s]?)?[6-9]\d{4}[\-\s]?\d{5}\b|\b[6-9]\d{9}\b'), "PHONE"),
    # US Social Security Number
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), "SSN"),
    # Credit Card Numbers
    (re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4,7}\b'), "CREDIT_CARD"),
    # Explicit Personal Data Context (Name/ID)
    (re.compile(r'(?:Aadhaar number is|Employee ID is|account number is|DOB is)\s+([A-Za-z0-9\-\s]+)', re.IGNORECASE), "EXPLICIT_PII"),
]

# ==============================================================================
# 4. NETWORK & INFRASTRUCTURE PATTERNS
# ==============================================================================
INFRASTRUCTURE_PATTERNS: List[Tuple[Pattern, str]] = [
    # IPv4 Addresses
    (re.compile(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'), "IP_ADDR"),
    # Internal Hostnames
    (re.compile(r'\b[a-zA-Z0-9_\-]+\.(?:internal|local|corp|lan)\b', re.IGNORECASE), "INTERNAL_HOST"),
]

# ==============================================================================
# 5. SENSITIVE FINANCIAL & CORPORATE FIGURES
# ==============================================================================
FINANCIAL_PATTERNS: List[Tuple[Pattern, str]] = [
    # Currency Figures (e.g. $185,000, €45,000, £250k, ₹10 crore, 10 Lakh INR)
    (re.compile(r'(?:\$|€|£|₹|Rs\.?)\s*\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:k|m|million|billion|crore|lakh))?\b', re.IGNORECASE), "FINANCIAL_AMOUNT"),
    # Contextual Revenue/Profit figures (e.g., revenue was 50000, margin: 20%)
    (re.compile(r'\b(?:revenue|profit|margin|sales)\s*(?:of|is|was|reached|crossed|at|growth)?\s*[:=]?\s*(?:\$|€|£|₹|Rs\.?)?\s*\d+(?:,\d+)*(?:\.\d+)?(?:\s*(?:k|m|million|billion|crore|lakh|%))?\b', re.IGNORECASE), "FINANCIAL_METRIC"),
    # Strategic percentages
    (re.compile(r'\b\d+(?:\.\d+)?%\s*(?:discount|undercut|drop|increase|more customers|margin|growth)\b', re.IGNORECASE), "STRATEGIC_PERCENTAGE"),
]

# ==============================================================================
# 6. CONFIDENTIAL BUSINESS STRATEGY & M&A PHRASES
# ==============================================================================
BUSINESS_PATTERNS: List[Tuple[Pattern, str]] = [
    (re.compile(r'\b(?:negotiating with|in talks with|acquisition of|merger with)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)', re.IGNORECASE), "PARTNER_ORG"),
    (re.compile(r'\b(?:expanding into|entering)\s+([A-Za-z0-9\s]+?)(?=\s+(?:next|soon|in|and|,|\.))', re.IGNORECASE), "EXPANSION_TARGET"),
    (re.compile(r'\b(?:internal sales information|unreleased financials|internal roadmap|pricing strategy|unannounced|kept quiet)\b', re.IGNORECASE), "CONFIDENTIAL_DOC"),
]

def mask_text_with_rules(text: str, vault: EntityVault) -> Tuple[str, List[AuditEntry]]:
    """
    Deterministic rule-based sanitizer.
    Applies regex categories, registers matches into the EntityVault,
    and replaces them with reversible placeholder tokens.
    Respects technical allowlist to prevent over-masking.
    """
    masked = text
    audit_entries: List[AuditEntry] = []

    # 1. Identify allowlist spans to avoid masking them
    safe_spans = []
    for safe_pattern in TECHNICAL_ALLOWLIST:
        for match in safe_pattern.finditer(masked):
            safe_spans.append(match.span())

    def is_safe_span(start, end):
        for s_start, s_end in safe_spans:
            if start >= s_start and end <= s_end:
                return True
        return False

    all_rule_groups = [
        CREDENTIAL_PATTERNS,
        PII_PATTERNS,
        INFRASTRUCTURE_PATTERNS,
        FINANCIAL_PATTERNS,
        BUSINESS_PATTERNS
    ]

    for group in all_rule_groups:
        for pattern, category in group:
            # We must finditer dynamically because masked text changes length,
            # but for simplicity, we find all matches first and replace them if they are not safe.
            # A more robust way is to re-evaluate or just use string replace.
            # Using finditer on current masked state:
            matches = list(pattern.finditer(masked))
            # Sort matches in reverse order so replacements don't mess up indices
            matches.sort(key=lambda m: m.start(), reverse=True)
            
            for match in matches:
                # Extract targeted group if captured, otherwise full match
                secret_value = match.group(1) if match.groups() else match.group(0)
                if not secret_value or len(secret_value.strip()) < 2:
                    continue
                # Do not re-mask existing tokens like [API_KEY_1]
                if secret_value.startswith("[") and secret_value.endswith("]"):
                    continue
                
                # Check against allowlist (using original text coordinates approximately)
                # If the match is entirely within a safe span, skip it
                if is_safe_span(match.start(), match.end()):
                    continue
                
                token = vault.get_or_create_token(secret_value, category)
                
                # Replace exactly this occurrence
                masked = masked[:match.start()] + masked[match.start():].replace(secret_value, token, 1)
                
                audit_entries.append(AuditEntry(
                    category=category,
                    reason=f"Matched deterministic regex rule for {category}",
                    source="deterministic_rule",
                    value=secret_value
                ))

    return masked, audit_entries
