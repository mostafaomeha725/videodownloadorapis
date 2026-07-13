"""
Video downloader service.

All yt-dlp interactions are isolated here so routes stay clean.
The service is fully async: the blocking yt-dlp call is executed in a
thread-pool via ``asyncio.to_thread`` so the event loop is never blocked.
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
# Helpers
# ---------------------------------------------------------------------------

def _make_ydl_opts() -> dict[str, Any]:
    """Build a yt-dlp options dictionary (no file download, metadata only)."""
    return {
        # Never write anything to disk — we only want metadata / URLs
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "color": "no_color",
        "socket_timeout": settings.YT_DLP_SOCKET_TIMEOUT,
        "retries": settings.YT_DLP_RETRIES,
        # Override format resolution to prevent 'Requested format is not available' error during extraction
        "format": "all",
        # Use ios and tv clients to bypass YouTube bot detection and 403s on datacenter IPs without limiting quality
        "extractor_args": {
            "youtube": ["player_client=ios,tv,web"]
        },
    }


def _quality_label(fmt: dict[str, Any]) -> str:
    """Derive a human-readable quality label from a yt-dlp format dict."""
    height: int | None = fmt.get("height")
    if height:
        return f"{height}p"
    note: str | None = fmt.get("format_note") or fmt.get("format_id")
    return note or "unknown"


def _sort_key(fmt: dict[str, Any]) -> tuple[int, int]:
    """
    Sort formats so that the highest video quality comes first.

    Primary key  : video height (descending) — ``0`` when absent
    Secondary key: file-size  (descending)   — ``0`` when absent
    """
    return (
        -(fmt.get("height") or 0),
        -(fmt.get("filesize") or fmt.get("filesize_approx") or 0),
    )


_YT_QUALITY_HEIGHTS = [1080, 720, 480, 360, 240, 144]


def _extract_formats(info: dict[str, Any]) -> list[QualityOption]:
    """
    Parse raw yt-dlp ``info`` dict and return sorted QualityOption list.

    - YouTube: shows one entry per standard quality height (1080p, 720p, ...)
      based on available video-only streams. quality_index matches
      _download_with_ytdlp's _YT_QUALITY_HEIGHTS list.
    - TikTok / Facebook: only combined video+audio formats, h264 preferred.
    """
    webpage_url: str = info.get("webpage_url") or info.get("original_url") or ""
    is_youtube = "youtube.com" in webpage_url or "youtu.be" in webpage_url

    raw_formats: list[dict[str, Any]] = info.get("formats") or []

    if is_youtube:
        # Find available video heights
        available_heights = {
            f.get("height")
            for f in raw_formats
            if f.get("vcodec") not in (None, "", "none")
            and f.get("height")
        }

        options: list[QualityOption] = []
        for idx, height in enumerate(_YT_QUALITY_HEIGHTS):
            if height in available_heights:
                options.append(
                    QualityOption(
                        quality=f"{height}p",
                        url="",  # Actual download via /download-file
                        ext="mp4",
                        filesize=None,
                        quality_index=idx,  # Maps to _YT_QUALITY_HEIGHTS index
                    )
                )
        return options

    # ── TikTok / Facebook: combined video+audio formats ─────────────────────
    combined = [
        f for f in raw_formats
        if f.get("vcodec") not in (None, "", "none")
        and f.get("acodec") not in (None, "", "none")
        and f.get("url", "").startswith("http")
    ]

    if not combined:
        # Fallback: use the single top-level URL yt-dlp chose
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

    # Sort: h264 first (best browser compat), then by height descending
    def sort_key(f: dict[str, Any]) -> tuple[int, int, int]:
        vcodec = f.get("vcodec") or ""
        is_h264 = 0 if "h264" in vcodec else 1
        height = -(f.get("height") or 0)
        filesize = -(f.get("filesize") or f.get("filesize_approx") or 0)
        return (is_h264, height, filesize)

    combined.sort(key=sort_key)

    seen_qualities: set[str] = set()
    options = []

    for fmt in combined:
        label = _quality_label(fmt)
        if label in seen_qualities:
            continue
        seen_qualities.add(label)
        options.append(
            QualityOption(
                quality=label,
                url=fmt["url"],
                ext=fmt.get("ext"),
                filesize=fmt.get("filesize") or fmt.get("filesize_approx"),
            )
        )

    return options




def _extract_info_sync(url: str) -> dict[str, Any]:
    """Blocking yt-dlp call — must be run inside a thread."""
    opts = _make_ydl_opts()
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            raise RuntimeError("yt-dlp returned no info for the given URL")
        # Sanitise (removes non-serialisable objects)
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

        Raises :class:`ValueError` for validation errors and
        :class:`RuntimeError` for extraction failures so the route layer
        can map them to the correct HTTP status codes.
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

        # ── 3. Parse formats ───────────────────────────────────────────────
        qualities = _extract_formats(info)
        if not qualities:
            raise RuntimeError(
                "No downloadable video formats found for this URL. "
                "The video may be private, deleted, or geo-restricted."
            )

        # ── 4. Build response ──────────────────────────────────────────────
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
