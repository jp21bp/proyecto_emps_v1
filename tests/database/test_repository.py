import sqlite3
from pathlib import Path
from uuid import UUID

import pytest

from job_discovery.database.connection import get_connection
from job_discovery.database.repository import Repository
from job_discovery.models.company import ATSBoardCreate, CompanyCreate
from job_discovery.models.job import JobCreate


def create_test_company(repository: Repository) -> tuple[str, str]:
    company_id = repository.create_company(
        CompanyCreate(
            name="Example Company",
            website_url="https://example.com",
            careers_url="https://example.com/careers",
            headquarters_country="United States",
        )
    )

    board_id = repository.create_ats_board(
        ATSBoardCreate(
            company_id=UUID(company_id),
            platform="GREENHOUSE",
            board_identifier="example",
        )
    )

    return company_id, board_id


def create_test_job(
    company_id: str,
    board_id: str,
) -> JobCreate:
    return JobCreate(
        company_id=UUID(company_id),
        ats_board_id=UUID(board_id),
        external_id="12345",
        title="Junior Data Analyst",
        application_url="https://example.com/jobs/12345",
        location="Remote - Americas",
        raw_payload={
            "id": "12345",
            "title": "Junior Data Analyst",
        },
    )


def test_database_initialization(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "jobs.db")

    counts = repository.count_records()

    assert counts == {
        "companies": 0,
        "ats_boards": 0,
        "jobs": 0,
        "raw_job_payloads": 0,
        "job_history": 0,
        "applications": 0,
    }


def test_create_company_and_board(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "jobs.db")

    company_id, board_id = create_test_company(repository)

    assert UUID(company_id)
    assert UUID(board_id)

    counts = repository.count_records()

    assert counts["companies"] == 1
    assert counts["ats_boards"] == 1


def test_save_new_job(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "jobs.db")

    company_id, board_id = create_test_company(repository)

    job = create_test_job(company_id, board_id)

    job_id, created = repository.save_job(job)

    assert UUID(job_id)
    assert created is True

    counts = repository.count_records()

    assert counts["jobs"] == 1
    assert counts["raw_job_payloads"] == 1
    assert counts["job_history"] == 1


def test_save_duplicate_job(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "jobs.db")

    company_id, board_id = create_test_company(repository)

    job = create_test_job(company_id, board_id)

    first_id, first_created = repository.save_job(job)
    second_id, second_created = repository.save_job(job)

    assert first_id == second_id
    assert first_created is True
    assert second_created is False

    counts = repository.count_records()

    assert counts["jobs"] == 1
    assert counts["raw_job_payloads"] == 1


def test_changed_raw_payload_is_preserved(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "jobs.db")

    company_id, board_id = create_test_company(repository)

    first_job = create_test_job(company_id, board_id)
    second_job = create_test_job(company_id, board_id)

    second_job.raw_payload["new_field"] = "new value"

    first_id, _ = repository.save_job(first_job)
    second_id, _ = repository.save_job(second_job)

    assert first_id == second_id

    counts = repository.count_records()

    assert counts["jobs"] == 1
    assert counts["raw_job_payloads"] == 2


def test_foreign_key_enforcement(tmp_path: Path) -> None:
    database_path = tmp_path / "jobs.db"
    Repository(database_path)

    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(database_path) as connection:
            connection.execute(
                """
                INSERT INTO ats_boards (
                    id, company_id, platform, board_identifier,
                    first_seen_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "invalid-board",
                    "nonexistent-company",
                    "GREENHOUSE",
                    "example",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
