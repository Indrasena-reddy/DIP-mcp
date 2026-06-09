"""Unit tests for MCP tool business logic functions (Task 10.8).

_get_persons is mocked so no real API calls are made and no credentials
are required. The cache is cleared before each test to ensure isolation.
"""

# Standard library
from unittest.mock import AsyncMock, patch

# Third-party
import pytest
from pytest_mock import MockerFixture

# Local
from dip_mcp.api.models import DistributionReport, Person
from dip_mcp.mcp import tools as tools_module
from dip_mcp.mcp.tools import fetch_fraktion_distribution, fetch_person_info

WAHLPERIODE: int = 20


@pytest.fixture(autouse=True)
def clear_persons_cache() -> None:
    """Clear the in-process persons cache before every test."""
    tools_module._persons_cache.clear()


async def test_fetch_fraktion_distribution_returns_report(
    mocker: MockerFixture,
    sample_persons: list[Person],
    sample_fraktion_distribution_report: DistributionReport,
) -> None:
    """Test that fetch_fraktion_distribution returns a DistributionReport."""
    mocker.patch(
        "dip_mcp.mcp.tools._get_persons",
        new=AsyncMock(return_value=sample_persons),
    )
    mocker.patch(
        "dip_mcp.mcp.tools.build_distribution_report",
        return_value=sample_fraktion_distribution_report,
    )

    report = await fetch_fraktion_distribution(WAHLPERIODE)

    assert isinstance(report, DistributionReport)
    assert report.total_persons == 10
    assert len(report.distribution) == 4


async def test_fetch_person_info_found(
    mocker: MockerFixture,
    sample_persons: list[Person],
) -> None:
    """Test that fetch_person_info returns a dict with expected keys when a match exists."""
    mocker.patch(
        "dip_mcp.mcp.tools._get_persons",
        new=AsyncMock(return_value=sample_persons),
    )

    result = await fetch_person_info("Merz", WAHLPERIODE)

    assert "error" not in result
    assert result["full_name"] == sample_persons[0].display_name
    assert result["fraktion"] == "CDU/CSU"
    assert "id" in result
    assert "wahlperiode_nummer" in result


async def test_fetch_person_info_not_found(mocker: MockerFixture) -> None:
    """Test that fetch_person_info returns an error dict when no match is found."""
    mocker.patch(
        "dip_mcp.mcp.tools._get_persons",
        new=AsyncMock(return_value=[]),
    )

    result = await fetch_person_info("NonExistentPolitician", WAHLPERIODE)

    assert "error" in result
    assert "NonExistentPolitician" in str(result["error"])
