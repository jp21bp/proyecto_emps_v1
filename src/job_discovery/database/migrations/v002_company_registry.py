import sqlite3


def upgrade(connection: sqlite3.Connection) -> None:
    """Add company domain and ATS monitoring metadata."""

    connection.execute("""
        ALTER TABLE companies
        ADD COLUMN normalized_domain TEXT
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_companies_domain
        ON companies(normalized_domain)
    """)

    connection.execute("""
        ALTER TABLE ats_boards
        ADD COLUMN last_attempted_at TEXT
    """)

    connection.execute("""
        ALTER TABLE ats_boards
        ADD COLUMN last_successful_at TEXT
    """)

    connection.execute("""
        ALTER TABLE ats_boards
        ADD COLUMN consecutive_failures INTEGER NOT NULL DEFAULT 0
    """)

    connection.execute("""
        ALTER TABLE ats_boards
        ADD COLUMN last_error TEXT
    """)

    connection.execute("""
        ALTER TABLE ats_boards
        ADD COLUMN next_check_at TEXT
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_ats_boards_next_check
        ON ats_boards(next_check_at)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_ats_boards_last_successful
        ON ats_boards(last_successful_at)
    """)
