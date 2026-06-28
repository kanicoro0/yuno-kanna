import asyncio
from typing import Dict, List, Optional

from yuno.infra.json_store import JsonStore
from yuno.mind.records import MindState, MindUpdate


class MindStateStorage:
    def __init__(self, store: JsonStore):
        self.store = store
        self._lock = asyncio.Lock()

    async def _load(self) -> Dict[str, MindState]:
        payload = await self.store.load({"schema_version": 1, "states": {}})
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("unsupported mind state schema; expected schema_version 1")
        states = payload.get("states", {})
        if not isinstance(states, dict):
            raise ValueError("mind states must be an object")
        result: Dict[str, MindState] = {}
        for scope, value in states.items():
            if isinstance(value, dict):
                state = MindState.from_dict(value)
                state.scope = str(scope)
                result[str(scope)] = state
        return result

    async def _save(self, states: Dict[str, MindState]) -> None:
        await self.store.save({"schema_version": 1,
                               "states": {scope: state.to_dict() for scope, state in states.items()}})

    async def get(self, scope: str) -> Optional[MindState]:
        return (await self._load()).get(scope)

    async def get_many(self, scopes: List[str]) -> List[MindState]:
        states = await self._load()
        return [states[scope] for scope in scopes if scope in states]

    async def count(self) -> int:
        return len(await self._load())

    async def update(self, scope: str, update: MindUpdate, source_message_id: str) -> MindState:
        state = MindState.from_update(scope, update, source_message_id)
        async with self._lock:
            states = await self._load()
            states[scope] = state
            await self._save(states)
        return state

    async def clear(self, scope: str) -> bool:
        async with self._lock:
            states = await self._load()
            existed = states.pop(scope, None) is not None
            if existed:
                await self._save(states)
            return existed
