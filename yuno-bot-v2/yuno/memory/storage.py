import asyncio
from dataclasses import replace
from typing import Dict, List, Optional

from yuno.infra.json_store import JsonStore
from yuno.memory.records import MemoryRecord, utc_now


class MemoryStorage:
    SCHEMA_VERSION = 2

    def __init__(self, store: JsonStore):
        self.store = store
        # JsonStore protects individual I/O; this protects read-modify-write transactions.
        self._mutation_lock = asyncio.Lock()

    async def _load_records(self) -> List[MemoryRecord]:
        payload = await self.store.load({"schema_version": self.SCHEMA_VERSION, "records": []})
        if not isinstance(payload, dict) or payload.get("schema_version") != self.SCHEMA_VERSION:
            raise ValueError("unsupported memory file schema; expected schema_version 2")
        raw_records = payload.get("records", [])
        if not isinstance(raw_records, list):
            raise ValueError("memory records must be a list")
        return [MemoryRecord.from_dict(item) for item in raw_records if isinstance(item, dict)]

    async def _save_records(self, records: List[MemoryRecord]) -> None:
        await self.store.save({
            "schema_version": self.SCHEMA_VERSION,
            "records": [record.to_dict() for record in records],
        })

    async def load(self) -> List[MemoryRecord]:
        return await self._load_records()

    async def save(self, records: List[MemoryRecord]) -> None:
        for record in records:
            record.validate()
        await self._save_records(records)

    async def list_active(self, scopes: Optional[List[str]] = None) -> List[MemoryRecord]:
        records = [record for record in await self._load_records() if record.state == "active"]
        if scopes is not None:
            records = [record for record in records if record.scope in scopes]
        return records

    async def get_by_id(self, memory_id: str) -> Optional[MemoryRecord]:
        return next((record for record in await self._load_records() if record.id == memory_id), None)

    async def search_recent(self, scopes: List[str], limit: int = 10) -> List[MemoryRecord]:
        records = await self.list_active(scopes)
        return sorted(records, key=lambda item: item.updated_at, reverse=True)[:limit]

    async def search_by_tag(self, scopes: List[str], tag: str, limit: int = 20) -> List[MemoryRecord]:
        tag = tag.strip().lower()
        return [record for record in await self.list_active(scopes) if tag in record.tags][:limit]

    async def search_by_text(self, scopes: List[str], word: str, limit: int = 20) -> List[MemoryRecord]:
        word = word.strip().casefold()
        return [record for record in await self.list_active(scopes) if word in record.content.casefold()][:limit]

    async def upsert(self, record: MemoryRecord) -> MemoryRecord:
        record.validate()
        async with self._mutation_lock:
            records = await self._load_records()
            now = utc_now()
            for index, current in enumerate(records):
                if current.id == record.id:
                    record = replace(record, created_at=current.created_at, updated_at=now)
                    records[index] = record
                    break
            else:
                record = replace(record, updated_at=now)
                records.append(record)
            await self._save_records(records)
            return record

    async def mark_deleted(self, memory_id: str) -> Optional[MemoryRecord]:
        async with self._mutation_lock:
            records = await self._load_records()
            for index, record in enumerate(records):
                if record.id == memory_id:
                    deleted = replace(record, state="deleted", updated_at=utc_now())
                    records[index] = deleted
                    await self._save_records(records)
                    return deleted
            return None
