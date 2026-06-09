"""Groq LLM client for distribution summarisation and interactive tool-calling chat.

Wraps the Groq async SDK with two high-level methods:
  - generate_distribution_summary: German-language narrative from a DistributionReport.
  - chat_with_tools: Raw tool-calling completion for the interactive chat CLI.

All prompt text is defined as module-level constants so it can be reviewed and
adjusted without touching business logic.
"""

# Standard library
import logging
from types import TracebackType
from typing import Any, cast

# Third-party
import groq
import groq.types.chat

# Local
from dip_mcp.api.models import DistributionReport
from dip_mcp.config import Settings, get_logger
from dip_mcp.core.analytics import format_distribution_as_text

SUMMARY_SYSTEM_PROMPT: str = (
    "You are a political analyst assistant specializing in the German Bundestag. "
    "You receive structured data about parliamentary group distributions and produce "
    "clear, accurate, professional German-language summaries. "
    "You always cite the exact numbers and percentages from the data provided. "
    "You do not invent or extrapolate beyond the data given."
)

SUMMARY_USER_TEMPLATE: str = (
    "Analysiere die folgende Fraktionsverteilung des Deutschen Bundestags für die "
    "{wahlperiode}. Wahlperiode und schreibe eine professionelle Auswertung auf Deutsch. "
    "Nenne alle Fraktionen mit ihren genauen Mitgliederzahlen und prozentualen Anteilen. "
    "Gehe auf die stärksten und schwächsten Fraktionen ein.\n\n"
    "{distribution_text}"
)

CHAT_SYSTEM_PROMPT: str = (
    "You are a parliamentary information assistant. You have access to tools to look up "
    "Fraktion distribution data and politician biographical information from the German "
    "Bundestag DIP database. Use these tools to answer user questions accurately. "
    "Always respond in the same language the user used."
)

MAX_TOKENS: int = 1024
TEMPERATURE: float = 0.3


class GroqClient:
    """Async wrapper around the Groq SDK for LLM summarisation and tool-calling.

    Use as an async context manager to ensure the underlying HTTP client
    is properly closed after use.

    Attributes:
        _client: Underlying Groq async API client.
        _model: Groq model identifier resolved from settings.
        _log: Module-level logger.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialise the Groq client from application configuration.

        Args:
            settings: Application configuration providing the Groq API key and model.
        """
        self._client: groq.AsyncGroq = groq.AsyncGroq(
            api_key=settings.groq_api_key
        )
        self._model: str = settings.groq_model
        self._fallback_model: str = settings.groq_fallback_model
        self._log: logging.Logger = get_logger(__name__)

    async def __aenter__(self) -> "GroqClient":
        """Enter the async context manager.

        Returns:
            The initialised GroqClient instance ready for requests.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager and close the underlying HTTP client.

        Args:
            exc_type: Exception class raised inside the context, or None.
            exc_val: Exception instance raised inside the context, or None.
            exc_tb: Traceback of the exception, or None.
        """
        await self._client.close()

    async def _complete(self, **kwargs: Any) -> groq.types.chat.ChatCompletion:
        """Call chat.completions.create with automatic fallback on rate-limit.

        Tries the primary model first. If Groq returns a 429 rate-limit error,
        retries once with the configured fallback model.

        Args:
            **kwargs: Arguments forwarded to chat.completions.create (excluding model).

        Returns:
            ChatCompletion from whichever model succeeded.

        Raises:
            groq.RateLimitError: If the fallback model is also rate-limited.
            groq.APIError: On any other Groq API failure.
        """
        try:
            raw = await self._client.chat.completions.create(model=self._model, **kwargs)
        except groq.RateLimitError:
            self._log.warning(
                "Rate limit hit on %s — retrying with fallback model %s",
                self._model,
                self._fallback_model,
            )
            raw = await self._client.chat.completions.create(
                model=self._fallback_model, **kwargs
            )
        return cast(groq.types.chat.ChatCompletion, raw)

    async def generate_distribution_summary(
        self,
        report: DistributionReport,
    ) -> str:
        """Generate a German-language narrative summary of a distribution report.

        Formats the report as plain text, sends it to the configured Groq model
        with the analyst system prompt, and returns the generated analysis.

        Args:
            report: The Fraktion distribution report to summarise.

        Returns:
            Professional German-language analysis as a plain string.
            Returns an empty string if the model produces no content.

        Raises:
            groq.APIError: On Groq API failure after the request is sent.
        """
        user_message = SUMMARY_USER_TEMPLATE.format(
            wahlperiode=report.wahlperiode,
            distribution_text=format_distribution_as_text(report),
        )

        try:
            response = await self._complete(
                messages=[
                    {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
            )
        except groq.APIError as exc:
            self._log.error("Groq API error during summary generation: %s", exc)
            raise

        content = response.choices[0].message.content
        return content if content is not None else ""

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> groq.types.chat.ChatCompletion:
        """Send a tool-calling chat request and return the raw completion.

        The caller is responsible for inspecting tool_calls in the response,
        executing the chosen MCP tools, and sending the results back.

        Args:
            messages: Conversation history in OpenAI-compatible message format.
            tools: Tool schemas in OpenAI function-calling format.

        Returns:
            Raw ChatCompletion response, which may include tool_calls in choices.

        Raises:
            groq.APIError: On Groq API failure after the request is sent.
        """
        try:
            return await self._complete(  # type: ignore[call-overload]
                messages=messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
            )
        except groq.APIError as exc:
            self._log.error("Groq API error during tool-calling chat: %s", exc)
            raise
