# Only for Greenhouse, needs update for Lever and others
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CollectorJob(BaseModel):
    """Normalized representation of a job returned by an ATS."""

    model_config = ConfigDict(extra="ignore")

    external_id: str
    title: str

    application_url: str | None = None
    location: str | None = None

    description_html: str | None = None
    description_text: str | None = None

    departments: list[str] = Field(default_factory=list)
    offices: list[str] = Field(default_factory=list)

    employment_type: str | None = None
    publication_date: datetime | None = None
    updated_at: datetime | None = None

    language: str | None = None
    requisition_id: str | None = None

    raw_payload: dict[str, Any]


class CollectionResult(BaseModel):
    """Result of collecting jobs from one ATS board."""

    platform: str
    board_identifier: str

    jobs: list[CollectorJob] = Field(default_factory=list)

    collected_at: datetime

    total_received: int = 0
    total_valid: int = 0
    total_skipped: int = 0

    warnings: list[str] = Field(default_factory=list)
