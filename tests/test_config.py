from pathlib import Path

import pytest
from pydantic import ValidationError

from job_discovery.core.config import Settings, load_settings


def test_load_valid_configuration(tmp_path: Path) -> None:
    config_file = tmp_path / "settings.yaml"

    config_file.write_text(
        """
project:
  name: test-project

http:
  timeout_seconds: 15
  max_retries: 2
""",
        encoding="utf-8",
    )

    settings = load_settings(config_file)

    assert settings.project.name == "test-project"
    assert settings.http.timeout_seconds == 15
    assert settings.http.max_retries == 2


def test_missing_configuration_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "missing.yaml")


def test_invalid_http_timeout() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "http": {
                    "timeout_seconds": -1,
                }
            }
        )


def test_unknown_configuration_field() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "unknown_setting": True,
            }
        )
