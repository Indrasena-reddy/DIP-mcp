"""Central configuration module for dip-mcp.

Loaded once at import time. All downstream modules read settings from
this module — never via direct os.environ calls.
"""

# Standard library
import logging

# Third-party
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VALID_LOG_LEVELS: frozenset[str] = frozenset(
    {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
)

_logging_configured: bool = False


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file.

    Attributes:
        dip_api_key: DIP Bundestag API key.
        groq_api_key: Groq API key.
        dip_api_base_url: Base URL for the DIP API.
        groq_model: Groq model identifier.
        log_level: Python logging level name.
        request_timeout_seconds: httpx request timeout in seconds.
        max_concurrent_requests: Semaphore limit for parallel API calls.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    dip_api_key: str
    groq_api_key: str
    dip_api_base_url: str = "https://search.dip.bundestag.de/api/v1"
    groq_model: str = "llama-3.3-70b-versatile"
    log_level: str = "INFO"
    request_timeout_seconds: int = 30
    max_concurrent_requests: int = 5

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Validate that log_level is a recognised Python logging level.

        Args:
            value: The log level string to validate.

        Returns:
            The uppercased log level string if valid.

        Raises:
            ValueError: If value is not one of DEBUG, INFO, WARNING, ERROR, CRITICAL.
        """
        upper = value.upper()
        if upper not in VALID_LOG_LEVELS:
            raise ValueError(
                f"Invalid log_level '{value}'. "
                f"Must be one of: {', '.join(sorted(VALID_LOG_LEVELS))}."
            )
        return upper


settings: Settings = Settings()  # type: ignore[call-arg]  # values come from env


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for the given name.

    Configures the root logger on first call using settings.log_level.
    Subsequent calls reuse the existing configuration.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        A standard library Logger instance bound to name.
    """
    global _logging_configured  # noqa: PLW0603
    if not _logging_configured:
        logging.basicConfig(
            level=settings.log_level,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
        _logging_configured = True
    return logging.getLogger(name)
