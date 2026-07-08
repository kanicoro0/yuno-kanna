# yuno-bot v2.0 の次の方向

この文書は、現在の runtime を前提に、これからどこを整理していくかを示します。
挙動そのものの規範は [`yuno_design_principles.md`](yuno_design_principles.md)、作業単位の切り方は [`implementation_practice.md`](implementation_practice.md) を見てください。

## 現在地

現行 runtime は次の状態にあります。

- 会話の本体は `ConversationLog`
- 印は `CareMark`
- 索引は `ReadCue`
- 会話観察は `CareReader`
- 最終返答は `Speaker`
- 管理入口は `/status` `/listening` `/memories` `/guide`
- selected message panel と小さな Discord UI は補助として使う

旧 `yuno/interest`、`yuno/attention`、`yuno/memory` runtime modules は削除済みです。
旧名称は、履歴文書や移行記録の説明としてのみ残ります。

## いま明確にしたいこと

### CareMark

CareMark は独立した記憶庫ではありません。
ConversationLog につく印です。

- memory-like: `draft / active / hidden`
- attention-like: `open / closed / hidden`

`/memories` は CareMark 全体の管理名ではなく、覚えていることの表面として扱います。
`/memories list` の初期表示は active memory-like CareMark だけに寄せ、open attention-like CareMark は `/memories open` で見る対象にします。

### ReadCue

ReadCue は CareMark に戻るための弱い索引です。

- 独立した関心ではない
- 返信確率そのものではない
- Speaker に直接見せる本文ではない

### CareReader

CareReader は本文や口調を書く役ではありません。
CareMark candidate、ReadCue update、会話上の補助判断を返すだけにとどめます。

### Speaker

Speaker は最終的な一通を書く役です。
内部理由や score を受け取らず、same-stream の会話と少数の CareMark 本文だけを読んで返します。

## directed 会話と listening 会話

### directed 会話

現行 runtime では、directed 会話で返信前に CareReader が使われることがあります。
これは返信可否判断の補助や Speaker へ含める印の補助のためです。

ただし、CareReader が本文を書くわけではありません。
最終返答は常に Speaker が一通だけ返します。

### listening 通常発言

listening 対象の通常発言は、低信号なら保存のみで終わることがあります。
安い前処理で十分な信号がある時だけ CareReader を先に走らせ、`wants_to_speak` と `should_speak` の両方が立つ時だけ控えめに返します。

## latency と maintenance

現行 runtime では、auto maintenance は返信前の critical path にいません。
必要なら背景で進み、maintenance の失敗で返信自体は失敗させません。

今後も、この線は保ちます。

- reply latency を maintenance で悪化させない
- maintenance 失敗を reply failure にしない
- 会話品質と整理処理を必要以上に密結合させない

## command surface

現在の管理入口は増やしすぎません。

- `/status`: いまの場の状態確認
- `/listening`: listening 対象の管理
- `/memories list`: 初期表示では覚えていることだけを見る
- `/memories open`: まだ開いているものを見る
- `/guide`: いま使える入口の案内

旧 `/memory` `/attention` `/interest` は current-facing surface としては使いません。

open attention-like CareMark は `/memories` から完全には消しません。
ただし `/memories list` の初期表示からは外し、`/memories open` に分けます。
これは「覚えていること」と「まだ開いているもの」を同じ棚に混ぜないためです。

## これからの整理方向

### 1. 会話境界を保ったまま整理する

- CareReader と Speaker の境界を崩さない
- Speaker へ内部判定名、score、routing 理由を渡さない
- ReadCue を独立 UI にしない

### 2. tool 系は別層で進める

- CareReader に tool 操作を混ぜない
- ToolReader / ActionPlanner / executor の境界を保つ
- read-only と write 系の危険度を分ける

### 3. command と UI は小さく保つ

- slash command は入口と状態確認に寄せる
- button panel は、すでに開いた対象の継続操作に限定する
- ordinary reply はボタンだらけにしない

### 4. historical docs は履歴として残す

移行記録や queue 文書は、履歴として意味がある限り残します。
ただし current runtime の説明として誤読される箇所は、注記を足すか current-facing docs 側で明確に打ち消します。

## いまこの文書で提案だけにとどめるもの

この文書で方向だけ示し、実装変更は別 PR に分けるもの:

- directed 会話の pre CareReader 条件の見直し
- より広い tool surface
- import / migration の再有効化
- log / service read の拡張

実装を触る時は、何を守るかを先に書いてから分離して進めます。
