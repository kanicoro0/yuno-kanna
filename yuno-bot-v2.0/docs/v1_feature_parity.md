# v1 feature parity

v1は動作・文面・操作感の参照元です。v2からv1をimportせず、`Note`、scope、Planner → Executor → Speaker → Commitの境界に合わせて再実装します。

| 機能 | v1参照ファイル | v2移植先 | 状態 | 注意点 |
|---|---|---|---|---|
| v1 personal memo UI | v1 `memory_ui.py`, `memory_model.py` | `yuno/commands/notebook.py`, `yuno/notebook/` | Notebookとして実装 | scope別CRUD、get/search、component一覧、history/undo。deleteは`state: deleted` |
| v1 server memo command | v1 `server_memory.py` | `/notebook server` | 吸収済み | 独立commandと`guild_notes.json`は作らない |
| `/guide` | `general_commands.py` | `yuno/commands/general.py` | 今回実装 | 実際に登録される機能だけを案内 |
| `/status` | `general_commands.py` | `yuno/commands/general.py` | 今回実装 | secretは表示せず、設定状態とscope別件数を表示 |
| sleep / wake | `owner_tools.py`, `auto_reply.py` | `yuno/commands/control.py`, `yuno/runtime/settings.py` | 今回実装 | 安全に操作できるchannel単位をslash command化 |
| auto reply settings | `auto_reply.py` | `yuno/commands/control.py`, `yuno/runtime/settings.py` | 今回実装 | server/channel単位。既定は非メンション無効。server明示offは全体を止める |
| 非メンション文脈反応 | `conversation.py`, `auto_reply.py` | `yuno/core/preplanning.py`, `yuno/core/events.py` | 今回は制御経路を実装 | AI判定は入れず、明示的に許可された場所だけPlannerへ送る |
| v1 automatic memo | v1 `conversation.py`, `memory_model.py` | `yuno/actions/planner.py`, `executor.py`, `notebook/service.py` | Note actionとして基盤実装 | 送信成功後だけcommitし、slash CRUDと同じchange logへ記録。半自動確認は後回し |
| owner debug tools | `owner_tools.py` | 未定 | 後回し | Note、deleted state、change log、source map、表示権限を再設計してから実装 |
| `/remind`, `/cancelremind`, `/reminders` | `reminders.py` | 未定 | 後回し | `reminders.json`移行と再起動復元を含め、今回はcommand登録しない |

## 今回の境界

```text
Discord message
  → route判定
  → PrePlanner（sleep / auto reply / cooldown。AIを呼ばない）
  → Pre-retrieval
  → Planner
  → Executor
  → Speaker
  → send
  → Commit
```

未完成のcommandはDiscordへ登録しません。reminderとowner debug toolsは、責務と永続形式を決めてから別の段階で扱います。
