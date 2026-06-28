# yuno-bot-v2

Discord bot「ゆの / 唯乃」v2 の開発版です。

## 内部概念

```text
Notebook        ゆののメモ帳。明示的に書き留めたNoteを保存する
MindState       ゆのの今の頭の中。会話の現在地や開いている問いを短期保持する
ConversationLog 実際に交わされた言葉。必要な場合だけ少し広く参照する
```

会話処理は次の境界を維持します。

```text
Pre-planning → Notebook retrieval → Planner → Executor → Speaker → Send → Commit
```

NotebookとMindStateはDiscord送信成功後だけ更新します。通常時は最新発言、統合した短い`mind_context`、直近2〜4件のConversationLog、retrievalされたNote候補だけをmodelへ渡します。Plannerが`needs_log_lookup`を返した場合だけ、Speakerへ最大16件のrecent logを渡します。

## Models

- Speaker: `OPENAI_MODEL`
- Planner: `OPENAI_FALLBACK_MODEL`
- `OPENAI_FALLBACK_MODEL`未設定時はPlannerも`OPENAI_MODEL`

名前はfallbackですが、v2ではPlanner用modelとしても使います。Plannerは返答本文を書かず、小さなroute/note/log判断だけを担当します。

## Setup

```powershell
cd yuno-bot-v2
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

```env
DISCORD_TOKEN=
DISCORD_CLIENT_ID=
DISCORD_GUILD_ID=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.5
OPENAI_FALLBACK_MODEL=gpt-5
YUNO_ENV=dev
NOTEBOOK_FILE=data/notebook.json
NOTEBOOK_CHANGELOG_FILE=data/notebook_changelog.json
MIND_STATE_FILE=data/mind_state.json
RUNTIME_SETTINGS_FILE=data/runtime_settings.json
OWNER_ID=
DEBUG_ENABLED=false
PROMPT_DEBUG_ENABLED=false
DEBUG_DIR=data/debug
```

API key未設定時はPlanner/Speakerともmock fallbackになります。secretやprompt本文はログへ出しません。

## Owner debug（hidden prefix）

`OWNER_ID`本人かつ`DEBUG_ENABLED=true`（または`PROMPT_DEBUG_ENABLED=true`）のときだけ、次のprefix入力を処理します。slash commandには登録されません。

```text
yuno-debug trace last
yuno-debug prompt last
yuno-debug mind diff
yuno-debug note find note_0045
yuno-debug cost last
```

長いpromptや内部状態はDiscordへ貼らず、`DEBUG_DIR`（既定`data/debug/`）へ保存します。このdirectoryはGit管理外です。保持するのは再起動までの直前1処理分で、debug採取・保存の失敗は通常会話へ伝播させません。

## Commands

```text
/notebook user|server|channel show|add|edit|delete|undo|history
/notebook get id:note_0045 detail:true|false
/notebook get id:45 detail:true|false
/notebook search query:...
/mind show target:user|server|channel|dm
/mind clear target:user|server|channel|dm
/mind status
/settings notebook_view mode:normal|debug
/status
/guide
/sleep target:channel|server|global
/wake target:channel|server|global
/autorespond status|server|channel
```

Notebook一覧は通常`note_0045: 内容`のcompact表示です。`detail:true`で対象/tags/weightを追加し、`OWNER_ID`本人がdebug modeを選んだ場合だけroute/context/timestamp等を追加します。button/select UIにも場所と操作者の再検証があります。

新規Note IDは既存数値IDの最大値+1を`note_####`（最低4桁）として採番します。欠番や既存IDは変更しません。数字だけの入力は`note_####`へ解決します。

## Runtime data

次の実データはGit管理しません。

```text
data/notebook.json
data/notebook_changelog.json
data/mind_state.json
data/runtime_settings.json
data/notebook_embeddings.json（将来用）
```

`notebook.json`はschema v2の`notes`配列、changelogはschema v1の`changes`配列、MindStateはschema v1のscope別`states` objectです。example JSONを初期形として使えます。

## Current limitations

- semantic/vector retrievalは未実装
- ConversationLogはプロセス内のみで永続化しない
- server会話ではSpeakerのMindState更新をchannel scopeへ保存する（user/guild scopeは保存・統合可能だが自動更新policyは今後調整）
- Notebook本体とchangelogの複数ファイルtransactionは未実装
- Note metadata編集Modal、optional third call、reminder、より広いowner管理toolsは未実装

実Discord確認項目は[`docs/manual_test_plan.md`](docs/manual_test_plan.md)にあります。

## Verification

```powershell
python -m compileall .
python -c "from yuno.core.bot import create_bot; bot=create_bot(); print('bot ok')"
```
