import os

from dotenv import load_dotenv


load_dotenv()

BASE_DIR = os.path.dirname(__file__)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OWNER_ID = os.getenv("OWNER_ID")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))
LOG_INNER_TO_DISCORD = os.getenv("LOG_INNER_TO_DISCORD", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
INNER_LOG_LIMIT = max(0, int(os.getenv("INNER_LOG_LIMIT", "1000")))
MEMORY_LOG_LIMIT = max(0, int(os.getenv("MEMORY_LOG_LIMIT", "1000")))

_DISCORD_GUILD_ID_RAW = os.getenv("DISCORD_GUILD_ID", "").strip()
try:
    DISCORD_GUILD_ID = int(_DISCORD_GUILD_ID_RAW) if _DISCORD_GUILD_ID_RAW else None
except ValueError as error:
    raise EnvironmentError("DISCORD_GUILD_IDは数値で指定してください") from error

if not DISCORD_TOKEN or not OPENAI_API_KEY:
    raise EnvironmentError("DISCORD_TOKENまたはOPENAI_API_KEYが設定されていません")

PREFIXES = ["/yuno ", "!yuno ", "yuno. "]

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-5")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.6"))
OPENAI_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "40"))

DISCORD_LIMIT = 2000
ENABLE_GIT_SAVE = os.getenv("ENABLE_GIT_SAVE", "0") == "1"

MAX_CHAT_HISTORY = 128
MAX_CHANNEL_LOG = 64
MAX_MESSAGES = 32
WINDOW_SECONDS = 3600
MAX_MEMORY_CHANGE_LOG = 50

CHAT_HISTORY_FILE = os.path.join(BASE_DIR, "chat_history.json")
LONGTERM_MEMORY_FILE = os.path.join(BASE_DIR, "longterm_memory.json")
GUILD_NOTES_FILE = os.path.join(BASE_DIR, "guild_notes.json")
REMINDERS_FILE = os.path.join(BASE_DIR, "reminders.json")
LAST_PROMPT_FILE = os.path.join(BASE_DIR, "last_prompt.json")
