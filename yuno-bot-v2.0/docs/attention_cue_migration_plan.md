# Attention cue migration plan

この文書は、独立している `InterestTerm` を、Attentionを見つけるためのcue termへ段階的に寄せる計画です。

この変更の目的は名前の置換ではありません。cueを新しい記憶庫にせず、Attentionの発見を助ける従属的な索引へ戻すことです。移行中もConversationLog、MemoryMark、Attentionを本体として扱います。

## 1. Current state

現在の `InterestTerm` はstream単位の独立した永続オブジェクトです。

- `interest_terms` tableに保存され、`int_...` ID、term、weight、active / sleeping / hidden、sourceを持つ。
- `InterestService` / `InterestRepository` が作成、更新、一覧、状態変更を担う。
- CareReaderは `interest_terms` を読み、`interest_updates` を返す。`CareService` がその更新を保存する。
- listening通常発言では、active termとの一致から求めたsalienceがCareReaderを呼ぶ入口の一つになる。
- `ReferenceSelector` は一致したtermをcueとして使い、MemoryMarkまたはAttentionの選択を補助する。
- term本文、ID、weight、salienceはSpeakerへ渡されない。
- `/interest list|add|hide|sleep|wake` と `CoreAdminService` に独立した管理面がある。
- `ContextBuilder` は `InterestService` を受け取るが、現在のcontext組み立てでは直接使用していない。

したがって、現状はすでに「反応の手掛かり」として働く部分を持つ一方、保存、service、UIではAttentionと並列の主役になっています。

## 2. Problem with independent InterestTerm

独立したInterestTermには、何のAttentionを見つけるための語なのかという関係がありません。同じstreamにあるだけなので、termの寿命とAttentionのopen / closed / hiddenが別々に動きます。

このまま独立管理を強めると、次のずれが起きます。

- closedまたはhiddenのAttentionと無関係にtermだけactiveで残る。
- 手動追加されたtermが、記憶や人格状態のように見える。
- `/interest` がAttentionと同格の管理対象に見える。
- weightを返信確率や重要度そのものとして扱いやすくなる。
- Cue用に別tableや別memoryを追加すると、同じ役割の概念がさらに並立する。

問題はtermが存在することではなく、termが何を支えるかを持たず、独立したライフサイクルを持っていることです。

## 3. Target model

目標は次の関係です。

```text
ConversationLog
├─ MemoryMark
└─ AttentionItem
   └─ cue_terms
```

cue termは、近い発言が来た時にAttentionへ到達しやすくするための索引です。

- cueは独立したmemoryではない。
- cue単体をSpeakerのreferenceにしない。
- cueの一致は返信決定や返信確率ではない。
- cueはAttentionの可視性と寿命に従う。closed / hiddenのAttentionを通常経路で再活性化しない。
- scopeは少なくとも現在と同じstream内に閉じ、移行によって広げない。
- term、weight、内部ID、match scoreをSpeakerへ渡さない。

一つのcueを一つのAttentionだけが所有するか、複数のAttentionで共有できるかはまだ決めません。現在のdataだけから安全に推測できないため、schema設計前に実データの重なりと必要な操作を確認します。この未決定を隠すために先にtableを作ってはいけません。

## 4. Compatibility phase

最初の実装段階では、保存形式と外部契約を変えません。

- `interest_terms` table、`InterestTerm`、`InterestService`、`InterestRepository` を残す。
- public ID、status、source、weight、stream分離をそのまま読む。
- CareReaderの `interest_terms` / `interest_updates` JSONを変えない。
- `interest_salience`、listening pre-filter、`ReferenceSelector` の結果を変えない。
- `/interest` の全subcommandを互換入口として残す。
- existing dataをrename、backfill、deleteしない。

この段階で変えてよいのは説明上の位置づけだけです。新しい機能や文書では「独立した関心」ではなく「Attentionを見つけるためのlegacy cue source」と呼びます。ただし、runtime classやJSON fieldを部分的にrenameして二重語彙を作ることはしません。

## 5. UI / command phase

最初に弱めるべきなのは、独立した主役としての表示です。

1. 将来の `/memories` ではMemoryMark、Attention、Attentionに属するcueの順に表示し、cueだけを最上位一覧にしない。
2. `/interest` はlegacy/debug入口であることをdocsと管理表示で明示する。
3. 新しい独立cue commandは追加しない。
4. Attentionとの所有関係を表せない間は、既存termを無理に特定Attentionの下へ表示しない。必要なら「未割当のlegacy cue」として区別する。
5. `/interest` の削除やalias化は、同じ操作が新しい入口で可能になり、移行確認が終わった後の別taskにする。

単なる表示名変更でownershipができたことにしません。UI上の入れ子は、serviceとdataが関係を保証できる段階まで待ちます。

## 6. Service boundary phase

次の実装taskでは、storageを変える前に利用側の境界を狭めます。

- CareServiceとReferenceSelectorが必要とする操作を列挙する。最低限は、stream内のactive cue取得、正規化、一致評価、CareReader由来更新の保存です。
- その操作をAttention側から使えるcue service境界へ集める。
- 最初の実装は既存 `interest_terms` をbacking storeとするcompatibility adapterにし、新しい保存先を増やさない。
- adapterが返すcueはlegacy recordのviewであり、第二の永続modelではない。
- `ContextBuilder` の未使用 `InterestService` dependencyは、call site確認後に別taskで削除候補とする。
- `CoreAdminService` がrepositoryへ直接触る経路は、新しいUIへ移す時にservice境界へ寄せる。今回の移行理由だけで広い管理service rewriteはしない。

この段階の目的は、呼び出し側が `InterestTerm` の保存詳細を知らなくても現在と同じ挙動を得られることです。class名の一括renameではありません。

## 7. Later migration phase

schemaとdataの変更は、service境界とownership判断が固まった後の明示的なmigration taskで行います。

1. one-to-manyかmany-to-manyかを決め、Attentionとの関係、status継承、削除・復元規則を書く。
2. 追加schema、既存data件数、未割当件数、重複、rollback方法を先に文書化する。
3. 既存termをdry-runで分類する。語の一致だけでAttentionへ自動所属させない。
4. 新旧を一定期間dual-readし、同じcueを二重に数えない。
5. write先を切り替える場合も、CareReader contractとlistening判定の変更を同じdeployに混ぜない。
6. stream分離、active/sleeping/hidden互換、reference選択結果を比較する。
7. 読み取りとrollback確認後に旧writeを止める。
8. `/interest`、`InterestService`、`InterestRepository`、`InterestTerm`、最後に `interest_terms` tableの順で削除候補を評価する。

table dropは最後の独立taskです。旧dataを読み戻す必要がある間は削除しません。

## 8. Things explicitly not done in this task

この計画taskでは、以下を行いません。

- InterestTerm、`/interest`、table、indexの削除またはrename
- Attention用の新しいcue tableや並列memoryの追加
- data migration、backfill、ownership推測
- CareReader prompt、request、result、`interest_updates` formatの変更
- Pipeline、listening pre-filter、salience、routingの変更
- ContextBuilder、ReferenceSelector、Speaker referenceの変更
- command表示や操作の変更
- status、weight、sourceの意味変更

## 9. Tests / verification for future implementation

各段階で、追加した構造だけでなく現在の挙動が残ることを確認します。

- active cue一致時だけ、現在と同じ条件でlistening発言がCareReader候補になる。
- sleeping / hidden cueは通常一致に使われない。
- cue一致だけでは返信せず、CareReaderの `wants_to_speak` と `should_speak` が必要なままである。
- MemoryMark / Attentionのreference選択件数とsame-stream制約が変わらない。
- cue本文、ID、weight、salience、ownership情報がSpeakerへ渡らない。
- closed / hidden Attentionに属するcueを通常経路で使わない。
- compatibility adapterと旧serviceで、同じfixtureから同じactive termsとsalienceを得る。
- dual-read期間に重複計上しない。
- migration dry-runの総数が、移行予定、未割当、重複、保留の合計と一致する。
- migrationを適用しなくても旧versionが同じDBを読めるか、読めない場合はrollback手順を実証する。
- legacy `/interest` を残す期間は、既存subcommandとephemeral表示の互換testを維持する。

最初の安全な実装taskは、DBやpromptを変えず、既存 `interest_terms` を読むcue service境界とcompatibility testsだけを追加することです。
