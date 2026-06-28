# yuno-bot-v2.0 manual test plan

## 起動

1. `python main.py` で起動し、`Yuno v2.0 ready` が表示される。
2. slash commandがglobal syncされ、`/status` が利用できる。
3. `/status` のlistening対象と呼び名が `.env` と一致する。

## 会話の連続性

1. DMで2往復し、直前の話題を保って返す。
2. botを再起動し、同じDMで続きを話して文脈が残っている。
3. listening対象チャンネルで、二人の表示名と発言内容を混同しない。
4. 別チャンネルの固有の話題を尋ねても、生ログを知っているように返さない。
5. listening対象外の非mention発言がDBへ保存されない。
6. listening対象の非mention発言は保存されるが、botが割り込んで返信しない。
7. listening対象で「ゆの」「唯乃」「yuno」と呼ぶと、ユーザーmentionなしのplain送信で返す。
8. ゆのの保存済み発言へDiscord replyするとreplyで返し、人やDBにない発言へのreplyには反応しない。
9. mentionだけを送っても、内部判定の説明ではなく自然な最小発話になる。

## 障害境界

1. OpenAI設定なしでも受信・fallback返信・ログ保存が動く。
2. Discord送信に失敗した場合、受信ログは残り、存在しない返信ログは作られない。
