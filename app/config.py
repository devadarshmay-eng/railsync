from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "RailSync AI"
    APP_ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = Path(__file__).resolve().parent.parent / "data"

    # Database
    DATABASE_URL: str = "sqlite:///./data/railsync.db"

    # LAYA Engine
    LAYA_MODE: Literal["live", "mock", "finetuned"] = "live"
    LAYA_MODEL_PATH: str = "convaiinnovations/laya"
    LAYA_FINETUNED_PATH: str = "./models/laya-ir-checkpoint"
    LAYA_DEVICE: str = "cpu"

    # Block Planner
    PLANNER_DEFAULT_SOLVER: Literal["ortools", "deterministic"] = "ortools"
    PLANNING_HORIZON_HOURS: int = 48

    # ASR Pipeline
    ASR_ENGINE: Literal["whisper", "sarvam", "mock"] = "whisper"
    ASR_MODEL_NAME: str = "tiny"
    SARVAM_API_KEY: str = ""
    SARVAM_ENDPOINT: str = "https://api.sarvam.ai/speech-to-text"

    # Safety
    REQUIRE_HUMAN_CONTROLLER_APPROVAL: bool = True
    ADVISORY_MODE: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
# Ensure data directory exists
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
