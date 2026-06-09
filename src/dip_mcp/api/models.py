"""Pydantic v2 domain models for DIP API responses and internal analytics.

Covers both API-facing models (Person, Fraktion, PaginatedResponse) and
internal analytics models (FraktionDistribution, DistributionReport).
All API-facing models use extra="ignore" so unknown fields never cause failures.

Note: The real DIP API returns a flat Person structure with vorname/nachname
at the top level and fraktion as a list, which differs from the nested schema
in the DIP documentation. These models reflect the actual API behaviour.
"""

# Standard library
from typing import Generic, Self, TypeVar

# Third-party
from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")


class PersonName(BaseModel):
    """Structured name components for a parliamentary member.

    Attributes:
        vorname: First name.
        nachname: Last name (family name).
        anrede_titel: Honorific title, e.g. "Dr." or "Prof.".
        akademischer_titel: Academic title if separate from anrede_titel.
        namenszusatz: Name suffix or particle, e.g. "von".
    """

    model_config = ConfigDict(extra="ignore")

    vorname: str
    nachname: str
    anrede_titel: str | None = None
    akademischer_titel: str | None = None
    namenszusatz: str | None = None

    @property
    def full_name(self) -> str:
        """Return the canonical display name assembled from non-None parts.

        Returns:
            Space-separated name string, e.g. "Dr. Friedrich Merz".
        """
        parts = [
            self.anrede_titel,
            self.akademischer_titel,
            self.vorname,
            self.namenszusatz,
            self.nachname,
        ]
        return " ".join(p for p in parts if p is not None)


class PersonBiography(BaseModel):
    """Biographical details for a parliamentary member.

    Attributes:
        geburtsdatum: Date of birth as ISO 8601 string.
        geburtsort: Place of birth.
        beruf: List of professions.
        religion: Religious denomination.
    """

    model_config = ConfigDict(extra="ignore")

    geburtsdatum: str | None = None
    geburtsort: str | None = None
    beruf: list[str] = Field(default_factory=list)
    religion: str | None = None


class PersonRole(BaseModel):
    """A single parliamentary role entry with WP-specific Fraktion data.

    Attributes:
        fraktion: Fraktion name for this role, or None if not a Fraktion role.
        wahlperiode_nummer: Wahlperioden this role applies to.
    """

    model_config = ConfigDict(extra="ignore")

    fraktion: str | None = None
    wahlperiode_nummer: list[int] = Field(default_factory=list)


class Person(BaseModel):
    """A parliamentary member as returned by the DIP /person endpoint.

    The DIP API returns a flat structure — vorname and nachname are at the top
    level, and fraktion is a list. The person_name property constructs a
    PersonName from these flat fields for downstream compatibility.

    Attributes:
        id: Unique DIP identifier.
        typ: Document type, always "Person".
        vorname: First name.
        nachname: Last name (family name).
        namenszusatz: Name suffix or particle, e.g. "von".
        titel: Full formatted title string, e.g. "Dr. Friedrich Merz, MdB, CDU/CSU".
        fraktion: List of Fraktion names this person belongs to.
        funktion: List of parliamentary functions, e.g. ["MdB"].
        wahlperiode: List of Wahlperiode numbers this person appears in.
        datum: Last update date as ISO 8601 string.
        basisdatum: Base date as ISO 8601 string.
        aktualisiert: Last modification timestamp as ISO 8601 string.
        biografie: Optional biographical details (available from detail endpoint).
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    typ: str
    vorname: str
    nachname: str
    namenszusatz: str | None = None
    titel: str | None = None
    fraktion: list[str] = Field(default_factory=list)
    funktion: list[str] = Field(default_factory=list)
    wahlperiode: list[int] = Field(default_factory=list)
    person_roles: list[PersonRole] = Field(default_factory=list)
    datum: str | None = None
    basisdatum: str | None = None
    aktualisiert: str | None = None
    biografie: PersonBiography | None = None

    @property
    def person_name(self) -> PersonName:
        """Return structured name components constructed from flat API fields.

        Returns:
            PersonName built from vorname, nachname, and namenszusatz.
        """
        return PersonName(
            vorname=self.vorname,
            nachname=self.nachname,
            namenszusatz=self.namenszusatz,
        )

    @property
    def display_name(self) -> str:
        """Return the canonical display name for this person.

        Prefers the API-provided titel (first segment before the first comma)
        since it includes academic honorifics not available as separate fields.

        Returns:
            Display name string, e.g. "Dr. Friedrich Merz".
        """
        if self.titel:
            return self.titel.split(",")[0].strip()
        return self.person_name.full_name

    @property
    def fraktion_name(self) -> str | None:
        """Return the primary Fraktion name, or None if unaffiliated.

        Returns:
            First Fraktion name from the list, or None if the list is empty.
        """
        return self.fraktion[0] if self.fraktion else None

    def fraktion_for_wp(self, wahlperiode: int) -> str | None:
        """Return the Fraktion this person belonged to in a specific Wahlperiode.

        Checks person_roles first for a WP-specific Fraktion entry, then falls
        back to the top-level fraktion field.

        Args:
            wahlperiode: The election period to look up.

        Returns:
            Fraktion name for the given WP, or None if unaffiliated.
        """
        for role in self.person_roles:
            if wahlperiode in role.wahlperiode_nummer and role.fraktion:
                return role.fraktion
        return self.fraktion_name


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response envelope from the DIP API.

    Attributes:
        num_found: Total number of matching documents across all pages.
        cursor: Opaque pagination cursor for the next page, or None on last page.
        documents: List of documents for the current page.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    num_found: int = Field(alias="numFound")
    cursor: str | None = None
    documents: list[T] = Field(default_factory=list)


class FraktionDistribution(BaseModel):
    """Per-Fraktion share of the total parliamentary membership.

    Attributes:
        fraktion_name: Official name of the parliamentary group.
        person_count: Number of members belonging to this Fraktion.
        percentage: Share of total parliamentary members as a percentage (0-100).
    """

    fraktion_name: str
    person_count: int
    percentage: float


class DistributionReport(BaseModel):
    """Aggregated Fraktion distribution report for a given Wahlperiode.

    Attributes:
        wahlperiode: Election period number.
        total_persons: Total number of persons fetched from the API.
        unaffiliated_count: Number of persons with no Fraktion affiliation.
        distribution: Ordered list of per-Fraktion distribution entries.
    """

    wahlperiode: int
    total_persons: int
    unaffiliated_count: int
    distribution: list[FraktionDistribution]

    @model_validator(mode="after")
    def validate_percentage_sum(self) -> Self:
        """Validate that Fraktion percentages are arithmetically consistent.

        Skips the check when distribution is empty or unaffiliated members are
        present, since their share is excluded from the distribution list.

        Returns:
            The validated DistributionReport instance.

        Raises:
            ValueError: If percentage sum exceeds 100 by more than 1.0.
        """
        if not self.distribution or self.unaffiliated_count > 0:
            return self
        total = sum(d.percentage for d in self.distribution)
        if total > 101.0:
            raise ValueError(
                f"Distribution percentages sum to {total:.2f}, "
                "which exceeds 100 by more than the allowed 1.0 tolerance."
            )
        return self
