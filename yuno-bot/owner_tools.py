from config import OWNER_ID
from memory_model import ensure_memory_entry, format_memory_for_display


bot = None


def configure(*, discord_bot):
    global bot
    bot = discord_bot


async def send_long(channel, text, limit=2000):
    if not text:
        return
    for index in range(0, len(text), limit):
        await channel.send(text[index:index + limit])


async def revealmemory(ctx, user_id: str = None):
    if str(ctx.author.id) != OWNER_ID:
        await ctx.send("⚠️ このコマンドは管理者しか使えないみたい")
        return

    target_id = user_id or str(ctx.author.id)
    entry = ensure_memory_entry(target_id)
    member = None
    if ctx.guild is not None:
        try:
            member = ctx.guild.get_member(int(target_id))
        except (TypeError, ValueError):
            pass
    display_name = member.display_name if member is not None else f"ID:{target_id}"

    lines = [f"🔍 {display_name} の全記憶："]
    lines.extend(format_memory_for_display(entry) or ["（なし）"])
    lines.append(f"・change_log: {len(entry.get('change_log', []))}件")

    await send_long(ctx.channel, "\n".join(lines[:200]))

async def sleep(ctx):
    if str(ctx.author.id) != OWNER_ID:
        await ctx.send("⚠️ このコマンドは管理者しか使えないみたい")
        return
    await ctx.send("……おやすみ")
    print(f"🌙 {ctx.author.display_name} によって終了されました")
    await bot.close()
