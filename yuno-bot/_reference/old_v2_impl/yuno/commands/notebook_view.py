import math
from typing import List, Optional, Tuple

import discord

from yuno.notebook.records import Note
from yuno.notebook.storage import NotebookStorage
from yuno.text import NO_NOTES


def scope_for(interaction: discord.Interaction, kind: str) -> Optional[str]:
    if kind == "user":
        return f"user:{interaction.user.id}"
    if kind == "server" and interaction.guild_id:
        return f"guild:{interaction.guild_id}"
    if kind == "channel" and interaction.guild_id and interaction.channel_id:
        return f"channel:{interaction.channel_id}"
    return None


def accessible_scopes(interaction: discord.Interaction) -> List[str]:
    scopes = [f"user:{interaction.user.id}"]
    if interaction.guild_id:
        scopes.extend((f"guild:{interaction.guild_id}", f"channel:{interaction.channel_id}"))
    return scopes


def format_record(record: Note, detail: bool, debug: bool = False) -> str:
    if not detail:
        return f"{record.id}: {record.content}"
    lines = [
        f"id: `{record.id}`",
        record.content,
        f"対象: `{record.scope}`",
        f"tags: `{', '.join(record.tags) or '-'}`",
        f"weight: `{record.weight}`",
    ]
    if debug:
        lines.extend((
            f"routes: `{', '.join(record.routes) or '-'}`",
            f"contexts: `{', '.join(record.contexts) or '-'}`",
            f"state: `{record.state}`",
            f"created: `{record.created_at}`",
            f"updated: `{record.updated_at}`",
            f"last used: `{record.last_used_at or '-'}` / count: `{record.use_count}`",
        ))
    return "\n".join(lines)


def paginate(records: List[Note], page: int, limit: int) -> Tuple[List[Note], int, int]:
    total_pages = max(1, math.ceil(len(records) / limit))
    safe_page = min(max(1, page), total_pages)
    start = (safe_page - 1) * limit
    return records[start:start + limit], safe_page, total_pages


def format_page(
    title: str,
    records: List[Note],
    page: int,
    limit: int,
    detail: bool,
    debug: bool,
) -> Tuple[str, List[Note], int, int]:
    shown, safe_page, total_pages = paginate(records, page, limit)
    if not shown:
        return f"{title}\n\n{NO_NOTES}", shown, safe_page, total_pages
    separator = "\n\n" if detail else "\n"
    body = separator.join(format_record(record, detail, debug) for record in shown)
    return f"{title}\n\n{body}\n\n{safe_page}/{total_pages}", shown, safe_page, total_pages


class NoteSelect(discord.ui.Select):
    def __init__(self, pager: "NotebookPagerView", records: List[Note]):
        options = [discord.SelectOption(
            label=(f"{record.id} {record.content}".replace("\n", " "))[:100],
            value=record.id,
        ) for record in records]
        super().__init__(placeholder="詳しく見るnote", options=options, min_values=1, max_values=1)
        self.pager = pager

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.pager.show_selected(interaction, self.values[0])


class NotebookPagerView(discord.ui.View):
    def __init__(
        self,
        *,
        storage: NotebookStorage,
        requester_id: int,
        owner_id: Optional[int],
        kind: str,
        scope: str,
        title: str,
        records: List[Note],
        page: int,
        limit: int,
        detail: bool,
        debug: bool,
    ):
        super().__init__(timeout=180)
        self.storage = storage
        self.requester_id = requester_id
        self.owner_id = owner_id
        self.kind = kind
        self.scope = scope
        self.title = title
        self.records = records
        self.page = page
        self.limit = limit
        self.detail = detail
        self.debug = debug and owner_id == requester_id
        self.message: Optional[discord.InteractionMessage] = None
        self._rebuild()

    def content(self) -> str:
        text, _, self.page, _ = format_page(
            self.title, self.records, self.page, self.limit, self.detail, self.debug
        )
        return text[:2000]

    def _rebuild(self) -> None:
        self.clear_items()
        _, shown, self.page, total_pages = format_page(
            self.title, self.records, self.page, self.limit, self.detail, self.debug
        )
        previous = discord.ui.Button(label="前へ", style=discord.ButtonStyle.secondary, disabled=self.page <= 1)
        previous.callback = self.previous
        next_button = discord.ui.Button(label="次へ", style=discord.ButtonStyle.secondary, disabled=self.page >= total_pages)
        next_button.callback = self.next_page
        detail_button = discord.ui.Button(
            label="簡易表示" if self.detail else "詳細表示", style=discord.ButtonStyle.secondary
        )
        detail_button.callback = self.toggle_detail
        close = discord.ui.Button(label="閉じる", style=discord.ButtonStyle.secondary)
        close.callback = self.close_view
        self.add_item(previous)
        self.add_item(next_button)
        self.add_item(detail_button)
        self.add_item(close)
        if shown:
            self.add_item(NoteSelect(self, shown))

    async def _allowed(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "これは、きみに向けて開いたnoteじゃないみたい", ephemeral=True
            )
            return False
        if scope_for(interaction, self.kind) != self.scope:
            await interaction.response.send_message("この場所からは、そのnoteを見られないよ", ephemeral=True)
            return False
        return True

    async def _refresh(self, interaction: discord.Interaction) -> None:
        self.records = sorted(
            await self.storage.list_active([self.scope]), key=lambda item: item.updated_at, reverse=True
        )
        self._rebuild()
        await interaction.response.edit_message(content=self.content(), view=self)

    async def previous(self, interaction: discord.Interaction) -> None:
        if await self._allowed(interaction):
            self.page -= 1
            await self._refresh(interaction)

    async def next_page(self, interaction: discord.Interaction) -> None:
        if await self._allowed(interaction):
            self.page += 1
            await self._refresh(interaction)

    async def toggle_detail(self, interaction: discord.Interaction) -> None:
        if await self._allowed(interaction):
            self.detail = not self.detail
            self.limit = min(self.limit, 3) if self.detail else max(self.limit, 5)
            self.page = 1
            await self._refresh(interaction)

    async def show_selected(self, interaction: discord.Interaction, note_id: str) -> None:
        if not await self._allowed(interaction):
            return
        record = await self.storage.get_by_id(note_id)
        if record is None or record.state != "active" or record.scope != self.scope:
            await interaction.response.send_message("そのnoteは、もうここにないみたい", ephemeral=True)
            return
        await interaction.response.send_message(
            format_record(record, detail=True, debug=self.debug)[:2000], ephemeral=True
        )

    async def close_view(self, interaction: discord.Interaction) -> None:
        if await self._allowed(interaction):
            self.stop()
            await interaction.response.edit_message(content="閉じたよ", view=None)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
