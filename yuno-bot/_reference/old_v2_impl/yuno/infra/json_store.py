import asyncio
import json
import os
from pathlib import Path
from typing import Any


class JsonStore:
    """Small atomic JSON-file adapter. Callers own schema validation."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()

    def load_sync(self, default: Any) -> Any:
        if not self.path.exists():
            return default
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    async def load(self, default: Any) -> Any:
        async with self._lock:
            return await asyncio.to_thread(self.load_sync, default)

    def _save_sync(self, value: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(str(temp_path), str(self.path))

    async def save(self, value: Any) -> None:
        async with self._lock:
            await asyncio.to_thread(self._save_sync, value)
