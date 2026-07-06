# Legacy v2 Notebook import requirements

この文書は、旧v2 Notebookをyuno-bot-v2.0へ取り込む場合の実装契約です。
現在のConversationLog中心設計には、import処理を自動では含めません。

旧記憶は破棄しません。
ただし、旧構造をそのまま復活させたり、新しい通常経路へ混ぜたりしません。

## 変換先

旧 `notebook.json` のnoteは、内容に応じて次のどちらかへ変換します。

- MemoryMark
- AttentionItem

旧noteを置く場所が曖昧な場合は、自動推測せず保留します。

InterestTermを新しい独立記憶として増やしません。
必要な語は、将来の AttentionCue / cue_terms へ寄せます。

## 入力と変換

- importは起動時に行わず、明示的なCLIスクリプトまたは管理コマンドから実行する。
- 最初は本文、scope、tags、state、旧note IDを優先し、`notebook_changelog.json` は完全再現しない。
- source messageが存在しないため、source kindを `legacy_v2_notebook` とする。ConversationLogへ架空のmessageを作らない。
- legacy metadataとして旧note ID、import日時、import batch IDを保持する。
- legacy sourceはimport専用で、新規MemoryMark / AttentionItemの通常経路には使用しない。
- 変換不能なnoteは捨てず、dry-run結果で理由付き保留にする。

## Scopeと優先順位

- 旧scopeは広げない。
- 変換不能なscopeは自動推測せず `legacy_unscoped` として保留する。
- legacy由来のMemoryMark / AttentionItemは、ConversationLog由来のものよりprovenance strengthを低くする。
- 内容が矛盾または曖昧な場合は、新しいConversationLog由来のMemoryMark / AttentionItemを優先する。
- stateがinactive/deletedの旧noteは既定で取り込まず、dry-runの除外件数へ計上する。

## 安全性

- import keyをsource kindと旧note IDの組にして一意制約を設け、再実行を冪等にする。
- dry-runはDBを変更しない。
- dry-run結果には、取込予定、除外、既存、内容衝突、scope不明、変換不能、保留の件数と対象IDを含める。
- previewは `data/import_preview_<batch-id>.json` へUTF-8で出力できるようにする。
- apply時も同じ判定結果を使い、batch単位のtransactionで全件成功または全件rollbackとする。
- import処理は通常のCareReader経路を通さない。
- import結果をSpeakerへ自動で渡さない。active化または参照対象化には明示操作を挟む。

## 整理方針

旧v2 Notebook importのためだけに、長期的な本体概念を増やしません。

禁止:

- Notebook専用tableを通常経路として復活させる
- annotationという新しい中間概念を本体へ追加する
- legacy noteをConversationLogの架空messageとして作る
- InterestTermを独立した新規記憶として増やす
- import都合でscopeを広げる

許可:

- import専用の一時変換コード
- dry-run preview
- legacy metadata
- 明示的なrollback可能transaction
- MemoryMark / AttentionItemへの限定変換

## 検索の将来要件

older log検索の導入時は、FTS5 trigram、通常FTS5、期間・件数制限付きLIKEの順に利用可能な方式へfallbackする。

MindState summaryが必要になっても、ConversationLogを置き換える本体ではなく、再生成可能な派生cacheとして扱う。
