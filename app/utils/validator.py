"""URL validation and platform detection utilities."""

import re
import logging
from urllib.parse import urlparse
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform detection patterns
# ---------------------------------------------------------------------------

PLATFORM_PATTERNS: dict[str, list[re.Pattern]] = {
    "tiktok": [
        re.compile(r"https?://(www\.)?tiktok\.com/", re.IGNORECASE),
        re.compile(r"https?://vm\.tiktok\.com/", re.IGNORECASE),
        re.compile(r"https?://vt\.tiktok\.com/", re.IGNORECASE),
        re.compile(r"https?://m\.tiktok\.com/", re.IGNORECASE),
    ],
    "facebook": [
        re.compile(r"https?://(www\.)?facebook\.com/", re.IGNORECASE),
        re.compile(r"https?://(www\.)?fb\.watch/", re.IGNORECASE),
        re.compile(r"https?://m\.facebook\.com/", re.IGNORECASE),
        re.compile(r"https?://web\.facebook\.com/", re.IGNORECASE),
    ],
    "youtube": [
        re.compile(r"https?://(www\.)?youtube\.com/watch", re.IGNORECASE),
        re.compile(r"https?://(www\.)?youtube\.com/shorts/", re.IGNORECASE),
        re.compile(r"https?://youtu\.be/", re.IGNORECASE),
        re.compile(r"https?://m\.youtube\.com/", re.IGNORECASE),
    ],
}

# Basic URL sanity check (scheme + host present)
_URL_RE = re.compile(
    r"^https?://"
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
    r"localhost|"
    r"\d{1,3}(?:\.\d{1,3}){3})"
    r"(?::\d+)?"
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)


def is_valid_url(url: str) -> bool:
    """Return True when *url* is a well-formed HTTP/HTTPS URL."""
    if not url or not url.strip():
        return False
    try:
        result = urlparse(url)
        if result.scheme not in ("http", "https"):
            return False
        if not result.netloc:
            return False
        return bool(_URL_RE.match(url))
    except Exception:
        logger.debug("URL parse error for: %s", url)
        return False


def detect_platform(url: str) -> Optional[str]:
    """
    Identify which supported platform *url* belongs to.

    Returns the platform key (e.g. ``"tiktok"``) or ``None`` when the URL
    does not match any known platform.
    """
    for platform, patterns in PLATFORM_PATTERNS.items():
        if platform not in settings.SUPPORTED_PLATFORMS:
            continue
        for pattern in patterns:
            if pattern.match(url):
                logger.debug("Detected platform '%s' for URL: %s", platform, url)
                return platform
    logger.debug("No supported platform detected for URL: %s", url)
    return None


def validate_download_url(url: str) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Full validation pipeline for an incoming download URL.

    Returns a 3-tuple: ``(is_ok, platform, error_message)``.

    * ``is_ok``  – ``True`` when the URL passes every check.
    * ``platform`` – the detected platform key, or ``None`` on failure.
    * ``error_message`` – human-readable reason for rejection, or ``None`` on success.
    """
    if not url or not url.strip():
        return False, None, "URL must not be empty"

    if not is_valid_url(url):
        return False, None, "Invalid URL format"

    platform = detect_platform(url)
    if platform is None:
        supported = ", ".join(
            p.capitalize() for p in settings.SUPPORTED_PLATFORMS
        )
        return False, None, f"Unsupported platform. Supported platforms: {supported}"

    return True, platform, None
