"""MCP server for the DIP parliamentary data analyser.

Registers three tools with FastMCP and exposes run_server() as the
stdio-based MCP server entrypoint used by the CLI serve command.
"""

# Standard library
import logging
from typing import Any

# Third-party
from mcp.server.fastmcp import FastMCP

# Local
from dip_mcp.config import get_logger
from dip_mcp.mcp.tools import (
    fetch_fraktion_distribution,
    fetch_person_info,
)

log: logging.Logger = get_logger(__name__)

mcp: FastMCP = FastMCP(
    "dip-parliamentary-analyst",
    instructions="Parliamentary data analyser for the German Bundestag DIP API",
)


@mcp.tool(
    description=(
        "Fetch the parliamentary group (Fraktion) distribution for a given Wahlperiode "
        "(election period). Returns the percentage and count of politicians per Fraktion. "
        "Use this for questions about group distribution or election period statistics."
    )
)
async def get_fraktion_distribution(wahlperiode: int) -> dict[str, Any]:
    """Compute and return the Fraktion distribution for the given election period.

    Args:
        wahlperiode: The election period number, e.g. 20 for the 20th Wahlperiode (2021-2025).

    Returns:
        DistributionReport serialized to a dict with wahlperiode, total_persons,
        unaffiliated_count, and a sorted distribution list.
    """
    report = await fetch_fraktion_distribution(wahlperiode)
    result: dict[str, Any] = report.model_dump()
    return result


@mcp.tool(
    description=(
        "Look up biographical and parliamentary information for a specific politician "
        "by name. Returns Fraktion membership, biographical data, and election periods. "
        "Use this for questions about specific individuals."
    )
)
async def get_person_info(name: str, wahlperiode: int = 20) -> dict[str, Any]:
    """Return biographical and parliamentary data for a politician matched by name.

    Args:
        name: Full or partial name of the politician to search for.
        wahlperiode: Election period to search within. Defaults to 20.

    Returns:
        Dictionary with full_name, fraktion, wahlperiode_nummer, and biographical
        fields, or an error dict if no match is found.
    """
    data = await fetch_person_info(name, wahlperiode)
    result: dict[str, Any] = dict(data)
    return result


def run_server() -> None:
    """Start the MCP server using stdio transport.

    Intended to be called as a CLI entrypoint. Blocks until the server is
    stopped by the client or process signal.
    """
    log.info("Starting MCP stdio server (transport=stdio)")
    mcp.run(transport="stdio")
