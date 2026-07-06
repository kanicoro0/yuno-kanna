import discord
from discord import app_commands


GUIDE_TEXT = '''ゆのの使い方
`/status` この場所でどう聞いているか見る
`/listening` 聞く場所を確認・変更する
`/memories list` この場所に残したものを見る（種類や状態で絞れるよ）

メッセージを右クリック → アプリ → `ゆのに預ける`
`残す` `あとで見る` `閉じる` が使えるよ
一覧では `隠す` `戻す` もできる

操作したい時は、コマンドか右クリックから開いてね'''


def create_guide_command() -> app_commands.Command:
    @app_commands.command(name='guide', description='ゆのでできることを見る')
    async def guide(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            GUIDE_TEXT,
            ephemeral=True,
        )

    return guide
