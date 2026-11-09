from urllib.parse import urlsplit


def normalize_domain(url: str | None) -> str | None:
    """
    Extract and normalize a hostname from a URL.

    This deliberately does not attempt to infer company identity
    from unrelated social media or ATS hosting domains.
    """

    if not url:
        return None

    candidate = url.strip()

    if not candidate:
        return None

    if "://" not in candidate:
        candidate = f"https://{candidate}"

    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname

        if not hostname:
            return None

        hostname = hostname.lower().rstrip(".")

        if hostname.startswith("www."):
            hostname = hostname[4:]

        return hostname or None

    except ValueError:
        return None
