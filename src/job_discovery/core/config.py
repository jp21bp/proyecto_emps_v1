"""
This file creates a pseudo dataclass with corresponding fields
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ProjectConfig(BaseModel):
    name: str = "job-discovery"
    environment: Literal["development", "production", "testing"] = "development"


class StorageConfig(BaseModel):
    database_path: Path = Path("data/jobs.db")
    raw_data_dir: Path = Path("data/raw")
    exports_dir: Path = Path("data/exports")


class LoggingConfig(BaseModel):
    directory: Path = Path("logs")
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    filename: str = "application.log"


class HTTPConfig(BaseModel):
    timeout_seconds: float = Field(default=30, gt=0)
    request_interval_seconds: float = Field(default=2.0, ge=0)
    max_retries: int = Field(default=3, ge=0)
    user_agent: str = "JobDiscovery/0.1"


class DiscoveryConfig(BaseModel):
    company_discovery_enabled: bool = False
    search_discovery_enabled: bool = False


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    http: HTTPConfig = Field(default_factory=HTTPConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)


def load_settings(config_path: Path) -> Settings:
    """Load and validate application settings from a YAML file."""

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path.resolve()}")

    # with config_path.open("r", encoding="utf-8") as file:
    #     raw_config = yaml.safe_load(file)

    try:
        with config_path.open("r", encoding="utf-8") as file:
            raw_config = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML configuration: {exc}") from exc

    if raw_config is None:
        raw_config = {}

    if not isinstance(raw_config, dict):
        raise ValueError("The configuration root must be a YAML mapping.")

    return Settings.model_validate(raw_config)
