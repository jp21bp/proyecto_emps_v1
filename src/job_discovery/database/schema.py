import sqlite3

SCHEMA_VERSION = 2


SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    website_url TEXT,
    careers_url TEXT,
    headquarters_country TEXT,
    description TEXT,
    discovery_source TEXT,

    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,

    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_companies_name
    ON companies(name);

CREATE INDEX IF NOT EXISTS idx_companies_active
    ON companies(is_active);


CREATE TABLE IF NOT EXISTS ats_boards (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,

    platform TEXT NOT NULL,
    board_identifier TEXT NOT NULL,
    board_url TEXT,

    first_seen_at TEXT NOT NULL,
    last_checked_at TEXT,

    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),

    FOREIGN KEY (company_id)
        REFERENCES companies(id)
        ON DELETE RESTRICT,

    UNIQUE(platform, board_identifier)
);

CREATE INDEX IF NOT EXISTS idx_ats_boards_company
    ON ats_boards(company_id);

CREATE INDEX IF NOT EXISTS idx_ats_boards_active
    ON ats_boards(is_active);


CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,

    company_id TEXT NOT NULL,
    ats_board_id TEXT NOT NULL,
    external_id TEXT NOT NULL,

    title TEXT NOT NULL,
    description TEXT,

    application_url TEXT NOT NULL,
    source_url TEXT,

    location TEXT,
    remote_classification TEXT NOT NULL,
    geographic_eligibility TEXT NOT NULL,
    employment_type TEXT NOT NULL,

    publication_date TEXT,

    salary_min REAL,
    salary_max REAL,
    salary_currency TEXT,

    required_experience_years REAL,
    preferred_experience_years REAL,

    skills_json TEXT NOT NULL DEFAULT '[]',

    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,

    status TEXT NOT NULL DEFAULT 'ACTIVE',

    match_score REAL
        CHECK (match_score IS NULL OR
               (match_score >= 0 AND match_score <= 100)),

    match_explanation TEXT,

    FOREIGN KEY (company_id)
        REFERENCES companies(id)
        ON DELETE RESTRICT,

    FOREIGN KEY (ats_board_id)
        REFERENCES ats_boards(id)
        ON DELETE RESTRICT,

    UNIQUE(ats_board_id, external_id),

    CHECK (salary_min IS NULL OR salary_max IS NULL
           OR salary_min <= salary_max)
);

CREATE INDEX IF NOT EXISTS idx_jobs_company
    ON jobs(company_id);

CREATE INDEX IF NOT EXISTS idx_jobs_board
    ON jobs(ats_board_id);

CREATE INDEX IF NOT EXISTS idx_jobs_status
    ON jobs(status);

CREATE INDEX IF NOT EXISTS idx_jobs_first_seen
    ON jobs(first_seen_at);

CREATE INDEX IF NOT EXISTS idx_jobs_publication_date
    ON jobs(publication_date);

CREATE INDEX IF NOT EXISTS idx_jobs_score
    ON jobs(match_score);


CREATE TABLE IF NOT EXISTS raw_job_payloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    job_id TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,

    collected_at TEXT NOT NULL,

    FOREIGN KEY (job_id)
        REFERENCES jobs(id)
        ON DELETE RESTRICT,

    UNIQUE(job_id, payload_hash)
);

CREATE INDEX IF NOT EXISTS idx_raw_payloads_job
    ON raw_job_payloads(job_id);


CREATE TABLE IF NOT EXISTS job_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    job_id TEXT NOT NULL,

    event_type TEXT NOT NULL,
    field_name TEXT,

    old_value TEXT,
    new_value TEXT,

    recorded_at TEXT NOT NULL,

    FOREIGN KEY (job_id)
        REFERENCES jobs(id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_job_history_job
    ON job_history(job_id);

CREATE INDEX IF NOT EXISTS idx_job_history_date
    ON job_history(recorded_at);


CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY,

    job_id TEXT NOT NULL UNIQUE,

    status TEXT NOT NULL,

    application_date TEXT,
    notes TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (job_id)
        REFERENCES jobs(id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_applications_status
    ON applications(status);
"""


## SCHEMA_VERSION == 1
# def initialize_database(connection: sqlite3.Connection) -> None:
#     """Create the initial schema and record its version."""

#     connection.execute("""
#         CREATE TABLE IF NOT EXISTS schema_version (
#             version INTEGER NOT NULL
#         )
#     """)

#     version_row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()

#     if version_row is None:
#         current_version = 0
#     else:
#         current_version = version_row["version"]

#     if current_version > SCHEMA_VERSION:
#         raise RuntimeError(
#             f"Database version {current_version} is newer than supported version {SCHEMA_VERSION}"
#         )

#     if current_version == 0:
#         # Ensures all tables are created
#         connection.executescript(SCHEMA)

#         connection.execute(
#             "INSERT INTO schema_version(version) VALUES (?)",
#             (SCHEMA_VERSION,),
#         )

#     elif current_version < SCHEMA_VERSION:
#         raise RuntimeError(
#             "Database requires a migration. "
#             f"Current version: {current_version}; "
#             f"supported version: {SCHEMA_VERSION}."
#         )

#     # if current_version == SCHEMA_VERSION: nothing needs to be done


## SCHEMA_VERSION == 2
def initialize_database(connection: sqlite3.Connection) -> None:
    """Create the initial schema and apply pending migrations."""

    from job_discovery.database.migrations.v002_company_registry import (
        upgrade as upgrade_v2,
    )

    connection.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        )
    """)

    version_row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()

    if version_row is None:
        connection.executescript(SCHEMA)

        connection.execute("INSERT INTO schema_version(version) VALUES (1)")

        current_version = 1
    else:
        current_version = version_row["version"]

    if current_version > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database version {current_version} is newer than supported version {SCHEMA_VERSION}."
        )

    migrations = {
        2: upgrade_v2,
    }

    while current_version < SCHEMA_VERSION:
        next_version = current_version + 1
        migration = migrations.get(next_version)

        if migration is None:
            raise RuntimeError(f"Missing database migration for version {next_version}.")

        migration(connection)

        connection.execute(
            "UPDATE schema_version SET version = ?",
            (next_version,),
        )

        current_version = next_version
