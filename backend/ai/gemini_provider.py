"""Official Google GenAI SDK integration with structured output and safe fallbacks."""

import asyncio
import json
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from backend.ai.base import LLMProvider
from backend.ai.prompts import INTELLIGENCE_SYSTEM_PROMPT, VERIFICATION_SYSTEM_PROMPT
from backend.config import settings
from backend.logging import logger


class GeminiProvider(LLMProvider):
    """Integrates official google-genai SDK for claims verification and extraction."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        raw_key = api_key or (
            settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None
        )
        if not raw_key:
            raise ValueError(
                "Gemini API key is required when ENABLE_AI=true. Set GEMINI_API_KEY in environment."
            )

        self.model_name = model_name or settings.GEMINI_MODEL
        if not self.model_name:
            raise ValueError("GEMINI_MODEL setting must not be empty.")

        self.client = genai.Client(api_key=raw_key)

    async def _generate_json(self, system_prompt: str, user_content: str) -> Dict[str, Any]:
        """Execute model request expecting JSON response."""
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.1,
        )

        def call():
            return self.client.models.generate_content(
                model=self.model_name,
                contents=user_content,
                config=config,
            )

        try:
            response = await asyncio.to_thread(call)
            text = response.text or ""
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Gemini returned invalid JSON: {str(e)}")
            return {"error": "malformed_json", "raw_output": text[:200]}
        except Exception as e:
            logger.error(f"Gemini API call failed: {type(e).__name__}: {str(e)}")
            return {"error": "api_error", "details": str(e)}

    async def verify_claims(
        self, masked_transcript: str, masked_summary: str
    ) -> List[Dict[str, Any]]:
        user_content = f"TRANSCRIPT:\n{masked_transcript}\n\nSUMMARY:\n{masked_summary}"
        data = await self._generate_json(VERIFICATION_SYSTEM_PROMPT, user_content)

        if "error" in data:
            return [
                {
                    "id": "c_error",
                    "text": "Verification could not complete due to provider error.",
                    "claim_type": "claim",
                    "verdict": "unverifiable",
                    "confidence": 0.0,
                    "explanation": f"Provider failure: {data.get('error')}",
                    "evidence": [],
                }
            ]

        claims = data.get("claims", [])
        if not isinstance(claims, list):
            return []
        return claims

    async def extract_intelligence(
        self, masked_transcript: str, masked_summary: str
    ) -> Dict[str, Any]:
        user_content = f"TRANSCRIPT:\n{masked_transcript}\n\nSUMMARY:\n{masked_summary}"
        data = await self._generate_json(INTELLIGENCE_SYSTEM_PROMPT, user_content)

        if "error" in data:
            return {
                "financial": [],
                "deal": [],
                "business": [],
                "risks": [],
                "decisions_actions": [],
            }

        return data
