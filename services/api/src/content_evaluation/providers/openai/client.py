"""OpenAI structured analysis client."""

from __future__ import annotations

import json

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from content_evaluation.domain.exceptions import ProviderError
from content_evaluation.domain.models import ArtifactBlock


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
    async def analyze(
        self,
        agent_id: str,
        instruction: str,
        title: str,
        blocks: list[ArtifactBlock],
        context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Request structured JSON from OpenAI."""

        prompt = self._build_prompt(agent_id, instruction, title, blocks, context or {})
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
                                "Return JSON only. Include a top-level 'findings' array. "
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
        if not isinstance(parsed, dict):
            raise ProviderError("OpenAI response was not a JSON object")
        findings = parsed.get("findings", [])
        if not isinstance(findings, list):
            raise ProviderError("OpenAI response had an invalid 'findings' shape")
        return parsed

    @staticmethod
    def _build_prompt(
        agent_id: str,
        instruction: str,
        title: str,
        blocks: list[ArtifactBlock],
        context: dict[str, object],
    ) -> str:
        """Build the analysis prompt for one agent."""

        joined_blocks = "\n\n".join(f"[{block.id}] {block.text}" for block in blocks)
        return (
            f"Agent: {agent_id}\n"
            f"Title: {title}\n\n"
            f"Instruction:\n{instruction}\n\n"
            f"Upstream context:\n{json.dumps(context, indent=2, ensure_ascii=True)}\n\n"
            "Analyze the document and return JSON only.\n\n"
            f"Document:\n{joined_blocks}"
        )
