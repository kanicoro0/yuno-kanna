import discord
from discord import app_commands


GUIDE_TEXT = '''ゆのとの話し方
ふつうに話しかけてくれたら、ゆのは聞いてるよ
「これ覚えて」って言えば覚えるし、「さっきのは忘れて」って言えば手放す
「もう閉じていい」「ちゃんと覚えておいて」「その呼び方はやめて」も、会話の中でそのまま頼めるよ
どれのことか分からない時は、ゆのから聞き返すことがある

たしかめたい時・直したい時
`/status` この場所でどう聞いているか見る
`/listening` 聞く場所を確認・変更する
`/memories list` この場所に残したものを見る（種類や状態で絞れるよ）
`/memories recent` この場所の最近の動きを見る

メッセージを右クリック → アプリ → `ゆのに預ける`
`残す` `あとで見る` `閉じる` が使えるよ
一覧では `隠す` `戻す` もできる

コマンドか右クリックから開いてね'''


def create_guide_command() -> app_commands.Command:
    @app_commands.command(name='guide', description='ゆのでできることを見る')
    async def guide(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            GUIDE_TEXT,
            ephemeral=True,
        )

    return guide
