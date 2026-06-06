"""Underlying logic functions for MCP tool definitions.

Each function here is the business logic layer. The MCP decorators and tool
schemas are applied in server.py to keep tool registration decoupled from
application logic and to avoid circular imports.
"""

# Local
from dip_mcp.api.client import DipApiClient
from dip_mcp.api.models import DistributionReport
from dip_mcp.config import settings
from dip_mcp.core.analytics import build_distribution_report


async def fetch_fraktion_distribution(wahlperiode: int) -> DistributionReport:
    """Fetch all persons for a Wahlperiode and compute their Fraktion distribution.

    Args:
        wahlperiode: Election period number, e.g. 20 for the 20th Bundestag.

    Returns:
        DistributionReport with per-Fraktion counts, percentages, and totals.

    Raises:
        ValueError: If no persons are found for the given Wahlperiode.
    """
    async with DipApiClient(settings) as client:
        persons = await client.get_persons(wahlperiode)
    return build_distribution_report(persons, wahlperiode)


async def fetch_person_info(
    name: str,
    wahlperiode: int = 20,
) -> dict[str, str | int | list[str] | None]:
    """Look up biographical and parliamentary information for a politician by name.

    Searches for the first person whose display name contains the given string
    (case-insensitive substring match) within the specified Wahlperiode.

    Args:
        name: Full or partial name to search for.
        wahlperiode: Election period to search within. Defaults to 20.

    Returns:
        Dictionary with id, full_name, fraktion, wahlperiode_nummer, geburtsdatum,
        geburtsort, and beruf keys. Returns a single-key error dict if no match
        is found.
    """
    async with DipApiClient(settings) as client:
        matches = await client.search_persons_by_name(name, wahlperiode)

    if not matches:
        not_found: dict[str, str | int | list[str] | None] = {
            "error": f"No person found matching '{name}'"
        }
        return not_found

    person = matches[0]
    result: dict[str, str | int | list[str] | None] = {
        "id": person.id,
        "full_name": person.display_name,
        "fraktion": person.fraktion_name,
        "wahlperiode_nummer": [str(w) for w in person.wahlperiode],
        "geburtsdatum": (
            person.biografie.geburtsdatum if person.biografie else None
        ),
        "geburtsort": (
            person.biografie.geburtsort if person.biografie else None
        ),
        "beruf": list(person.biografie.beruf) if person.biografie else [],
    }
    return result


async def fetch_fraktionen_list(
    wahlperiode: int = 20,
) -> list[dict[str, str | int | None]]:
    """List all parliamentary groups (Fraktionen) for a given Wahlperiode.

    Args:
        wahlperiode: Election period to list Fraktionen for. Defaults to 20.

    Returns:
        List of dictionaries with id, bezeichnung, wahlperiode_nummer,
        anfangsdatum, and enddatum keys for each Fraktion.
    """
    async with DipApiClient(settings) as client:
        fraktionen = await client.get_fraktionen(wahlperiode)

    return [
        {
            "id": f.id,
            "bezeichnung": f.bezeichnung,
            "wahlperiode_nummer": f.wahlperiode_nummer,
            "anfangsdatum": f.anfangsdatum,
            "enddatum": f.enddatum,
        }
        for f in fraktionen
    ]
