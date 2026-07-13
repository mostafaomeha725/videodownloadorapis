from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Any


class QualityOption(BaseModel):
    """A single available quality/format for a video."""

    quality: str = Field(..., description="Human-readable quality label, e.g. '1080p'")
    url: str = Field(..., description="Direct downloadable URL for this quality")
    ext: Optional[str] = Field(default=None, description="File extension, e.g. 'mp4'")
    filesize: Optional[int] = Field(default=None, description="Approximate file size in bytes")
    quality_index: int = Field(default=0, description="Index for /download-file endpoint")


class DownloadSuccessResponse(BaseModel):
    """Successful response returned after extracting video metadata."""

    success: bool = Field(default=True)
    platform: str = Field(..., description="Detected platform identifier")
    title: str = Field(..., description="Video title")
    thumbnail: Optional[str] = Field(default=None, description="Thumbnail image URL")
    duration: Optional[int] = Field(default=None, description="Video duration in seconds")
    qualities: List[QualityOption] = Field(
        default_factory=list,
        description="Available video qualities sorted best-first",
    )


class ErrorResponse(BaseModel):
    """Standard error response body."""

    success: bool = Field(default=False)
    message: str = Field(..., description="Human-readable error message")
    detail: Optional[Any] = Field(default=None, description="Optional additional detail")


class HealthResponse(BaseModel):
    """Root health-check response."""

    name: str
    version: str
    status: str = Field(default="running")
