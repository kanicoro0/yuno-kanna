# 旧実装との関係

現在はConversationLogの縦切りだけを実装しています。旧v1/v2との機能互換を完成条件にはしていません。

後続段階では、旧v2 Notebookを破棄せず、明示的なdry-run付きimportから取り込みます。起動時の自動移行、旧changelogの完全再現、旧scopeの自動拡大は行いません。
