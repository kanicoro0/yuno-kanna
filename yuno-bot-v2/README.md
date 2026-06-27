# yuno-bot-v2

Discord bot「ゆの / 唯乃」v2 の初期骨格です。完成版ではなく、次の責務境界をコード上で試すための実装です。

```text
Message
  → Pre-context
  → Pre-planning（sleep / auto reply / rate limit。原則AIを呼ばない）
  → Pre-retrieval
  → Planner（見る場所と行動候補を決める）
  → Executor（候補を検証し、実行可能な形にする）
  → Speaker（声にする）
  → Discord send
  → Commit（送信成功後に記憶と履歴を確定する）
```

v1 の `yuno-bot/` とはコード・設定・記憶ファイルを共有しません。v1機能は、その操作感を参照しながらv2の責務構造に合わせて移植します。対応状況は[`docs/v1_feature_parity.md`](docs/v1_feature_parity.md)にあります。

`data/memories.json`、`data/runtime_settings.json`、`data/memory_changelog.json`はGit管理しないruntime実データです。対応する`.example.json`だけを管理します。将来の`data/memory_embeddings.json`もignore済みです。

## Persona

v2では、ゆのの声と判断の質感を定めるpersona promptをSpeaker側に置きます。Plannerは見る場所と行動候補を決めるだけで、返答本文を書きません。

personaはv1の「唯乃 / ゆの」を参照していますが、v1固有の記憶形式、`memory_operations`、`guild_memory_operations`は移植していません。現在はv1記憶の移行より先に、Speakerの声がゆのとして安定するかを確認する段階です。

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
RUNTIME_SETTINGS_FILE=data/runtime_settings.json
MEMORY_CHANGELOG_FILE=data/memory_changelog.json
OWNER_ID=
```

`OPENAI_API_KEY` が空でも Bot 自体は構築でき、Planner / Speaker は構造確認用 mock に切り替わります。Discordへ接続するには常に `DISCORD_TOKEN` が必要です。

```powershell
python main.py
```

Discord Developer Portal で Message Content Intent を有効にしてください。`YUNO_ENV=dev` かつ `DISCORD_GUILD_ID` が設定されている場合、slash command は開発guildへ同期します。それ以外ではglobal syncします。

## 現在あるもの

- DM・メンション・`/yuno ` / `!yuno ` / `yuno. ` prefix の route 判定
- AIを呼ぶ前のsleep・非メンション許可・user/channel/global rate limit
- scope / context / routes / tags / keyword / weight による理由付き Pre-retrieval
- JSONを境界にした Planner と Speaker（API失敗時も mock fallback）
- `ActionPlan → Executor → ExecutionResult` の検証境界
- `record action + scope` に統一した add / rewrite / delete 候補
- 送信成功まで保存しない `PendingCommit`
- schema v2 の独立した MemoryRecord / JSON storage
- `/memory user|server|channel show|add|edit|delete|undo|history`
- `/memory get|search`と、button/select付きのscope別一覧
- `/guide`、`/status`、channel/server/global対応の`/sleep`と`/wake`
- `/settings memory_view`によるnormal/debug表示切り替え
- server/channel単位の`/autorespond`設定
- 設定で許可された場所だけ非メンション発言をPlannerへ渡す経路

記憶操作のsystem reactionは、user scopeの add / rewrite / delete が `📌` / `📝` / `🗑️`、guild / channel scopeが `🏷️` です。AIの通常 `react` actionからこれらを付けることはできません。

## Commands

記憶はuser/server/channelのscope別UIで扱います。v1の`/servermemory`は`/memory server`へ吸収し、`guild_notes.json`は使いません。

```text
/memory user show|add|edit|delete
/memory user undo|history
/memory server show|add|edit|delete|undo|history
/memory channel show|add|edit|delete|undo|history
/memory get id:45 detail:true|false
/memory search query:... page:1 limit:5 detail:false
/guide
/status
/sleep scope:channel|server|global
/wake scope:channel|server|global
/autorespond status
/autorespond server enabled:true|false
/autorespond channel enabled:true|false
/settings memory_view mode:normal|debug
```

serverの変更にはサーバー管理権限、channelの変更にはチャンネル管理権限が必要です。global sleep/wakeとdebug表示は`OWNER_ID`だけが使えます。debugでも閲覧可能scopeは増えません。

memory一覧は既定でcompactな`id: 内容`形式です。`detail:true`ではid/content/scope/tags/weightを表示し、ownerがdebug modeを選んだ場合だけroutes/contexts/state/timestamp/usageも追加します。一覧にはpage/limitのslash fallbackと、前へ・次へ・詳細表示・閉じるbutton、1件を選ぶselect menuがあります。componentは操作したユーザーと現在scopeを毎回検証し、timeout後は無効化します。

新規IDは、既存の数値IDの最大値+1を`mem_####`（最低4桁）として作ります。既存IDや欠番は変更せず、`id` optionには完全IDまたは`45`のような数字を渡せます。

自動記憶は会話prompt内で直接保存せず、Plannerのrecord候補をExecutorが検証し、Discord送信成功後にCommitします。slash CRUDとPlanner commitは同じ`MemoryService`を通り、before/afterをchange logへ残します。scope別undoは自分が行った直近の未undo変更だけを戻し、undo自体も記録します。

## 仮実装・保留・TODO

- mock Planner は原則 `speak` を返し、mock Speaker は構造確認用の定型応答です。賢さの代替ではありません。
- `semantic` route はschemaとして許可していますが、embedding/vector検索は未実装です。現在は lexical candidate と合流できる境界だけがあります。
- `SpeakerOutput.next_call` は実装済みですが、followup / repair / second_thought の3回目呼び出しはまだ実行しません。
- `/memory edit`は現在、本文の直接編集に対応しています。tags / routes / contexts / weightの編集ModalはTODOです。
- Planner由来の record action は安全検証後に自動commitできます。複数JSONファイルをまたぐ厳密なtransactionと、曖昧な記憶依頼の確認UIは未実装です。
- `last_used_at` / `use_count` は保存できますが、retrieval利用後の更新は未実装です。weightの自動変更は行いません。
- 会話履歴はプロセス内だけです。再起動後の復元、要約、長期context管理は未実装です。
- 非メンションのAI判定フェーズは未実装です。現在は設定許可後、そのまま通常Plannerへ渡します。
- Discord上の文字数超過は初期実装では2000文字で切ります。自然な分割送信は行いません。
- JSON storeは単一プロセス向けです。複数プロセス同時書き込みやDB移行は未対応です。
- Planner / Speaker promptとaction policyは初期版です。運用前に実際のmodel出力を使った安全テストが必要です。

`/remind`、`/cancelremind`、`/reminders`は後回しです。owner debug toolsも、MemoryRecord・deleted state・change log・表示権限を含めて後から再設計します。使えないcommandは登録していません。

semantic retrievalは未実装です。既存のalways/keyword/tag retrievalを維持しており、将来はpre-planning通過後に追加候補として合流させます。無効・失敗時は通常retrievalだけで続行する設計にします。

次の分割候補は、(1) memory edit Modal、(2) semantic候補の合流、(3)複数ファイルtransaction、(4) optional third call、(5)非メンション用の追加判断フェーズです。

## 構文確認

```powershell
python -m compileall .
```
