from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class ApplicationStatus(StrEnum):
    INTERESTED = "INTERESTED"
    PREPARING = "PREPARING"
    APPLIED = "APPLIED"
    INTERVIEWING = "INTERVIEWING"
    REJECTED = "REJECTED"
    OFFERED = "OFFERED"
    WITHDRAWN = "WITHDRAWN"


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: UUID
    status: ApplicationStatus = ApplicationStatus.INTERESTED
    application_date: date | None = None
    notes: str | None = None


class Application(ApplicationCreate):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
