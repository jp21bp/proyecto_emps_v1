import logging
from pathlib import Path


def configure_logging(
    log_directory: Path,
    level: str = "INFO",
    filename: str = "application.log",
) -> None:
    """Configure console and rotating-independent file logging."""

    # Creates the logging directory
    log_directory.mkdir(parents=True, exist_ok=True)

    # UNSURE: level priority?
    numeric_level = getattr(logging, level.upper(), None)
    # print(numeric_level) -> 20

    # Verifies numeric_level
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid logging level: {level}")

    # Creates the logging format
    print("logging.py: Before logging.Formatter")
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    print("logging.py: After logging.Formatter")

    # Creates the logger itself
    root_logger = logging.getLogger()

    # UNSURE: Sets the level of the logger?
    root_logger.setLevel(numeric_level)

    # Avoid duplicate handlers when logging is configured more than once.
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    # Sets up streaming handlers (stdio)
    print("logging.py: Before logging.StreamHandler")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    print("logging.py: After logging.StreamHandler")

    # Sets up file handlers
    print("logging.py: Before logging.FileHandler")
    file_handler = logging.FileHandler(
        log_directory / filename,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    print("logging.py: After logging.FileHandler")

    # Connects logger created to the handlers created
    print("logging.py: Before console and file handlers")
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    print("logging.py: After console and file handlers")
