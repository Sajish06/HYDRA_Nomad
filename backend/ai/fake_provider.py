"""Deterministic FakeProvider for testing and offline execution."""

from typing import Any, Dict, List

from backend.ai.base import LLMProvider


class FakeProvider(LLMProvider):
    """Configurable mock AI provider for testing edge cases."""

    def __init__(self, mode: str = "good"):
        self.mode = mode

    async def verify_claims(
        self, masked_transcript: str, masked_summary: str
    ) -> List[Dict[str, Any]]:
        if self.mode == "malformed_json":
            raise ValueError("Malformed AI response: Invalid JSON syntax from upstream provider.")

        if self.mode == "invented_quote":
            return [
                {
                    "id": "c_invented",
                    "text": "The company has 500 offices worldwide.",
                    "claim_type": "claim",
                    "verdict": "supported",
                    "confidence": 0.95,
                    "explanation": "Stated by CEO in opening remarks.",
                    "evidence": [
                        {
                            "text": "We operate over 500 offices on Mars and Neptune.",
                            "speaker": "CEO",
                            "timestamp": "00:01:00",
                        }
                    ],
                }
            ]

        if self.mode == "contradicts_local":
            # The AI falsely claims "$50,000 was approved" is supported by "fifteen thousand" quote
            return [
                {
                    "id": "c_number_test",
                    "text": "$50,000 vendor payment approved by finance.",
                    "claim_type": "claim",
                    "verdict": "supported",  # AI incorrectly hallucinated supported
                    "confidence": 0.90,
                    "explanation": "Approved during diligence review.",
                    "evidence": [
                        {
                            "text": "I approve the fifteen thousand dollars expense.",
                            "speaker": "Sarah Chen",
                            "timestamp": "00:04:15",
                        }
                    ],
                }
            ]

        # Default "good" mode
        return [
            {
                "id": "c1",
                "text": "Target reported EBITDA of 4.2 million.",
                "claim_type": "claim",
                "verdict": "supported",
                "confidence": 0.95,
                "explanation": "Explicitly confirmed by CFO in segment 2.",
                "evidence": [
                    {
                        "text": "EBITDA was 4.2 million.",
                        "speaker": "Speaker 1",
                        "timestamp": "00:02:15",
                    }
                ],
            }
        ]

    async def extract_intelligence(
        self, masked_transcript: str, masked_summary: str
    ) -> Dict[str, Any]:
        return {
            "financial": [
                {
                    "category": "financial",
                    "metric_or_topic": "EBITDA",
                    "value_description": "4.2 million",
                    "period": "FY23",
                    "unit_or_currency": "USD",
                    "confidence": 0.95,
                    "basis": "explicit",
                    "evidence_quote": "EBITDA was 4.2 million.",
                }
            ],
            "deal": [
                {
                    "category": "deal",
                    "metric_or_topic": "Structure",
                    "value_description": "Asset purchase with 10% holdback",
                    "period": None,
                    "unit_or_currency": None,
                    "confidence": 0.85,
                    "basis": "explicit",
                    "evidence_quote": "We agreed on an asset purchase structure with a 10% escrow.",
                }
            ],
            "business": [
                {
                    "category": "business",
                    "metric_or_topic": "Core Product",
                    "value_description": "Enterprise behavioral intelligence platform",
                    "period": None,
                    "unit_or_currency": None,
                    "confidence": 0.9,
                    "basis": "explicit",
                    "evidence_quote": "Our core SaaS platform focuses on behavioral data analytics.",
                }
            ],
            "risks": [
                {
                    "category": "risk",
                    "metric_or_topic": "Customer Concentration",
                    "value_description": "Top 2 enterprise clients generate 45% of annual revenue",
                    "period": None,
                    "unit_or_currency": "%",
                    "confidence": 0.9,
                    "basis": "explicit",
                    "evidence_quote": "Two clients account for forty-five percent of our revenue.",
                }
            ],
            "decisions_actions": [
                {
                    "category": "decision_action",
                    "metric_or_topic": "Diligence Data Room",
                    "value_description": "Send customer concentration data by Friday",
                    "owner": "[PERSON_1]",
                    "due_date": "Friday",
                    "confidence": 0.9,
                    "basis": "explicit",
                    "evidence_quote": "Priya sends customer concentration data by Friday.",
                }
            ],
        }
