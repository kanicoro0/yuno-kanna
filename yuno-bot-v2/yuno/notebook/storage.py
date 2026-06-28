import asyncio
from dataclasses import replace
import re
from typing import Dict, List, Optional

from yuno.infra.json_store import JsonStore
from yuno.notebook.records import Note, new_note_id, utc_now


NUMERIC_NOTE_ID = re.compile(r"^note_(\d+)$")


class NotebookStorage:
    SCHEMA_VERSION = 2

    def __init__(self, store: JsonStore):
        self.store = store
        # JsonStore protects individual I/O; this protects read-modify-write transactions.
        self._mutation_lock = asyncio.Lock()

    async def _load_records(self) -> List[Note]:
        payload = await self.store.load({"schema_version": self.SCHEMA_VERSION, "notes": []})
        if not isinstance(payload, dict) or payload.get("schema_version") != self.SCHEMA_VERSION:
            raise ValueError("unsupported notebook file schema; expected schema_version 2")
        raw_notes = payload.get("notes", [])
        if not isinstance(raw_notes, list):
            raise ValueError("notebook notes must be a list")
        return [Note.from_dict(item) for item in raw_notes if isinstance(item, dict)]

    async def _save_records(self, records: List[Note]) -> None:
        await self.store.save({
            "schema_version": self.SCHEMA_VERSION,
            "notes": [record.to_dict() for record in records],
        })

    async def load(self) -> List[Note]:
        return await self._load_records()

    async def save(self, records: List[Note]) -> None:
        for record in records:
            record.validate()
        await self._save_records(records)

    async def list_active(self, scopes: Optional[List[str]] = None) -> List[Note]:
        records = [record for record in await self._load_records() if record.state == "active"]
        if scopes is not None:
            records = [record for record in records if record.scope in scopes]
        return records

    async def get_by_id(self, note_id: str) -> Optional[Note]:
        return next((record for record in await self._load_records() if record.id == note_id), None)

    async def resolve_id(self, reference: str) -> Optional[str]:
        value = reference.strip()
        if value.isdigit():
            value = f"note_{int(value):04d}"
        return value if await self.get_by_id(value) is not None else None

    async def search_recent(self, scopes: List[str], limit: int = 10) -> List[Note]:
        records = await self.list_active(scopes)
        return sorted(records, key=lambda item: item.updated_at, reverse=True)[:limit]

    async def search_by_tag(self, scopes: List[str], tag: str, limit: int = 20) -> List[Note]:
        tag = tag.strip().lower()
        return [record for record in await self.list_active(scopes) if tag in record.tags][:limit]

    async def search_by_text(self, scopes: List[str], word: str, limit: int = 20) -> List[Note]:
        word = word.strip().casefold()
        return [record for record in await self.list_active(scopes) if word in record.content.casefold()][:limit]

    async def upsert(self, record: Note) -> Note:
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

    @staticmethod
    def _next_id(records: List[Note]) -> str:
        used = {record.id for record in records}
        numeric = [int(match.group(1)) for record in records if (match := NUMERIC_NOTE_ID.fullmatch(record.id))]
        try:
            candidate = max(numeric, default=0) + 1
            while f"note_{candidate:04d}" in used:
                candidate += 1
            return f"note_{candidate:04d}"
        except (OverflowError, ValueError):
            fallback = new_note_id()
            while fallback in used:
                fallback = new_note_id()
            return fallback

    async def create(self, record: Note) -> Note:
        """Create with a numeric ID atomically; existing IDs are never rewritten."""
        record.validate()
        async with self._mutation_lock:
            records = await self._load_records()
            created = replace(
                record,
                id=self._next_id(records),
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            created.validate()
            records.append(created)
            await self._save_records(records)
            return created

    async def mark_deleted(self, note_id: str) -> Optional[Note]:
        async with self._mutation_lock:
            records = await self._load_records()
            for index, record in enumerate(records):
                if record.id == note_id:
                    deleted = replace(record, state="deleted", updated_at=utc_now())
                    records[index] = deleted
                    await self._save_records(records)
                    return deleted
            return None
