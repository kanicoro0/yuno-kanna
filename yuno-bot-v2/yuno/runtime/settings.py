import asyncio
from copy import deepcopy
from typing import Any, Dict, Optional

from yuno.infra.json_store import JsonStore


DEFAULT_RUNTIME_SETTINGS: Dict[str, Any] = {
    "schema_version": 1,
    "sleep": {"global": False, "guilds": [], "channels": []},
    "auto_reply": {"guilds": {}, "channels": {}},
    "memory_view": {"users": {}},
}


class RuntimeSettings:
    SCHEMA_VERSION = 1

    def __init__(self, store: JsonStore):
        self.store = store
        self._lock = asyncio.Lock()
        self._data: Optional[Dict[str, Any]] = None

    @staticmethod
    def _normalize(payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("unsupported runtime settings schema; expected schema_version 1")
        sleep = payload.get("sleep") if isinstance(payload.get("sleep"), dict) else {}
        auto_reply = payload.get("auto_reply") if isinstance(payload.get("auto_reply"), dict) else {}
        memory_view = payload.get("memory_view") if isinstance(payload.get("memory_view"), dict) else {}
        sleeping_guilds = sleep.get("guilds") if isinstance(sleep.get("guilds"), list) else []
        sleeping_channels = sleep.get("channels") if isinstance(sleep.get("channels"), list) else []
        auto_guilds = auto_reply.get("guilds") if isinstance(auto_reply.get("guilds"), dict) else {}
        auto_channels = auto_reply.get("channels") if isinstance(auto_reply.get("channels"), dict) else {}
        view_users = memory_view.get("users") if isinstance(memory_view.get("users"), dict) else {}
        return {
            "schema_version": 1,
            "sleep": {
                "global": sleep.get("global") is True,
                "guilds": list(dict.fromkeys(str(item) for item in sleeping_guilds if str(item))),
                "channels": list(dict.fromkeys(str(item) for item in sleeping_channels if str(item))),
            },
            "auto_reply": {
                "guilds": {str(key): bool(value) for key, value in auto_guilds.items()},
                "channels": {str(key): bool(value) for key, value in auto_channels.items()},
            },
            "memory_view": {
                "users": {
                    str(key): value
                    for key, value in view_users.items()
                    if value in {"normal", "debug"}
                }
            },
        }

    async def _data_locked(self) -> Dict[str, Any]:
        if self._data is None:
            payload = await self.store.load(deepcopy(DEFAULT_RUNTIME_SETTINGS))
            self._data = self._normalize(payload)
        return self._data

    async def snapshot(self) -> Dict[str, Any]:
        async with self._lock:
            return deepcopy(await self._data_locked())

    async def _save_locked(self) -> None:
        if self._data is not None:
            await self.store.save(self._data)

    async def is_sleeping(self, guild_id: Optional[int], channel_id: Optional[int]) -> bool:
        data = await self.snapshot()
        sleep = data["sleep"]
        return (
            sleep["global"]
            or (guild_id is not None and str(guild_id) in sleep["guilds"])
            or (channel_id is not None and str(channel_id) in sleep["channels"])
        )

    async def set_sleep(self, scope: str, target_id: Optional[int], enabled: bool) -> None:
        async with self._lock:
            data = await self._data_locked()
            if scope == "global":
                data["sleep"]["global"] = enabled
            elif scope in {"guilds", "channels"} and target_id is not None:
                values = data["sleep"][scope]
                key = str(target_id)
                if enabled and key not in values:
                    values.append(key)
                elif not enabled and key in values:
                    values.remove(key)
            else:
                raise ValueError("invalid sleep scope")
            await self._save_locked()

    async def auto_reply_allowed(self, guild_id: Optional[int], channel_id: Optional[int]) -> bool:
        if guild_id is None or channel_id is None:
            return False
        data = await self.snapshot()
        guild_value = data["auto_reply"]["guilds"].get(str(guild_id))
        if guild_value is False:
            return False
        channel_value = data["auto_reply"]["channels"].get(str(channel_id))
        if channel_value is not None:
            return channel_value
        return guild_value is True

    async def set_auto_reply(self, scope: str, target_id: int, enabled: bool) -> None:
        if scope not in {"guilds", "channels"}:
            raise ValueError("invalid auto reply scope")
        async with self._lock:
            data = await self._data_locked()
            data["auto_reply"][scope][str(target_id)] = enabled
            await self._save_locked()

    async def memory_view(self, user_id: int) -> str:
        data = await self.snapshot()
        return data["memory_view"]["users"].get(str(user_id), "normal")

    async def set_memory_view(self, user_id: int, mode: str) -> None:
        if mode not in {"normal", "debug"}:
            raise ValueError("invalid memory view mode")
        async with self._lock:
            data = await self._data_locked()
            data["memory_view"]["users"][str(user_id)] = mode
            await self._save_locked()
