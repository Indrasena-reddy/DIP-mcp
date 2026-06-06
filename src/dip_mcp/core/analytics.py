"""Core analytics engine for parliamentary Fraktion distribution.

Pure, stateless functions with no I/O. Transforms a list of Person objects
into a DistributionReport suitable for LLM summarisation. Every function here
is fully unit-testable without mocks.
"""

# Standard library
from collections import Counter

# Local
from dip_mcp.api.models import DistributionReport, FraktionDistribution, Person

UNKNOWN_FRAKTION: str = "Unbekannt"
PERCENTAGE_PRECISION: int = 2


def count_per_fraktion(persons: list[Person]) -> dict[str, int]:
    """Count the number of persons per Fraktion.

    Persons with no Fraktion affiliation are counted under UNKNOWN_FRAKTION.

    Args:
        persons: List of parliamentary members to aggregate.

    Returns:
        Dictionary mapping each Fraktion name (or UNKNOWN_FRAKTION) to its
        member count.
    """
    keys = [
        person.fraktion_name if person.fraktion_name is not None else UNKNOWN_FRAKTION
        for person in persons
    ]
    return dict(Counter(keys))


def calculate_percentages(counts: dict[str, int], total: int) -> dict[str, float]:
    """Calculate the percentage share of each Fraktion.

    Args:
        counts: Dictionary mapping Fraktion names to member counts.
        total: Total number of persons used as the denominator.

    Returns:
        Dictionary mapping each Fraktion name to its rounded percentage share.

    Raises:
        ValueError: If total is zero or negative, which would cause division by zero.
    """
    if total <= 0:
        raise ValueError(
            f"total must be a positive integer for percentage calculation, got {total}."
        )
    return {
        name: round(count / total * 100, PERCENTAGE_PRECISION)
        for name, count in counts.items()
    }


def build_distribution_report(
    persons: list[Person],
    wahlperiode: int,
) -> DistributionReport:
    """Build a Fraktion distribution report from a list of parliamentary members.

    Aggregates persons by Fraktion, computes percentage shares relative to the
    total headcount (including unaffiliated), and returns a sorted report.
    Unaffiliated persons appear in unaffiliated_count but not in distribution.

    Args:
        persons: List of parliamentary members to aggregate. Must be non-empty.
        wahlperiode: Election period number the persons were fetched for.

    Returns:
        DistributionReport with a descending-sorted Fraktion distribution list.

    Raises:
        ValueError: If persons is empty because percentages cannot be computed.
    """
    counts = count_per_fraktion(persons)
    total = len(persons)
    unaffiliated_count = counts.pop(UNKNOWN_FRAKTION, 0)

    percentages = calculate_percentages(counts, total)

    distribution = sorted(
        [
            FraktionDistribution(
                fraktion_name=name,
                person_count=count,
                percentage=percentages[name],
            )
            for name, count in counts.items()
        ],
        key=lambda d: d.person_count,
        reverse=True,
    )

    return DistributionReport(
        wahlperiode=wahlperiode,
        total_persons=total,
        unaffiliated_count=unaffiliated_count,
        distribution=distribution,
    )


def format_distribution_as_text(report: DistributionReport) -> str:
    """Format a DistributionReport as a compact plain-text string for LLM input.

    Produces a fixed-width table with a header, total summary, and one row
    per Fraktion sorted by member count descending.

    Args:
        report: The distribution report to format.

    Returns:
        Multi-line plain-text representation suitable for inclusion in an LLM prompt.
    """
    col_fraktion = 35
    col_members = 10
    col_share = 8
    separator = "-" * (col_fraktion + col_members + col_share + 2)

    header = (
        f"Fraktion-Verteilung — Wahlperiode {report.wahlperiode}\n"
        f"Gesamt: {report.total_persons} Personen "
        f"({report.unaffiliated_count} ohne Fraktionszugehörigkeit)\n"
    )
    column_header = (
        f"{'Fraktion':<{col_fraktion}} "
        f"{'Mitglieder':>{col_members}} "
        f"{'Anteil':>{col_share}}"
    )

    rows = [
        f"{entry.fraktion_name:<{col_fraktion}} "
        f"{entry.person_count:>{col_members}} "
        f"{entry.percentage:>{col_share - 1}.2f}%"
        for entry in report.distribution
    ]

    return "\n".join([header, column_header, separator, *rows])
