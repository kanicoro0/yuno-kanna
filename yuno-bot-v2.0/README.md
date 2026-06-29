# yuno-bot-v2.0

Discord bot「ゆの / 唯乃」の、ConversationLogを本体にした再設計版です。

実装判断の基準は [`docs/yuno_design_principles.md`](docs/yuno_design_principles.md) にあります。

現在は第3A段階として、会話の縦切りを保ったままMemoryMark、AttentionItem、InterestTerm、CareReaderを接続しています。

実装や設計を進める前に、まず [`docs/yuno_design_principles.md`](docs/yuno_design_principles.md) を読んでください。ゆのv2.0では、機能追加よりも「相手の言葉を処理対象として消費せず、預かったものとして扱うこと」を優先します。

```text
Discord入力変換 → routing → user保存 → CareReader → Core更新
→ ContextBuilder → Speaker
→ PipelineResult → Discord送信 → 送信成功後だけassistant保存
```

MemoryMarkは独立した記憶庫ではなく、ConversationLogにつく印です。`pending` は失くさない候補、`active` は通常参照可能、`hidden` は通常contextから外した状態です。

AttentionItemは、まだ閉じていない話題や問いです。人格状態、気分、口調のmodeではありません。InterestTermはCareReaderの注意を少し寄せる語であり、返信スイッチや返信確率ではありません。

CareReaderは同じstreamを静かに読み、印・Attention・関心語・話すかどうかをJSONで返します。返答本文や口調指示は書きません。SpeakerへはContextBuilderが組み立てた実際の履歴と、同じstreamのvisibleな参照だけを渡します。routing名、内部理由、salienceは渡しません。

操作command、完全削除、legacy v2 import本体は次段階です。Notebook専用tableや旧Notebook JSONは復活させません。

## 会話ログの範囲

- DMは保存して返信します。
- 直接mentionと、DBに保存済みのゆのの発言へのDiscord replyは保存してreplyします。
- `LISTENING_CHANNEL_IDS` のチャンネルでは人間の通常発言を保存しますが、割り込みません。
- listening対象で `YUNO_CALL_NAMES` の呼び名を含む発言にはplain送信で返します。
- それ以外のguild発言は保存しません。
- `/status` で現在の保存範囲を確認できます。

会話の単位はDiscordチャンネル／DMです。別チャンネルやDMの生ログを混ぜません。

## Setup

```powershell
cd yuno-bot-v2.0
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

必須設定は `DISCORD_TOKEN`、`OPENAI_API_KEY`、`OPENAI_MODEL` です。OpenAI設定が空の場合は、ローカルの短いfallback応答を使います。

SQLiteは既定で `data/yuno.sqlite3` に作成され、WAL、foreign keys、busy timeout、schema migrationを使用します。runtime dataはGit管理外です。

## 旧v2 Notebookの扱い

旧記憶は破棄しません。後続段階で、明示的なdry-run付きimportとして実装します。

- 旧noteをannotationへ変換する
- source messageがなければ `legacy_v2_notebook` sourceとする
- 旧note ID、import日時、batch IDを保持する
- scopeを拡大せず、不明なscopeは `legacy_unscoped` とする
- 同じ旧noteを重複作成しない
- ConversationLog由来annotationと矛盾した場合は新しい方を優先する
- previewを `data/import_preview_*.json` に出力できるようにする

この互換sourceは新規記憶の通常経路には使用しません。
詳細な変換契約は [`docs/legacy_v2_import_plan.md`](docs/legacy_v2_import_plan.md) に固定しています。

## Verification

```powershell
python -m compileall main.py yuno tests
python -m unittest discover -s tests
python -c "from yuno.app import create_bot; bot=create_bot(); print('bot ok')"
```
