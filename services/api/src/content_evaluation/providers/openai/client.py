"""OpenAI structured analysis client."""

from __future__ import annotations

import json

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from content_evaluation.domain.exceptions import ProviderError
from content_evaluation.domain.models import AgentCategory, DocumentBlock


class OpenAIAnalysisProvider:
    """Call OpenAI for structured analysis findings."""

    def __init__(self, api_key: str, *, model_name: str = "gpt-4.1-mini", timeout_seconds: float = 45.0) -> None:
        """Initialize the OpenAI client."""

        self._api_key = api_key
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds

    @property
    def model_name(self) -> str:
        """Expose the configured model name."""

        return self._model_name

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=6),
        retry=retry_if_exception_type((httpx.HTTPError, ProviderError)),
        reraise=True,
    )
    async def analyze_category(
        self,
        category: AgentCategory,
        title: str,
        blocks: list[DocumentBlock],
    ) -> list[dict[str, object]]:
        """Request structured findings from OpenAI."""

        prompt = self._build_prompt(category, title, blocks)
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model_name,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a structured editorial analysis agent. "
                                "Return JSON only with a top-level 'findings' array. "
                                "Each finding must include excerpt, rationale, confidence, and suggestion."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
            )
        if response.status_code >= 400:
            raise ProviderError(f"OpenAI request failed with status {response.status_code}")
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        if not content:
            raise ProviderError("OpenAI returned empty content")
        parsed = json.loads(content)
        findings = parsed.get("findings", [])
        if not isinstance(findings, list):
            raise ProviderError("OpenAI response had an invalid 'findings' shape")
        return findings

    @staticmethod
    def _build_prompt(category: AgentCategory, title: str, blocks: list[DocumentBlock]) -> str:
        """Build the analysis prompt for one category."""

        joined_blocks = "\n\n".join(f"[{block.id}] {block.text}" for block in blocks)
        return (
            f"Title: {title}\n"
            f"Category: {category.value}\n\n"
            "Analyze the document. Return 1-3 findings.\n"
            "Each finding must include:\n"
            "- excerpt: exact quoted text from the document\n"
            "- rationale: short explanation\n"
            "- confidence: number from 0 to 1\n"
            "- suggestion: optional editorial recommendation\n\n"
            f"Document:\n{joined_blocks}"
        )
