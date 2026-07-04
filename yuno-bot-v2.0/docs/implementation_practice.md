# yuno-bot-v2.0 実装作法

この文書は、yuno-bot-v2.0 をどう実装していくかの作法をまとめます。

`next_direction.md` は「どこへ向かうか」を扱います。
この文書は「どう進めるか」「何を増やさないか」「実装ごとに何を整理するか」を扱います。

目的は、実装内容の終着点を固定することではありません。
方針転換があっても不要コードが増え続けないように、変更の進め方を固定します。

## 基本姿勢

新しい機能を足す前に、まず置き場所を決めます。

- Conversation / Pipeline
- CareReader
- Speaker
- Memory / Attention / Cue
- Tool
- Permission
- Discord UI
- Infra
- Docs / Operation

どこにも自然に入らない場合は、まだ実装しません。

## 追加より先に畳む

新しい名前、新しいService、新しいtable、新しいcommandを足す前に、既存概念で表せないか確認します。

特に注意するもの:

- Attention と Cue
- Memory と設定
- Tool と command
- scope と permission
- CareReader と ToolReader
- status と health
- export と backup
- hide と forget

似た概念がある場合は、新規追加ではなく、統合、移動、または既存概念の再命名を優先します。

## 実装単位

1回の実装で、複数の方向転換を同時にしません。

よい単位:

- PermissionServiceだけを足す
- ToolDefinition / ToolRegistryだけを足す
- /statusの表示を整理する
- InterestTermをUI上でCue扱いへ寄せる
- LogServiceのread-onlyだけを足す

悪い単位:

- ToolReader、ログ取得、restart、UI再編、DB migrationを同時に入れる
- Speaker prompt変更と管理tool実装を同時に入れる
- scope modelとuser memoryを同時に入れる

## 既存会話挙動を守る

管理機能やtoolを足す回では、通常会話の挙動をなるべく変えません。

特に、以下は別件にします。

- persona変更
- Speaker prompt変更
- CareReader prompt変更
- listeningの割り込み基準変更
- recent件数変更
- MemoryMark参照件数変更

必要がある場合は、変更理由を明記し、before / afterを小さく確認します。

## 表の入口を増やさない

slash commandを増やす前に、既存の入口へ入れられるか確認します。

基本入口:

- /status
- /settings
- /memories
- /tools

一時的にdebug commandを追加する場合は、以下を明記します。

- なぜ既存入口では足りないか
- いつ消すか
- 何に統合するか

## Serviceを先に作り、UIは薄くする

Discord commandはできるだけ薄くします。

よい形:

```text
Discord command
→ PermissionService
→ Application Service
→ Result object
→ Discord renderer
```

避ける形:

```text
Discord command内でDB操作、権限判定、表示文、実行処理を全部書く
```

UI文言は後から変わります。
変わりやすい表示層と、守るべき実行層を混ぜません。

## Tool実装の作法

Toolは増やせるようにします。
ただし、万能化しません。

禁止:

- 任意shell
- 任意ファイル読み取り
- LLMによる権限判定
- allowlistなしの外部操作
- secretを含む可能性のあるraw logをそのままSpeakerへ渡す

Toolを追加するときは、必ず以下を定義します。

- name
- description
- scope
- required_permission
- required_discord_permissions
- risk_level
- input_schema
- executor
- result type
- raw出力をSpeakerへ渡すかどうか

read-onlyから始めます。
write、restart、delete、restore、permission変更は後回しにし、権限があっても確認を挟みます。

## 権限実装の作法

権限判定はコードで行います。

LLMや自然文解釈は、操作意図をToolPlanへ変換するだけです。
実行可否はPermissionServiceが決めます。

分けるもの:

- Discord上の権限
- owner権限
- OS上で許される操作
- bot自身が持つDiscord権限
- toolのrisk_level

自然文操作でもslash commandでも、同じPermissionServiceを通します。

## Speakerへ渡してよいもの

Tool結果をSpeakerへ渡す場合、渡すのは表示可能な要約だけにします。

渡してよいもの:

- tool名ではなく、人間に見せてよい短い結果
- 成功 / 失敗
- 件数
- masked excerpt
- 次に確認すべきこと

渡さないもの:

- ToolPlanの内部理由
- raw JSON
- permission判定の内部詳細
- risk score
- secretを含む可能性のあるraw log
- allowlistの内部path
- traceback全文

## ログ取得の作法

ログ取得は、必ず範囲と量を制限します。

必須:

- allowlist source
- since / until または明示的な件数limit
- 最大行数
- secret mask
- raw表示とsummary表示の分離
- owner限定またはguild_admin以上の明示判定

禁止:

- サーバー上の任意ファイル読み取り
- `/var/log` 全体の自由探索
- token、env、cookie、secretの未mask表示
- ログ全量をLLMへ渡す

## DB変更の作法

DB migrationは、機能追加と分けるのが望ましいです。

migrationを入れる場合は、以下を書く。

- 追加するtable / column
- 既存dataへの影響
- rollbackできない場合の理由
- old dataの扱い
- migration後の確認方法

旧概念を消す場合も、すぐdropしないでよいです。
まずUIから隠し、互換層を置き、移行確認後に削除します。

## テストと確認

各実装回で最低限行う確認:

```powershell
python -m compileall main.py yuno tests
python -m unittest discover -s tests
python -c "from yuno.app import create_bot; bot=create_bot(); print('bot ok')"
```

機能ごとに追加する確認:

- PermissionService: owner / guild_admin / user / denied の判定
- ToolRegistry: 未登録toolを実行しない
- ToolReader: write系は確認なしで実行しない
- LogService: limit、mask、allowlist
- Memory / Attention / Cue: 重複作成しすぎない
- Discord UI: 権限なしはephemeralで短く拒否

## 作業メモに必ず書くこと

PR、Codex依頼、または作業メモには、以下を必ず書きます。

- 目的
- 触ってよい範囲
- 触らない範囲
- 追加するもの
- 既存から置き換えるもの
- まだ残すlegacy/debug
- 次に削る候補
- 確認方法

## 削除候補を毎回出す

各実装回では、追加したものだけでなく、次に削る候補も出します。

削除候補の例:

- 旧command alias
- 使われなくなったService method
- 旧InterestTerm UI
- 旧import用の一時変換コード
- debug用の表示文
- 使われない抽象class

削除できない場合は、理由を書く。

- 互換のため
- migration待ち
- 次回で置き換え予定
- まだ参照が残っている

## 使われない抽象を残さない

将来使うかもしれないだけの抽象は残しません。

許される抽象は、次のどれかに限ります。

- すでに1つ以上の実装がある
- 次の実装回で確実に使う
- 既存の重複を減らしている

## Codexへ依頼するときの型

Codexへ投げる依頼は、次の形にします。

```text
目的:

触ってよい範囲:

触らない範囲:

実装すること:

整理すること:

追加してはいけないもの:

確認方法:

作業後に報告してほしいこと:
- 追加したもの
- 置き換えたもの
- 残したlegacy/debug
- 次に削る候補
- 実行した確認
```

## 判断基準

迷ったら、以下を優先します。

- 新しい機能より、既存概念の整理
- 表示より、Serviceの境界
- 自然文の便利さより、PermissionService
- 管理機能より、ConversationLog中心
- toolの強さより、allowlist
- 実装完了より、次に整理できる状態
