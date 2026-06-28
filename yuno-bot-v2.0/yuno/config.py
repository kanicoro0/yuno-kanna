from dataclasses import dataclass
import os
from pathlib import Path
from typing import FrozenSet, Optional, Tuple

from dotenv import load_dotenv


def _optional_int(name: str) -> Optional[int]:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def _channel_ids(value: str) -> FrozenSet[int]:
    if not value.strip():
        return frozenset()
    try:
        return frozenset(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as error:
        raise ValueError("LISTENING_CHANNEL_IDS must contain comma-separated integers") from error


def _call_names(value: str) -> Tuple[str, ...]:
    names = [item.strip() for item in value.split(",") if item.strip()]
    if not names:
        names = ["ゆの", "唯乃", "yuno"]
    return tuple(dict.fromkeys(names))


@dataclass(frozen=True)
class Settings:
    discord_token: str
    discord_client_id: Optional[int]
    openai_api_key: str
    openai_model: str
    database_file: Path
    listening_channel_ids: FrozenSet[int]
    yuno_call_names: Tuple[str, ...]
    log_level: str


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        discord_token=os.getenv("DISCORD_TOKEN", "").strip(),
        discord_client_id=_optional_int("DISCORD_CLIENT_ID"),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "").strip(),
        database_file=Path(os.getenv("DATABASE_FILE", "data/yuno.sqlite3")),
        listening_channel_ids=_channel_ids(os.getenv("LISTENING_CHANNEL_IDS", "")),
        yuno_call_names=_call_names(os.getenv("YUNO_CALL_NAMES", "")),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
    )
