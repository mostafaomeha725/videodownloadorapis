"""
Video downloader service.

All yt-dlp interactions are isolated here so routes stay clean.
The service is fully async: the blocking yt-dlp call is executed in a
thread-pool via ``asyncio.to_thread`` so the event loop is never blocked.

ROOT CAUSE OF RAILWAY BUG (documented here for future reference):
-----------------------------------------------------------------
The old code used player_client=['android_vr','android','mweb'] which returns
only 4 formats and maximum 360p quality. The yt-dlp 'web' client provides the
full 27 formats including 1080p, but requires a PO token on datacenter IPs
(Railway, Render, etc.). The fix is to list 'web' FIRST so it is tried for
format enumeration, then fall through to 'android_vr'/'android'/'mweb'/'ios'
as fallbacks. yt-dlp merges the format lists from all successful clients.

Additionally: yt-dlp 2024.11.18 was too old to use the modern PO-token bypass
introduced in 2025 builds. Upgrading to >=2025.6.30 is required.
"""

import asyncio
import logging
from typing import Any
from functools import lru_cache

import yt_dlp

from app.core.config import settings
from app.models.responses import DownloadSuccessResponse, QualityOption
from app.utils.validator import validate_download_url

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# yt-dlp configuration
# ---------------------------------------------------------------------------

# Player client order for YouTube:
# - 'web'        → most formats (all heights), but needs PO token on datacenter IPs
#                  yt-dlp >=2025.6 can work around this for many videos
# - 'android_vr' → bypasses bot detection on datacenter IPs; fewer formats
# - 'android'    → good fallback; combined streams
# - 'mweb'       → mobile web; light formats
# - 'ios'        → Apple formats; good quality fallback
# Listing all ensures yt-dlp merges the format lists and picks the best available.
_YT_PLAYER_CLIENTS = ["web", "android_vr", "android", "mweb", "ios"]

_YT_QUALITY_HEIGHTS = [1080, 720, 480, 360, 240, 144]


def _make_ydl_opts() -> dict[str, Any]:
    """
    Build a yt-dlp options dictionary for metadata extraction (no download).

    Key production settings for Railway/Linux/datacenter IPs:
    - source_address=0.0.0.0  : forces IPv4. Railway may route via IPv6 which
                                 YouTube blocks for datacenter ranges.
    - player_client list       : tries 'web' first for full format list, then
                                 falls back to mobile clients that bypass
                                 YouTube bot-detection on datacenter IPs.
    """
    return {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "color": "no_color",
        "socket_timeout": settings.YT_DLP_SOCKET_TIMEOUT,
        "retries": settings.YT_DLP_RETRIES,
        # Force IPv4 — datacenter IPv6 is blocked by YouTube
        "source_address": "0.0.0.0",
        # Multi-client strategy: web provides full format list; mobile clients
        # act as fallbacks on datacenter IPs where 'web' may be restricted.
        "extractor_args": {
            "youtube": {
                "player_client": _YT_PLAYER_CLIENTS,
            }
        },
    }


# ---------------------------------------------------------------------------
# Format parsing helpers
# ---------------------------------------------------------------------------

def _quality_label(fmt: dict[str, Any]) -> str:
    """Derive a human-readable quality label from a yt-dlp format dict."""
    height: int | None = fmt.get("height")
    if height:
        return f"{height}p"
    note: str | None = fmt.get("format_note") or fmt.get("format_id")
    return note or "unknown"


def _sort_key(fmt: dict[str, Any]) -> tuple[int, int]:
    """Sort formats highest quality first."""
    return (
        -(fmt.get("height") or 0),
        -(fmt.get("filesize") or fmt.get("filesize_approx") or 0),
    )


def _extract_formats(info: dict[str, Any]) -> list[QualityOption]:
    """
    Parse raw yt-dlp info dict and return sorted QualityOption list.

    - YouTube: one entry per standard height (1080p, 720p, ...) based on
      available video-only or combined streams. quality_index maps to
      _YT_QUALITY_HEIGHTS for use in /download-file.
    - TikTok / Facebook: combined video+audio formats, h264 preferred.
    """
    webpage_url: str = info.get("webpage_url") or info.get("original_url") or ""
    is_youtube = "youtube.com" in webpage_url or "youtu.be" in webpage_url

    raw_formats: list[dict[str, Any]] = info.get("formats") or []

    logger.info(
        "_extract_formats: total_formats=%d is_youtube=%s url=%s",
        len(raw_formats), is_youtube, webpage_url,
    )

    if is_youtube:
        # Collect all heights from formats that have a video stream
        available_heights: set[int] = set()
        for f in raw_formats:
            h = f.get("height")
            vc = f.get("vcodec")
            if h and vc and vc not in ("none", ""):
                available_heights.add(h)

        logger.info("YouTube available heights: %s", sorted(available_heights, reverse=True))

        options: list[QualityOption] = []
        for idx, height in enumerate(_YT_QUALITY_HEIGHTS):
            if height in available_heights:
                options.append(
                    QualityOption(
                        quality=f"{height}p",
                        url="",  # Actual download happens via /download-file
                        ext="mp4",
                        filesize=None,
                        quality_index=idx,
                    )
                )

        # Safety net: if no standard heights matched, offer the best available height
        if not options and available_heights:
            best = max(available_heights)
            logger.warning(
                "No standard heights matched; offering best available: %dp", best
            )
            options.append(
                QualityOption(
                    quality=f"{best}p",
                    url="",
                    ext="mp4",
                    filesize=None,
                    quality_index=0,
                )
            )

        return options

    # ── TikTok / Facebook: combined video+audio formats ──────────────────────
    combined = [
        f for f in raw_formats
        if f.get("vcodec") not in (None, "", "none")
        and f.get("acodec") not in (None, "", "none")
        and f.get("url", "").startswith("http")
    ]

    if not combined:
        # Last resort: use top-level url from info
        fallback_url: str | None = info.get("url")
        if fallback_url and fallback_url.startswith("http"):
            return [
                QualityOption(
                    quality=_quality_label(info),
                    url=fallback_url,
                    ext=info.get("ext"),
                    filesize=info.get("filesize") or info.get("filesize_approx"),
                )
            ]
        return []

    def sort_key(f: dict[str, Any]) -> tuple[int, int, int]:
        vcodec = f.get("vcodec") or ""
        return (
            0 if "h264" in vcodec else 1,         # h264 first
            -(f.get("height") or 0),               # higher height first
            -(f.get("filesize") or f.get("filesize_approx") or 0),
        )

    combined.sort(key=sort_key)

    seen: set[str] = set()
    options = []
    for fmt in combined:
        label = _quality_label(fmt)
        if label in seen:
            continue
        seen.add(label)
        options.append(
            QualityOption(
                quality=label,
                url=fmt["url"],
                ext=fmt.get("ext"),
                filesize=fmt.get("filesize") or fmt.get("filesize_approx"),
            )
        )

    return options


# ---------------------------------------------------------------------------
# Blocking extractor (runs in thread pool)
# ---------------------------------------------------------------------------

def _extract_info_sync(url: str) -> dict[str, Any]:
    """Blocking yt-dlp call — must be run inside a thread via asyncio.to_thread."""
    opts = _make_ydl_opts()
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            raise RuntimeError("yt-dlp returned no info for the given URL")
        return ydl.sanitize_info(info)


# ---------------------------------------------------------------------------
# Public service interface
# ---------------------------------------------------------------------------

class DownloaderService:
    """
    Stateless service that validates, extracts, and structures video metadata.
    Instantiate once (via FastAPI dependency injection) and reuse.
    """

    async def process(self, url: str) -> DownloadSuccessResponse:
        """
        Full pipeline:
        1. Validate URL & detect platform.
        2. Extract metadata with yt-dlp (async, thread-pool).
        3. Parse & sort available formats.
        4. Return a structured response.
        """
        # ── 1. Validate ────────────────────────────────────────────────────
        is_ok, platform, error_msg = validate_download_url(url)
        if not is_ok:
            raise ValueError(error_msg or "Invalid URL")

        logger.info("Processing URL for platform='%s': %s", platform, url)

        # ── 2. Extract ─────────────────────────────────────────────────────
        try:
            info: dict[str, Any] = await asyncio.to_thread(_extract_info_sync, url)
        except yt_dlp.utils.DownloadError as exc:
            logger.warning("yt-dlp DownloadError for %s: %s", url, exc)
            raise RuntimeError(f"Could not extract video info: {exc}") from exc
        except Exception as exc:
            logger.exception("Unexpected error extracting %s", url)
            raise RuntimeError(f"Extraction failed: {exc}") from exc

        # ── 3. Parse formats ────────────────────────────────────────────────
        qualities = _extract_formats(info)
        if not qualities:
            raise RuntimeError(
                "No downloadable video formats found for this URL. "
                "The video may be private, deleted, or geo-restricted."
            )

        # ── 4. Build response ───────────────────────────────────────────────
        thumbnail: str | None = info.get("thumbnail")
        duration_raw = info.get("duration")
        duration: int | None = int(duration_raw) if duration_raw is not None else None

        response = DownloadSuccessResponse(
            platform=platform,  # type: ignore[arg-type]
            title=info.get("title") or "Untitled",
            thumbnail=thumbnail,
            duration=duration,
            qualities=qualities,
        )

        logger.info(
            "Extracted %d format(s) for '%s' on %s",
            len(qualities),
            response.title,
            platform,
        )
        return response


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_downloader_service() -> DownloaderService:
    """Cached singleton factory for use with ``Depends()``."""
    return DownloaderService()
