"""
API route definitions.

Routes contain NO business logic — they delegate entirely to the injected
DownloaderService and convert service-level exceptions into HTTP responses.
"""

import asyncio
import logging
import os
import re
import tempfile
import urllib.parse
import uuid
from typing import Annotated

import imageio_ffmpeg
import yt_dlp
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import settings
from app.models.requests import DownloadRequest
from app.models.responses import (
    DownloadSuccessResponse,
    ErrorResponse,
    HealthResponse,
)
from app.services.downloader import (
    DownloaderService,
    _YT_PLAYER_CLIENTS,
    _YT_QUALITY_HEIGHTS,
    get_downloader_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Resolve ffmpeg binary once at startup (bundled via imageio-ffmpeg)
_FFMPEG_DIR: str = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
logger.info("FFmpeg directory: %s", _FFMPEG_DIR)

# Shared extractor_args for YouTube (keeps routes in sync with the service)
_YT_EXTRACTOR_ARGS: dict = {
    "youtube": {
        "player_client": _YT_PLAYER_CLIENTS,
    }
}

ServiceDep = Annotated[DownloaderService, Depends(get_downloader_service)]


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=HealthResponse,
    summary="Health check",
    tags=["Health"],
)
async def health_check() -> HealthResponse:
    return HealthResponse(
        name=settings.APP_NAME,
        version=settings.APP_VERSION,
        status="running",
    )


# ---------------------------------------------------------------------------
# POST /download  (metadata extraction)
# ---------------------------------------------------------------------------

@router.post(
    "/download",
    response_model=DownloadSuccessResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation / unsupported platform"},
        422: {"model": ErrorResponse, "description": "Request body parse error"},
        500: {"model": ErrorResponse, "description": "Extraction failure"},
    },
    summary="Fetch video metadata and available qualities",
    tags=["Downloader"],
)
async def download_video(
    body: DownloadRequest,
    service: ServiceDep,
) -> DownloadSuccessResponse | JSONResponse:
    logger.info("Received /download request: url=%s", body.url)

    try:
        result = await service.process(body.url)
        return result

    except ValueError as exc:
        logger.warning("Validation error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )
    except RuntimeError as exc:
        logger.error("Extraction error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("Unhandled exception in /download")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(message="An unexpected error occurred").model_dump(),
        )


# ---------------------------------------------------------------------------
# Internal helpers for /download-file
# ---------------------------------------------------------------------------

def _is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def _download_with_ytdlp(page_url: str, quality_index: int, out_path: str) -> str:
    """
    Blocking yt-dlp download call — run in a thread via asyncio.to_thread.

    Returns the absolute path of the downloaded file.
    """
    is_yt = _is_youtube_url(page_url)

    # ── Step 1: Extract available formats ───────────────────────────────────
    info_opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        # Force IPv4 — datacenter IPv6 is blocked by YouTube
        "source_address": "0.0.0.0",
        # Use Node.js runtime so yt-dlp can generate PO Tokens on Railway
        "js_runtimes": {"node": {}},
    }

    if is_yt:
        info_opts["extractor_args"] = _YT_EXTRACTOR_ARGS
    else:
        info_opts["http_headers"] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }

    with yt_dlp.YoutubeDL(info_opts) as ydl:
        info = ydl.extract_info(page_url, download=False)

    if info is None:
        raise RuntimeError("yt-dlp returned no info for the given URL.")

    all_formats = info.get("formats") or []
    if not all_formats:
        raise RuntimeError("No formats found for this URL.")

    logger.info(
        "_download_with_ytdlp: %d total formats, is_yt=%s", len(all_formats), is_yt
    )

    # ── Step 2: Select format_id ────────────────────────────────────────────
    if is_yt:
        max_height = _YT_QUALITY_HEIGHTS[min(quality_index, len(_YT_QUALITY_HEIGHTS) - 1)]
        logger.info("YouTube target max_height=%d", max_height)

        video_only = [
            f for f in all_formats
            if f.get("vcodec") not in ("none", None, "")
            and f.get("acodec") in ("none", None, "")
        ]
        audio_only = [
            f for f in all_formats
            if f.get("acodec") not in ("none", None, "")
            and f.get("vcodec") in ("none", None, "")
        ]
        combined = [
            f for f in all_formats
            if f.get("vcodec") not in ("none", None, "")
            and f.get("acodec") not in ("none", None, "")
        ]

        logger.info(
            "YouTube stream counts: video_only=%d audio_only=%d combined=%d",
            len(video_only), len(audio_only), len(combined),
        )

        # Filter to requested quality; fall back to all if none match
        valid_video = [f for f in video_only if (f.get("height") or 0) <= max_height] or video_only
        valid_combined = [f for f in combined if (f.get("height") or 0) <= max_height] or combined

        def by_quality(f: dict) -> tuple:
            return (f.get("height") or 0, f.get("tbr") or 0, f.get("filesize") or 0)

        def by_audio(f: dict) -> tuple:
            return (f.get("abr") or 0, f.get("tbr") or 0)

        valid_video.sort(key=by_quality, reverse=True)
        valid_combined.sort(key=by_quality, reverse=True)
        audio_only.sort(key=by_audio, reverse=True)

        if valid_video and audio_only:
            # Best quality: separate streams merged by ffmpeg
            fmt_id = f"{valid_video[0]['format_id']}+{audio_only[0]['format_id']}"
        elif valid_combined:
            fmt_id = valid_combined[0]["format_id"]
        elif valid_video:
            fmt_id = valid_video[0]["format_id"]
        else:
            fmt_id = all_formats[-1]["format_id"]

        logger.info("YouTube selected format_id: %s", fmt_id)

        dl_opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": out_path,
            "format": fmt_id,
            "merge_output_format": "mp4",
            "ffmpeg_location": _FFMPEG_DIR,
            "source_address": "0.0.0.0",
            "extractor_args": _YT_EXTRACTOR_ARGS,
        }

    else:
        # TikTok / Facebook: pick combined stream by quality_index
        combined_fmt = [
            f for f in all_formats
            if f.get("vcodec") not in (None, "", "none")
            and f.get("acodec") not in (None, "", "none")
            and f.get("url", "").startswith("http")
        ]

        if not combined_fmt:
            raise RuntimeError("No combined video+audio formats found for this URL.")

        def sort_key(f: dict) -> tuple:
            vcodec = f.get("vcodec") or ""
            return (
                0 if "h264" in vcodec else 1,
                -(f.get("height") or 0),
                -(f.get("filesize") or f.get("filesize_approx") or 0),
            )

        combined_fmt.sort(key=sort_key)
        chosen = combined_fmt[min(quality_index, len(combined_fmt) - 1)]
        fmt_id = chosen["format_id"]

        logger.info(
            "TikTok/FB format_id=%s height=%s vcodec=%s (index=%d)",
            fmt_id, chosen.get("height"), chosen.get("vcodec"), quality_index,
        )

        dl_opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": out_path,
            "format": fmt_id,
            "http_headers": info_opts.get("http_headers", {}),
        }

    # ── Step 3: Download ────────────────────────────────────────────────────
    with yt_dlp.YoutubeDL(dl_opts) as ydl:
        ydl.download([page_url])

    # yt-dlp may append the file extension automatically
    for ext in ["", ".mp4", ".m4v", ".webm", ".mkv"]:
        candidate = out_path + ext
        if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
            return candidate

    raise RuntimeError("Downloaded file not found after yt-dlp finished.")


# ---------------------------------------------------------------------------
# GET /download-file  (actual video file download)
# ---------------------------------------------------------------------------

@router.get(
    "/download-file",
    summary="Download and stream video file via yt-dlp",
    description=(
        "Uses yt-dlp on the server to download the video and streams it directly "
        "to the client. Bypasses client-side IP/token restrictions."
    ),
    responses={
        200: {"content": {"video/mp4": {}}},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    tags=["Downloader"],
)
async def download_file(
    page_url: str = Query(..., description="The original page URL"),
    quality_index: int = Query(0, description="Quality index (0 = best)"),
    title: str = Query(None, description="Optional filename title"),
):
    logger.info(
        "download-file request: url=%s quality_index=%d title=%s",
        page_url, quality_index, title,
    )

    tmp_name = os.path.join(tempfile.gettempdir(), f"vdl_{uuid.uuid4().hex}")

    try:
        out_path = await asyncio.to_thread(
            _download_with_ytdlp, page_url, quality_index, tmp_name
        )
    except Exception as exc:
        logger.error("yt-dlp download failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Download failed: {exc}",
        )

    logger.info("Streaming file: %s (%d bytes)", out_path, os.path.getsize(out_path))

    def iter_file():
        try:
            with open(out_path, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    yield chunk
        finally:
            try:
                os.remove(out_path)
                logger.info("Temp file deleted: %s", out_path)
            except OSError:
                pass

    safe_title = "video"
    if title:
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title).strip() or "video"

    encoded_filename = urllib.parse.quote(f"{safe_title}.mp4")

    return StreamingResponse(
        iter_file(),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        },
    )
