from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


def utc_now() -> datetime:
    return datetime.now(UTC)


class CompanyCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    website_url: HttpUrl | None = None
    careers_url: HttpUrl | None = None
    headquarters_country: str | None = Field(default=None, max_length=100)
    description: str | None = None
    discovery_source: str | None = Field(default=None, max_length=100)


class Company(CompanyCreate):
    id: UUID = Field(default_factory=uuid4)
    first_seen_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)
    is_active: bool = True


class ATSBoardCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    company_id: UUID
    platform: str = Field(min_length=1, max_length=50)
    board_identifier: str = Field(min_length=1, max_length=255)
    board_url: HttpUrl | None = None


class ATSBoard(ATSBoardCreate):
    id: UUID = Field(default_factory=uuid4)
    first_seen_at: datetime = Field(default_factory=utc_now)
    last_checked_at: datetime | None = None
    is_active: bool = True
