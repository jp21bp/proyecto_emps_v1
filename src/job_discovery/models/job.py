from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


def utc_now() -> datetime:
    return datetime.now(UTC)


class RemoteClassification(StrEnum):
    WORLDWIDE = "WORLDWIDE"
    US_ONLY = "US_ONLY"
    LATAM = "LATAM"
    AMERICAS = "AMERICAS"
    COUNTRY_RESTRICTED = "COUNTRY_RESTRICTED"
    UNCLEAR = "UNCLEAR"
    HYBRID = "HYBRID"
    ONSITE = "ONSITE"


class GeographicEligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class EmploymentType(StrEnum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    INTERNSHIP = "INTERNSHIP"
    TEMPORARY = "TEMPORARY"
    UNKNOWN = "UNKNOWN"


class JobStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"


class JobCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    company_id: UUID
    ats_board_id: UUID
    external_id: str = Field(min_length=1, max_length=255)

    title: str = Field(min_length=1, max_length=500)
    description: str | None = None

    application_url: HttpUrl
    source_url: HttpUrl | None = None

    location: str | None = None
    remote_classification: RemoteClassification = RemoteClassification.UNCLEAR
    geographic_eligibility: GeographicEligibility = GeographicEligibility.NEEDS_REVIEW

    employment_type: EmploymentType = EmploymentType.UNKNOWN

    publication_date: date | None = None

    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=10)

    required_experience_years: float | None = Field(default=None, ge=0)
    preferred_experience_years: float | None = Field(default=None, ge=0)

    skills: list[str] = Field(default_factory=list)

    raw_payload: dict[str, Any] = Field(default_factory=dict)


class Job(JobCreate):
    id: UUID = Field(default_factory=uuid4)

    first_seen_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)

    status: JobStatus = JobStatus.ACTIVE

    match_score: float | None = Field(default=None, ge=0, le=100)
    match_explanation: str | None = None
