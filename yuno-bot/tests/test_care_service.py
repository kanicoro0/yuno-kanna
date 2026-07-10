from pathlib import Path
import tempfile
import unittest

from yuno.care.models import (
    CareMarkCandidate,
    CareReadResult,
    ReadCueUpdate,
)
from yuno.care.operations import care_outcome_note
from yuno.care.service import (
    CareApplication,
    CareService,
    CareState,
    immediate_care_decision,
)
from yuno.care_marks.models import CareMark
from yuno.care_marks.repository import CareMarkRepository
from yuno.care_marks.service import CareMarkService
from yuno.config import Settings
from yuno.conversation.context import ContextBuilder
from yuno.conversation.repository import ConversationRepository
from yuno.discord.routing import MessageRouter
from yuno.infra.database import Database
from yuno.messages import IncomingMessage, SentMessage
from yuno.pipeline import ConversationPipeline
from yuno.read_cues.repository import ReadCueRepository
from yuno.read_cues.service import ReadCueService


class RecordingReader:
    def __init__(self, result=None, results=None):
        self.result = result or CareReadResult()
        self.results = list(results) if results else []
        self.requests = []

    async def read(self, request):
        self.requests.append(request)
        if self.results:
            return self.results.pop(0)
        return self.result


class RecordingSpeaker:
    def __init__(self):
        self.contexts = []

    async def speak(self, context):
        self.contexts.append(context)
        return '自然な返事'


class CareServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / 'care.sqlite3')
        await self.database.open()
        self.conversations = ConversationRepository(self.database)
        self.stream = await self.conversations.get_or_create_stream(
            'channel', '10', '1'
        )
        self.message = await self.conversations.append(
            self.stream.id, 'message-1', 'user', '7', 'A', 'conversation'
        )
        self.marks = CareMarkService(CareMarkRepository(self.database))
        self.cues = ReadCueService(ReadCueRepository(self.database))
        self.service = CareService(
            self.conversations, self.marks, self.cues
        )

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temp_dir.cleanup()

    def test_explicit_language_triggers_immediate_care(self) -> None:
        examples = (
            ('これを覚えて', 'explicit_memory'),
            ('あとで見たい', 'attention_language'),
            ('こはると呼んで', 'name_preference'),
            ('青色が好き', 'preference'),
            ('締切を忘れそう', 'schedule_or_task'),
        )
        for content, reason in examples:
            with self.subTest(content=content):
                decision = immediate_care_decision(content, CareState())
                self.assertTrue(decision.run)
                self.assertEqual(decision.reason, reason)

    def pipeline(self, reader, speaker=None):
        settings = Settings(
            discord_token='',
            discord_client_id=None,
            openai_api_key='',
            openai_model='',
            database_file=Path(self.temp_dir.name) / 'care.sqlite3',
            listening_channel_ids=frozenset({10}),
            yuno_call_names=('ゆの', '唯乃', 'yuno'),
            log_level='INFO',
        )
        return ConversationPipeline(
            MessageRouter(settings, self.conversations),
            self.conversations,
            ContextBuilder(self.conversations),
            speaker or RecordingSpeaker(),
            reader,
            self.service,
        )

    @staticmethod
    def incoming(message_id, content, *, mention=False, author_id='7'):
        return IncomingMessage(
            discord_message_id=message_id,
            discord_channel_id='10',
            discord_guild_id='1',
            stream_kind='channel',
            author_id=author_id,
            author_name='A',
            author_is_bot=False,
            bot_user_id='99',
            mentions_bot=mention,
            raw_content=content,
            created_at='2026-01-01T00:00:00+00:00',
            reply_to_discord_message_id=None,
        )

    async def test_directed_reply_reads_care_before_speech_and_keeps_logs(self) -> None:
        reader = RecordingReader(CareReadResult())
        pipeline = self.pipeline(reader)

        result = await pipeline.process(
            self.incoming('low-reply', '今日はいい天気だね', mention=True)
        )
        await pipeline.record_sent_assistant(
            result,
            SentMessage('reply-1', '99', 'ゆの', result.reply_text, 'now'),
        )
        application = await pipeline.observe_after_send(
            result.observation_ticket
        )

        self.assertIsNone(application)
        self.assertEqual(len(reader.requests), 1)
        self.assertEqual(result.care_mark_changes, ())
        self.assertEqual(
            await self.conversations.count_messages(self.stream.id),
            3,
        )
        self.assertTrue(
            await self.conversations.is_assistant_message('reply-1')
        )
        self.assertEqual(await self.marks.list_for_stream(self.stream.id), [])

    async def test_explicit_memory_and_name_preference_runs_before_send(self) -> None:
        reader = RecordingReader(CareReadResult(care_mark_candidates=(
            CareMarkCandidate('memory', 'draft', 'こはると呼ぶ'),
        )))
        pipeline = self.pipeline(reader)

        result = await pipeline.process(
            self.incoming(
                'remember-name',
                '名前はこはる。そう呼んで、覚えて',
                mention=True,
            )
        )
        application = await pipeline.observe_after_send(
            result.observation_ticket
        )

        self.assertEqual(len(reader.requests), 1)
        self.assertIsNone(application)
        self.assertEqual(len(result.care_mark_changes), 1)

    async def test_low_signal_listening_skips_care(self) -> None:
        reader = RecordingReader(CareReadResult(care_mark_candidates=(
            CareMarkCandidate('attention', 'open', '作られてはいけない'),
        )))
        pipeline = self.pipeline(reader)

        result = await pipeline.process(
            self.incoming('low-listening', '今日はいい天気だね')
        )

        self.assertFalse(result.should_send)
        self.assertEqual(reader.requests, [])
        self.assertEqual(result.care_mark_changes, ())
        self.assertEqual(await self.marks.list_for_stream(self.stream.id), [])
        self.assertEqual(
            await self.conversations.count_messages(self.stream.id),
            2,
        )

    async def test_strong_cue_runs_listening_reader(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'memory', 'active', '星の話'
        )
        await self.cues.upsert(mark.id, '星', 0.6)
        reader = RecordingReader()
        pipeline = self.pipeline(reader)

        result = await pipeline.process(
            self.incoming('strong-cue', '星が見える')
        )

        self.assertFalse(result.should_send)
        self.assertEqual(len(reader.requests), 1)
        self.assertGreaterEqual(reader.requests[0].cue_salience, 0.5)

    async def test_creates_care_mark_and_downgrades_sensitive_memory(self) -> None:
        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(care_mark_candidates=(
                CareMarkCandidate(
                    'memory', 'active', '通院している', sensitive=True
                ),
            )),
        )

        self.assertEqual(len(application.created_care_mark_ids), 1)
        mark = await self.marks.get_by_public_id(
            application.created_care_mark_ids[0]
        )
        self.assertEqual((mark.kind, mark.status), ('memory', 'draft'))
        self.assertEqual(application.affected_care_marks, (mark,))

    async def test_similar_open_attention_is_touched_not_duplicated(self) -> None:
        existing = await self.marks.create(
            self.stream.id, 'attention', 'open', '星 の話'
        )

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(care_mark_candidates=(
                CareMarkCandidate('attention', 'open', '星・の話'),
            )),
        )

        self.assertEqual(application.created_care_mark_ids, ())
        self.assertEqual(application.touched_care_mark_ids, (existing.public_id,))
        self.assertEqual(
            tuple(mark.public_id for mark in application.affected_care_marks),
            (existing.public_id,),
        )

    async def test_hidden_memory_is_not_recreated_by_candidate(self) -> None:
        hidden = await self.marks.create(
            self.stream.id, 'memory', 'active', '青い花が好き'
        )
        await self.marks.update(hidden.public_id, status='hidden')

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(care_mark_candidates=(
                CareMarkCandidate('memory', 'active', '青い花が好き'),
            )),
        )

        self.assertEqual(application.created_care_mark_ids, ())
        self.assertEqual(application.touched_care_mark_ids, ())
        remaining = await self.marks.list_for_stream(
            self.stream.id, statuses=('draft', 'active', 'hidden')
        )
        self.assertEqual(
            [mark.status for mark in remaining], ['hidden']
        )

    async def test_hidden_attention_is_not_recreated_by_candidate(self) -> None:
        hidden = await self.marks.create(
            self.stream.id, 'attention', 'open', 'あとで見る話'
        )
        await self.marks.update(hidden.public_id, status='hidden')

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(care_mark_candidates=(
                CareMarkCandidate('attention', 'open', 'あとで見る話'),
            )),
        )

        self.assertEqual(application.created_care_mark_ids, ())
        remaining = await self.marks.list_for_stream(
            self.stream.id, statuses=('open', 'closed', 'hidden')
        )
        self.assertEqual([mark.status for mark in remaining], ['hidden'])

    async def test_visible_match_still_wins_over_hidden_twin(self) -> None:
        hidden = await self.marks.create(
            self.stream.id, 'memory', 'active', '月の話'
        )
        await self.marks.update(hidden.public_id, status='hidden')
        visible = await self.marks.create(
            self.stream.id, 'memory', 'active', '月の話'
        )

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(care_mark_candidates=(
                CareMarkCandidate('memory', 'active', '月の話'),
            )),
        )

        self.assertEqual(application.created_care_mark_ids, ())
        self.assertEqual(
            application.touched_care_mark_ids, (visible.public_id,)
        )

    async def test_dedup_sees_marks_beyond_visible_state_window(self) -> None:
        old = await self.marks.create(
            self.stream.id, 'memory', 'active', 'ふるい約束'
        )
        for index in range(25):
            await self.marks.create(
                self.stream.id, 'memory', 'draft', f'埋める印{index}'
            )
        state = await self.service.current_state(self.stream.id)
        self.assertNotIn(
            old.public_id,
            {mark.public_id for mark in state.care_marks},
        )

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(care_mark_candidates=(
                CareMarkCandidate('memory', 'active', 'ふるい約束'),
            )),
        )

        self.assertEqual(application.created_care_mark_ids, ())
        self.assertEqual(application.touched_care_mark_ids, (old.public_id,))

    async def test_read_cue_update_links_to_created_candidate(self) -> None:
        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(
                care_mark_candidates=(
                    CareMarkCandidate('memory', 'active', '星の話'),
                ),
                read_cue_updates=(
                    ReadCueUpdate('星', 0.6, candidate_text='星の話'),
                ),
            ),
        )

        self.assertEqual(len(application.upserted_read_cue_ids), 1)
        cues = await self.cues.list_for_stream(self.stream.id)
        self.assertEqual(cues[0].term, '星')

    async def test_touch_id_links_to_existing_mark(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'memory', 'active', '月の話'
        )

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(touch_care_mark_ids=(mark.public_id,)),
        )

        self.assertEqual(application.touched_care_mark_ids, (mark.public_id,))
        self.assertEqual(application.affected_care_marks[0].public_id, mark.public_id)

    def test_memory_operation_language_triggers_immediate_care(self) -> None:
        examples = (
            'さっきのことは忘れて',
            'それはもう覚えなくていいよ',
            'この件は閉じていいよ',
            'これは固定しておいて',
        )
        for content in examples:
            with self.subTest(content=content):
                decision = immediate_care_decision(content, CareState())
                self.assertTrue(decision.run)

    async def test_close_operation_closes_open_attention(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'attention', 'open', '週末の約束の話'
        )

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(close_care_mark_ids=(mark.public_id,)),
            source_content='その件、もう閉じていいよ',
        )

        self.assertEqual(application.closed_care_mark_ids, (mark.public_id,))
        refreshed = await self.marks.get_by_public_id(mark.public_id)
        self.assertEqual(refreshed.status, 'closed')
        self.assertEqual(
            application.affected_care_marks[0].status, 'closed'
        )

    async def test_close_operation_ignores_non_open_targets(self) -> None:
        memory = await self.marks.create(
            self.stream.id, 'memory', 'active', '青が好き'
        )
        already_closed = await self.marks.create(
            self.stream.id, 'attention', 'closed', '前の話'
        )

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(close_care_mark_ids=(
                memory.public_id, already_closed.public_id,
            )),
            source_content='もう閉じていいよ',
        )

        self.assertEqual(application.closed_care_mark_ids, ())
        self.assertEqual(
            (await self.marks.get_by_public_id(memory.public_id)).status,
            'active',
        )

    async def test_forget_needs_spoken_request(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'memory', 'active', 'こはると呼ぶ'
        )

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(forget_care_mark_ids=(mark.public_id,)),
            source_content='今日は晴れだね',
        )

        self.assertEqual(application.forgotten_care_mark_ids, ())
        self.assertEqual(
            (await self.marks.get_by_public_id(mark.public_id)).status,
            'active',
        )

    async def test_forget_hides_mark_when_spoken_request_matches(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'memory', 'active', 'こはると呼ぶ'
        )

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(forget_care_mark_ids=(mark.public_id,)),
            source_content='さっきの呼び方はもう忘れて',
        )

        self.assertEqual(
            application.forgotten_care_mark_ids, (mark.public_id,)
        )
        refreshed = await self.marks.get_by_public_id(mark.public_id)
        self.assertEqual(refreshed.status, 'hidden')

    async def test_forget_applies_at_most_two_marks_per_turn(self) -> None:
        marks = [
            await self.marks.create(
                self.stream.id, 'memory', 'active', f'話その{index}'
            )
            for index in range(3)
        ]

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(forget_care_mark_ids=tuple(
                mark.public_id for mark in marks
            )),
            source_content='ぜんぶ忘れて',
        )

        self.assertEqual(len(application.forgotten_care_mark_ids), 2)
        statuses = [
            (await self.marks.get_by_public_id(mark.public_id)).status
            for mark in marks
        ]
        self.assertEqual(statuses.count('hidden'), 2)

    async def test_correction_forgets_old_mark_and_creates_new_one(self) -> None:
        old = await self.marks.create(
            self.stream.id, 'memory', 'active', 'こはると呼ぶ'
        )

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(
                forget_care_mark_ids=(old.public_id,),
                care_mark_candidates=(
                    CareMarkCandidate('memory', 'active', 'ゆきと呼ぶ'),
                ),
            ),
            source_content='さっきの呼び方はやめて、ゆきって呼んで',
        )

        self.assertEqual(application.forgotten_care_mark_ids, (old.public_id,))
        self.assertEqual(len(application.created_care_mark_ids), 1)
        self.assertEqual(
            (await self.marks.get_by_public_id(old.public_id)).status,
            'hidden',
        )
        created = await self.marks.get_by_public_id(
            application.created_care_mark_ids[0]
        )
        self.assertEqual((created.kind, created.status), ('memory', 'active'))
        self.assertEqual(created.text, 'ゆきと呼ぶ')

    async def test_promote_activates_draft_but_never_sensitive_text(self) -> None:
        plain = await self.marks.create(
            self.stream.id, 'memory', 'draft', '紅茶が好きらしい'
        )
        sensitive = await self.marks.create(
            self.stream.id, 'memory', 'draft', '通院している'
        )

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(promote_care_mark_ids=(
                plain.public_id, sensitive.public_id,
            )),
            source_content='それ、ちゃんと覚えておいて',
        )

        self.assertEqual(application.promoted_care_mark_ids, (plain.public_id,))
        self.assertEqual(
            (await self.marks.get_by_public_id(plain.public_id)).status,
            'active',
        )
        self.assertEqual(
            (await self.marks.get_by_public_id(sensitive.public_id)).status,
            'draft',
        )

    async def test_promote_needs_spoken_request(self) -> None:
        draft = await self.marks.create(
            self.stream.id, 'memory', 'draft', '紅茶が好きらしい'
        )

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(promote_care_mark_ids=(draft.public_id,)),
            source_content='ふうん、そうなんだ',
        )

        self.assertEqual(application.promoted_care_mark_ids, ())
        self.assertEqual(
            (await self.marks.get_by_public_id(draft.public_id)).status,
            'draft',
        )

    async def test_closed_mark_is_not_included_as_reference(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'attention', 'open', '週末の約束の話'
        )

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(
                close_care_mark_ids=(mark.public_id,),
                include_care_mark_ids=(mark.public_id,),
            ),
            source_content='その件はもう閉じていい',
        )

        self.assertEqual(application.closed_care_mark_ids, (mark.public_id,))
        self.assertEqual(application.include_care_mark_ids, ())

    async def test_natural_language_close_reaches_speaker(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'attention', 'open', '週末の約束の話'
        )
        reader = RecordingReader(CareReadResult(
            close_care_mark_ids=(mark.public_id,),
        ))
        speaker = RecordingSpeaker()
        pipeline = self.pipeline(reader, speaker)

        result = await pipeline.process(
            self.incoming('nl-close', '週末の約束の件、もう閉じていいよ', mention=True)
        )

        self.assertTrue(result.should_send)
        self.assertEqual(
            (await self.marks.get_by_public_id(mark.public_id)).status,
            'closed',
        )
        self.assertIn('閉じた', speaker.contexts[-1].care_note)
        self.assertNotIn('とは言わない', speaker.contexts[-1].care_note)

    async def test_unfulfilled_forget_request_reaches_speaker_as_denial(self) -> None:
        reader = RecordingReader(CareReadResult())
        speaker = RecordingSpeaker()
        pipeline = self.pipeline(reader, speaker)

        result = await pipeline.process(
            self.incoming('nl-forget-miss', 'さっきのことは忘れて', mention=True)
        )

        self.assertTrue(result.should_send)
        self.assertIn('忘れた、とは言わない', speaker.contexts[-1].care_note)

    async def test_forget_gate_accepts_a_pending_ask_back(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'memory', 'active', 'こはると呼ぶ'
        )

        application = await self.service.apply(
            self.stream.id,
            self.message.id,
            CareReadResult(forget_care_mark_ids=(mark.public_id,)),
            source_content='呼び方のやつだよ',
            pending_operation='forget',
        )

        self.assertEqual(
            application.forgotten_care_mark_ids, (mark.public_id,)
        )
        self.assertEqual(
            (await self.marks.get_by_public_id(mark.public_id)).status,
            'hidden',
        )

    async def test_ask_back_round_trip_finishes_the_forget(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'memory', 'active', 'こはると呼ぶ'
        )
        reader = RecordingReader(results=[
            CareReadResult(
                decision_made=True,
                should_speak=True,
                unclear_operation='forget',
            ),
            CareReadResult(
                decision_made=True,
                should_speak=True,
                forget_care_mark_ids=(mark.public_id,),
            ),
        ])
        speaker = RecordingSpeaker()
        pipeline = self.pipeline(reader, speaker)

        first = await pipeline.process(
            self.incoming('ask-1', '前に言ったこと、忘れてほしい', mention=True)
        )
        self.assertTrue(first.should_send)
        self.assertIn('聞き返していい', speaker.contexts[-1].care_note)
        self.assertEqual(
            (await self.marks.get_by_public_id(mark.public_id)).status,
            'active',
        )

        second = await pipeline.process(
            self.incoming('ask-2', '呼び方のやつだよ', mention=True)
        )

        self.assertTrue(second.should_send)
        self.assertEqual(reader.requests[1].pending_operation, 'forget')
        self.assertEqual(
            (await self.marks.get_by_public_id(mark.public_id)).status,
            'hidden',
        )
        self.assertIn('手放して', speaker.contexts[-1].care_note)

    async def test_pending_ask_back_runs_reader_even_for_low_signal_listening(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'memory', 'active', 'こはると呼ぶ'
        )
        reader = RecordingReader(results=[
            CareReadResult(
                decision_made=True,
                should_speak=True,
                unclear_operation='forget',
            ),
            CareReadResult(
                decision_made=True,
                should_speak=False,
                forget_care_mark_ids=(mark.public_id,),
            ),
        ])
        pipeline = self.pipeline(reader)

        await pipeline.process(
            self.incoming('quiet-1', 'さっきのは忘れて', mention=True)
        )
        second = await pipeline.process(
            self.incoming('quiet-2', '呼び方のやつ')
        )

        self.assertFalse(second.should_send)
        self.assertEqual(len(reader.requests), 2)
        self.assertEqual(reader.requests[1].pending_operation, 'forget')
        self.assertEqual(
            (await self.marks.get_by_public_id(mark.public_id)).status,
            'hidden',
        )

    async def test_pending_ask_back_ignores_other_speakers(self) -> None:
        mark = await self.marks.create(
            self.stream.id, 'memory', 'active', 'こはると呼ぶ'
        )
        reader = RecordingReader(results=[
            CareReadResult(
                decision_made=True,
                should_speak=True,
                unclear_operation='forget',
            ),
            CareReadResult(decision_made=True, should_speak=True),
        ])
        pipeline = self.pipeline(reader)

        await pipeline.process(
            self.incoming('other-1', 'さっきのは忘れて', mention=True)
        )
        await pipeline.process(
            self.incoming(
                'other-2', '呼び方のやつだよ', mention=True, author_id='8'
            )
        )

        self.assertEqual(reader.requests[1].pending_operation, '')
        self.assertEqual(
            (await self.marks.get_by_public_id(mark.public_id)).status,
            'active',
        )

    async def test_unclear_forget_lets_speaker_ask_back(self) -> None:
        reader = RecordingReader(CareReadResult(
            decision_made=True,
            should_speak=True,
            unclear_operation='forget',
        ))
        speaker = RecordingSpeaker()
        pipeline = self.pipeline(reader, speaker)

        result = await pipeline.process(
            self.incoming('nl-forget-vague', 'あれはもう忘れて', mention=True)
        )

        self.assertTrue(result.should_send)
        note = speaker.contexts[-1].care_note
        self.assertIn('聞き返していい', note)
        self.assertNotIn('いまここでは起きていない', note)
        self.assertEqual(await self.marks.list_for_stream(self.stream.id), [])


class CareOutcomeNoteTests(unittest.TestCase):
    @staticmethod
    def mark(public_id, kind, status, text='何か'):
        return CareMark(
            id=1,
            public_id=public_id,
            stream_id=1,
            source_message_id=None,
            kind=kind,
            status=status,
            text=text,
            created_at='now',
            updated_at='now',
        )

    def test_notes_report_only_real_changes(self) -> None:
        note = care_outcome_note(
            'さっきのことは忘れて',
            CareApplication(forgotten_care_mark_ids=('care_1',)),
        )
        self.assertIn('もう覚えていないことにした', note)
        self.assertNotIn('とは言わない', note)

    def test_unfulfilled_forget_request_yields_denial_note(self) -> None:
        note = care_outcome_note('さっきのことは忘れて', CareApplication())
        self.assertIn('忘れた、とは言わない', note)

    def test_unfulfilled_close_request_yields_denial_note(self) -> None:
        note = care_outcome_note('この話は閉じて', CareApplication())
        self.assertIn('閉じた、とは言わない', note)

    def test_remember_request_with_new_active_memory(self) -> None:
        created = self.mark('care_1', 'memory', 'active')
        note = care_outcome_note(
            'これは覚えて',
            CareApplication(
                created_care_mark_ids=('care_1',),
                affected_care_marks=(created,),
            ),
        )
        self.assertIn('覚えることにした', note)
        self.assertNotIn('とは言わない', note)

    def test_remember_request_with_sensitive_draft_stays_humble(self) -> None:
        created = self.mark('care_1', 'memory', 'draft')
        note = care_outcome_note(
            'これは覚えて',
            CareApplication(
                created_care_mark_ids=('care_1',),
                affected_care_marks=(created,),
            ),
        )
        self.assertIn('言い切らない', note)

    def test_remember_request_touching_known_memory(self) -> None:
        touched = self.mark('care_1', 'memory', 'active')
        note = care_outcome_note(
            'これは覚えておいて',
            CareApplication(
                touched_care_mark_ids=('care_1',),
                affected_care_marks=(touched,),
            ),
        )
        self.assertIn('前から覚えている', note)

    def test_plain_talk_yields_no_note(self) -> None:
        self.assertEqual(
            care_outcome_note('今日は晴れだね', CareApplication()), ''
        )

    def test_unclear_forget_becomes_ask_back_instead_of_denial(self) -> None:
        note = care_outcome_note(
            'さっきのことは忘れて', CareApplication(), 'forget'
        )
        self.assertIn('聞き返していい', note)
        self.assertIn('忘れた、とは言わず', note)
        self.assertNotIn('いまここでは起きていない', note)

    def test_unclear_signal_works_even_outside_gate_lexicon(self) -> None:
        note = care_outcome_note(
            '記憶から消し去ってほしいな', CareApplication(), 'forget'
        )
        self.assertIn('聞き返していい', note)

    def test_unclear_is_ignored_when_the_operation_happened(self) -> None:
        note = care_outcome_note(
            'さっきのことは忘れて',
            CareApplication(forgotten_care_mark_ids=('care_1',)),
            'forget',
        )
        self.assertIn('もう覚えていないことにした', note)
        self.assertNotIn('聞き返していい', note)

    def test_unknown_unclear_value_is_ignored(self) -> None:
        self.assertEqual(
            care_outcome_note('今日は晴れだね', CareApplication(), 'reset'),
            '',
        )

    def test_notes_never_leak_internal_words(self) -> None:
        samples = (
            care_outcome_note('さっきのことは忘れて', CareApplication()),
            care_outcome_note(
                '忘れて。ついでに閉じて。あと覚えて',
                CareApplication(
                    forgotten_care_mark_ids=('care_1',),
                    closed_care_mark_ids=('care_2',),
                    promoted_care_mark_ids=('care_3',),
                ),
            ),
        )
        for note in samples:
            lowered = note.casefold()
            for word in (
                'caremark', 'readcue', 'care_', 'status', 'draft', 'active',
                'open', 'closed', 'hidden', 'memory', 'attention',
            ):
                self.assertNotIn(word, lowered)
