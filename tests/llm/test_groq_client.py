"""Unit tests for the Groq LLM client wrapper.

All Groq API calls are mocked via pytest-mock so no real API keys or network
access are required.
"""

# Standard library
from unittest.mock import AsyncMock, MagicMock

# Third-party
import groq
import httpx
import pytest
from pytest_mock import MockerFixture

# Local
from dip_mcp.config import Settings
from dip_mcp.llm.groq_client import GroqClient


def _make_completion(content: str | None = "Test answer") -> MagicMock:
    """Build a minimal ChatCompletion mock with the given message content.

    Args:
        content: Message content string, or None to simulate an empty response.

    Returns:
        MagicMock shaped like groq.types.chat.ChatCompletion.
    """
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message.content = content
    choice.message.tool_calls = None

    completion = MagicMock()
    completion.choices = [choice]
    return completion


async def test_generate_distribution_summary_returns_string(
    mocker: MockerFixture,
    mock_settings: Settings,
    sample_fraktion_distribution_report: object,
) -> None:
    """Test that generate_distribution_summary returns the model's text content.

    Args:
        mocker: pytest-mock fixture for patching.
        mock_settings: Session-scoped Settings fixture from conftest.
        sample_fraktion_distribution_report: Pre-built DistributionReport fixture.
    """
    from dip_mcp.api.models import DistributionReport

    mock_async_groq = MagicMock()
    mock_async_groq.chat.completions.create = AsyncMock(
        return_value=_make_completion("SPD und CDU/CSU teilen sich die Mandate.")
    )
    mock_async_groq.close = AsyncMock()

    mocker.patch("groq.AsyncGroq", return_value=mock_async_groq)

    report: DistributionReport = sample_fraktion_distribution_report  # type: ignore[assignment]

    async with GroqClient(mock_settings) as client:
        result = await client.generate_distribution_summary(report)

    assert isinstance(result, str)
    assert "SPD" in result
    mock_async_groq.chat.completions.create.assert_awaited_once()


async def test_generate_distribution_summary_raises_on_api_error(
    mocker: MockerFixture,
    mock_settings: Settings,
    sample_fraktion_distribution_report: object,
) -> None:
    """Test that groq.APIError propagates without being swallowed.

    Args:
        mocker: pytest-mock fixture for patching.
        mock_settings: Session-scoped Settings fixture from conftest.
        sample_fraktion_distribution_report: Pre-built DistributionReport fixture.
    """
    from dip_mcp.api.models import DistributionReport

    api_error = groq.APIConnectionError(
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    )
    mock_async_groq = MagicMock()
    mock_async_groq.chat.completions.create = AsyncMock(side_effect=api_error)
    mock_async_groq.close = AsyncMock()

    mocker.patch("groq.AsyncGroq", return_value=mock_async_groq)

    report: DistributionReport = sample_fraktion_distribution_report  # type: ignore[assignment]

    async with GroqClient(mock_settings) as client:
        with pytest.raises(groq.APIError):
            await client.generate_distribution_summary(report)


async def test_rate_limit_falls_back_to_fallback_model(
    mocker: MockerFixture,
    mock_settings: Settings,
    sample_fraktion_distribution_report: object,
) -> None:
    """Test that a RateLimitError on the primary model retries with the fallback model.

    Args:
        mocker: pytest-mock fixture for patching.
        mock_settings: Session-scoped Settings fixture from conftest.
        sample_fraktion_distribution_report: Pre-built DistributionReport fixture.
    """
    from dip_mcp.api.models import DistributionReport

    rate_limit_error = groq.RateLimitError(
        message="rate limit",
        response=MagicMock(status_code=429, headers={}),
        body={},
    )
    mock_async_groq = MagicMock()
    mock_async_groq.chat.completions.create = AsyncMock(
        side_effect=[rate_limit_error, _make_completion("Fallback answer")]
    )
    mock_async_groq.close = AsyncMock()
    mocker.patch("groq.AsyncGroq", return_value=mock_async_groq)

    report: DistributionReport = sample_fraktion_distribution_report  # type: ignore[assignment]

    async with GroqClient(mock_settings) as client:
        result = await client.generate_distribution_summary(report)

    assert mock_async_groq.chat.completions.create.await_count == 2
    assert result == "Fallback answer"


async def test_chat_with_tools_raises_on_api_error(
    mocker: MockerFixture,
    mock_settings: Settings,
) -> None:
    """Test that chat_with_tools re-raises groq.APIError without swallowing it.

    Args:
        mocker: pytest-mock fixture for patching.
        mock_settings: Session-scoped Settings fixture from conftest.
    """
    api_error = groq.APIConnectionError(
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    )
    mock_async_groq = MagicMock()
    mock_async_groq.chat.completions.create = AsyncMock(side_effect=api_error)
    mock_async_groq.close = AsyncMock()
    mocker.patch("groq.AsyncGroq", return_value=mock_async_groq)

    async with GroqClient(mock_settings) as client:
        with pytest.raises(groq.APIError):
            await client.chat_with_tools([{"role": "user", "content": "test"}], [])


async def test_chat_with_tools_returns_completion(
    mocker: MockerFixture,
    mock_settings: Settings,
) -> None:
    """Test that chat_with_tools returns the raw ChatCompletion from Groq.

    Args:
        mocker: pytest-mock fixture for patching.
        mock_settings: Session-scoped Settings fixture from conftest.
    """
    mock_completion = _make_completion("Die Fraktion CDU/CSU hat 40% der Sitze.")

    mock_async_groq = MagicMock()
    mock_async_groq.chat.completions.create = AsyncMock(return_value=mock_completion)
    mock_async_groq.close = AsyncMock()

    mocker.patch("groq.AsyncGroq", return_value=mock_async_groq)

    messages = [{"role": "user", "content": "Wie ist die Fraktionsverteilung?"}]
    tools: list = []

    async with GroqClient(mock_settings) as client:
        result = await client.chat_with_tools(messages, tools)

    assert result is mock_completion
    assert result.choices[0].message.content == "Die Fraktion CDU/CSU hat 40% der Sitze."
    mock_async_groq.chat.completions.create.assert_awaited_once()
