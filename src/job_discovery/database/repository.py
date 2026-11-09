import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from job_discovery.database.connection import get_connection
from job_discovery.database.schema import initialize_database
from job_discovery.models.application import ApplicationCreate
from job_discovery.models.company import ATSBoardCreate, CompanyCreate
from job_discovery.models.job import JobCreate


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Repository:
    """Persistence interface for the job discovery application."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

        with get_connection(self.database_path) as connection:
            initialize_database(connection)

    def create_company(self, company: CompanyCreate) -> str:
        data = company.model_dump(mode="json")
        now = utc_now_iso()
        company_id = str(uuid4())

        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO companies (
                    id, name, website_url, careers_url,
                    headquarters_country, description,
                    discovery_source, first_seen_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id,
                    data["name"],
                    data["website_url"],
                    data["careers_url"],
                    data["headquarters_country"],
                    data["description"],
                    data["discovery_source"],
                    now,
                    now,
                ),
            )

            return company_id

    def create_ats_board(self, board: ATSBoardCreate) -> Any:
        data = board.model_dump(mode="json")
        now = utc_now_iso()
        board_id = str(uuid4())

        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO ats_boards (
                    id, company_id, platform, board_identifier,
                    board_url, first_seen_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(platform, board_identifier)
                DO NOTHING
                """,
                (
                    board_id,
                    data["company_id"],
                    data["platform"].upper(),
                    data["board_identifier"],
                    data["board_url"],
                    now,
                ),
            )

            row = connection.execute(
                """
                SELECT id, company_id
                FROM ats_boards
                WHERE platform = ? AND board_identifier = ?
                """,
                (
                    data["platform"].upper(),
                    data["board_identifier"],
                ),
            ).fetchone()

            if row is None:
                raise RuntimeError("Failed to retrieve ATS board.")

            if row["company_id"] != data["company_id"]:
                raise ValueError("The ATS board identifier already belongs to another company.")

            return row["id"]

    def save_job(self, job: JobCreate) -> tuple[str, bool]:
        """
        Insert or update a job and preserve its original discovery timestamp.

        Returns:
            (job_id, created)
        """

        data = job.model_dump(mode="json")
        now = utc_now_iso()

        payload_json = json.dumps(
            data["raw_payload"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

        with get_connection(self.database_path) as connection:
            existing = connection.execute(
                """
                SELECT id FROM jobs
                WHERE ats_board_id = ? AND external_id = ?
                """,
                (data["ats_board_id"], data["external_id"]),
            ).fetchone()

            created = existing is None

            if created:
                job_id = str(uuid4())

                connection.execute(
                    """
                    INSERT INTO jobs (
                        id, company_id, ats_board_id, external_id,
                        title, description, application_url, source_url,
                        location, remote_classification,
                        geographic_eligibility, employment_type,
                        publication_date, salary_min, salary_max,
                        salary_currency, required_experience_years,
                        preferred_experience_years, skills_json,
                        first_seen_at, last_seen_at, status,
                        match_score, match_explanation
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, 'ACTIVE', NULL, NULL
                    )
                    """,
                    (
                        job_id,
                        data["company_id"],
                        data["ats_board_id"],
                        data["external_id"],
                        data["title"],
                        data["description"],
                        data["application_url"],
                        data["source_url"],
                        data["location"],
                        data["remote_classification"],
                        data["geographic_eligibility"],
                        data["employment_type"],
                        data["publication_date"],
                        data["salary_min"],
                        data["salary_max"],
                        data["salary_currency"],
                        data["required_experience_years"],
                        data["preferred_experience_years"],
                        json.dumps(data["skills"], ensure_ascii=False),
                        now,
                        now,
                    ),
                )

                connection.execute(
                    """
                    INSERT INTO job_history (
                        job_id, event_type, recorded_at
                    )
                    VALUES (?, 'NEW', ?)
                    """,
                    (job_id, now),
                )

            else:
                job_id = existing["id"]

                connection.execute(
                    """
                    UPDATE jobs SET
                        title = ?,
                        description = ?,
                        application_url = ?,
                        source_url = ?,
                        location = ?,
                        remote_classification = ?,
                        geographic_eligibility = ?,
                        employment_type = ?,
                        publication_date = ?,
                        salary_min = ?,
                        salary_max = ?,
                        salary_currency = ?,
                        required_experience_years = ?,
                        preferred_experience_years = ?,
                        skills_json = ?,
                        last_seen_at = ?,
                        status = 'ACTIVE'
                    WHERE id = ?
                    """,
                    (
                        data["title"],
                        data["description"],
                        data["application_url"],
                        data["source_url"],
                        data["location"],
                        data["remote_classification"],
                        data["geographic_eligibility"],
                        data["employment_type"],
                        data["publication_date"],
                        data["salary_min"],
                        data["salary_max"],
                        data["salary_currency"],
                        data["required_experience_years"],
                        data["preferred_experience_years"],
                        json.dumps(data["skills"], ensure_ascii=False),
                        now,
                        job_id,
                    ),
                )

            connection.execute(
                """
                INSERT INTO raw_job_payloads (
                    job_id, payload_hash, payload_json, collected_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(job_id, payload_hash) DO NOTHING
                """,
                (job_id, payload_hash, payload_json, now),
            )

            return job_id, created

    def create_application(
        self,
        application: ApplicationCreate,
    ) -> str:
        data = application.model_dump(mode="json")
        now = utc_now_iso()

        from uuid import uuid4

        application_id = str(uuid4())

        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO applications (
                    id, job_id, status, application_date,
                    notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application_id,
                    data["job_id"],
                    data["status"],
                    data["application_date"],
                    data["notes"],
                    now,
                    now,
                ),
            )

        return application_id

    def count_records(self) -> dict[str, int]:
        tables = [
            "companies",
            "ats_boards",
            "jobs",
            "raw_job_payloads",
            "job_history",
            "applications",
        ]

        with get_connection(self.database_path) as connection:
            return {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in tables
            }
