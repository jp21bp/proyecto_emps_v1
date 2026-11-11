from collections.abc import Callable
from typing import Any

from job_discovery.collectors.ashby import AshbyCollector
from job_discovery.collectors.base import BaseCollector
from job_discovery.collectors.greenhouse import GreenhouseCollector
from job_discovery.collectors.lever import LeverCollector

CollectorConstructor = Callable[..., BaseCollector]


COLLECTOR_REGISTRY: dict[str, CollectorConstructor] = {
    "GREENHOUSE": GreenhouseCollector,
    "LEVER": LeverCollector,
    "ASHBY": AshbyCollector,
}


def normalize_platform(platform: str) -> str:
    """Normalize an ATS platform identifier."""

    if not isinstance(platform, str) or not platform.strip():
        raise ValueError("ATS platform cannot be empty.")

    return platform.strip().upper().replace("-", "_").replace(" ", "_")


def supported_platforms() -> tuple[str, ...]:
    """Return the currently supported ATS platforms."""

    return tuple(sorted(COLLECTOR_REGISTRY))


def create_collector(
    platform: str,
    **collector_options: Any,
) -> BaseCollector:
    """
    Create an ATS collector.

    Parameters
    ----------
    platform:
        ATS platform identifier, such as GREENHOUSE, LEVER or ASHBY.

    **collector_options:
        Optional arguments forwarded to the selected collector.

    Returns
    -------
    BaseCollector
        An instantiated ATS collector.

    Raises
    ------
    ValueError
        If the requested platform is unsupported.
    """

    normalized_platform = normalize_platform(platform)

    constructor = COLLECTOR_REGISTRY.get(normalized_platform)

    if constructor is None:
        supported = ", ".join(supported_platforms())

        raise ValueError(
            f"Unsupported ATS platform: {platform!r}. Supported platforms: {supported}"
        )

    return constructor(**collector_options)
