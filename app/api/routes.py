"""
API route definitions.

Routes contain NO business logic — they delegate entirely to the injected
DownloaderService and convert service-level exceptions into HTTP responses.
"""

import asyncio
import logging
import os
import tempfile
import uuid
from typing import Annotated

import imageio_ffmpeg
import yt_dlp
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app.core.config import settings
from app.models.requests import DownloadRequest
from app.models.responses import (
    DownloadSuccessResponse,
    ErrorResponse,
    HealthResponse,
)
from app.services.downloader import DownloaderService, get_downloader_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Resolve ffmpeg binary once at startup (bundled via imageio-ffmpeg)
_FFMPEG_DIR: str = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
logger.info("FFmpeg directory: %s", _FFMPEG_DIR)

# Convenience type alias for dependency injection
ServiceDep = Annotated[DownloaderService, Depends(get_downloader_service)]


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns basic API metadata and confirms the service is running.",
    tags=["Health"],
)
async def health_check() -> HealthResponse:
    return HealthResponse(
        name=settings.APP_NAME,
        version=settings.APP_VERSION,
        status="running",
    )


# ---------------------------------------------------------------------------
# POST /download
# ---------------------------------------------------------------------------

@router.post(
    "/download",
    response_model=DownloadSuccessResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation / unsupported platform"},
        422: {"model": ErrorResponse, "description": "Request body parse error"},
        500: {"model": ErrorResponse, "description": "Extraction failure"},
    },
    summary="Download video metadata",
    description=(
        "Accepts a public video URL from TikTok or Facebook and returns "
        "structured metadata including available download qualities."
    ),
    tags=["Downloader"],
)
async def download_video(
    body: DownloadRequest,
    service: ServiceDep,
) -> DownloadSuccessResponse | JSONResponse:
    """
    Pipeline:
    1. Pydantic validates the request body (empty / missing URL caught here).
    2. The service validates the URL and detects the platform.
    3. yt-dlp extracts metadata asynchronously.
    4. A structured response is returned.
    """
    logger.info("Received /download request: url=%s", body.url)

    try:
        result = await service.process(body.url)
        return result

    except ValueError as exc:
        # Validation errors (empty url, invalid format, unsupported platform)
        logger.warning("Validation error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )

    except RuntimeError as exc:
        # Extraction / yt-dlp errors
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


def _is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


# YouTube quality presets: (max_height, label)
_YT_QUALITY_HEIGHTS = [1080, 720, 480, 360, 240, 144]


def _download_with_ytdlp(page_url: str, quality_index: int, out_path: str) -> str:
    """
    Blocking call: uses yt-dlp to download the chosen quality video.
    Returns the actual output file path (yt-dlp may add extension).

    - TikTok / Facebook: combined video+audio formats, no FFmpeg needed.
    - YouTube: separate video+audio streams → FFmpeg merge required.
    """
    is_yt = _is_youtube_url(page_url)

    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    info_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "format": "all",
        "extractor_args": {
            "youtube": ["player_client=ios,tv,web"]
        },
    }
    
    # Only override headers for non-YouTube platforms (TikTok/Facebook) to avoid breaking YT PO token
    if not is_yt:
        info_opts["http_headers"] = {"User-Agent": ua}

    with yt_dlp.YoutubeDL(info_opts) as ydl:
        info = ydl.extract_info(page_url, download=False)
        
    all_formats = info.get("formats") or []
    if not all_formats:
        raise RuntimeError("No formats found for this URL.")

    # ── YouTube ────────────────────────────────────────────────────────────
    if is_yt:
        max_height = _YT_QUALITY_HEIGHTS[min(quality_index, len(_YT_QUALITY_HEIGHTS) - 1)]
        logger.info("YouTube dynamic selection: target max_height=%d", max_height)

        video_streams = [f for f in all_formats if f.get("vcodec") not in ("none", None, "") and f.get("acodec") in ("none", None, "")]
        audio_streams = [f for f in all_formats if f.get("acodec") not in ("none", None, "") and f.get("vcodec") in ("none", None, "")]
        combined_streams = [f for f in all_formats if f.get("vcodec") not in ("none", None, "") and f.get("acodec") not in ("none", None, "")]

        valid_video = [f for f in video_streams if (f.get("height") or 0) <= max_height]
        valid_combined = [f for f in combined_streams if (f.get("height") or 0) <= max_height]

        if not valid_video and video_streams:
            valid_video = video_streams
        if not valid_combined and combined_streams:
            valid_combined = combined_streams

        def video_sort_key(f):
            return (f.get("height") or 0, f.get("tbr") or 0, f.get("filesize") or 0)
            
        def audio_sort_key(f):
            return (f.get("abr") or 0, f.get("tbr") or 0, f.get("filesize") or 0)

        if valid_video:
            valid_video.sort(key=video_sort_key, reverse=True)
        if valid_combined:
            valid_combined.sort(key=video_sort_key, reverse=True)
        if audio_streams:
            audio_streams.sort(key=audio_sort_key, reverse=True)

        if valid_video and audio_streams:
            v_id = valid_video[0]["format_id"]
            a_id = audio_streams[0]["format_id"]
            fmt_id = f"{v_id}+{a_id}"
        elif valid_combined:
            fmt_id = valid_combined[0]["format_id"]
        else:
            fmt_id = all_formats[-1]["format_id"]  # Ultimate fallback to any valid stream

        logger.info("YouTube dynamically selected format_id: %s", fmt_id)

        dl_opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": out_path,
            "format": fmt_id,
            "merge_output_format": "mp4",
            "ffmpeg_location": _FFMPEG_DIR,
            "extractor_args": {
                "youtube": ["player_client=ios,tv,web"]
            },
        }

        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            ydl.download([page_url])

    # ── TikTok / Facebook ──────────────────────────────────────────────────
    else:
        # Keep only formats with BOTH video and audio streams
        combined = [
            f for f in all_formats
            if f.get("vcodec") not in (None, "", "none")
            and f.get("acodec") not in (None, "", "none")
            and f.get("url", "").startswith("http")
        ]

        if not combined:
            raise RuntimeError("No combined video+audio formats found for this URL.")

        # Sort: prefer h264 (best browser compat), then by height descending
        def sort_key(f):
            vcodec = f.get("vcodec") or ""
            is_h264 = 0 if "h264" in vcodec else 1
            height = -(f.get("height") or 0)
            filesize = -(f.get("filesize") or f.get("filesize_approx") or 0)
            return (is_h264, height, filesize)

        combined.sort(key=sort_key)

        chosen_index = min(quality_index, len(combined) - 1)
        chosen_fmt = combined[chosen_index]
        fmt_id = chosen_fmt["format_id"]

        logger.info(
            "Downloading format_id=%s height=%s vcodec=%s acodec=%s (quality_index=%d)",
            fmt_id, chosen_fmt.get("height"), chosen_fmt.get("vcodec"), chosen_fmt.get("acodec"), quality_index,
        )

        dl_opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": out_path,
            "format": fmt_id,
            "http_headers": info_opts["http_headers"],
        }

        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            ydl.download([page_url])

    # yt-dlp may append the file extension automatically
    for ext in ["", ".mp4", ".m4v", ".webm", ".mkv"]:
        candidate = out_path + ext
        if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
            return candidate

    raise RuntimeError("Downloaded file not found after yt-dlp finished.")




@router.get(
    "/download-file",
    summary="Download video file via yt-dlp",
    description=(
        "Uses yt-dlp on the server to download the video and streams it directly "
        "to the client. This bypasses client-side IP/token restrictions."
    ),
    responses={
        200: {"content": {"video/mp4": {}}},
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    tags=["Downloader"],
)
async def download_file(
    page_url: str = Query(..., description="The original page URL (TikTok, etc.)"),
    quality_index: int = Query(0, description="The index of the quality to download"),
    title: str = Query(None, description="Optional title to name the downloaded file"),
):
    logger.info("download-file request: page_url=%s quality_index=%d title=%s", page_url, quality_index, title)

    tmp_dir = tempfile.gettempdir()
    tmp_name = os.path.join(tmp_dir, f"vdl_{uuid.uuid4().hex}")

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

    # Stream the file and delete it after sending
    def iter_file():
        try:
            with open(out_path, "rb") as f:
                while chunk := f.read(1024 * 1024):  # 1 MB chunks
                    yield chunk
        finally:
            try:
                os.remove(out_path)
                logger.info("Temp file deleted: %s", out_path)
            except OSError:
                pass

    import re
    import urllib.parse
    
    safe_title = "video"
    if title:
        # Remove invalid path characters
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title).strip()
        if not safe_title:
            safe_title = "video"
    
    # We must URL encode the filename for the Content-Disposition header to handle Arabic/Unicode characters safely
    encoded_filename = urllib.parse.quote(f"{safe_title}.mp4")

    return StreamingResponse(
        iter_file(),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        },
    )

