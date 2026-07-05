import discord
from discord import app_commands


GUIDE_TEXT = '''ゆのでできること
`/status` いまの聞こえ方を見る
`/listening` 聞く場所を管理する
`/memories list` この場所に残したものを見る

メッセージを右クリックして `ゆのに預ける`
`残す` `あとで見る` `閉じる` が使えるよ
一覧では `隠す` `戻す` もできる

ふつうの返事には、ボタンはつかないよ'''


def create_guide_command() -> app_commands.Command:
    @app_commands.command(name='guide', description='ゆのでできることを見る')
    async def guide(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            GUIDE_TEXT,
            ephemeral=True,
        )

    return guide
