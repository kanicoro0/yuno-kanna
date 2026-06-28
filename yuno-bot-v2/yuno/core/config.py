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


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    discord_token: str
    discord_client_id: Optional[int]
    discord_guild_id: Optional[int]
    openai_api_key: str
    openai_model: str
    openai_fallback_model: str
    yuno_env: str
    notebook_file: Path
    runtime_settings_file: Path = PROJECT_ROOT / "data" / "runtime_settings.json"
    notebook_changelog_file: Path = PROJECT_ROOT / "data" / "notebook_changelog.json"
    owner_id: Optional[int] = None
    mind_state_file: Path = PROJECT_ROOT / "data" / "mind_state.json"
    debug_enabled: bool = False
    debug_dir: Path = PROJECT_ROOT / "data" / "debug"


def load_settings() -> Settings:
    notebook_value = os.getenv("NOTEBOOK_FILE", "data/notebook.json").strip()
    notebook_path = Path(notebook_value)
    if not notebook_path.is_absolute():
        notebook_path = PROJECT_ROOT / notebook_path
    runtime_value = os.getenv("RUNTIME_SETTINGS_FILE", "data/runtime_settings.json").strip()
    runtime_path = Path(runtime_value)
    if not runtime_path.is_absolute():
        runtime_path = PROJECT_ROOT / runtime_path
    changelog_value = os.getenv("NOTEBOOK_CHANGELOG_FILE", "data/notebook_changelog.json").strip()
    changelog_path = Path(changelog_value)
    if not changelog_path.is_absolute():
        changelog_path = PROJECT_ROOT / changelog_path
    mind_value = os.getenv("MIND_STATE_FILE", "data/mind_state.json").strip()
    mind_path = Path(mind_value)
    if not mind_path.is_absolute():
        mind_path = PROJECT_ROOT / mind_path
    debug_value = os.getenv("DEBUG_DIR", "data/debug").strip() or "data/debug"
    debug_path = Path(debug_value)
    if not debug_path.is_absolute():
        debug_path = PROJECT_ROOT / debug_path
    speaker_model = os.getenv("OPENAI_MODEL", "gpt-5").strip() or "gpt-5"
    planner_model = os.getenv("OPENAI_FALLBACK_MODEL", "").strip() or speaker_model
    return Settings(
        discord_token=os.getenv("DISCORD_TOKEN", "").strip(),
        discord_client_id=_optional_int("DISCORD_CLIENT_ID"),
        discord_guild_id=_optional_int("DISCORD_GUILD_ID"),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=speaker_model,
        openai_fallback_model=planner_model,
        yuno_env=os.getenv("YUNO_ENV", "dev").strip() or "dev",
        notebook_file=notebook_path,
        runtime_settings_file=runtime_path,
        notebook_changelog_file=changelog_path,
        owner_id=_optional_int("OWNER_ID"),
        mind_state_file=mind_path,
        debug_enabled=_enabled("DEBUG_ENABLED") or _enabled("PROMPT_DEBUG_ENABLED"),
        debug_dir=debug_path,
    )
