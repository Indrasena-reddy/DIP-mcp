"""Async HTTP client for the DIP Bundestag parliamentary data API.

Handles cursor-based pagination, bounded concurrency via anyio.CapacityLimiter,
and transient HTTP error retries via tenacity. All public methods are safe to
call concurrently — the semaphore prevents overloading the upstream API.
"""

# Standard library
import logging
from types import TracebackType
from typing import Any

# Third-party
import anyio
import anyio.abc
import httpx
import tenacity
from pydantic import ValidationError

# Local
from dip_mcp.api.models import Person
from dip_mcp.config import Settings, get_logger

DEFAULT_PAGE_SIZE: int = 100
MAX_PAGES: int = 50
DEFAULT_WAHLPERIODE: int = 20


class DipApiClient:
    """Async HTTP client for the DIP Bundestag parliamentary data API.

    Fetches person and Fraktion data with transparent cursor-based pagination.
    Use as an async context manager to ensure the underlying HTTP connection
    pool is opened and closed correctly.

    Attributes:
        _settings: Application configuration.
        _client: Underlying httpx async client.
        _semaphore: Capacity limiter bounding parallel API requests.
        _log: Module-level logger.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialise the client from application configuration.

        Args:
            settings: Application configuration providing API credentials,
                base URL, timeout, and concurrency limits.
        """
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.dip_api_base_url,
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            headers={"Accept": "application/json"},
        )
        self._semaphore: anyio.abc.CapacityLimiter = anyio.CapacityLimiter(
            settings.max_concurrent_requests
        )
        self._log: logging.Logger = get_logger(__name__)

    async def __aenter__(self) -> "DipApiClient":
        """Open the HTTP connection pool.

        Returns:
            The initialised DipApiClient instance ready for requests.
        """
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the HTTP connection pool.

        Args:
            exc_type: Exception class raised inside the context, or None.
            exc_val: Exception instance raised inside the context, or None.
            exc_tb: Traceback of the exception, or None.
        """
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
        retry=tenacity.retry_if_exception(
            lambda exc: isinstance(exc, httpx.HTTPStatusError)
            and exc.response.status_code >= 500
        ),
        reraise=True,
    )
    async def _get(
        self,
        endpoint: str,
        params: dict[str, str | int],
    ) -> dict[str, Any]:
        """Perform a single authenticated GET request with retry on HTTP errors.

        The API key is injected here — callers must never include it in params.
        Concurrency is bounded by self._semaphore.

        Args:
            endpoint: API path relative to the base URL, e.g. "/person".
            params: Query parameters, excluding apikey.

        Returns:
            Parsed JSON response body as a dictionary.

        Raises:
            httpx.HTTPStatusError: On a non-2xx response after all retry attempts.
        """
        full_params: dict[str, str | int] = {
            **params,
            "apikey": self._settings.dip_api_key,
        }
        async with self._semaphore:
            response = await self._client.get(endpoint, params=full_params)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result

    async def _fetch_page(
        self,
        endpoint: str,
        params: dict[str, str | int],
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Fetch one page from a paginated endpoint.

        Args:
            endpoint: API path relative to the base URL.
            params: Base query parameters, excluding cursor and apikey.
            cursor: Opaque pagination cursor from the previous response,
                or None for the first page.

        Returns:
            A tuple of (documents, next_cursor) where next_cursor is None
            when the last page has been reached.
        """
        page_params: dict[str, str | int] = dict(params)
        if cursor is not None:
            page_params["cursor"] = cursor

        raw = await self._get(endpoint, page_params)

        documents: list[dict[str, Any]] = raw.get("documents", [])
        raw_cursor = raw.get("cursor")
        next_cursor: str | None = str(raw_cursor) if raw_cursor else None

        return documents, next_cursor

    async def _fetch_all_pages(
        self,
        endpoint: str,
        params: dict[str, str | int],
    ) -> list[dict[str, Any]]:
        """Fetch every page from a paginated endpoint by following cursors.

        Pages are fetched sequentially because each cursor is only available
        after its predecessor has been received. Stops at MAX_PAGES to guard
        against unexpected API behaviour causing an infinite loop.

        Args:
            endpoint: API path relative to the base URL.
            params: Base query parameters, excluding cursor and apikey.

        Returns:
            Flat list of all document dictionaries from every page.
        """
        all_documents: list[dict[str, Any]] = []
        cursor: str | None = None
        page_count = 0

        while page_count < MAX_PAGES:
            documents, cursor = await self._fetch_page(endpoint, params, cursor)
            all_documents.extend(documents)
            page_count += 1

            if cursor is None:
                break

        if page_count >= MAX_PAGES:
            self._log.warning(
                "MAX_PAGES limit (%d) reached for endpoint %s — results may be incomplete.",
                MAX_PAGES,
                endpoint,
            )

        return all_documents

    async def get_persons(self, wahlperiode: int) -> list[Person]:
        """Fetch all parliamentary members for a given Wahlperiode.

        Documents that fail Pydantic validation are logged at WARNING level
        and skipped so a single malformed record does not abort the full fetch.

        Args:
            wahlperiode: Election period number, e.g. 20 for the 20th Bundestag.

        Returns:
            List of validated Person objects for the requested Wahlperiode.
        """
        self._log.info("API call started: GET /person (Wahlperiode %d)", wahlperiode)
        raw_docs = await self._fetch_all_pages(
            "/person",
            {"wahlperiode-nummer": wahlperiode, "format": "json"},
        )

        persons: list[Person] = []
        for doc in raw_docs:
            try:
                persons.append(Person.model_validate(doc))
                self._log.debug("Parsed person document id=%s", doc.get("id", "?"))
            except ValidationError as exc:
                self._log.warning("Skipping invalid person document: %s", exc)

        # The API ignores wahlperiode-nummer — filter client-side using each
        # person's wahlperiode list so only actual members of that WP are kept.
        filtered = [p for p in persons if wahlperiode in p.wahlperiode]
        self._log.info(
            "Parsed %d persons, filtered to %d for Wahlperiode %d (skipped %d invalid)",
            len(persons),
            len(filtered),
            wahlperiode,
            len(raw_docs) - len(persons),
        )
        return filtered

    async def search_persons_by_name(
        self,
        name: str,
        wahlperiode: int | None = None,
    ) -> list[Person]:
        """Search for parliamentary members whose display name contains a string.

        Performs a case-insensitive substring match against Person.display_name.
        All persons for the Wahlperiode are fetched first, then filtered in memory.

        Args:
            name: Name substring to search for (case-insensitive).
            wahlperiode: Election period to search in. Defaults to DEFAULT_WAHLPERIODE.

        Returns:
            List of Person objects whose display name contains the search string.
        """
        period = wahlperiode if wahlperiode is not None else DEFAULT_WAHLPERIODE
        self._log.info("Searching persons by name '%s' in Wahlperiode %d", name, period)
        all_persons = await self.get_persons(period)
        name_lower = name.lower()
        matches = [p for p in all_persons if name_lower in p.display_name.lower()]
        self._log.info("Name search '%s' returned %d match(es)", name, len(matches))
        return matches

