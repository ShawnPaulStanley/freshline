"""
Groq LLM Client — sends optimized context to Groq's API and parses responses.
Uses llama-3.3-70b-versatile on the free tier.

Uses marker-delimited output format instead of JSON to avoid escaping issues
with code that contains quotes, backslashes, and nested strings.
"""

import re
import time
from groq import Groq

from app.config import GROQ_API_KEY, GROQ_MODEL, GROQ_MAX_TOKENS, GROQ_TEMPERATURE


class GroqClient:
    """Wrapper around the Groq SDK for code modernization tasks."""

    def __init__(self):
        if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
            raise ValueError(
                "GROQ_API_KEY not set! Get a free key from https://console.groq.com\n"
                "Then set it in freshline/.env"
            )

        self.client = Groq(api_key=GROQ_API_KEY)
        self.model = GROQ_MODEL
        self._request_count = 0
        self._last_request_time = 0.0

    def send(self, system_prompt: str, user_prompt: str) -> dict:
        """Send a prompt to Groq and return the parsed response.

        Returns:
            Dict with keys: code, explanation, confidence, confidence_notes
        """
        # Rate limiting: max 30 req/min on free tier
        self._rate_limit()

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=GROQ_MAX_TOKENS,
                temperature=GROQ_TEMPERATURE,
                # NO response_format=json_object — that causes escaping failures
                # with code that contains quotes/backslashes
            )

            raw = response.choices[0].message.content
            return self._parse_response(raw)

        except Exception as e:
            return {
                "code": f"# ERROR: LLM call failed: {e}",
                "explanation": f"Error: {e}",
                "confidence": 0.0,
                "confidence_notes": f"LLM call failed: {e}",
            }

    def _parse_response(self, raw: str) -> dict:
        """Parse the LLM's marker-delimited response.

        Expected format:
            ===PYTHON_CODE_START===
            (code)
            ===PYTHON_CODE_END===
            ===EXPLANATION_START===
            (explanation)
            ===EXPLANATION_END===
            ===CONFIDENCE===
            0.85
            ===CONFIDENCE_NOTES===
            (notes)
        """
        # Extract code between markers
        code = self._extract_between(raw, "===PYTHON_CODE_START===", "===PYTHON_CODE_END===")

        # If markers aren't found, try markdown code block fallback
        if not code:
            code_match = re.search(r"```python\n(.*?)```", raw, re.DOTALL)
            if code_match:
                code = code_match.group(1).strip()
            else:
                # Last resort: use the raw response
                code = raw.strip()

        # Extract explanation
        explanation = self._extract_between(raw, "===EXPLANATION_START===", "===EXPLANATION_END===")
        if not explanation:
            explanation = "Conversion completed."

        # Extract confidence score
        confidence = 0.5  # Default
        conf_match = re.search(r"===CONFIDENCE===\s*([\d.]+)", raw)
        if conf_match:
            try:
                confidence = float(conf_match.group(1))
                confidence = max(0.0, min(1.0, confidence))
            except ValueError:
                confidence = 0.5

        # Extract confidence notes
        conf_notes = self._extract_after(raw, "===CONFIDENCE_NOTES===")
        if not conf_notes:
            conf_notes = ""

        return {
            "code": code,
            "explanation": explanation,
            "confidence": confidence,
            "confidence_notes": conf_notes,
        }

    def _extract_between(self, text: str, start_marker: str, end_marker: str) -> str:
        """Extract text between two markers."""
        start_idx = text.find(start_marker)
        if start_idx == -1:
            return ""
        start_idx += len(start_marker)

        end_idx = text.find(end_marker, start_idx)
        if end_idx == -1:
            return text[start_idx:].strip()

        return text[start_idx:end_idx].strip()

    def _extract_after(self, text: str, marker: str) -> str:
        """Extract text after a marker (until end or next === marker)."""
        idx = text.find(marker)
        if idx == -1:
            return ""
        idx += len(marker)
        remaining = text[idx:].strip()

        # Stop at next === marker if present
        next_marker = remaining.find("===")
        if next_marker != -1:
            return remaining[:next_marker].strip()
        return remaining.strip()

    def _rate_limit(self):
        """Simple rate limiter: ensure minimum 2 seconds between requests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < 2.0:
            time.sleep(2.0 - elapsed)
        self._last_request_time = time.time()
        self._request_count += 1
