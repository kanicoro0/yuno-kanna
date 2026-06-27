# yuno-bot-v2

Discord bot「ゆの / 唯乃」v2 の初期骨格です。完成版ではなく、次の責務境界をコード上で試すための実装です。

```text
Message
  → Pre-context / Pre-retrieval
  → Planner（見る場所と行動候補を決める）
  → Executor（候補を検証し、実行可能な形にする）
  → Speaker（声にする）
  → Discord send
  → Commit（送信成功後に記憶と履歴を確定する）
```

v1 の `yuno-bot/` とはコード・設定・記憶ファイルを共有しません。`MEMORY_FILE` の既定値は、このディレクトリ内の `data/memories.json` です。`memories.json` はGit管理しないローカル実データで、`data/memories.example.json` は空schemaの見本です。

## セットアップ

Python 3.9 以上を想定しています。

```powershell
cd yuno-bot-v2
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` に v2 専用の `DISCORD_TOKEN` を設定してください。本番のAI応答には `OPENAI_API_KEY` も必要です。値をログやGitへ入れないでください。

```env
DISCORD_TOKEN=
DISCORD_CLIENT_ID=
DISCORD_GUILD_ID=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5
YUNO_ENV=dev
MEMORY_FILE=data/memories.json
```

`OPENAI_API_KEY` が空でも Bot 自体は構築でき、Planner / Speaker は構造確認用 mock に切り替わります。Discordへ接続するには常に `DISCORD_TOKEN` が必要です。

```powershell
python main.py
```

Discord Developer Portal で Message Content Intent を有効にしてください。`YUNO_ENV=dev` かつ `DISCORD_GUILD_ID` が設定されている場合、slash command は開発guildへ同期します。それ以外ではglobal syncします。

## 現在あるもの

- DM・メンション・`/yuno ` / `!yuno ` / `yuno. ` prefix の route 判定
- scope / context / routes / tags / keyword / weight による理由付き Pre-retrieval
- JSONを境界にした Planner と Speaker（API失敗時も mock fallback）
- `ActionPlan → Executor → ExecutionResult` の検証境界
- `record action + scope` に統一した add / rewrite / delete 候補
- 送信成功まで保存しない `PendingCommit`
- schema v2 の独立した MemoryRecord / JSON storage
- `/memory show` と `/memory edit` の検索入口
- 非メンション発言を短いインメモリ履歴へ残し、Speakerを呼ばない経路

記憶操作のsystem reactionは、user scopeの add / rewrite / delete が `📌` / `📝` / `🗑️`、guild / channel scopeが `🏷️` です。AIの通常 `react` actionからこれらを付けることはできません。

## Memory command

Discord の slash option として `query` を渡します。

```text
/memory show
/memory show query:recent
/memory show query:tag:tone
/memory show query:search:話し方

/memory edit
/memory edit query:recent
/memory edit query:tag:tone
/memory edit query:search:話し方
/memory edit query:id:mem_xxx
```

表示・検索は呼び出した本人の user scopeと、現在の guild / channel scopeに限定されます。

## 仮実装・保留・TODO

- mock Planner は原則 `speak` を返し、mock Speaker は構造確認用の定型応答です。賢さの代替ではありません。
- `semantic` route はschemaとして許可していますが、embedding/vector検索は未実装です。現在は lexical candidate と合流できる境界だけがあります。
- `SpeakerOutput.next_call` は実装済みですが、followup / repair / second_thought の3回目呼び出しはまだ実行しません。
- `/memory edit query:id:...` は詳細表示のみです。content / tags / routes / contexts / weight / state の編集ModalはTODOです。
- Planner由来の record action は安全検証後に自動commitできますが、ユーザー意図の高度な曖昧性判定、undo、change logは未実装です。
- `last_used_at` / `use_count` は保存できますが、retrieval利用後の更新は未実装です。weightの自動変更は行いません。
- 会話履歴はプロセス内だけです。再起動後の復元、要約、長期context管理は未実装です。
- 非メンションは観察のみです。Plannerによるreaction / 短文応答 / context更新は今後の段階です。
- Discord上の文字数超過は初期実装では2000文字で切ります。自然な分割送信は行いません。
- JSON storeは単一プロセス向けです。複数プロセス同時書き込みやDB移行は未対応です。
- Planner / Speaker promptとaction policyは初期版です。運用前に実際のmodel出力を使った安全テストが必要です。

次の分割候補は、(1) record policyとchange log/undo、(2) memory edit UI、(3) retrieval provider interfaceとsemantic候補の合流、(4) optional third callの厳格な発火条件、(5)非メンション用policyです。

## 構文確認

```powershell
python -m py_compile main.py yuno\core\*.py yuno\infra\*.py yuno\actions\*.py yuno\memory\*.py yuno\commands\*.py
```
