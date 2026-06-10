"""Unit tests for DIP API Pydantic domain models (Task 10.4)."""

# Third-party
import pytest
from pydantic import ValidationError

# Local
from dip_mcp.api.models import (
    DistributionReport,
    FraktionDistribution,
    PaginatedResponse,
    Person,
    PersonName,
)


def test_person_name_full_name_with_title() -> None:
    """Test that full_name assembles title + vorname + nachname correctly."""
    name = PersonName(vorname="Friedrich", nachname="Merz", anrede_titel="Dr.")
    assert name.full_name == "Dr. Friedrich Merz"


def test_person_name_full_name_without_title() -> None:
    """Test that full_name contains only vorname and nachname when no title is set."""
    name = PersonName(vorname="Max", nachname="Mustermann")
    assert name.full_name == "Max Mustermann"
    assert "None" not in name.full_name


def test_person_extra_fields_ignored() -> None:
    """Test that extra JSON fields from the DIP API payload do not raise ValidationError."""
    person = Person.model_validate(
        {
            "id": "999",
            "typ": "Person",
            "vorname": "Test",
            "nachname": "User",
            "unknown_api_field": "should_be_dropped",
            "another_extra": 42,
        }
    )
    assert person.id == "999"
    assert person.vorname == "Test"


def test_paginated_response_generic() -> None:
    """Test that PaginatedResponse[Person] parses documents as Person objects."""
    raw = {
        "numFound": 2,
        "cursor": "next_page_token",
        "documents": [
            {"id": "1", "typ": "Person", "vorname": "Anna", "nachname": "Schmidt"},
            {"id": "2", "typ": "Person", "vorname": "Bert", "nachname": "Müller"},
        ],
    }
    response = PaginatedResponse[Person].model_validate(raw)

    assert response.num_found == 2
    assert response.cursor == "next_page_token"
    assert len(response.documents) == 2
    assert isinstance(response.documents[0], Person)
    assert response.documents[0].vorname == "Anna"


def test_distribution_report_validator() -> None:
    """Test that DistributionReport raises ValidationError when percentages exceed 101."""
    with pytest.raises(ValidationError):
        DistributionReport(
            wahlperiode=20,
            total_persons=2,
            unaffiliated_count=0,
            distribution=[
                FraktionDistribution(fraktion_name="A", person_count=1, percentage=60.0),
                FraktionDistribution(fraktion_name="B", person_count=1, percentage=60.0),
            ],
        )


def test_distribution_report_validator_skips_when_unaffiliated() -> None:
    """Test that the percentage validator is skipped when unaffiliated_count > 0."""
    report = DistributionReport(
        wahlperiode=20,
        total_persons=3,
        unaffiliated_count=1,
        distribution=[
            FraktionDistribution(fraktion_name="A", person_count=1, percentage=60.0),
            FraktionDistribution(fraktion_name="B", person_count=1, percentage=60.0),
        ],
    )
    assert report.unaffiliated_count == 1


def test_person_fraktion_for_wp_uses_role() -> None:
    """Test that fraktion_for_wp returns the WP-specific role Fraktion when present."""
    from dip_mcp.api.models import Person, PersonRole

    person = Person(
        id="p1",
        typ="Person",
        vorname="Anna",
        nachname="Schmidt",
        fraktion=["SPD"],
        wahlperiode=[19, 20],
        person_roles=[
            PersonRole(fraktion="CDU/CSU", wahlperiode_nummer=[19]),
            PersonRole(fraktion="SPD", wahlperiode_nummer=[20]),
        ],
    )

    assert person.fraktion_for_wp(19) == "CDU/CSU"
    assert person.fraktion_for_wp(20) == "SPD"


def test_person_fraktion_for_wp_falls_back_to_top_level() -> None:
    """Test that fraktion_for_wp falls back to the top-level fraktion when no role matches."""
    from dip_mcp.api.models import Person

    person = Person(
        id="p2",
        typ="Person",
        vorname="Max",
        nachname="Mustermann",
        fraktion=["FDP"],
        wahlperiode=[20],
    )

    assert person.fraktion_for_wp(20) == "FDP"


def test_person_display_name_without_titel() -> None:
    """Test that display_name falls back to full_name when titel is not set."""
    from dip_mcp.api.models import Person

    person = Person(id="p3", typ="Person", vorname="Olaf", nachname="Scholz")
    assert person.display_name == "Olaf Scholz"


def test_person_fraktion_name_empty() -> None:
    """Test that fraktion_name returns None when the fraktion list is empty."""
    from dip_mcp.api.models import Person

    person = Person(id="p4", typ="Person", vorname="A", nachname="B", fraktion=[])
    assert person.fraktion_name is None


