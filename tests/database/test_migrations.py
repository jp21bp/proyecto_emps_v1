import sqlite3
from pathlib import Path

from job_discovery.database.repository import Repository
from job_discovery.database.schema import SCHEMA


def test_v1_database_migrates_to_v2(tmp_path: Path) -> None:
    database_path = tmp_path / "jobs.db"

    connection = sqlite3.connect(database_path)

    connection.executescript(SCHEMA)

    connection.execute("""
        CREATE TABLE schema_version (
            version INTEGER NOT NULL
        )
    """)

    connection.execute(
        "INSERT INTO schema_version(version) VALUES (1)"
    )

    connection.commit()
    connection.close()

    Repository(database_path)

    connection = sqlite3.connect(database_path)

    version = connection.execute(
        "SELECT version FROM schema_version"
    ).fetchone()[0]

    columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(ats_boards)"
        ).fetchall()
    }

    connection.close()

    assert version == 2
    assert "last_successful_at" in columns
    assert "consecutive_failures" in columns
    assert "next_check_at" in columns