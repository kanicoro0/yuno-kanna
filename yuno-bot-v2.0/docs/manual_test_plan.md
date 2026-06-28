# yuno-bot-v2 manual test plan

実Discord接続で行う確認項目です。テスト用guildとv2専用tokenを使い、v1と同じchannelでauto replyを同時に有効にしないでください。

## Command registration

- guild sync後、以下のcommandが更新される
- `/guide`, `/status`, `/settings notebook_view`
- `/notebook user|server|channel show|add|edit|delete|undo|history`
- `/notebook get`, `/notebook search`
- `/mind show|clear|status`
- `/sleep`, `/wake`, `/autorespond status|server|channel`
- 旧server memo command、reminder系、owner debug toolsが登録されていない

## Notebook scope and CRUD

1. `/notebook user add`後、`note_####`のIDが返る
2. `/notebook user show page:1 limit:5 detail:false`が`id: 内容`形式になる
3. `detail:true limit:3`でid/content/対象/tags/weightが表示される
4. `/notebook get id:45 detail:true`と完全IDの両方で同じrecordを取得できる
5. user notebookは別ユーザーの`/notebook get`から見えない
6. server notebook変更は`manage_guild`なしで拒否される
7. channel notebook変更は`manage_channels`なしで拒否される
8. 別guildのserver/channel recordは取得できない
9. delete後は通常show/getに出ず、IDは再利用されない

## Components

1. showの「前へ」「次へ」でページが動く
2. 「詳細表示」で一覧表示が切り替わる
3. select menuから選んだ完全IDの詳細がephemeral表示される
4. 開いた本人以外の操作は短く拒否される
5. channelを移動した状態で古いchannel viewを操作できない
6. 「閉じる」とtimeout後に安全に停止する
7. mutation buttonが存在しない

## Change log and undo

1. add/edit/deleteの各操作が`/notebook ... history`に出る
2. `/notebook ... undo`が自分の直近変更だけを戻す
3. delete undoで同じIDがactiveへ戻る
4. add undoで同じIDがdeletedになる
5. rewrite undoで以前の内容へ戻る
6. undoもchange logへ追加される
7. Planner由来record commitのactorが発言者IDになる

## Settings and debug

1. 既定normalでは内部route/context/timestampが出ない
2. ownerだけが`/settings notebook_view mode:debug`を選べる
3. owner以外のdebug指定は拒否される
4. debugでも他人・別guild・別channelのscopeは見えない
5. `OWNER_ID`未設定時はdebugとglobal sleep/wakeが使えない

## Sleep, auto reply, and rate limits

1. channel/server/globalそれぞれのsleep/wakeが権限どおり動く
2. sleep中のscopeではPlanner/Speakerが呼ばれない
3. `/autorespond server enabled:false`がchannel onより優先される
4. 非メンションは許可された場所だけ反応する
5. user 10秒、channel 5秒、global 60秒20回の制限がAI前に働く
6. direct requestのrate limitは短文、非メンションは無言になる

## Pipeline and fallback

1. typing表示はSpeaker呼び出し中だけ出る
2. Discord send成功後だけPlanner note actionとchange logが確定する
3. semantic retrieval未実装の現在もalways/keyword/tag retrievalで通常応答できる
4. OpenAI未設定時にmock fallbackでBot構築できる

## MindState and ConversationLog

1. `/mind show`はserverでchannel、DMでdm scopeを既定表示する
2. user/server/channel/dm scopeの権限境界を越えない
3. reply送信成功後だけ`mind_state.json`が更新される
4. server会話の自動更新はchannel scope、DMはdm scopeへ保存される
5. PlannerとSpeakerに統合済み`mind_context`が渡る
6. 通常時はPlanner最大4件、Speaker最大2件のrecent logだけを使う
7. 「前の案」「さっき」「前回」「ログ」等の明示参照時だけSpeakerへ最大16件渡る
8. `active_note_ids`がretrieval候補を強め、`suppressed_note_ids`が候補を除外する

## Model split

1. Speakerは`OPENAI_MODEL`を使う
2. Plannerは`OPENAI_FALLBACK_MODEL`を使う
3. Planner model未設定時はSpeaker modelへfallbackする
