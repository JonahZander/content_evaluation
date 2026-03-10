"""OpenAI provider tests."""

import pytest
import respx
from httpx import Response

from content_evaluation.domain.models import AgentCategory, DocumentBlock
from content_evaluation.providers.openai.client import OpenAIAnalysisProvider


@pytest.mark.asyncio
async def test_openai_provider_parses_structured_findings() -> None:
    """Parse JSON findings from OpenAI."""

    provider = OpenAIAnalysisProvider("key")
    with respx.mock(assert_all_called=True) as router:
        route = router.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": '{"findings":[{"excerpt":"Alpha","rationale":"Reason","confidence":0.8,"suggestion":"Trim"}]}'
                            }
                        }
                    ]
                },
            )
        )
        findings = await provider.analyze_category(AgentCategory.VALUE, "Title", [DocumentBlock(index=0, text="Alpha text")])

    assert route.called
    assert findings[0]["rationale"] == "Reason"
