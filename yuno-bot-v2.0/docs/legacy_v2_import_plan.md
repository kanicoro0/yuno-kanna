# Legacy v2 Notebook import requirements

この文書は次段階の実装契約です。現在のConversationLog縦切りにはimport処理を含めません。

## 入力と変換

- importは起動時に行わず、明示的なCLIスクリプトまたは管理コマンドから実行する。
- 旧 `notebook.json` のnoteをv2.0 annotationへ変換する。
- 最初は本文、scope、tags、state、旧note IDを優先し、`notebook_changelog.json` は完全再現しない。
- source messageが存在しないため、source kindを `legacy_v2_notebook` とする。ConversationLogへ架空のmessageを作らない。
- legacy metadataとして旧note ID、import日時、import batch IDを保持する。
- legacy sourceはimport専用で、新規annotationの通常経路には使用しない。

## Scopeと優先順位

- 旧scopeは広げない。変換不能なscopeは自動推測せず `legacy_unscoped` として保留する。
- legacy annotationはConversationLog由来annotationよりprovenance strengthを低くする。
- 内容が矛盾または曖昧な場合は、新しいConversationLog由来annotationを優先する。
- stateがinactive/deletedの旧noteは既定で取り込まず、dry-runの除外件数へ計上する。

## 安全性

- import keyをsource kindと旧note IDの組にして一意制約を設け、再実行を冪等にする。
- dry-runはDBを変更しない。
- dry-run結果には、取込予定、除外、既存、内容衝突、scope不明、変換不能の件数と対象IDを含める。
- previewは `data/import_preview_<batch-id>.json` へUTF-8で出力できるようにする。
- apply時も同じ判定結果を使い、batch単位のtransactionで全件成功または全件rollbackとする。

## 検索の将来要件

Annotation／older log検索の導入時は、FTS5 trigram、通常FTS5、期間・件数制限付きLIKEの順に利用可能な方式へfallbackする。MindState summaryが必要になっても、ConversationLogを置き換える本体ではなく再生成可能な派生cacheとして扱う。
