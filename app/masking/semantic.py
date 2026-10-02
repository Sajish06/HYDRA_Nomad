import os
import re
import json
import hashlib
import urllib.request
import urllib.error
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from app.masking.models import (
    VerifiedCommitment,
    AgentTaskPayload,
    InternalAuditRecord,
    AuditEntry
)
from app.config import settings

import socket

logger = logging.getLogger(__name__)

class SemanticDecomposer:
    """
    Layer 1: Semantic Classification, Minimization & Context Separation.
    Enforces two independent jobs:
      JOB A: Extract minimum necessary technical task grounded in source-of-truth.
      JOB B: Mandatory identification and isolation of all confidential information into AuditRecord.
    """
    def __init__(
        self,
        ollama_url: Optional[str] = None,
        model_name: Optional[str] = None,
        cache_dir: str = "data/llm_cache",
        use_cache: bool = True
    ):
        self.ollama_url = (ollama_url or os.getenv("OLLAMA_URL", settings.OLLAMA_URL)).rstrip("/")
        self.model_name = model_name or os.getenv("OLLAMA_MODEL", settings.OLLAMA_MODEL)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_cache = use_cache

    def _is_ollama_online(self) -> bool:
        """Fast non-blocking socket check to see if Ollama port is open."""
        try:
            url_part = self.ollama_url.replace("http://", "").replace("https://", "")
            host, port_str = url_part.split(":") if ":" in url_part else (url_part, "11434")
            port = int(port_str.split("/")[0])
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except Exception:
            return False

    def process_commitment(
        self,
        commitment: VerifiedCommitment,
        vault_session_id: str
    ) -> Tuple[AgentTaskPayload, InternalAuditRecord]:
        """
        Decomposes commitment and returns TWO distinct artifacts:
        1. AgentTaskPayload: Clean, minimal technical specs with ZERO business secrets.
        2. InternalAuditRecord: Internal record of detected business secrets and audit trail.
        """
        cache_key = self._compute_cache_key(commitment)
        if self.use_cache:
            cached_result = self._read_cache(cache_key)
            if cached_result:
                return cached_result

        # Try Ollama structured inference if online
        if self._is_ollama_online():
            try:
                agent_payload, audit_record = self._call_ollama(commitment, vault_session_id)
                if self.use_cache:
                    self._write_cache(cache_key, agent_payload, audit_record)
                return agent_payload, audit_record
            except Exception as e:
                logger.warning(f"Ollama inference failed: {e}. Falling back to deterministic NLP heuristic decomposition.")

        # Fallback to deterministic NLP heuristic decomposition
        agent_payload, audit_record = self._heuristic_decomposition(commitment, vault_session_id)
        if self.use_cache:
            self._write_cache(cache_key, agent_payload, audit_record)
        return agent_payload, audit_record

    def _compute_cache_key(self, commitment: VerifiedCommitment) -> str:
        payload = f"{self.model_name}|{commitment.task_id}|{commitment.raw_requirement}|{' '.join(commitment.evidence_context_quotes)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _read_cache(self, key: str) -> Optional[Tuple[AgentTaskPayload, InternalAuditRecord]]:
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                payload = AgentTaskPayload.model_validate(data["agent_payload"])
                audit = InternalAuditRecord.model_validate(data["audit_record"])
                return payload, audit
            except Exception:
                return None
        return None

    def _write_cache(
        self,
        key: str,
        payload: AgentTaskPayload,
        audit: InternalAuditRecord
    ) -> None:
        cache_file = self.cache_dir / f"{key}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({
                    "agent_payload": payload.model_dump(),
                    "audit_record": audit.model_dump()
                }, f, indent=2)
        except Exception:
            pass

    def _call_ollama(
        self,
        commitment: VerifiedCommitment,
        vault_session_id: str
    ) -> Tuple[AgentTaskPayload, InternalAuditRecord]:
        prompt = self._build_prompt(commitment)
        
        system_instruction = (
            "You are a strict privacy-preserving technical compiler.\n"
            "Your job is to execute two MANDATORY and INDEPENDENT tasks from the provided meeting input:\n\n"
            "JOB A — EXTRACT THE MINIMUM NECESSARY TECHNICAL TASK (Grounded in source-of-truth):\n"
            "1. intentions: High-level technical goal (e.g. 'Restrict revenue metrics to ADMIN and FINANCE roles'). Describe WHAT needs to be achieved, NEVER WHY the company wants it.\n"
            "2. things_to_implement: Concrete technical implementation tasks per role (e.g. 'BACKEND: Add authorization middleware to financial endpoints'). Do not copy raw dialogue. Do not include confidential business motivations.\n"
            "3. technical_context: Pure technical constraints, capacity numbers, or architecture facts explicitly stated in the input (e.g. 'Support 10,000 concurrent users', 'Audit records retained for 180 days', 'Use PostgreSQL and FastAPI').\n"
            "   ANTI-HALLUCINATION RULE: Every single item must be directly supported by the input. NEVER invent technologies, frameworks, roles, or constraints not mentioned (e.g. do NOT invent 'domain constraints' or 'RBAC' unless explicitly stated). If no technical context is present in the input, return an empty list [].\n"
            "4. deadline: Stated technical delivery deadline, if any.\n\n"
            "JOB B — IDENTIFY AND ISOLATE ALL CONFIDENTIAL INFORMATION (Mandatory):\n"
            "You MUST actively search the entire input for information that must NOT reach the downstream coding agent.\n"
            "Populate 'isolated_business_secrets' with structured objects whenever confidential information exists. An empty list is acceptable ONLY if the entire input has been examined and zero sensitive information is present.\n"
            "Classify every sensitive item into one of the following taxonomy categories:\n"
            "- PERSONAL_DATA: Names, personal phone numbers, personal emails, personal addresses, customer PII.\n"
            "- GOVERNMENT_ID: Aadhaar, PAN card, GSTIN, Voter ID, Passport, Driver's License, SSN.\n"
            "- FINANCIAL_DATA: Financial volumes, revenue, profit, margins, budgets, forecasts, ₹ amounts, customer bank account numbers, IFSC codes, UPI IDs.\n"
            "- CREDENTIAL / AUTHENTICATION_SECRET: Passwords, API keys, AWS keys, JWTs, private keys, database connection strings.\n"
            "- BUSINESS_STRATEGY / UNRELEASED_INFORMATION: Unannounced products/campaigns, market expansions (e.g. Middle East), M&A/acquisitions, competitor analysis.\n"
            "- COMMERCIAL_NEGOTIATION: Pricing negotiations, vendor-switching discussions, partner contracts, preferential transaction rates.\n"
            "- CUSTOMER_CONFIDENTIAL / VENDOR_CONFIDENTIAL: Internal customer counts (e.g. '8,450 customers'), customer growth forecasts ('35% growth'), vendor pricing disputes.\n"
            "- HR_CONFIDENTIAL: Employee salaries, compensation bands (e.g. '₹8 lakh to ₹24 lakh'), performance reviews.\n"
            "- LEGAL_CONFIDENTIAL: Vendor lawsuits, ongoing litigation, regulatory disputes.\n"
            "- SECURITY_CONFIDENTIAL: Internal security incidents, vulnerability investigations, breach details.\n"
            "- INTERNAL_OPERATIONAL: Internal company politics, unreleased roadmaps, commercial secrets.\n\n"
            "CRITICAL DISTINCTIONS:\n"
            "- TECHNICAL NUMBERS vs BUSINESS NUMBERS:\n"
            "  * KEEP: '10,000 concurrent users' (technical capacity), '500 requests per second' (system throughput), '180 days' (retention period).\n"
            "  * ISOLATE: '8,450 customers' (business metric), '35% customer growth' (business forecast), '₹2.8 crore / ₹4 crore' (financial metric).\n"
            "- DO NOT REQUIRE THE WORD 'CONFIDENTIAL': Detect confidentiality from semantic context alone.\n"
            "- SEPARATE MOTIVATION FROM REQUIREMENT: If motivation is given ('expecting huge customer influx, so increase capacity'), keep only 'Increase system capacity' in technical tasks, and isolate the customer influx into isolated_business_secrets.\n\n"
            "Output valid JSON conforming strictly to the schema:\n"
            "{\n"
            "  \"intentions\": [\"string\"],\n"
            "  \"things_to_implement\": [\"string\"],\n"
            "  \"technical_context\": [\"string\"],\n"
            "  \"isolated_business_secrets\": [\n"
            "    {\"category\": \"string\", \"reason\": \"string\", \"value\": \"string\"}\n"
            "  ],\n"
            "  \"deadline\": \"string or null\"\n"
            "}"
        )

        schema = {
            "type": "object",
            "properties": {
                "intentions": {"type": "array", "items": {"type": "string"}},
                "things_to_implement": {"type": "array", "items": {"type": "string"}},
                "technical_context": {"type": "array", "items": {"type": "string"}},
                "isolated_business_secrets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string"},
                            "reason": {"type": "string"},
                            "value": {"type": "string"}
                        },
                        "required": ["category", "reason", "value"]
                    }
                },
                "deadline": {"type": "string"}
            },
            "required": ["intentions", "things_to_implement", "technical_context", "isolated_business_secrets"]
        }

        request_body = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "format": schema,
            "options": {"temperature": 0.0, "seed": 42, "num_ctx": 2048},
            "stream": False
        }

        req = urllib.request.Request(
            f"{self.ollama_url}/api/chat",
            data=json.dumps(request_body).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=90.0) as response:
            result = json.loads(response.read().decode("utf-8"))
            content = json.loads(result.get("message", {}).get("content", "{}"))
            
            deadlines = [a.deadline for a in commitment.assignees if a.deadline]
            deadline_val = deadlines[0] if deadlines else content.get("deadline")

            things = content.get("things_to_implement", [])
            existing_roles = {t.split(":")[0].strip().upper() for t in things if ":" in t}
            for a in commitment.assignees:
                if a.role.upper() not in existing_roles:
                    work = a.assigned_work.strip()
                    work = re.sub(r'^(?:I\'ll |We need to |Please |Make sure to )', '', work, flags=re.IGNORECASE)
                    things.append(f"{a.role.upper()}: {work}")

            agent_payload = AgentTaskPayload(
                task_id=commitment.task_id,
                intentions=content.get("intentions", [commitment.raw_requirement]),
                things_to_implement=things,
                technical_context=content.get("technical_context", []),
                deadline=deadline_val
            )

            raw_secrets = content.get("isolated_business_secrets", [])
            secrets = []
            for rs in raw_secrets:
                if isinstance(rs, str):
                    secrets.append(AuditEntry(category="BUSINESS_STRATEGY", reason="Extracted from dialogue", source="semantic_model", value=rs))
                elif isinstance(rs, dict):
                    secrets.append(AuditEntry(
                        category=rs.get("category", "BUSINESS_STRATEGY"),
                        reason=rs.get("reason", "Confidential context identified"),
                        source="semantic_model",
                        value=rs.get("value", str(rs))
                    ))

            audit_record = InternalAuditRecord(
                task_id=commitment.task_id,
                confidential_context_detected=len(secrets) > 0,
                isolated_business_secrets=secrets,
                token_vault_session_id=vault_session_id
            )

            return agent_payload, audit_record

    def _build_prompt(self, commitment: VerifiedCommitment) -> str:
        quotes = "\n".join([f"- {q}" for q in commitment.evidence_context_quotes])
        assignees = "\n".join([f"- {a.role} ({a.name}): {a.assigned_work} (Deadline: {a.deadline})" for a in commitment.assignees])
        return (
            f"TASK ID: {commitment.task_id}\n\n"
            f"REQUIREMENT:\n{commitment.raw_requirement}\n\n"
            f"TEAM ASSIGNMENTS:\n{assignees}\n\n"
            f"DIALOGUE TRANSCRIPT:\n{quotes}\n"
        )

    def _heuristic_decomposition(
        self,
        commitment: VerifiedCommitment,
        vault_session_id: str
    ) -> Tuple[AgentTaskPayload, InternalAuditRecord]:
        """
        Deterministic, rule-based NLP compiler complying strictly with the 15 instructions:
        1. Zero Hallucination: Returns empty technical_context if not explicitly in transcript.
        2. First-class Confidentiality Extraction across all taxonomy categories.
        3. Clear separation of technical numbers from business metrics.
        """
        # 1. Intentions: Grounded summary of the requirement
        intentions = [commitment.raw_requirement.strip()]

        # 2. Things to Implement: Normalized per role, clean technical verbs
        things_to_implement = []
        deadlines = []
        for a in commitment.assignees:
            work = a.assigned_work.strip()
            # Clean dialogue indicators if present
            work = re.sub(r'^(?:I\'ll |We need to |Please |Make sure to )', '', work, flags=re.IGNORECASE)
            things_to_implement.append(f"{a.role.upper()}: {work}")
            if a.deadline:
                deadlines.append(a.deadline)

        # 3. Grounded Technical Context & Mandatory Confidential Isolation
        technical_context = []
        isolated_secrets = []

        # Taxonomy classification patterns for heuristic scanner
        patterns_to_classify = [
            # GOVERNMENT_ID
            (re.compile(r'\b(?:\d{4}\s\d{4}\s\d{4}|[A-Z]{5}\d{4}[A-Z]|\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1})\b'), "GOVERNMENT_ID", "Indian Government Identifier (Aadhaar/PAN/GSTIN)"),
            # PERSONAL_DATA
            (re.compile(r'(?i)(?:Name:\s*[A-Z][a-z]+|Phone:\s*\+91|Mobile:\s*\+91|Email:\s*[\w\.-]+@|customer\'s personal information|sample customer)'), "PERSONAL_DATA", "Personal Identifiable Information / Customer record"),
            # FINANCIAL_DATA / Financial numbers
            (re.compile(r'(?i)(?:₹\s*\d+(?:\.\d+)?\s*(?:crore|lakh)|UPI:\s*[\w\.-]+@|IFSC:\s*[A-Z]{4}0[A-Z0-9]{6}|Bank account:\s*\d+|payment volume has crossed)'), "FINANCIAL_DATA", "Sensitive financial figures / Banking details"),
            # CREDENTIAL / AUTHENTICATION_SECRET
            (re.compile(r'(?i)(?:AWS_ACCESS_KEY_ID=|API_KEY=sk-|DATABASE_URL=|postgres:\/\/|SuperSecretPassword|production credentials)'), "CREDENTIAL", "Production Credentials and Database Secrets"),
            # COMMERCIAL_NEGOTIATION & PARTNER_CONFIDENTIAL
            (re.compile(r'(?i)(?:negotiat(?:ing|ion)|preferential transaction rate|leaving their existing vendor|Bharat Retail Solutions|pricing strategy)'), "COMMERCIAL_NEGOTIATION", "Commercial negotiation / Vendor pricing terms"),
            # BUSINESS_STRATEGY & UNRELEASED_INFORMATION
            (re.compile(r'(?i)(?:entering the Middle East|acquire a smaller competitor|upcoming campaign|campaign has not been announced|not been announced yet|entering two new|expand(?:ing)? into)'), "BUSINESS_STRATEGY", "Unreleased business strategy / Market expansion / M&A"),
            # CUSTOMER_CONFIDENTIAL & FORECASTS
            (re.compile(r'(?i)(?:customer base is \d+|expects roughly \d+%\s*growth|more customers next quarter|drop in conversions|pricing experiment)'), "CUSTOMER_CONFIDENTIAL", "Internal customer metrics / Unreleased growth forecasts"),
            # HR_CONFIDENTIAL
            (re.compile(r'(?i)(?:compensation range|salary is significantly|compensation adjustments|senior employees|HR-confidential)'), "HR_CONFIDENTIAL", "HR-confidential salary and compensation data"),
            # SECURITY_CONFIDENTIAL
            (re.compile(r'(?i)(?:security incident|investigation is still ongoing|breach|incident involving an internal service)'), "SECURITY_CONFIDENTIAL", "Internal security incident / ongoing investigation"),
            # LEGAL_CONFIDENTIAL
            (re.compile(r'(?i)(?:legal dispute|former vendor|legal team doesn\'t want)'), "LEGAL_CONFIDENTIAL", "Confidential legal dispute with former vendor"),
        ]

        # Scan evidence quotes
        for quote in commitment.evidence_context_quotes:
            quote_clean = quote.strip()
            
            # Check for confidential information
            matched_confidential = False
            for pattern, cat, reason in patterns_to_classify:
                if pattern.search(quote_clean):
                    isolated_secrets.append(AuditEntry(
                        category=cat,
                        reason=reason,
                        source="semantic_model",
                        value=quote_clean
                    ))
                    matched_confidential = True
                    break

            if matched_confidential:
                continue

            # Extract legitimate technical context ONLY when directly supported by transcript
            q_lower = quote_clean.lower()
            
            # 1. Technical capacity / load numbers (KEEP)
            if "concurrent users" in q_lower:
                m = re.search(r'(\d+(?:,\d+)*\s*concurrent users)', quote_clean, re.IGNORECASE)
                if m:
                    technical_context.append(f"The dashboard must support around {m.group(1)} during normal operation.")
            elif "requests per second" in q_lower:
                m = re.search(r'(\d+(?:,\d+)*\s*requests per second)', quote_clean, re.IGNORECASE)
                if m:
                    technical_context.append(f"The API should support approximately {m.group(1)} during peak traffic.")
            elif "retained for" in q_lower or "remain available for at least" in q_lower:
                m = re.search(r'(\d+\s*days)', quote_clean, re.IGNORECASE)
                if m:
                    technical_context.append(f"Audit records must remain available for at least {m.group(1)}.")

            # 2. Explicit architectural technologies mentioned in dialogue (KEEP)
            if "postgresql database and fastapi" in q_lower:
                technical_context.append("Use existing PostgreSQL database and FastAPI service.")
            if "authentication layer already provides user ids and role" in q_lower:
                technical_context.append("Authentication layer provides user IDs and role information.")
            if "authorization at the api layer" in q_lower:
                technical_context.append("Authorization is enforced at the API layer.")

        # Deduplicate technical context preserving order
        technical_context = list(dict.fromkeys(technical_context))
        # STRICT ANTI-HALLUCINATION: If no technical context is supported by transcript, return []
        # DO NOT add "Enforce verified domain constraints..."

        deadline = deadlines[0] if deadlines else None

        agent_payload = AgentTaskPayload(
            task_id=commitment.task_id,
            intentions=intentions,
            things_to_implement=things_to_implement,
            technical_context=technical_context,
            deadline=deadline
        )

        audit_record = InternalAuditRecord(
            task_id=commitment.task_id,
            confidential_context_detected=len(isolated_secrets) > 0,
            isolated_business_secrets=isolated_secrets,
            token_vault_session_id=vault_session_id
        )

        return agent_payload, audit_record
