from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Explicit path: never discover or load v1's environment file.
load_dotenv(PROJECT_ROOT / ".env")


def _optional_int(name: str) -> Optional[int]:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error


@dataclass(frozen=True)
class Settings:
    discord_token: str
    discord_client_id: Optional[int]
    discord_guild_id: Optional[int]
    openai_api_key: str
    openai_model: str
    yuno_env: str
    memory_file: Path


def load_settings() -> Settings:
    memory_value = os.getenv("MEMORY_FILE", "data/memories.json").strip()
    memory_path = Path(memory_value)
    if not memory_path.is_absolute():
        memory_path = PROJECT_ROOT / memory_path
    return Settings(
        discord_token=os.getenv("DISCORD_TOKEN", "").strip(),
        discord_client_id=_optional_int("DISCORD_CLIENT_ID"),
        discord_guild_id=_optional_int("DISCORD_GUILD_ID"),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5").strip() or "gpt-5",
        yuno_env=os.getenv("YUNO_ENV", "dev").strip() or "dev",
        memory_file=memory_path,
    )
