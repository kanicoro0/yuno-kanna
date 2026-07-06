from typing import List, Optional

import discord
from discord import app_commands

from yuno.commands.notebook_view import (
    NotebookPagerView, accessible_scopes, format_page, format_record, paginate, scope_for,
)
from yuno.notebook.records import Note, utc_now
from yuno.notebook.service import Notebook
from yuno.notebook.storage import NotebookStorage
from yuno.runtime.settings import RuntimeSettings
from yuno.text import note_not_found


DEFAULT_ROUTES = ["semantic", "keyword", "tag"]
DEFAULT_CONTEXTS = ["dm", "mention", "prefix", "nonmention"]
SCOPE_TITLES = {
    "user": "きみについて書き留めたnote",
    "server": "このサーバーのnote",
    "channel": "このチャンネルのnote",
}


def _split_values(value: Optional[str], default: List[str]) -> List[str]:
    if not value:
        return list(default)
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _can_mutate(interaction: discord.Interaction, kind: str) -> bool:
    if kind == "user":
        return True
    if kind == "server":
        return interaction.permissions.manage_guild
    return interaction.permissions.manage_channels


async def _debug_enabled(
    interaction: discord.Interaction, runtime_settings: RuntimeSettings, owner_id: Optional[int]
) -> bool:
    return (
        owner_id is not None
        and interaction.user.id == owner_id
        and await runtime_settings.notebook_view(interaction.user.id) == "debug"
    )


async def _resolve_active_in_scope(
    storage: NotebookStorage, reference: str, scopes: List[str]
) -> Optional[Note]:
    note_id = await storage.resolve_id(reference)
    if note_id is None:
        return None
    record = await storage.get_by_id(note_id)
    if record is None or record.state != "active" or record.scope not in scopes:
        return None
    return record


def _create_scope_group(
    kind: str,
    storage: NotebookStorage,
    service: Notebook,
    runtime_settings: RuntimeSettings,
    owner_id: Optional[int],
) -> app_commands.Group:
    labels = {"user": "自分", "server": "サーバー", "channel": "チャンネル"}
    group = app_commands.Group(name=kind, description=f"{labels[kind]}のメモ帳")

    @group.command(name="show", description=f"{labels[kind]}のnoteを表示します")
    @app_commands.describe(page="ページ", limit="1ページの件数", detail="詳細表示")
    async def show(
        interaction: discord.Interaction,
        page: app_commands.Range[int, 1, 999] = 1,
        limit: app_commands.Range[int, 1, 8] = 5,
        detail: bool = False,
    ) -> None:
        scope = scope_for(interaction, kind)
        if scope is None:
            await interaction.response.send_message("サーバーの中で使ってね", ephemeral=True)
            return
        effective_limit = min(int(limit), 3) if detail else int(limit)
        records = sorted(
            await storage.list_active([scope]), key=lambda item: item.updated_at, reverse=True
        )
        debug = await _debug_enabled(interaction, runtime_settings, owner_id)
        view = NotebookPagerView(
            storage=storage,
            requester_id=interaction.user.id,
            owner_id=owner_id,
            kind=kind,
            scope=scope,
            title=SCOPE_TITLES[kind],
            records=records,
            page=int(page),
            limit=effective_limit,
            detail=detail,
            debug=debug,
        )
        await interaction.response.send_message(view.content(), view=view, ephemeral=True)
        try:
            view.message = await interaction.original_response()
        except (discord.HTTPException, AttributeError):
            pass

    @group.command(name="add", description=f"{labels[kind]}のメモ帳へnoteを追加します")
    @app_commands.describe(
        content="覚える内容", tags="カンマ区切りのタグ", routes="カンマ区切りのroute",
        contexts="カンマ区切りのcontext", weight="noteの強さ（1〜5）",
    )
    async def add(
        interaction: discord.Interaction,
        content: str,
        tags: Optional[str] = None,
        routes: Optional[str] = None,
        contexts: Optional[str] = None,
        weight: app_commands.Range[int, 1, 5] = 3,
    ) -> None:
        scope = scope_for(interaction, kind)
        if scope is None:
            await interaction.response.send_message("サーバーの中で使ってね", ephemeral=True)
            return
        if not _can_mutate(interaction, kind):
            await interaction.response.send_message("ここを変える権限がないみたい", ephemeral=True)
            return
        now = utc_now()
        record = Note(
            id="", scope=scope, content=content.strip(),
            routes=_split_values(routes, DEFAULT_ROUTES),
            contexts=_split_values(contexts, DEFAULT_CONTEXTS),
            weight=int(weight), tags=_split_values(tags, ["note"]),
            created_at=now, updated_at=now,
        )
        try:
            saved = await service.add(record, str(interaction.user.id), "slash")
        except ValueError:
            await interaction.response.send_message("その形では覚えられなかったよ", ephemeral=True)
            return
        await interaction.response.send_message(f"覚えたよ\n{saved.id}", ephemeral=True)

    @group.command(name="edit", description=f"{labels[kind]}のnoteを書き換えます")
    @app_commands.rename(note_id="id")
    @app_commands.describe(note_id="note IDまたは数字", content="新しいnote本文")
    async def edit(interaction: discord.Interaction, note_id: str, content: str) -> None:
        scope = scope_for(interaction, kind)
        if scope is None:
            await interaction.response.send_message("サーバーの中で使ってね", ephemeral=True)
            return
        if not _can_mutate(interaction, kind):
            await interaction.response.send_message("ここを変える権限がないみたい", ephemeral=True)
            return
        record = await _resolve_active_in_scope(storage, note_id, [scope])
        if record is None:
            await interaction.response.send_message(note_not_found(note_id), ephemeral=True)
            return
        try:
            saved = await service.rewrite(
                record.id, {"content": content.strip()}, str(interaction.user.id), "slash"
            )
        except ValueError:
            saved = None
        if saved is None:
            await interaction.response.send_message("その形には書き換えられなかったよ", ephemeral=True)
            return
        await interaction.response.send_message(f"書き換えたよ\n{saved.id}", ephemeral=True)

    @group.command(name="delete", description=f"{labels[kind]}のnoteを外します")
    @app_commands.rename(note_id="id")
    @app_commands.describe(note_id="note IDまたは数字")
    async def delete(interaction: discord.Interaction, note_id: str) -> None:
        scope = scope_for(interaction, kind)
        if scope is None:
            await interaction.response.send_message("サーバーの中で使ってね", ephemeral=True)
            return
        if not _can_mutate(interaction, kind):
            await interaction.response.send_message("ここを変える権限がないみたい", ephemeral=True)
            return
        record = await _resolve_active_in_scope(storage, note_id, [scope])
        if record is None:
            await interaction.response.send_message(note_not_found(note_id), ephemeral=True)
            return
        deleted = await service.delete(record.id, str(interaction.user.id), "slash")
        if deleted is None:
            await interaction.response.send_message(note_not_found(note_id), ephemeral=True)
            return
        await interaction.response.send_message(f"そっと外したよ\n{deleted.id}", ephemeral=True)

    @group.command(name="undo", description=f"{labels[kind]}のメモ帳で直近の変更を戻します")
    async def undo(interaction: discord.Interaction) -> None:
        scope = scope_for(interaction, kind)
        if scope is None:
            await interaction.response.send_message("サーバーの中で使ってね", ephemeral=True)
            return
        if not _can_mutate(interaction, kind):
            await interaction.response.send_message("ここを変える権限がないみたい", ephemeral=True)
            return
        try:
            result = await service.undo(scope, str(interaction.user.id))
        except ValueError:
            await interaction.response.send_message("その後に別の変更があるから、戻すのを止めたよ", ephemeral=True)
            return
        if result is None:
            await interaction.response.send_message("戻せる変更はないみたい", ephemeral=True)
            return
        target, restored = result
        await interaction.response.send_message(
            f"ひとつ戻したよ\n{restored.id}: {target.action}", ephemeral=True
        )

    @group.command(name="history", description=f"{labels[kind]}のメモ帳の変更履歴")
    @app_commands.describe(page="ページ", limit="1ページの件数")
    async def history(
        interaction: discord.Interaction,
        page: app_commands.Range[int, 1, 999] = 1,
        limit: app_commands.Range[int, 1, 10] = 5,
    ) -> None:
        scope = scope_for(interaction, kind)
        if scope is None:
            await interaction.response.send_message("サーバーの中で使ってね", ephemeral=True)
            return
        changes = await service.history(scope)
        total_pages = max(1, (len(changes) + int(limit) - 1) // int(limit))
        safe_page = min(int(page), total_pages)
        start = (safe_page - 1) * int(limit)
        shown = changes[start:start + int(limit)]
        if not shown:
            text = "変更履歴は、まだないよ"
        else:
            lines = [f"{item.timestamp[:16]}  {item.action}  {item.note_id}" for item in shown]
            text = "変更履歴\n\n" + "\n".join(lines) + f"\n\n{safe_page}/{total_pages}"
        await interaction.response.send_message(text, ephemeral=True)

    return group


def create_notebook_group(
    storage: NotebookStorage,
    service: Notebook,
    runtime_settings: RuntimeSettings,
    owner_id: Optional[int],
) -> app_commands.Group:
    root = app_commands.Group(name="notebook", description="ゆののメモ帳")
    for kind in ("user", "server", "channel"):
        root.add_command(_create_scope_group(kind, storage, service, runtime_settings, owner_id))

    @root.command(name="get", description="IDからnoteを1件表示します")
    @app_commands.rename(note_id="id")
    @app_commands.describe(note_id="note IDまたは数字", detail="詳細表示")
    async def get(interaction: discord.Interaction, note_id: str, detail: bool = False) -> None:
        record = await _resolve_active_in_scope(storage, note_id, accessible_scopes(interaction))
        if record is None:
            await interaction.response.send_message(note_not_found(note_id), ephemeral=True)
            return
        debug = await _debug_enabled(interaction, runtime_settings, owner_id)
        await interaction.response.send_message(
            format_record(record, detail=detail, debug=debug and detail)[:2000], ephemeral=True
        )

    @root.command(name="search", description="アクセスできるnoteを本文・タグから探します")
    @app_commands.describe(query="検索語", page="ページ", limit="件数", detail="詳細表示")
    async def search(
        interaction: discord.Interaction,
        query: str,
        page: app_commands.Range[int, 1, 999] = 1,
        limit: app_commands.Range[int, 1, 8] = 5,
        detail: bool = False,
    ) -> None:
        needle = query.strip().casefold()
        records = [
            record for record in await storage.list_active(accessible_scopes(interaction))
            if needle in record.content.casefold() or any(needle in tag for tag in record.tags)
        ]
        records.sort(key=lambda item: item.updated_at, reverse=True)
        effective_limit = min(int(limit), 3) if detail else int(limit)
        debug = await _debug_enabled(interaction, runtime_settings, owner_id)
        text, _, _, _ = format_page(
            "見つけたnote", records, int(page), effective_limit, detail, debug and detail
        )
        await interaction.response.send_message(text[:2000], ephemeral=True)

    return root
