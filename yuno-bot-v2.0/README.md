# yuno-bot-v2.0

Discord bot「ゆの / 唯乃」の、ConversationLogを本体にした再設計版です。

現在は第2段階として、会話の縦切りを保ったままDiscord・routing・pipeline・context・Speakerの境界を分離しています。

```text
Discord入力変換 → routing → user保存 → ContextBuilder → Speaker
→ PipelineResult → Discord送信 → 送信成功後だけassistant保存
```

Notebook、Annotation、MindState、Planner、旧v2 Notebook importはまだ実装していません。将来の追加文脈はContextBuilderへだけ接続し、routingの内部判定をSpeakerへ渡さない構造です。

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
