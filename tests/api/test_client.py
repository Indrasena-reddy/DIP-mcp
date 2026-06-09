"""Unit tests for the DIP API async HTTP client (Task 10.5).

Uses respx to intercept httpx at the transport layer — no real network calls
are made and no real API keys are required.

Pattern: always use `with respx.mock() as mock:` and route via `mock.get(...)`,
not `respx.get(...)`, to ensure routes are added to the active context router.
"""

# Standard library
from typing import Any

# Third-party
import httpx
import pytest
import respx

# Local
from dip_mcp.api.client import DipApiClient
from dip_mcp.config import Settings

BASE_URL: str = "https://search.dip.bundestag.de/api/v1"
PERSON_URL: str = f"{BASE_URL}/person"
FRAKTION_URL: str = f"{BASE_URL}/fraktion"

_VALID_DOC: dict[str, Any] = {
    "id": "1001",
    "typ": "Person",
    "vorname": "Olaf",
    "nachname": "Scholz",
    "fraktion": ["SPD"],
    "wahlperiode": [20],
}

_VALID_DOC_2: dict[str, Any] = {
    "id": "1002",
    "typ": "Person",
    "vorname": "Friedrich",
    "nachname": "Merz",
    "titel": "Dr. Friedrich Merz, MdB, CDU/CSU",
    "fraktion": ["CDU/CSU"],
    "wahlperiode": [20],
}


def _ok(docs: list[dict[str, Any]], cursor: str | None = None) -> httpx.Response:
    """Return a 200 JSON response shaped like a DIP API paginated envelope.

    Args:
        docs: List of raw document dicts to include.
        cursor: Optional next-page cursor string.

    Returns:
        httpx.Response with the paginated JSON body.
    """
    return httpx.Response(
        200,
        json={"numFound": len(docs), "cursor": cursor, "documents": docs},
    )


# ---------------------------------------------------------------------------
# get_persons
# ---------------------------------------------------------------------------


async def test_get_persons_single_page(mock_settings: Settings) -> None:
    """Test that get_persons returns all persons when the API fits in one page.

    Args:
        mock_settings: Session-scoped Settings fixture from conftest.
    """
    with respx.mock() as mock:
        mock.get(PERSON_URL).mock(return_value=_ok([_VALID_DOC, _VALID_DOC_2]))

        async with DipApiClient(mock_settings) as client:
            persons = await client.get_persons(20)

    assert len(persons) == 2
    assert persons[0].id == "1001"
    assert persons[1].id == "1002"


async def test_get_persons_pagination(mock_settings: Settings) -> None:
    """Test that get_persons chains cursor-paginated requests into a flat list.

    Args:
        mock_settings: Session-scoped Settings fixture from conftest.
    """
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _ok([_VALID_DOC], cursor="page2_token")
        return _ok([_VALID_DOC_2])

    with respx.mock() as mock:
        mock.get(PERSON_URL).mock(side_effect=handler)

        async with DipApiClient(mock_settings) as client:
            persons = await client.get_persons(20)

    assert call_count == 2
    assert len(persons) == 2
    ids = {p.id for p in persons}
    assert "1001" in ids
    assert "1002" in ids



async def test_retry_on_500(mock_settings: Settings) -> None:
    """Test that the client retries on HTTP 500 and succeeds on the third attempt.

    Tenacity is configured for stop_after_attempt(3). Attempts 1 and 2 return
    500; attempt 3 returns 200 with a valid person document.

    Args:
        mock_settings: Session-scoped Settings fixture from conftest.
    """
    attempt = 0

    def retry_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempt
        attempt += 1
        if attempt <= 2:
            return httpx.Response(500, text="Internal Server Error")
        return _ok([_VALID_DOC])

    with respx.mock() as mock:
        mock.get(PERSON_URL).mock(side_effect=retry_handler)

        async with DipApiClient(mock_settings) as client:
            persons = await client.get_persons(20)

    assert attempt == 3
    assert len(persons) == 1


async def test_search_persons_by_name_found(mock_settings: Settings) -> None:
    """Test that search_persons_by_name returns matching persons on substring match.

    Args:
        mock_settings: Session-scoped Settings fixture from conftest.
    """
    doc_with_titel = {**_VALID_DOC, "titel": "Olaf Scholz, MdB, SPD"}

    with respx.mock() as mock:
        mock.get(PERSON_URL).mock(return_value=_ok([doc_with_titel, _VALID_DOC_2]))

        async with DipApiClient(mock_settings) as client:
            results = await client.search_persons_by_name("Scholz", 20)

    assert len(results) == 1
    assert results[0].id == "1001"


async def test_search_persons_by_name_not_found(mock_settings: Settings) -> None:
    """Test that search_persons_by_name returns an empty list when no name matches.

    Args:
        mock_settings: Session-scoped Settings fixture from conftest.
    """
    with respx.mock() as mock:
        mock.get(PERSON_URL).mock(return_value=_ok([_VALID_DOC, _VALID_DOC_2]))

        async with DipApiClient(mock_settings) as client:
            results = await client.search_persons_by_name("Baerbock", 20)

    assert results == []


async def test_invalid_person_document_skipped(mock_settings: Settings) -> None:
    """Test that malformed documents are skipped while valid ones are returned.

    A document missing required fields (vorname, nachname) fails Pydantic
    validation and is dropped with a WARNING log, leaving valid documents intact.

    Args:
        mock_settings: Session-scoped Settings fixture from conftest.
    """
    invalid_doc: dict[str, Any] = {"id": "bad", "typ": "Person"}  # missing vorname/nachname

    with respx.mock() as mock:
        mock.get(PERSON_URL).mock(return_value=_ok([_VALID_DOC, invalid_doc]))

        async with DipApiClient(mock_settings) as client:
            persons = await client.get_persons(20)

    assert len(persons) == 1
    assert persons[0].id == "1001"
