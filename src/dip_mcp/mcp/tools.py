"""Underlying logic functions for MCP tool definitions.

Each function here is the business logic layer. The MCP decorators and tool
schemas are applied in server.py to keep tool registration decoupled from
application logic and to avoid circular imports.

Person data is cached in-process per Wahlperiode so repeated questions about
the same election period skip the expensive paginated API fetch.
"""

# Standard library
import logging

# Third-party
import httpx

# Local
from dip_mcp.api.client import DipApiClient
from dip_mcp.api.models import DistributionReport, Person
from dip_mcp.config import get_logger, settings
from dip_mcp.core.analytics import build_distribution_report

log: logging.Logger = get_logger(__name__)

# In-memory cache: wahlperiode -> list of persons fetched for that period.
# Populated on first request; subsequent requests for the same WP are instant.
_persons_cache: dict[int, list[Person]] = {}


async def _get_persons(wahlperiode: int) -> list[Person]:
    """Return persons for a Wahlperiode, using the cache when available.

    Args:
        wahlperiode: Election period number.

    Returns:
        List of Person objects filtered to the requested Wahlperiode.

    Raises:
        httpx.HTTPStatusError: On a non-2xx response after all retry attempts.
    """
    if wahlperiode in _persons_cache:
        log.info(
            "Cache hit for Wahlperiode %d (%d persons)",
            wahlperiode,
            len(_persons_cache[wahlperiode]),
        )
        return _persons_cache[wahlperiode]

    log.info("Cache miss — fetching persons for Wahlperiode %d from API", wahlperiode)
    async with DipApiClient(settings) as client:
        persons = await client.get_persons(wahlperiode)

    _persons_cache[wahlperiode] = persons
    log.info("Cached %d persons for Wahlperiode %d", len(persons), wahlperiode)
    return persons


async def fetch_fraktion_distribution(wahlperiode: int) -> DistributionReport:
    """Fetch all persons for a Wahlperiode and compute their Fraktion distribution.

    Args:
        wahlperiode: Election period number, e.g. 20 for the 20th Bundestag.

    Returns:
        DistributionReport with per-Fraktion counts, percentages, and totals.

    Raises:
        ValueError: If no persons are found for the given Wahlperiode.
        httpx.HTTPStatusError: On a non-2xx response after all retry attempts.
    """
    try:
        persons = await _get_persons(wahlperiode)
    except httpx.HTTPStatusError as exc:
        log.error("HTTP error fetching persons for Wahlperiode %d: %s", wahlperiode, exc)
        raise

    if not persons:
        log.error("No persons returned for Wahlperiode %d", wahlperiode)
        raise ValueError(f"No persons found for Wahlperiode {wahlperiode}.")

    report = build_distribution_report(persons, wahlperiode)
    log.debug(
        "Distribution built: %d Fraktionen, %d unaffiliated",
        len(report.distribution),
        report.unaffiliated_count,
    )
    return report


async def fetch_person_info(
    name: str,
    wahlperiode: int = 20,
) -> dict[str, str | int | list[str] | None]:
    """Look up biographical and parliamentary information for a politician by name.

    Searches for the first person whose display name contains the given string
    (case-insensitive substring match) within the specified Wahlperiode.
    Uses the in-process persons cache to avoid redundant API calls.

    Args:
        name: Full or partial name to search for.
        wahlperiode: Election period to search within. Defaults to 20.

    Returns:
        Dictionary with id, full_name, fraktion, wahlperiode_nummer, geburtsdatum,
        geburtsort, and beruf keys. Returns a single-key error dict if no match
        is found.

    Raises:
        httpx.HTTPStatusError: On a non-2xx response after all retry attempts.
    """
    log.info("Searching for person '%s' in Wahlperiode %d", name, wahlperiode)
    try:
        persons = await _get_persons(wahlperiode)
    except httpx.HTTPStatusError as exc:
        log.error("HTTP error searching for person '%s': %s", name, exc)
        raise

    name_lower = name.lower()
    matches = [p for p in persons if name_lower in p.display_name.lower()]

    if not matches:
        log.warning("No person found matching '%s' in Wahlperiode %d", name, wahlperiode)
        not_found: dict[str, str | int | list[str] | None] = {
            "error": f"No person found matching '{name}'"
        }
        return not_found

    person = matches[0]
    log.info("Found person: %s (Fraktion: %s)", person.display_name, person.fraktion_name)
    result: dict[str, str | int | list[str] | None] = {
        "id": person.id,
        "full_name": person.display_name,
        "fraktion": person.fraktion_for_wp(wahlperiode),
        "wahlperiode_nummer": [str(w) for w in person.wahlperiode],
        "geburtsdatum": (person.biografie.geburtsdatum if person.biografie else None),
        "geburtsort": (person.biografie.geburtsort if person.biografie else None),
        "beruf": list(person.biografie.beruf) if person.biografie else [],
    }
    return result


