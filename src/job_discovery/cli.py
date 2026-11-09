import argparse
import logging
from pathlib import Path

from job_discovery.core.config import load_settings
from job_discovery.core.logging import configure_logging


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job-discovery",
        description="Local-first employer job discovery platform.",
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/settings.yaml"),
        help="Path to the YAML configuration file.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "init",
        help="Initialize local application directories.",
    )

    subparsers.add_parser(
        "check-config",
        help="Validate application configuration.",
    )

    return parser


def rand() -> None:
    print("sfafag")


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    try:
        settings = load_settings(args.config)

        configure_logging(
            log_directory=settings.logging.directory,
            level=settings.logging.level,
            filename=settings.logging.filename,
        )

        logger = logging.getLogger("job_discovery")

        if args.command == "check-config":
            # Actually prints the loggers to stream handlers
            print("cli.py: before logger.infos")
            logger.info("Configuration is valid.")
            logger.info("Project: %s", settings.project.name)
            logger.info("Database: %s", settings.storage.database_path)
            print("cli.py: after logger.infos")
            return

        if args.command == "init":
            directories = [
                settings.storage.database_path.parent,
                settings.storage.raw_data_dir,
                settings.storage.exports_dir,
                settings.logging.directory,
            ]

            for directory in directories:
                directory.mkdir(parents=True, exist_ok=True)

            # Prints to logger
            logger.info("Application directories initialized.")
            return

    except (FileNotFoundError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
