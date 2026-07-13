from pydantic import BaseModel, Field, field_validator
from typing import Annotated


class DownloadRequest(BaseModel):
    """Request model for the /download endpoint."""

    url: Annotated[str, Field(
        ...,
        min_length=1,
        description="Public video URL from a supported platform (TikTok, Facebook)",
        examples=[
            "https://www.tiktok.com/@user/video/1234567890",
            "https://www.facebook.com/watch/?v=1234567890",
        ],
    )]

    @field_validator("url", mode="before")
    @classmethod
    def strip_and_validate_not_empty(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("URL must be a string")
        stripped = v.strip()
        if not stripped:
            raise ValueError("URL must not be empty")
        return stripped
