# Legacy v2 Notebook import requirements

> Historical note:
> この文書は、旧 v2 Notebook を現行 `yuno-bot` へ持ち込む場合の import 計画です。
> 現在の runtime はこの import を通常経路として使っていません。
> 旧 `yuno/interest` `yuno/attention` `yuno/memory` runtime modules は削除済みです。

## 目的

旧 v2 Notebook を再利用する場合でも、現行 runtime の中心を壊さないことを優先します。

守る前提:

- 会話の本体は `ConversationLog`
- 印は `CareMark`
- `ReadCue` は独立記憶として増やさない
- import は通常の会話経路や CareReader 経路に混ぜない

## 変換先

旧 note は、内容に応じて次のどちらかへ変換します。

- memory 系の `CareMark`
- attention 系の `CareMark`

独立した `InterestTerm` を新規に増やしません。
ReadCue は必要なら、変換後の CareMark に付随する弱い索引として別段階で扱います。

## import の基本方針

- import は明示実行だけで行う
- 通常の Discord command や会話経路から自動実行しない
- dry-run を先に持つ
- import で Speaker に自動返答させない
- import で CareReader を走らせない

## metadata と provenance

旧 note 由来であることは metadata と provenance で明示します。

- 旧 note ID
- import batch ID
- source kind などの legacy 印
- scope 不明なら `legacy_unscoped`

ConversationLog 由来の CareMark と矛盾した場合は、新しい会話由来のものを優先します。

## current runtime に合わせて守ること

- import 処理は reply behavior を変えない
- import は maintenance や selection の通常経路に混ぜない
- Speaker へ旧 metadata や raw import 情報を渡さない
- ReadCue を独立した主役として増やさない

## いまこの文書で決めないこと

- 実際の CLI や admin surface
- import schema の最終形
- ReadCue の backfill ルール
- 旧 data の全面 migration

これらは import を本当に再開する時に、現行 runtime の制約を見直した別 task で決めます。