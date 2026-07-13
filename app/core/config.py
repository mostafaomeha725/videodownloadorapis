from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = Field(default="Video Downloader API")
    APP_VERSION: str = Field(default="1.0.0")
    DEBUG: bool = Field(default=False)
    LOG_LEVEL: str = Field(default="INFO")
    ALLOWED_ORIGINS: List[str] = Field(default=["*"])

    SUPPORTED_PLATFORMS: List[str] = Field(
        default=["tiktok", "facebook", "youtube"],
        description="List of supported platform identifiers",
    )

    YT_DLP_SOCKET_TIMEOUT: int = Field(default=30)
    YT_DLP_RETRIES: int = Field(default=3)


settings = Settings()
