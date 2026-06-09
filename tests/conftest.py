"""Shared pytest fixtures and test configuration for dip-mcp.

Environment variables are set at module level before any dip_mcp import
because config.py instantiates Settings() at import time.
"""

# Standard library
import os

# Set test credentials BEFORE any dip_mcp module is imported.
os.environ.setdefault("DIP_API_KEY", "test_dip_key")
os.environ.setdefault("GROQ_API_KEY", "test_groq_key")

# Third-party
import pytest

# Local — imported AFTER env vars are set
from dip_mcp.api.models import (
    DistributionReport,
    FraktionDistribution,
    Person,
)
from dip_mcp.config import Settings

SAMPLE_WAHLPERIODE: int = 20


@pytest.fixture(scope="session")
def mock_settings() -> Settings:
    """Return a Settings instance built from test values, not real credentials.

    Uses a short timeout and low concurrency to keep tests fast.
    Session-scoped so the Settings object is created only once per test run.

    Returns:
        Settings configured with placeholder API keys and test-friendly limits.
    """
    return Settings(
        dip_api_key="test_dip_key",
        groq_api_key="test_groq_key",
        request_timeout_seconds=5,
        max_concurrent_requests=2,
    )


@pytest.fixture
def sample_persons() -> list[Person]:
    """Return 10 hardcoded Person objects with a realistic Fraktion spread.

    Distribution: CDU/CSU × 4, SPD × 3, Grüne × 2, FDP × 1.
    Used across test_analytics, test_tools, and test_client modules.

    Returns:
        List of ten Person objects across four Fraktionen.
    """
    return [
        # CDU/CSU — 4 members
        Person(id="p01", typ="Person", vorname="Friedrich", nachname="Merz",
               titel="Dr. Friedrich Merz, MdB, CDU/CSU", fraktion=["CDU/CSU"], wahlperiode=[20]),
        Person(id="p02", typ="Person", vorname="Annegret", nachname="Kramp-Karrenbauer",
               fraktion=["CDU/CSU"], wahlperiode=[20]),
        Person(id="p03", typ="Person", vorname="Armin", nachname="Laschet",
               fraktion=["CDU/CSU"], wahlperiode=[20]),
        Person(id="p04", typ="Person", vorname="Julia", nachname="Klöckner",
               fraktion=["CDU/CSU"], wahlperiode=[20]),
        # SPD — 3 members
        Person(id="p05", typ="Person", vorname="Olaf", nachname="Scholz",
               titel="Olaf Scholz, MdB, SPD", fraktion=["SPD"], wahlperiode=[20]),
        Person(id="p06", typ="Person", vorname="Lars", nachname="Klingbeil",
               fraktion=["SPD"], wahlperiode=[20]),
        Person(id="p07", typ="Person", vorname="Saskia", nachname="Esken",
               fraktion=["SPD"], wahlperiode=[20]),
        # Grüne — 2 members
        Person(id="p08", typ="Person", vorname="Annalena", nachname="Baerbock",
               fraktion=["Grüne"], wahlperiode=[20]),
        Person(id="p09", typ="Person", vorname="Robert", nachname="Habeck",
               fraktion=["Grüne"], wahlperiode=[20]),
        # FDP — 1 member
        Person(id="p10", typ="Person", vorname="Christian", nachname="Lindner",
               fraktion=["FDP"], wahlperiode=[20]),
    ]


@pytest.fixture
def sample_fraktion_distribution_report() -> DistributionReport:
    """Return a pre-built DistributionReport matching the sample_persons fixture.

    CDU/CSU: 4 (40%), SPD: 3 (30%), Grüne: 2 (20%), FDP: 1 (10%).
    Total percentage sums to exactly 100.0, which passes the model validator.

    Returns:
        DistributionReport with four Fraktionen and no unaffiliated persons.
    """
    return DistributionReport(
        wahlperiode=SAMPLE_WAHLPERIODE,
        total_persons=10,
        unaffiliated_count=0,
        distribution=[
            FraktionDistribution(fraktion_name="CDU/CSU", person_count=4, percentage=40.0),
            FraktionDistribution(fraktion_name="SPD", person_count=3, percentage=30.0),
            FraktionDistribution(fraktion_name="Grüne", person_count=2, percentage=20.0),
            FraktionDistribution(fraktion_name="FDP", person_count=1, percentage=10.0),
        ],
    )
