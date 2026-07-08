# yuno-bot

Discord bot「ゆの / 唯乃」の、ConversationLogを本体にした再設計版です。

実装判断の基準は [`docs/yuno_design_principles.md`](docs/yuno_design_principles.md) にあります。
次にどう変化させるか、道具・権限・整理の方針は [`docs/next_direction.md`](docs/next_direction.md) にあります。
実装をどう進めるか、作業ごとに何を整理するかは [`docs/implementation_practice.md`](docs/implementation_practice.md) にあります。

現在はCareMark / ReadCue移行後の構成です。会話につく印はCareMarkへ統合され、ReadCueはその印へ戻るための選択用索引として扱います。

実装や設計を進める前に、まず [`docs/yuno_design_principles.md`](docs/yuno_design_principles.md)、[`docs/next_direction.md`](docs/next_direction.md)、[`docs/implementation_practice.md`](docs/implementation_practice.md) を読んでください。ゆのでは、機能追加よりも「相手の言葉を処理対象として消費せず、預かったものとして扱うこと」と、不要な概念を増やさず整理しながら進めることを優先します。

```text
directed: user保存 → pre CareReader → recent 6件 + 必要なCareMark → Speaker → Discord送信
→ assistant保存 → 必要なら送信後観察

listening通常発言: user保存 → pre-filter → 必要ならCareReader
→ wants_to_speak && should_speak の時だけSpeaker → Discord送信 → assistant保存
```

CareMarkは独立した記憶庫ではなく、ConversationLogにつく印です。memory-likeな印は`draft / active / hidden`、attention-likeな印は`open / closed / hidden`を使います。

ReadCueはCareMarkを選ぶための弱い手がかりです。独立した記憶や関心ではなく、返信スイッチや返信確率でもありません。

CareReaderは同じstreamを静かに読み、CareMark候補とReadCue更新をJSONで返します。返答本文や口調指示は書きません。directed会話では送信前に読み、返信可否判断やSpeakerへの補助に使われます。listening通常発言では低信号なら読まずに保存のみとし、必要な場合だけ割り込み判断も担います。auto maintenanceは返信前には待たず、別タスクとして進めます。

Speakerは同じstreamのrecent 6件を基本に、一通の返答へ集中します。補助断片は既定で空です。必要な時だけsame-streamのactive memory CareMarkとopen attention CareMarkから合計3件までを選び、本文だけを渡します。ReadCue、ID、状態、routing名、内部理由、scoreは渡しません。

管理commandは現状 `/memories` と `/listening` です。`/memory`、`/attention`、`/interest` は旧table廃止に伴って登録を終了しました。表示と操作は実行したDMまたはchannelのstreamだけに限定され、すべてephemeralです。

## 会話ログの範囲

- DMは保存して返信します。
- 直接mentionと、DBに保存済みのゆのの発言へのDiscord replyは保存してreplyします。
- `LISTENING_CHANNEL_IDS` と `/listening add` の対象では人間の通常発言を保存します。
- 通常発言は、Cue / Termやopen Attentionに軽く重なる場合だけCareReaderが読み、`wants_to_speak` と `should_speak` の両方が成立した時だけ控えめに返します。それ以外は保存のみです。
- listening対象で `YUNO_CALL_NAMES` の呼び名を含む発言にはplain送信で返します。
- それ以外のguild発言は保存しません。
- `/status` で現在の保存範囲を確認できます。

会話の単位はDiscordチャンネル／DMです。別チャンネルやDMの生ログを混ぜません。

## Setup

```powershell
cd yuno-bot
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

必須設定は `.env.example` を参照してください。OpenAI設定が空の場合は、ローカルの短いfallback応答を使います。

SQLiteは既定で `data/yuno.sqlite3` に作成されます。相対パスは起動時のcurrent directoryではなく、必ず `yuno-bot` を基準に解決されます。WAL、foreign keys、busy timeout、schema migrationを使用し、DB・WAL・SHM・local env fileはGit管理外です。

## 管理command

```text
/status
/memories list|add|status
/listening list|add|remove|clear
```

`/listening` はenv初期値とDB設定を統合します。env由来はcommandで解除できず、DB由来の追加・解除は再起動なしでroutingへ反映されます。変更操作にはManage Channels権限が必要です。

`/memories` はownerまたはサーバー管理者だけが使用でき、実行したstreamのCareMarkだけを扱います。ReadCueを独立管理するcommandはありません。

将来追加する場合も、入口は次へ寄せます。

```text
/status
/settings
/memories
/tools
```

画像・添付・音声・外部リンク本文の読み取りは未実装です。与えられていないものを見たふりはせず、CareReaderもテキストで説明された内容だけを扱います。

## 旧v2 Notebookの扱い

旧記憶は破棄しません。後続段階で、明示的なdry-run付きimportとして実装します。

- 旧noteをmemory系またはattention系のCareMarkへ変換する
- source messageがなければ `legacy_v2_notebook` sourceとする
- 旧note ID、import日時、batch IDを保持する
- scopeを拡大せず、不明なscopeは `legacy_unscoped` とする
- 同じ旧noteを重複作成しない
- ConversationLog由来のCareMarkと矛盾した場合は新しい方を優先する
- previewを `data/import_preview_*.json` に出力できるようにする

この互換sourceは新規記憶の通常経路には使用しません。
詳細な変換契約は [`docs/legacy_v2_import_plan.md`](docs/legacy_v2_import_plan.md) に固定しています。

## Verification

```powershell
python -m compileall main.py yuno tests
python -m unittest discover -s tests
python -c "from yuno.app import create_bot; bot=create_bot(); print('bot ok')"
```
