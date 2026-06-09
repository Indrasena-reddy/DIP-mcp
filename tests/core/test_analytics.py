"""Unit tests for the core analytics engine (Task 10.6).

All functions under test are pure with no I/O — no mocks are needed.
"""

# Standard library
import pytest

# Local
from dip_mcp.api.models import Person
from dip_mcp.core.analytics import (
    UNKNOWN_FRAKTION,
    build_distribution_report,
    calculate_percentages,
    count_per_fraktion,
    format_distribution_as_text,
)

WAHLPERIODE: int = 20


# ---------------------------------------------------------------------------
# count_per_fraktion
# ---------------------------------------------------------------------------


def test_count_per_fraktion_basic(sample_persons: list[Person]) -> None:
    """Test that each affiliated person is counted under the correct Fraktion key.

    Uses the 10-person fixture: CDU/CSU×4, SPD×3, Grüne×2, FDP×1.

    Args:
        sample_persons: 10-person fixture from conftest.
    """
    counts = count_per_fraktion(sample_persons, WAHLPERIODE)

    assert counts["CDU/CSU"] == 4
    assert counts["SPD"] == 3
    assert counts["Grüne"] == 2
    assert counts["FDP"] == 1
    assert UNKNOWN_FRAKTION not in counts


def test_count_per_fraktion_null_fraktion() -> None:
    """Test that persons with an empty fraktion list are counted under UNKNOWN_FRAKTION."""
    persons = [
        Person(id="u1", typ="Person", vorname="A", nachname="B", fraktion=[], wahlperiode=[20]),
        Person(id="u2", typ="Person", vorname="C", nachname="D", fraktion=[], wahlperiode=[20]),
    ]
    counts = count_per_fraktion(persons, WAHLPERIODE)

    assert counts[UNKNOWN_FRAKTION] == 2
    assert len(counts) == 1


# ---------------------------------------------------------------------------
# calculate_percentages
# ---------------------------------------------------------------------------


def test_calculate_percentages_sum_to_100(sample_persons: list[Person]) -> None:
    """Test that percentages for fully affiliated persons sum to approximately 100.0.

    Uses sample_persons (10 persons, 0 unaffiliated) so the sum should be exact.

    Args:
        sample_persons: 10-person fixture from conftest.
    """
    counts = count_per_fraktion(sample_persons, WAHLPERIODE)
    # No unaffiliated, so no pop needed — all counts are real Fraktionen
    percentages = calculate_percentages(counts, len(sample_persons))
    total = sum(percentages.values())

    assert abs(total - 100.0) < 0.1


def test_calculate_percentages_zero_total_raises() -> None:
    """Test that calculate_percentages raises ValueError when total is zero."""
    with pytest.raises(ValueError, match="positive integer"):
        calculate_percentages({"SPD": 1}, 0)


# ---------------------------------------------------------------------------
# build_distribution_report
# ---------------------------------------------------------------------------


def test_build_distribution_report_empty_raises() -> None:
    """Test that an empty person list raises ValueError."""
    with pytest.raises(ValueError):
        build_distribution_report([], WAHLPERIODE)


def test_build_distribution_report_sorted_descending(sample_persons: list[Person]) -> None:
    """Test that distribution entries are ordered by person_count descending.

    With sample_persons: CDU/CSU(4) > SPD(3) > Grüne(2) > FDP(1).

    Args:
        sample_persons: 10-person fixture from conftest.
    """
    report = build_distribution_report(sample_persons, WAHLPERIODE)

    counts = [entry.person_count for entry in report.distribution]
    assert counts == sorted(counts, reverse=True)
    assert report.distribution[0].fraktion_name == "CDU/CSU"
    assert report.distribution[0].person_count == 4


# ---------------------------------------------------------------------------
# format_distribution_as_text
# ---------------------------------------------------------------------------


def test_format_distribution_as_text_contains_fraktion_names(
    sample_fraktion_distribution_report: object,
) -> None:
    """Test that all four Fraktion names appear in the formatted output.

    Args:
        sample_fraktion_distribution_report: Pre-built DistributionReport fixture.
    """
    from dip_mcp.api.models import DistributionReport

    report: DistributionReport = sample_fraktion_distribution_report  # type: ignore[assignment]
    text = format_distribution_as_text(report)

    assert "CDU/CSU" in text
    assert "SPD" in text
    assert "Grüne" in text
    assert "FDP" in text
    assert "Wahlperiode 20" in text
    assert "%" in text
