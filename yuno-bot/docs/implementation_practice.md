# yuno-bot-v2.0 実装の進め方

この文書は、現行 runtime を前提に、PR や小さな実装タスクをどう切るかを整理します。

何を作るかは [`next_direction.md`](next_direction.md)、何を守るかは [`yuno_design_principles.md`](yuno_design_principles.md) を見てください。

## 現在の前提

現行 runtime の中心は次の通りです。

- 会話の本体は `ConversationLog`
- 印は `CareMark`
- 索引は `ReadCue`
- 観察は `CareReader`
- 最終返答は `Speaker`
- 管理入口は `/status` `/listening` `/memories` `/guide`
- auto maintenance は返信前に待たない

旧 `yuno/interest`、`yuno/attention`、`yuno/memory` runtime modules は削除済みです。
以後の実装タスクでは、それらを現行前提として扱いません。

## 変更を分ける単位

次のものは、できるだけ同じ PR に混ぜません。

- CareReader 実装変更
- Speaker 実装変更
- command surface 変更
- tool 境界変更
- schema 変更
- listening 判定変更
- maintenance ポリシー変更

理由は、何が reply quality を変えたかを見失わないためです。

## 現行 runtime で特に敏感な境界

### CareReader と Speaker

- CareReader は本文を書かない
- Speaker は最終の一通だけを書く
- ReadCue の詳細や raw の内部理由を Speaker に渡さない
- `speaker_note` は残してよいが、Speaker へ渡す時に `CareReader` や field 名を見せない
- `reply_reason` を Speaker へ渡すなら raw 値ではなく短い定型補助にする

この境界を触る変更は、小さく独立させます。

### directed と listening

- directed 会話では、返信前に CareReader が使われることがある
- listening 通常発言では、低信号なら保存のみで終わることがある
- pre CareReader 条件の変更は reply behavior に触れる可能性が高い

そのため、directed の pre CareReader 条件見直しは docs 更新や command 整理と混ぜません。

### maintenance

- auto maintenance は返信前の critical path に置かない
- maintenance failure で reply を失敗させない

maintenance の変更は、会話の返答そのものと分離して進めます。

## よい PR の形

よい PR は、次のどれか 1 つに主題を絞っています。

- runtime behavior の小さな改善
- command / UI の小さな整理
- schema / persistence の整理
- docs の current-runtime alignment
- historical record の明確化

1 本の PR でやりすぎないことの方が大事です。

## いま避けたい混ぜ方

避けたい例:

- Speaker prompt 変更と tool 実装を同時に入れる
- CareReader prompt 変更と command surface 変更を同時に入れる
- listening 判定変更と status / guide 文言変更を同時に入れる
- schema 変更と broad refactor を同時に入れる
- docs 更新に便乗して runtime 挙動まで直す

## docs 更新の扱い

current-facing docs は、現行 runtime を誤読なく説明することを優先します。

残してよいもの:

- 移行記録
- historical plan
- codex queue の履歴

ただし、現行仕様のように読めてしまう古い記述は次のどちらかにします。

- current-facing docs 側で言い直す
- historical note を明示する

## command / UI の進め方

- ordinary reply は通常ボタンを付けない
- slash command は入口と状態確認に寄せる
- button panel は、すでに開いた対象の継続操作に寄せる
- ephemeral を基本にする

## tool 系の進め方

- CareReader に tool 操作を混ぜない
- ToolReader / planner / executor を分ける
- Speaker に渡すのは安全な要約だけにする
- raw log / secret / traceback / internal score を Speaker へ渡さない

## 変更前に書くとよいこと

runtime に触る PR では、先に次を言葉にすると崩れにくくなります。

- 何を守るか
- 何を変えるか
- 何を意図的に変えないか
- before / after の critical path または data flow

## 使わないものを消す時の基準

legacy/debug の削除では、次を先に確認します。

- live import がないか
- command wiring に入っていないか
- schema 作成に使われていないか
- tests が current runtime の guard として必要か
- historical docs と current-facing docs を混同していないか

削除してよいのは、現行 runtime から切れていて、履歴として残す必要も module file としてはないものだけです。
