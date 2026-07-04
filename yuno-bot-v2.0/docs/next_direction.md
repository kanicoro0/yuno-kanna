# yuno-bot-v2.0 次の方針

この文書は、yuno-bot-v2.0 を次にどう変化させるかを決めるための方針です。

既存の `yuno_design_principles.md` は、ゆのが会話の中でどう存在するかを扱います。
この文書では、その芯を残したまま、自分のサーバーで常駐させ、必要な仕事を任せられる状態へ進めるための判断基準を書きます。

実装をどう進めるか、作業ごとに何を整理するかは [`implementation_practice.md`](implementation_practice.md) に分けます。

## 目的

yuno-bot-v2.0 は、Discord上で自然に会話する「唯乃（ゆの）」を本体として育てます。

ただし、今後は会話の自然さだけではなく、自分のサーバーで常駐させ、必要な仕事を任せられる状態へ進めます。

ゆのはコンピュータそのものではありません。
ゆのは、任された道具を使って、見に行ったり、持ってきたり、危ない時に止めたりする存在です。

ログ、設定、権限、tool、サーバー状態は、ゆのの身体ではなく、預かった仕事のための道具です。

## 旧プランとの差分

以前の方針は、公開前提の安全化や、既存の管理コマンド群をそのまま整える方向に寄っていました。

新しい方針では、公開botではなく、自分のサーバーに住ませて運用することを前提にします。
そのため、一般公開向けの説明や広い利用者対応よりも、以下を優先します。

- owner中心の運用
- 自分のサーバーでの常駐
- ログ取得と要約
- health確認
- backup / export / forget
- systemdやservice状態確認
- 自然文からのread-only tool実行
- 機能追加と同時に整理すること

旧プランでは、`MemoryMark`、`AttentionItem`、`InterestTerm` を並列の管理対象として扱う前提が残っていました。
新しい方針では、`InterestTerm` を独立した主役にせず、`AttentionItem` に反応するための Cue / Term へ寄せます。

旧プランでは、`/memory`、`/attention`、`/interest`、`/listening` のように機能別コマンドを増やして管理していました。
新しい方針では、表の入口を以下に寄せます。

- /status
- /settings
- /memories
- /tools

旧プランでは、CareReaderに「読む」「覚える」「割り込む」を多く背負わせていました。
新しい方針では、CareReaderにtool操作を混ぜず、ToolReader / ActionPlanner を別層に置きます。

旧プランでは、実装の終着点を決めることに寄りすぎると、途中の方針転換で不要コードが残り続ける危険がありました。
新しい方針では、各実装回で「追加したもの」だけでなく「置き換えたもの」「残っているlegacy/debug」「次に削る候補」を必ず扱います。

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
