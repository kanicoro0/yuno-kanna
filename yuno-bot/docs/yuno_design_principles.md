# yuno v2.0 の設計原則

この文書は、現在の `yuno-bot` runtime が何を守るために組まれているかを説明します。
実装を進める時は、まずここを基準にしてから [`next_direction.md`](next_direction.md) と [`implementation_practice.md`](implementation_practice.md) を読んでください。

## いまの中心

現行 runtime の中心は次の 6 つです。

- `ConversationLog`: 同じ stream の会話を保存する土台
- `CareMark`: 会話につく印。独立した記憶庫ではない
- `ReadCue`: CareMark へ戻るための弱い索引
- `CareReader`: 静かに読んで、印候補や補助判断を返す層
- `Speaker`: 最後の一通を書く層
- `PermissionService` / command surface: 操作権限と管理入口

旧 `yuno/interest`、`yuno/attention`、`yuno/memory` runtime modules は削除済みです。
それらの名前は、履歴文書や移行記録の中にだけ残ります。

## ConversationLog と印

ゆのは、相手の言葉をすぐ消費して終わる対象ではなく、同じ stream の流れの中で預かります。
そのため、会話の本体は常に `ConversationLog` です。

`CareMark` はその会話にあとから付く印です。

- memory-like な印: `draft / active / hidden`
- attention-like な印: `open / closed / hidden`

CareMark は独立した記憶庫ではありません。
同じ stream の会話にぶら下がる薄い印として扱います。

`/memories` は CareMark 全体の名前ではなく、覚えていることの表面です。
`/memories list` の初期表示では active な memory-like CareMark だけを見せます。
open な attention-like CareMark は同じ印の一種ですが、まだ閉じていない話題やあとで見るものなので、覚えていることの棚とは分けて `/memories open` で扱います。

覚えていることは、将来的に固定で残すものと最近だけ持つものに分けます。

- fixed remembered: 明示的な呼び名、強い好み、設定、相手が覚えてほしいと言ったもの。明示的な削除や訂正がない限り、勝手に流さない
- recent remembered: しばらく使えるが、件数制限や時間経過で通常参照から外してよいもの。元の ConversationLog と CareMark は根拠として残す

現在の最小表示では、active な memory-like CareMark を「固定で覚えていること」、draft な memory-like CareMark を「固定する前の候補」に出します。
draft な memory-like CareMark は、返答時の Speaker 参照には使われません。返答で参照されるのは active な memory-like CareMark と open な attention-like CareMark だけです。
`/memories list` では draft な memory-like CareMark を `固定にする` 操作で active に上げられます。
この分割はまず表示と整理方針として扱います。
DB schema、CareReader contract、Speaker reference selection を同時に変えません。

## ReadCue

`ReadCue` は CareMark を見つけ直すための弱い索引です。

ReadCue を独立した主役にしません。
ReadCue は次のようなものではありません。

- 独立した記憶
- 独立した関心オブジェクト
- 返信確率そのもの
- Speaker に直接渡す reference 本文

ReadCue は CareMark を選ぶ補助です。
term、weight、内部 ID、match の詳細は Speaker へ渡しません。

## CareReader と Speaker

CareReader と Speaker は分けます。

### CareReader

CareReader は、返答本文や口調指示を書く役ではありません。
CareReader は同じ stream を静かに読み、次のような構造化結果を返します。

- CareMark candidate
- ReadCue update
- touch / include の候補
- 明示的に頼まれた時だけの状態変更候補（close / forget / promote）
- 必要なら Speaker への短い補助メモ（内部では `speaker_note`）
- `wants_to_speak` / `should_speak` のような会話上の補助判断

CareReader がしてはいけないこと:

- 返答本文を書く
- Speaker persona の代わりになる
- tool 操作を決める
- shell / file / service 実行を担う
- raw log や内部理由をそのまま Speaker に渡す

`speaker_note` は短い返答補助として内部で持ってよいですが、Speaker へ渡す時に `CareReader` や field 名を見せません。
`reply_reason` も判断記録として保持してよいですが、Speaker へ渡す時は raw 値のままではなく短い定型補助へ整えます。

### Speaker

Speaker は最後の一通を書く役です。
Speaker は同じ stream の recent 会話と、必要最小限の reference だけを受けて返答します。

Speaker に渡してよいもの:

- 同じ stream の recent 会話
- 選ばれた CareMark の本文
- 安全に整えられた最小限の補助情報
- 必要な時だけ、短い返答補助メモ

Speaker に渡してはいけないもの:

- ReadCue の本文や weight
- routing 名
- `reply_mode`
- `wants_to_speak` や `should_speak` の内部理由
- raw の `reply_reason` 値や field 名
- 内部 score
- raw JSON
- raw log / secret / traceback

## 現行の会話フロー

### directed 会話

`dm`、`mention`、`reply_to_yuno`、強い呼び名などの directed 会話では、返信前に CareReader が使われることがあります。
ここでは CareReader が、返信可否判断の補助や Speaker へ含める印の補助を行います。

ただし、CareReader は本文を書きません。
最終的な返答は Speaker が一通だけ返します。

### listening 通常発言

listening 対象の通常発言は、まず保存します。
そのうえで、低信号なら保存のみで終わる場合があります。

CareReader を先に読むのは次のような時だけです。

- 明示的な記憶語やあとで見る語がある
- 強い ReadCue 一致がある
- open attention と強く重なる
- そのほか安い前処理で十分な信号がある

低信号の通常発言では、保存のみで Speaker も CareReader も走らせないことがあります。

## 自然言語による印の状態変更

会話の中の明示的な頼みで、既にある印の状態を変えられます。

- 「もう閉じていい」: open な attention-like CareMark を closed にする
- 「忘れて」「もう覚えなくていい」: 対象の CareMark を hidden にする
- 「ちゃんと覚えて」「固定して」: draft な memory-like CareMark を active にする
- 呼び方や記憶の訂正: 古い印を hidden にし、新しい内容を candidate として置く

守る線は次の通りです。

- 状態変更は CareReader の提案だけでは適用しません。forget / promote は、いまの発言自体に操作の言葉が含まれる時だけ適用します
- 推測だけで忘れません。迷う時は何もしません
- センシティブな draft は自然言語では active に上げません
- 1 ターンあたりの適用件数に上限があります
- 実際に状態が変わった時だけ、短い定型メモとして Speaker に結果が渡ります
- 操作を頼まれたのに状態が変わらなかった時は、「変えたと言わない」旨のメモが渡ります
- Speaker は、知らされていないのに覚えた・忘れた・閉じたと言い切りません

## 返信前に待つもの / 待たないもの

現行 runtime では、`auto maintenance` を返信前の critical path に置きません。
CareMark 作成や touch のあとで必要なら走りますが、返信前には待たず、背景で進みます。

auto maintenance は提案を作るだけではありません。
close_attention に限り、確認なしで 1 回あたり最大 3 件まで自動で適用します。
そのターンで作成・touch された印は自動 close の対象から守られます。
close_attention 以外の提案は、`/memories tidy` でも自動でも適用されず、表示のみです。

この設計で守りたいことは次の通りです。

- 会話の返答を maintenance より優先する
- maintenance 失敗で返信自体を落とさない
- 印の整理を reply quality と直結させすぎない

## command surface

現行の管理入口は小さく保ちます。
通常の会話にボタンを常設しません。

現在の中心 command:

- `/status`
- `/listening`
- `/memories list`: 初期表示では active memory-like CareMark を見る
- `/memories open`: open attention-like CareMark を見る
- `/guide`
- selected message action panel

旧 `/memory` `/attention` `/interest` は現行 runtime では使いません。

## tool と会話の境界

tool 系の自然文解釈は CareReader ではなく、ToolReader / ActionPlanner 側で扱います。

理由は単純で、CareReader に

- 覚える
- 割り込む
- tool を選ぶ
- 権限を判断する

を同時に背負わせないためです。

CareReader は会話の観察に専念し、Speaker は返答に専念し、tool 系は別境界で扱います。

## 変えない線

次のものは、軽い整理でまとめて変えません。

- Speaker persona / prompt
- CareReader prompt contract
- listening の意味
- 同じ stream 制約
- Speaker へ内部構造を渡さない線

大きい変更をするときは、before / after と何を守るかを先に書きます。
