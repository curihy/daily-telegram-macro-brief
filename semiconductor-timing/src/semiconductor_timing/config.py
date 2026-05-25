from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    timezone: str = env("TIMEZONE", "Asia/Seoul")
    db_path: Path = Path(env("DB_PATH", "data/timing.db"))
    telegram_bot_token: str = env("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = env("TELEGRAM_CHAT_ID")
    fred_api_key: str = env("FRED_API_KEY")
    dry_run: bool = env("DRY_RUN", "1").lower() in {"1", "true", "yes"}


def get_settings() -> Settings:
    return Settings()
