# yuno-bot-v2.0 次の方針

この文書は、yuno-bot-v2.0 を次にどう変化させるかを決めるための作業方針です。

既存の `yuno_design_principles.md` は、ゆのが会話の中でどう存在するかを扱います。
この文書では、その芯を残したまま、自分のサーバーで常駐させ、必要な仕事を任せられる状態へ進めるための判断基準を書きます。

## 目的

yuno-bot-v2.0 は、Discord上で自然に会話する「唯乃（ゆの）」を本体として育てます。

ただし、今後は会話の自然さだけではなく、自分のサーバーで常駐させ、必要な仕事を任せられる状態へ進めます。

ゆのはコンピュータそのものではありません。
ゆのは、任された道具を使って、見に行ったり、持ってきたり、危ない時に止めたりする存在です。

ログ、設定、権限、tool、サーバー状態は、ゆのの身体ではなく、預かった仕事のための道具です。

## 残す芯

以下は削りません。

- ConversationLog を中心にする
- stream単位で会話を分ける
- Speaker と CareReader を分ける
- Speakerへ内部判定名、score、routing理由を渡さない
- MemoryMark は会話についた印として扱う
- pending / active / hidden の扱いを残す
- 小さな女の子のかたちを、ゆのの最低限の存在条件として残す
- 返答を管理説明にしすぎない
- 与えられていないものを見たふりしない

## 畳むもの

InterestTerm は、独立した管理対象としては強すぎます。

今後は、以下のように寄せます。

- AttentionItem: まだ閉じていない話題、問い、気にしているもの
- Cue / Term: Attentionに反応するための語

つまり、独立した三本柱としての

```text
MemoryMark
AttentionItem
InterestTerm
```

ではなく、次の形を目指します。

```text
MemoryMark
AttentionItem
  └ cue_terms
```

InterestTermをすぐ削除する必要はありません。
ただし、UI上では独立した主役にせず、将来的には AttentionCue へ移します。

## 追加する層

CareReaderにtool操作を混ぜません。

追加するなら、別に ToolReader / ActionPlanner を置きます。

- CareReader: 記憶、Attention、Cueを見る
- ToolReader / ActionPlanner: 自然文をtool操作の計画へ変換する
- ToolExecutor: 許可されたtoolだけを実行する
- Speaker: 結果を受けて、ゆのとして一通だけ返す

自然文操作の流れは以下とします。

```text
User message
→ ToolReader / ActionPlanner
→ PermissionService
→ RiskCheck
→ ToolExecutor
→ Speaker
```

AIに任意shellを渡しません。

禁止する形:

- run_shell(command)
- 自由なファイル読み取り
- 権限判定をLLMに任せる
- tool内部JSONをそのまま発話に出す
- ログ全量をモデルへ投げる

許可する形:

- read_status()
- read_journal(unit, since, until, limit)
- read_bot_log(since, until, level, limit)
- read_allowed_log(source, filter, limit)
- get_service_status(name)
- backup_database()
- restart_allowed_service(name)

## 権限

操作内容はユーザーの権限に沿わせます。

ただし、権限判定はAIではなくコードで行います。

- owner
- guild_admin
- user

Discord上の権限と、サーバーOS上の権限は分けます。

Discord管理者ができること:

- listening設定
- channel単位の設定
- サーバー内の表示・管理系操作

ownerだけができること:

- bot再起動
- DB backup / restore
- systemd log
- OS側service状態
- 危険操作

危険操作は、権限があっても確認を挟みます。

## scope

最初から全scopeを同格にしません。

内部は stream 中心を維持します。

最初に扱うscope:

- global
- server
- channel
- stream

user scope は後回しにします。

## コマンド入口

slash commandを機能ごとに増やしすぎません。

表の入口は以下に寄せます。

- /status
- /settings
- /memories
- /tools

既存の `/memory` `/attention` `/interest` `/listening` は、当面はlegacyまたはdebug入口として残してよいです。

対応:

- /status: 現在の稼働状態、listening、sleep、DB、OpenAI、tool状態を見る
- /settings: global / server / channel の設定を見る・変える
- /memories: MemoryMark、Attention、Cueを扱う
- /tools: ログ、health、backup、service状態など、任された仕事を扱う

## 実装順

### 1回目: 設計基盤

- scope model
- PermissionService
- ToolDefinition
- ToolPlan
- ToolResult
- ToolRegistry
- InterestをAttention Cueへ寄せる方針をdocsへ反映
- 既存会話挙動は変えない

### 2回目: 入口整理

- /status
- /settings
- /memories
- /tools
- 既存コマンドはlegacy/debug扱い
- 表示層とService層を分ける

### 3回目: 自然文tool実行 read-only

- 自然文からToolPlanを作る
- health
- status
- service status
- 権限はコードで判定
- Speakerへは結果だけ渡す

### 4回目: ログ取得と要約

- allowlist log source
- journalctl
- bot log
- since / until / limit / grep
- secret mask
- ログ要約

### 5回目: 常駐運用

- sleep / wake
- backup / export / forget
- health拡張
- systemd docs
- restartは確認必須
- error確認

## 整理しながら進めるためのルール

以前の方針転換で不要なコードが増え続けた反省から、以下を守ります。

### 追加より先に置き場所を決める

新しい機能を足す前に、それがどの層に属するかを決めます。

- Conversation / Pipeline
- CareReader
- Speaker
- Memory / Attention
- Tool
- Permission
- Discord UI
- Infra

どこにも自然に入らない場合は、まだ実装しません。

### 既存概念と重なるものを増やさない

新しい名前を足す前に、既存の概念で表せないか確認します。

特に注意するもの:

- Attention と Cue
- Memory と設定
- Tool と command
- scope と permission
- CareReader と ToolReader

似た概念がある場合は、新規追加ではなく統合または移動を優先します。

### 表の入口を増やさない

slash commandを増やす前に、既存の入口へ入れられるか確認します。

基本入口は以下に寄せます。

- /status
- /settings
- /memories
- /tools

一時的にdebug commandを追加する場合は、後で消す前提を明記します。

### 実装ごとに削除候補を書く

各実装回では、追加したものだけでなく、次に削る候補も書きます。

PRや作業メモには以下を含めます。

- 追加したもの
- 既存から置き換えたもの
- まだ残っているlegacy/debug
- 次に削る候補

### 使われない抽象を残さない

将来使うかもしれないだけの抽象は残しません。

許される抽象は、次のどれかに限ります。

- すでに1つ以上の実装がある
- 次の実装回で確実に使う
- 既存の重複を減らしている

### Toolは増やせるが、任意実行はしない

ToolRegistryは拡張可能にします。
ただし、万能化しません。

禁止:

- 任意shell
- 任意ファイル読み取り
- LLMによる権限判定
- allowlistなしの外部操作

### 会話の芯を壊さない

便利機能を足すときも、Speakerに内部構造を渡しません。

Tool結果をSpeakerへ渡す場合も、渡すのは表示可能な要約だけにします。

渡さないもの:

- ToolPlanの内部理由
- raw JSON
- permission判定の内部詳細
- risk score
- secretを含む可能性のあるraw log

## 判断基準

迷ったら、以下を優先します。

- ゆのの発話を管理説明にしない
- 内部構造をSpeakerへ漏らさない
- 自然文操作でも同じPermissionServiceを通す
- Toolは増やせるようにするが、任意実行はしない
- 便利さのためにConversationLog中心を崩さない
- ゆのを万能管理者にしない
- ゆのが任された道具を使う、という位置に置く
- 追加したら、同時に畳めるものがないか見る
