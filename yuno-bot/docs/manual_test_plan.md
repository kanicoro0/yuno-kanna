# yuno-bot-v2.0 manual test plan

## 起動

1. `python main.py` で起動し、`Yuno v2.0 ready` が表示される。
2. slash commandがglobal syncされ、`/status` が利用できる。
3. `/status` のlistening対象と呼び名が `.env` と一致する。

## 会話の連続性

1. DMで2往復し、直前の話題を保って返す。
2. botを再起動し、同じDMで続きを話して文脈が残っている。
3. listening対象チャンネルで、二人の表示名と発言内容を混同しない。
4. 別チャンネルの固有の話題を尋ねても、生ログを知っているように返さない。
5. listening対象外の非mention発言がDBへ保存されない。
6. listening対象の非mention発言は保存されるが、botが割り込んで返信しない。
7. listening対象で「ゆの」「唯乃」「yuno」と呼ぶと、ユーザーmentionなしのplain送信で返す。
8. ゆのの保存済み発言へDiscord replyするとreplyで返し、人やDBにない発言へのreplyには反応しない。
9. mentionだけを送っても、内部判定の説明ではなく自然な最小発話になる。

## 障害境界

1. OpenAI設定なしでも受信・fallback返信・ログ保存が動く。
2. Discord送信に失敗した場合、受信ログは残り、存在しない返信ログは作られない。

## 自然言語 Care 操作の観察（観察フェーズ）

集計は **通常利用** と **手動試験** を分けて数える。手動試験は不足する操作種を補うために行い、
誤爆 0 の判定は通常利用分だけを基準にする。

### ログで数えるもの

`care_operations` の INFO 行を grep して集計する。1 行の意味:

- `lexical_request_hit`: 既知のゲート語彙に一致したか。**実際の意図ではない**近似。
  hit あり・提案なし・unclear なし → 読み落とし疑いとして観察票へ。
  hit なしは、それだけでは語彙の穴と**断定しない**。close はゲートを通らず、
  pending 経由の forget / promote もゲート語彙なしで適用されるため、
  hit なしの適用行には正当な経路がある。
- **語彙の穴の候補**: forget / promote で `pending=none`・`proposed` ≥1・
  `blocked=…:gate:…` の行。CareReader は操作を読み取ったが、
  ゲート語彙が追いつかなかったことを示す。観察票へ。
- `proposed` と `applied` の差: CareReader は提案したが適用されなかった件数。
- `blocked`: 操作別×理由別の却下件数（gate / target / limit / sensitive）。
- `pending_outcome`: applied / re_asked / no_action。no_action は
  「答えが無関係だった」とは断定しない。何も起きなかった事実だけを意味する。
- `route` と `spoke`: `route=listening_only` かつ applied ありかつ `spoke=false` の行が
  無言適用。妥当だったかを観察票で判断する。

### 手動試験の項目

1. mention で「これ覚えて」→ 印が付き、覚えた旨の短い返答。
2. mention で「さっきのは忘れて」（対象が一意）→ hidden 化と手放した旨の返答。
3. mention で「あれは忘れて」（対象が曖昧）→ 状態不変で聞き返し。
4. 聞き返しの直後に対象を答える → 操作が完了する（聞き返し往復）。
5. 聞き返しの直後に別の話題を話す → 何も変わらない。
6. 「その呼び方はやめて、◯◯って呼んで」→ 旧印 hidden + 新印作成が同一ターンで起きる。
   ログでは forgotten ≥1 かつ created ≥1 の行を **correct_candidate** として数える。
   同一の訂正依頼によるものかはログでは確定できないので、訂正（correct）と
   確定するのは観察票での判断。片方だけの場合も観察票で判断。
7. listening チャンネルの非 mention で「もう閉じていい」→ 無言で閉じ、リアクションが 1 つ付く。
8. `/memories recent` で上記の変化が並び、「戻す」で復帰できる。
9. 「作業中は無音より雨音がある方が好きかもしれない」のような未確定の好みを話す
   → draft memory が `/memories list` の「固定する前の候補」に出る。続けて対象を示し
   「さっきの雨音の話、ちゃんと覚えて」と頼む → 同じ印が `promoted=1` で固定欄へ移り、
   2ターン目に同内容の別印を新規作成しない。発話も固定完了の実状態と一致する。

### 観察票

具体的な失敗例は `care_observation_sheet.md` の書式で匿名化して記録する。
ログは頻度、観察票は事例。両方そろって観察フェーズの完了条件になる。
