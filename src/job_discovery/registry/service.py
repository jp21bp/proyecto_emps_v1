from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from typing import Any

from job_discovery.database.connection import get_connection
from job_discovery.discovery.domain import normalize_domain
from job_discovery.models.company import ATSBoardCreate, CompanyCreate


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_iso(value: datetime | None = None) -> str:
    value = value or utc_now()
    return value.isoformat()


class CompanyRegistry:
    """Manage employer records and ATS board registrations."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def register_company(
        self,
        company: CompanyCreate,
    ) -> tuple[str, bool]:
        """
        Register a company.

        Returns:
            (company_id, created)

        An existing company with the same normalized website domain
        is returned instead of creating a duplicate.
        """

        data = company.model_dump(mode="json")
        domain = normalize_domain(data["website_url"])
        now = utc_iso()

        with get_connection(self.database_path) as connection:
            if domain:
                existing = connection.execute(
                    """
                    SELECT id FROM companies
                    WHERE normalized_domain = ?
                    ORDER BY first_seen_at
                    LIMIT 1
                    """,
                    (domain,),
                ).fetchone()

                if existing:
                    company_id = existing["id"]

                    connection.execute(
                        """
                        UPDATE companies
                        SET
                            last_seen_at = ?,
                            website_url = COALESCE(website_url, ?),
                            careers_url = COALESCE(careers_url, ?),
                            headquarters_country =
                                COALESCE(headquarters_country, ?),
                            description = COALESCE(description, ?),
                            discovery_source =
                                COALESCE(discovery_source, ?)
                        WHERE id = ?
                        """,
                        (
                            now,
                            data["website_url"],
                            data["careers_url"],
                            data["headquarters_country"],
                            data["description"],
                            data["discovery_source"],
                            company_id,
                        ),
                    )

                    return company_id, False

            company_id = str(uuid4())

            connection.execute(
                """
                INSERT INTO companies (
                    id, name, website_url, careers_url,
                    headquarters_country, description,
                    discovery_source, first_seen_at,
                    last_seen_at, is_active, normalized_domain
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
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
                    domain,
                ),
            )

            return company_id, True

    def register_ats_board(
        self,
        board: ATSBoardCreate,
    ) -> tuple[str, bool]:
        """
        Register an ATS board.

        Returns:
            (board_id, created)
        """

        data = board.model_dump(mode="json")
        board_id = str(uuid4())
        now = utc_iso()

        with get_connection(self.database_path) as connection:
            company = connection.execute(
                """
                SELECT id FROM companies
                WHERE id = ? AND is_active = 1
                """,
                (str(data["company_id"]),),
            ).fetchone()

            if company is None:
                raise ValueError(f"Company not found or inactive: {data['company_id']}")

            existing = connection.execute(
                """
                SELECT id, company_id FROM ats_boards
                WHERE platform = ? AND board_identifier = ?
                """,
                (
                    data["platform"],
                    data["board_identifier"],
                ),
            ).fetchone()

            if existing:
                if existing["company_id"] != str(data["company_id"]):
                    raise ValueError("ATS board identifier already belongs to another company.")

                connection.execute(
                    """
                    UPDATE ats_boards
                    SET
                        board_url = COALESCE(board_url, ?),
                        is_active = 1
                    WHERE id = ?
                    """,
                    (data["board_url"], existing["id"]),
                )

                return existing["id"], False

            connection.execute(
                """
                INSERT INTO ats_boards (
                    id, company_id, platform,
                    board_identifier, board_url,
                    first_seen_at, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    board_id,
                    str(data["company_id"]),
                    data["platform"],
                    data["board_identifier"],
                    data["board_url"],
                    now,
                ),
            )

            return board_id, True

    def get_active_companies(self) -> list[dict[str, Any]]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM companies
                WHERE is_active = 1
                ORDER BY name COLLATE NOCASE
                """
            ).fetchall()

            return [dict(row) for row in rows]

    def get_active_boards(
        self,
        platform: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                b.*,
                c.name AS company_name,
                c.website_url,
                c.careers_url
            FROM ats_boards b
            JOIN companies c ON c.id = b.company_id
            WHERE b.is_active = 1
              AND c.is_active = 1
        """

        parameters: tuple[Any, ...] = ()

        if platform:
            query += " AND b.platform = ?"
            parameters = (platform.upper(),)

        query += " ORDER BY c.name COLLATE NOCASE"

        with get_connection(self.database_path) as connection:
            rows = connection.execute(query, parameters).fetchall()
            return [dict(row) for row in rows]

    def get_boards_due_for_collection(
        self,
        interval_minutes: int = 180,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Retrieve boards that are due for routine monitoring.

        A failed board is eligible for retry after its next_check_at.
        """

        if interval_minutes < 0 or limit < 1:
            raise ValueError("Invalid collection interval or limit.")

        now = utc_iso()
        cutoff = utc_iso(utc_now() - timedelta(minutes=interval_minutes))

        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    b.*,
                    c.name AS company_name
                FROM ats_boards b
                JOIN companies c ON c.id = b.company_id
                WHERE b.is_active = 1
                  AND c.is_active = 1
                  AND (
                      b.last_successful_at IS NULL
                      OR b.last_successful_at <= ?
                  )
                  AND (
                      b.next_check_at IS NULL
                      OR b.next_check_at <= ?
                  )
                ORDER BY
                    b.last_successful_at IS NOT NULL,
                    b.last_successful_at ASC,
                    b.first_seen_at ASC
                LIMIT ?
                """,
                (cutoff, now, limit),
            ).fetchall()

            return [dict(row) for row in rows]

    def record_collection_success(
        self,
        board_id: str,
    ) -> None:
        now = utc_iso()

        with get_connection(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE ats_boards
                SET
                    last_attempted_at = ?,
                    last_successful_at = ?,
                    consecutive_failures = 0,
                    last_error = NULL,
                    next_check_at = NULL
                WHERE id = ?
                """,
                (now, now, board_id),
            )

            if cursor.rowcount == 0:
                raise ValueError(f"Unknown ATS board: {board_id}")

    def record_collection_failure(
        self,
        board_id: str,
        error: str,
        retry_minutes: int = 60,
    ) -> None:
        if retry_minutes < 0:
            raise ValueError("retry_minutes cannot be negative.")

        now = utc_now()

        with get_connection(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE ats_boards
                SET
                    last_attempted_at = ?,
                    consecutive_failures = consecutive_failures + 1,
                    last_error = ?,
                    next_check_at = ?
                WHERE id = ?
                """,
                (
                    now.isoformat(),
                    error[:2000],
                    utc_iso(now + timedelta(minutes=retry_minutes)),
                    board_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(f"Unknown ATS board: {board_id}")

    def set_company_active(
        self,
        company_id: str,
        active: bool,
    ) -> None:
        with get_connection(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE companies
                SET is_active = ?
                WHERE id = ?
                """,
                (int(active), company_id),
            )

            if cursor.rowcount == 0:
                raise ValueError(f"Unknown company: {company_id}")

    def set_board_active(
        self,
        board_id: str,
        active: bool,
    ) -> None:
        with get_connection(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE ats_boards
                SET is_active = ?
                WHERE id = ?
                """,
                (int(active), board_id),
            )

            if cursor.rowcount == 0:
                raise ValueError(f"Unknown ATS board: {board_id}")
