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


