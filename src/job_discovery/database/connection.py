import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def create_connection(database_path: Path) -> sqlite3.Connection:
    """Create a configured SQLite connection."""

    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        database_path,
        timeout=30.0,
    )

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")

    return connection


@contextmanager
def get_connection(
    database_path: Path,
) -> Iterator[sqlite3.Connection]:
    """Provide a connection with automatic commit and rollback."""

    connection = create_connection(database_path)

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
