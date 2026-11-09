from pathlib import Path

import pytest

from job_discovery.database.repository import Repository
from job_discovery.models.company import (
    ATSBoardCreate,
    ATSPlatform,
    CompanyCreate,
)
from job_discovery.registry.service import CompanyRegistry


@pytest.fixture
def registry(tmp_path: Path) -> CompanyRegistry:
    database_path = tmp_path / "jobs.db"
    Repository(database_path)
    return CompanyRegistry(database_path)


def create_company(registry: CompanyRegistry) -> str:
    company, created = registry.register_company(
        CompanyCreate(
            name="Example Company",
            website_url="https://www.example.com",
            careers_url="https://www.example.com/careers",
        )
    )

    assert created
    return company


def test_register_company(registry: CompanyRegistry) -> None:
    company_id, created = registry.register_company(
        CompanyCreate(
            name="Example Company",
            website_url="https://example.com",
        )
    )

    assert created
    assert len(company_id) == 36

    companies = registry.get_active_companies()

    assert len(companies) == 1
    assert companies[0]["name"] == "Example Company"
    assert companies[0]["normalized_domain"] == "example.com"


def test_duplicate_company_domain(registry: CompanyRegistry) -> None:
    first_id, first_created = registry.register_company(
        CompanyCreate(
            name="Example Company",
            website_url="https://www.example.com/",
        )
    )

    second_id, second_created = registry.register_company(
        CompanyCreate(
            name="Example Company",
            website_url="http://example.com",
            careers_url="https://example.com/careers",
        )
    )

    assert first_id == second_id
    assert first_created is True
    assert second_created is False

    assert len(registry.get_active_companies()) == 1


def test_register_ats_board(registry: CompanyRegistry) -> None:
    company_id = create_company(registry)

    board_id, created = registry.register_ats_board(
        ATSBoardCreate(
            company_id=company_id,
            platform=ATSPlatform.GREENHOUSE,
            board_identifier="example",
        )
    )

    assert created
    assert len(board_id) == 36

    boards = registry.get_active_boards()

    assert len(boards) == 1
    assert boards[0]["platform"] == "GREENHOUSE"
    assert boards[0]["company_name"] == "Example Company"


def test_duplicate_board_registration(
    registry: CompanyRegistry,
) -> None:
    company_id = create_company(registry)

    first_id, first_created = registry.register_ats_board(
        ATSBoardCreate(
            company_id=company_id,
            platform=ATSPlatform.LEVER,
            board_identifier="example",
        )
    )

    second_id, second_created = registry.register_ats_board(
        ATSBoardCreate(
            company_id=company_id,
            platform=ATSPlatform.LEVER,
            board_identifier="example",
        )
    )

    assert first_id == second_id
    assert first_created is True
    assert second_created is False


def test_board_cannot_belong_to_two_companies(
    registry: CompanyRegistry,
) -> None:
    first_company = create_company(registry)

    second_company, _ = registry.register_company(CompanyCreate(name="Another Company"))

    registry.register_ats_board(
        ATSBoardCreate(
            company_id=first_company,
            platform=ATSPlatform.ASHBY,
            board_identifier="example",
        )
    )

    with pytest.raises(ValueError, match="another company"):
        registry.register_ats_board(
            ATSBoardCreate(
                company_id=second_company,
                platform=ATSPlatform.ASHBY,
                board_identifier="example",
            )
        )


def test_monitoring_success_and_failure(
    registry: CompanyRegistry,
) -> None:
    company_id = create_company(registry)

    board_id, _ = registry.register_ats_board(
        ATSBoardCreate(
            company_id=company_id,
            platform=ATSPlatform.GREENHOUSE,
            board_identifier="example",
        )
    )

    registry.record_collection_failure(
        board_id,
        "HTTP 503",
        retry_minutes=60,
    )

    board = registry.get_active_boards()[0]

    assert board["consecutive_failures"] == 1
    assert board["last_error"] == "HTTP 503"
    assert board["next_check_at"] is not None

    registry.record_collection_success(board_id)

    board = registry.get_active_boards()[0]

    assert board["consecutive_failures"] == 0
    assert board["last_error"] is None
    assert board["last_successful_at"] is not None
    assert board["next_check_at"] is None


def test_deactivate_company(
    registry: CompanyRegistry,
) -> None:
    company_id = create_company(registry)

    registry.register_ats_board(
        ATSBoardCreate(
            company_id=company_id,
            platform=ATSPlatform.GREENHOUSE,
            board_identifier="example",
        )
    )

    registry.set_company_active(company_id, False)

    assert registry.get_active_companies() == []
    assert registry.get_active_boards() == []
