"""Per-session runtime: state access, the session lock, timers, lifecycle, host queue, promos and the
client snapshot (DEV_SPEC §8.1, §8.10, §8.11, §11.1).

Every state change runs under `SessionRuntime.lock` with a fresh read of the documents it changes,
and emits events through the bus. LLM calls never run while the lock is held.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ..agents.answer_composer import AnswerComposer
from ..agents.reply_translator import ReplyTranslator
from ..agents.comment_triage import CommentTriage
from ..logic import host_queue as hq
from ..logic.cache import PRICE_INTENTS, AnswerCache, TriageCache
from ..logic.catalog import Catalog
from ..logic.grouping import is_open
from ..logic.ranking import score
from ..logic.reply_status import REPLY_KINDS, waiting_status
from ..logic.segments import open_segment
from ..models.data import Intent, Passage, Promo, PrompterPoint
from ..logic.prompter import prompter_view
from ..models.session import (
    ActivePromo,
    AgentCall,
    Alert,
    Answer,
    Comment,
    CommentAnalysis,
    Event,
    Message,
    QuestionGroup,
    Segment,
    Session,
    Transcript,
)
from ..bus import viewer_comment, viewer_message, viewer_session
from ..store.base import SESSIONS, SUBCOLLECTIONS, sub

if TYPE_CHECKING:
    from ..context import AppContext

log = logging.getLogger(__name__)

TICK_MS = 1000
SNAPSHOT_COMMENTS = 200


class ActionError(Exception):
    """An invalid operator or lifecycle action; the API turns it into a 4xx."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class RateLimited(ActionError):
    def __init__(self, message: str) -> None:
        super().__init__(429, "rate_limited", message)


class SessionRuntime:
    def __init__(self, ctx: "AppContext", session: Session) -> None:
        from .feed import FeedEngine

        self.ctx = ctx
        self.sid = session.session_id
        self.settings = ctx.settings
        # D-142: the session's (market, language) pack; never ctx.pack inside a session
        self.pack, self.reflex = ctx.pack_for(session.market, session.lang,
                                              tuple(session.release_ids) or session.release_id)
        self.catalog = Catalog(self.pack, session.runsheet_id)
        # D-150: a market or language below "live" (no sealed eval yet) is a preview: host cards only, nothing
        # is posted by itself, and the screens say so
        lang_tier = next(x.tier for x in self.pack.market.languages if x.lang == self.pack.lang)
        self.tier = "live" if self.pack.market.tier == "live" and lang_tier == "live" else "preview"
        self.live = self.tier == "live"
        self.assistant = session.assistant  # D-139
        self.lock = asyncio.Lock()
        self.triage_cache = TriageCache()
        self.refused_at: dict[str, int] = {}  # author -> when they last got the fixed "cannot answer" reply
        self.shoutouts: deque = deque(maxlen=20)  # D-113: recent purchase/welcome/compliment comments
        self.answer_cache = AnswerCache()
        self.composing: dict[str, asyncio.Future] = {}
        self.prefetched: dict[str, list[Passage]] = {}
        self._doc_version = ctx.retriever.doc_version()
        self._doc_seen = self._doc_version  # D-152: the documents the open groups' answers were drafted from
        self.points = {pid: [PrompterPoint.model_validate(p) for p in pts] for pid, pts in session.prompter_points.items()}
        self.counters: defaultdict[str, int] = defaultdict(int)
        self._rate_session: deque[int] = deque()
        self._rate_author: defaultdict[str, deque[int]] = defaultdict(deque)
        self.triage = CommentTriage(ctx.llm, ctx.prompts["comment_triage"], self.catalog, ctx.settings,
                                    batch_prompt=ctx.prompts["comment_triage_batch"])
        self.composer = AnswerComposer(ctx.llm, ctx.prompts["answer_composer"], self.catalog)
        self.reply_translator = ReplyTranslator(ctx.llm, ctx.prompts["reply_translator"])
        self.translating: set[tuple[str, str]] = set()  # (message, language) being translated
        self._reply_status: dict[str, str | None] = {}  # comment -> the status last written, so a repeat reads nothing
        # D-278: no demo comments in a release show (only the tests' shipped run sheet has them)
        self.feed = FeedEngine(self, demo=session.release_id is None and not session.release_ids)
        from .utterances import UtterancePipeline

        self.utterances = UtterancePipeline(self)
        from .pd import PdDirector

        self.pd = PdDirector(self)
        from .comments import TriageQueue

        self.triage_queue = TriageQueue(self)
        self.reply_latencies: defaultdict[str, list[int]] = defaultdict(list)
        self.overtime_emitted: set[str] = set()
        self._ticks = 0
        self.closed = False

    # ---- basics --------------------------------------------------------------------------------

    def now(self) -> int:
        return self.ctx.clock.now_ms()

    def new_id(self, prefix: str) -> str:
        return self.ctx.ids.new(prefix, self.sid)

    def path(self, name: str) -> str:
        return sub(self.sid, name)

    def key(self, name: str) -> str:
        return f"{self.sid}:{name}"

    async def emit(self, type_: str, payload: BaseModel | dict) -> None:
        source = payload
        if type_ == "group.updated" and isinstance(payload, QuestionGroup) and payload.answer_id:
            # The client gets the draft/suggested answer with its group, no refetch (D-059).
            answer = await self.get_answer(payload.answer_id)
            data = payload.model_dump(mode="json")
            data["answer"] = answer.model_dump(mode="json") if answer else None
            payload = data
        await self.ctx.bus.emit(self.sid, type_, payload)
        if type_.startswith("alert.") and isinstance(payload, Alert):  # D-158: traces a cloud replay
            log.info("alert %s %s %s %s %s %s %s t=%s field=%s", self.sid, type_, payload.alert_id, payload.kind,
                     payload.rule_id or "-", payload.severity or "-", payload.status, payload.transcript_id,
                     payload.field or "-")
        pd = getattr(self, "pd", None)
        if pd is not None and type_ != "pd.card":
            pd.on_event(type_, payload)  # only schedules work; never takes the lock
        # Every change of a group and every posted reply passes here, so the askers' status follows from one place.
        if type_ == "group.updated" and isinstance(source, QuestionGroup):
            await self._set_reply_status(source.member_comment_ids, waiting_status(source))
        elif (type_ in ("message.published", "message.updated") and isinstance(source, Message)
              and source.state == "published" and source.kind in REPLY_KINDS):
            await self._set_reply_status(source.reply_to_comment_ids, "answered")

    async def _set_reply_status(self, comment_ids: list[str], status: str | None) -> None:
        """What each asker is told about their question (logic/reply_status). Only a comment whose status changes
        is read and written; "answered" stays, because a posted reply stays posted whatever happens to its group."""
        for cid in comment_ids:
            if self._reply_status.get(cid, "") in (status, "answered"):
                continue
            c = await self.get_comment(cid)
            if c is None:
                continue
            want = "answered" if c.reply_status == "answered" else status if c.visibility == "visible" else None
            self._reply_status[cid] = want
            if c.reply_status != want:
                c.reply_status = want
                await self.save_comment(c)
                await self.emit("comment.status", c)

    def spawn(self, coro, name: str | None = None) -> asyncio.Task:
        return self.ctx.scheduler.spawn(coro, name=name)

    def intent(self, name: str | None) -> Intent:
        return self.pack.intents_by_name.get(name or "other") or self.pack.intents_by_name["other"]

    # ---- documents -----------------------------------------------------------------------------

    async def load_session(self) -> Session:
        s = await self.ctx.store.get(SESSIONS, self.sid, Session)
        if s is None:
            raise ActionError(404, "session_not_found", f"session {self.sid} not found")
        return s

    async def save_session(self, s: Session) -> None:
        await self.ctx.store.put(SESSIONS, self.sid, s)

    async def segments(self) -> list[Segment]:
        return await self.ctx.store.query(self.path("segments"), Segment, order_by="started_at")

    async def current_segment(self) -> Segment | None:
        return open_segment(await self.segments())

    async def groups(self) -> list[QuestionGroup]:
        return await self.ctx.store.query(self.path("groups"), QuestionGroup, order_by="first_at")

    async def get_group(self, gid: str) -> QuestionGroup | None:
        return await self.ctx.store.get(self.path("groups"), gid, QuestionGroup)

    async def save_group(self, g: QuestionGroup) -> None:
        await self.ctx.store.put(self.path("groups"), g.group_id, g)

    async def get_answer(self, aid: str | None) -> Answer | None:
        return None if aid is None else await self.ctx.store.get(self.path("answers"), aid, Answer)

    async def save_answer(self, a: Answer) -> None:
        await self.ctx.store.put(self.path("answers"), a.answer_id, a)

    async def get_message(self, mid: str | None) -> Message | None:
        return None if mid is None else await self.ctx.store.get(self.path("messages"), mid, Message)

    async def save_message(self, m: Message) -> None:
        await self.ctx.store.put(self.path("messages"), m.message_id, m)

    async def get_comment(self, cid: str) -> Comment | None:
        return await self.ctx.store.get(self.path("comments"), cid, Comment)

    async def save_comment(self, c: Comment) -> None:
        await self.ctx.store.put(self.path("comments"), c.comment_id, c)

    async def save_analysis(self, a: CommentAnalysis) -> None:
        await self.ctx.store.put(self.path("analyses"), a.analysis_id, a)

    async def alerts(self) -> list[Alert]:
        return await self.ctx.store.query(self.path("alerts"), Alert, order_by="created_at")

    async def get_alert(self, aid: str) -> Alert | None:
        return await self.ctx.store.get(self.path("alerts"), aid, Alert)

    async def save_alert(self, a: Alert) -> None:
        await self.ctx.store.put(self.path("alerts"), a.alert_id, a)

    async def get_segment(self, sid: str) -> Segment | None:
        return await self.ctx.store.get(self.path("segments"), sid, Segment)

    async def save_segment(self, seg: Segment) -> None:
        await self.ctx.store.put(self.path("segments"), seg.segment_id, seg)

    async def inject_transcript(self, text: str, *, scenario: str = "default") -> Transcript:
        """§10.4: a final transcript from the Demo Console (source=injected, speech end = now)."""
        return await self.utterances.submit(text, source="injected", scenario=scenario)

    def promo(self, promo_id: str | None) -> Promo | None:
        return None if promo_id is None else self.pack.promos_by_id.get(promo_id)

    async def active_price_promo(self) -> Promo | None:
        return self.promo((await self.load_session()).active_promo_id)

    async def active_offers(self) -> list[Promo]:
        """D-168: running offers that change no price (a gift over a spend)."""
        return [p for p in (self.promo(ap.promo_id) for ap in (await self.load_session()).active_promos)
                if p is not None and not p.changes_prices]

    # ---- rate limits (§5) ----------------------------------------------------------------------

    def check_rate(self, author_id: str, now: int) -> None:
        horizon = now - 60_000
        for q in (self._rate_session, self._rate_author[author_id]):
            while q and q[0] <= horizon:
                q.popleft()
        if len(self._rate_session) >= self.settings.COMMENT_RATE_LIMIT_PER_MIN:
            raise RateLimited("Too many comments in this session. Try again in a minute.")
        if len(self._rate_author[author_id]) >= self.settings.COMMENT_RATE_LIMIT_PER_AUTHOR_PER_MIN:
            raise RateLimited("You are commenting too fast. Try again in a minute.")
        self._rate_session.append(now)
        self._rate_author[author_id].append(now)

    # ---- lifecycle (§8.1) ----------------------------------------------------------------------

    def sync_doc_version(self) -> None:
        """A /setup upload rebuilt the index: drop prefetched passages so they are fetched again (§8.12.3)."""
        v = self.ctx.retriever.doc_version()
        if v != self._doc_version:
            self._doc_version = v
            self.prefetched.clear()

    async def prefetch(self, product_id: str | None) -> None:
        if product_id is not None:
            self.prefetched[product_id] = await self.ctx.retriever.prefetch(product_id)

    async def start(self) -> Session:
        async with self.lock:
            s = await self.load_session()
            if s.status != "ready":
                raise ActionError(409, "invalid_state", f"session is {s.status}, not ready")
            now = self.now()
            first = self.catalog.order[0]
            item = self.catalog.runsheet_item(first)
            seg = Segment(segment_id=self.new_id("seg_"), product_id=first, order=item.order, started_at=now,
                          start_reason="session_start", planned_duration_sec=item.planned_duration_sec)
            await self.ctx.store.put(self.path("segments"), seg.segment_id, seg)
            s.status, s.started_at, s.current_segment_id = "live", now, seg.segment_id
            s.settings_snapshot = self.settings.snapshot()
            await self.save_session(s)
            await self.emit("session.started", s)
            await self.emit("segment.started", seg)
            await self.after_segment_started_locked(seg)
        await self.prefetch(first)
        await self.prefetch(self.catalog.next_product(first))
        self.spawn(self.ctx.llm.warm_up(), name="warm-up")
        for pid in self.catalog.order:  # D-247 arm FD; D-279: every release's files at the start of the show
            self.spawn(self.utterances.warm_facts_cache(pid), name=f"facts-files-cache:{pid}")
        self.ctx.scheduler.call_later(self.key("tick"), TICK_MS, self._tick)
        return s

    async def prompter_view_now(self, seg: Segment | None) -> dict:
        """D-423: the prompter view with the items as they are now (the running price promo's prices)."""
        return prompter_view(self.catalog, seg, self.points, await self.active_price_promo())

    async def after_segment_started_locked(self, seg: Segment) -> None:
        """Work that follows every segment start: prompter, host slots, feed bursts armed for it."""
        await self.emit("prompter.updated", await self.prompter_view_now(seg))
        await self.recompute_host_queue_locked()
        self.feed.on_segment_started(seg)

    async def end(self) -> Session:
        async with self.lock:
            s = await self.load_session()
            if s.status != "live":
                raise ActionError(409, "invalid_state", f"session is {s.status}, not live")
            now = self.now()
            seg = await self.current_segment()
            if seg is not None:
                seg.ended_at = now
                await self.ctx.store.put(self.path("segments"), seg.segment_id, seg)
            self.feed.stop_all()
            for m in await self.ctx.store.query(self.path("messages"), Message, where=[("state", "==", "pending")]):
                m.state = "cancelled"
                await self.save_message(m)
                await self.emit("message.cancelled", m)
            s.status, s.ended_at = "ended", now
            await self.save_session(s)
            self.ctx.scheduler.cancel_prefix(f"{self.sid}:")
            await self.emit("session.ended", s)
        if hasattr(self.ctx.store, "flush"):  # D-354: the show's writes are in Firestore when it ends
            await self.ctx.store.flush(timeout=10.0)
        # §8.1.4: summary stats, then the recap in the background; `summary.ready` follows.
        try:
            from .summary import run_summary
        except ModuleNotFoundError:
            run_summary = None
        if run_summary is not None:
            self.spawn(run_summary(self), name=f"summary:{self.sid}")
        return s

    async def _tick(self) -> None:
        if self.closed:
            return
        try:
            async with self.lock:
                s = await self.load_session()
                if s.status != "live":
                    return
                await self.tick_locked(s)
        finally:
            if not self.closed:
                s = await self.ctx.store.get(SESSIONS, self.sid, Session)
                if s is not None and s.status == "live":
                    self.ctx.scheduler.call_later(self.key("tick"), TICK_MS, self._tick)

    async def tick_locked(self, s: Session) -> None:
        now = self.now()
        self._ticks += 1
        for g in await self.groups():
            # a question still waiting for a person (the operator's review, the host's card) is not dropped after
            # ten quiet minutes like an answered one: it waits GROUP_TTL_WAITING_SEC, so nobody's question
            # disappears from the desk unanswered while the operator was busy
            waiting = g.status in ("needs_review", "ready", "new", "composing")
            ttl = self.settings.GROUP_TTL_WAITING_SEC if waiting else self.settings.GROUP_TTL_SEC
            if is_open(g) and g.host_slot != "on_host" and now - g.last_at >= ttl * 1000:
                g.status, g.closed_reason = "closed", "ttl"
                g.version += 1
                await self.save_group(g)
                await self.emit("group.updated", g)
        await self.recompute_host_queue_locked()
        seg = await self.current_segment()
        if seg is not None and seg.segment_id not in self.overtime_emitted:
            over_ms = now - seg.started_at - seg.planned_duration_sec * 1000
            if over_ms > 0:  # §8.1.5: once per segment; operator badge only
                self.overtime_emitted.add(seg.segment_id)
                await self.emit("segment.overtime", {"segment_id": seg.segment_id, "product_id": seg.product_id,
                                                     "overtime_sec": over_ms // 1000})
        if self._ticks % 5 == 0:
            await self.emit("metrics.updated", await self.compute_metrics())
        self.pd.on_tick()  # time milestones, promo endings, pauses

    async def extend_segment(self, sec: int = 120) -> Segment:
        """D-138 (feature B3): +2 min on the on-air segment. The status line, the overtime badge and the
        AI PD's wrap-up and switch thresholds all read `planned_duration_sec`, so they move together."""
        async with self.lock:
            seg = await self.current_segment()
            if seg is None:
                raise ActionError(409, "invalid_state", "no segment on air")
            seg.planned_duration_sec += sec
            self.overtime_emitted.discard(seg.segment_id)  # it can run over again, once, later
            await self.save_segment(seg)
            await self.emit("segment.extended", {"segment": seg.model_dump(mode="json"), "added_sec": sec})
            await self.emit("operator.action", {"actor": "operator", "action": "extend", "segment_id": seg.segment_id,
                                                "added_sec": sec, "at": self.now()})
            return seg

    async def simulate_overtime(self) -> Segment:
        """Demo tool: move the on-air segment start back by its planned duration."""
        async with self.lock:
            seg = await self.current_segment()
            if seg is None:
                raise ActionError(409, "invalid_state", "no segment on air")
            seg.started_at -= seg.planned_duration_sec * 1000
            await self.save_segment(seg)
            await self.emit("segment.started", seg)
            return seg

    def shutdown(self) -> None:
        self.closed = True
        self.feed.stop_all()
        self.ctx.scheduler.cancel_prefix(f"{self.sid}:")

    # ---- host queue (§8.11) --------------------------------------------------------------------

    def queue_params(self) -> hq.QueueParams:
        st = self.settings
        return hq.QueueParams(top_n=st.HOST_TOP_N, min_dwell_ms=st.HOST_MIN_DWELL_SEC * 1000,
                              repeat_threshold=st.HOST_REPEAT_THRESHOLD)

    def score_of(self, g: QuestionGroup, on_air: str | None, now: int) -> float:
        return score(g, self.intent(g.intent), self.pack.intents.ranking_weights, on_air, now)

    async def recompute_host_queue_locked(self, *, push: str | None = None, recall: str | None = None) -> None:
        s = await self.load_session()
        seg = await self.current_segment()
        on_air = seg.product_id if seg else None
        now = self.now()
        # D-117 B9: answered, rejected and closed groups are history; only open groups (or one still
        # holding a host slot) are scored and saved, so the lock is not held for the whole session's past
        groups = {g.group_id: g for g in await self.groups()
                  if g.status not in ("answered", "rejected", "closed") or g.host_slot != "none"}
        before = {gid: g.score for gid, g in groups.items()}
        for g in groups.values():
            g.score = self.score_of(g, on_air, now)
        scores = {gid: g.score for gid, g in groups.items()}
        slots = list(s.host_slots)
        if recall is not None:
            slots = hq.remove_slot(slots, recall)
        if push is not None:
            slots = hq.push_slot(slots, push, scores, now=now, top_n=self.settings.HOST_TOP_N)
        new_slots = hq.compute_slots(
            slots, groups, scores, on_air=on_air, segment_started_at=seg.started_at if seg else None,
            now=now, params=self.queue_params(), scope_of=lambda name: self.intent(name).product_scope,
        )
        on_host = {sl.group_id: sl for sl in new_slots}
        for g in groups.values():
            slot = on_host.get(g.group_id)
            want = ("on_host", slot.on_host_since) if slot else ("none", None)
            changed = (g.host_slot, g.on_host_since) != want
            if changed:
                g.host_slot, g.on_host_since = want
                g.version += 1
            if changed or g.score != before[g.group_id]:
                await self.save_group(g)  # scores move with time; saved without an event
            if changed:
                await self.emit("group.updated", g)
        old = [sl.model_dump() for sl in s.host_slots]
        if [sl.model_dump() for sl in new_slots] != old:
            s.host_slots = new_slots
            await self.save_session(s)
            await self.emit("hostqueue.updated", {"slots": [sl.model_dump() for sl in new_slots]})
            # D-163: what is on the host's list and what waits outside it (a full list, or another product on air)
            params = self.queue_params()
            outside = [g for g in groups.values() if g.group_id not in on_host and hq.is_candidate(
                g, on_air=on_air, scope=self.intent(g.intent).product_scope, now=now,
                repeat_threshold=params.repeat_threshold)]
            log.info("hostqueue %s on_air=%s list=[%s] outside=[%s]", self.sid, on_air,
                     ", ".join(f"{sl.group_id}:{groups[sl.group_id].intent}:{scores.get(sl.group_id, 0):.2f}"
                               for sl in new_slots if sl.group_id in groups),
                     ", ".join(f"{g.group_id}:{g.intent}:{scores.get(g.group_id, 0):.2f}" for g in outside))

    # ---- messages ------------------------------------------------------------------------------

    async def publish_message_locked(
        self,
        *,
        kind: str,
        text: str,
        group: QuestionGroup | None,
        comment_ids: list[str],
        citations: list[dict],
        idempotency_key: str,
        pending_until: int | None = None,
    ) -> Message:
        existing = await self.ctx.store.query(self.path("messages"), Message,
                                              where=[("idempotency_key", "==", idempotency_key)])
        live = [m for m in existing if m.state != "cancelled"]
        if live:
            return live[0]
        names: list[str] = []
        for cid in comment_ids:
            c = await self.get_comment(cid)
            if c is not None and c.author_name not in names:
                names.append(c.author_name)
        now = self.now()
        msg = Message(
            message_id=self.new_id("msg_"), kind=kind, text=text, group_id=group.group_id if group else None,
            reply_to_comment_ids=list(comment_ids), reply_to_author_names=names, citations=citations,
            state="pending" if pending_until else "published", created_at=now, publish_at=pending_until,
            published_at=None if pending_until else now, idempotency_key=idempotency_key,
        )
        await self.save_message(msg)
        await self.emit("message.pending" if pending_until else "message.published", msg)
        self.translate_later(msg.message_id)
        return msg

    def translate_later(self, message_id: str) -> None:
        """The reply in the askers' other languages, after it is posted (it never waits for a translation)."""
        from .translation import translate_reply  # the pipelines import this module

        self.spawn(translate_reply(self, message_id), name=f"translate:{message_id}")

    # ---- promotions (§8.10) --------------------------------------------------------------------

    async def rearm_timers(self) -> None:
        """D-361: a live session this process did not start (read back after a restart) gets the timers the old
        process held: the tick, each running promo's end, a pending switch's commit and each HIGH alert's escalation.
        A time already past fires at once."""
        s = await self.load_session()
        self.ctx.scheduler.call_later(self.key("tick"), TICK_MS, self._tick)
        for p in s.active_promos:
            self.ctx.scheduler.call_at(self.key(f"promo:{p.promo_id}"), p.ends_at,
                                       lambda pid=p.promo_id: self.stop_promo(pid, reason="timer"))
        for a in await self.alerts():
            if a.escalated_at is None:
                self.utterances._schedule_escalation(a)  # it checks kind, severity and status itself
        seg = await self.current_segment()  # D-428 (from the comments team's resume): the on-air product's prefetch
        if seg is not None:
            await self.prefetch(seg.product_id)
        log.info("session %s read back: timers re-armed (%d promos)", self.sid, len(s.active_promos))

    async def start_promo(self, promo_id: str) -> Session:
        async with self.lock:
            s = await self.load_session()
            promo = self.promo(promo_id)
            if promo is None or promo_id not in self.catalog.runsheet.promo_ids:
                raise ActionError(404, "unknown_promo", f"promo {promo_id} is not on this run-sheet")
            if s.status != "live":
                raise ActionError(409, "invalid_state", "promotions run only while live")
            if any(p.promo_id == promo_id for p in s.active_promos):
                raise ActionError(409, "promo_active", f"{promo.title} is already running")
            if promo.changes_prices and s.active_promo_id is not None:
                raise ActionError(409, "price_promo_active", "Another price promotion is already running.")
            now = self.now()
            active = ActivePromo(promo_id=promo_id, started_at=now, ends_at=now + promo.duration_sec * 1000)
            s.active_promos.append(active)
            if promo.changes_prices:
                s.active_promo_id, s.promo_started_at = promo_id, now
            await self.save_session(s)
            self.ctx.scheduler.call_at(self.key(f"promo:{promo_id}"), active.ends_at,
                                       lambda: self.stop_promo(promo_id, reason="timer"))
            await self.emit("promo.started", {**active.model_dump(), "changes_prices": promo.changes_prices})
            if promo.changes_prices:
                await self.emit("prompter.updated", await self.prompter_view_now(await self.current_segment()))  # D-423
                await self.price_promo_changed_locked()
            return s

    async def stop_promo(self, promo_id: str, *, reason: str = "operator") -> Session:
        async with self.lock:
            s = await self.load_session()
            active = next((p for p in s.active_promos if p.promo_id == promo_id), None)
            if active is None:
                if reason == "timer":
                    return s
                raise ActionError(409, "promo_not_active", f"promo {promo_id} is not running")
            promo = self.promo(promo_id)
            s.active_promos = [p for p in s.active_promos if p.promo_id != promo_id]
            if s.active_promo_id == promo_id:
                s.active_promo_id, s.promo_started_at = None, None
            await self.save_session(s)
            self.ctx.scheduler.cancel(self.key(f"promo:{promo_id}"))
            await self.emit("promo.ended", {"promo_id": promo_id, "ended_at": self.now(), "reason": reason})
            if promo is not None and promo.changes_prices:
                await self.emit("prompter.updated", await self.prompter_view_now(await self.current_segment()))  # D-423
                await self.price_promo_changed_locked()
            return s

    async def documents_changed_locked(self) -> None:
        """D-152 (comment-flow CF11): a /setup upload changed the documents. An open, answered group whose answer
        no longer matches is closed, as after a promo change, so the next asker gets a fresh answer instead of
        the old reply posted again."""
        from .comments import answer_key

        v = self.ctx.retriever.doc_version()
        if v == self._doc_seen:
            return
        self._doc_seen = v
        for g in await self.groups():
            ans = await self.get_answer(g.answer_id) if g.answer_id else None
            if is_open(g) and ans is not None and g.status != "composing" and ans.cache_key != await answer_key(self, g):
                g.status, g.closed_reason = "closed", "documents_changed"
                g.host_slot, g.on_host_since = "none", None
                g.version += 1
                await self.save_group(g)
                await self.emit("group.updated", g)
        s = await self.load_session()
        closed = {g.group_id for g in await self.groups() if g.status == "closed"}
        if any(sl.group_id in closed for sl in s.host_slots):
            s.host_slots = [sl for sl in s.host_slots if sl.group_id not in closed]
            await self.save_session(s)
            await self.emit("hostqueue.updated", {"slots": [sl.model_dump() for sl in s.host_slots]})
        await self.recompute_host_queue_locked()

    async def price_promo_changed_locked(self, intents: frozenset[str] = PRICE_INTENTS) -> None:
        """No old price is re-posted after a promo change: drop cached price answers and close open
        price groups, so new price questions get a fresh answer (§8.10)."""
        self.answer_cache.invalidate_intents(intents)
        for g in await self.groups():
            if is_open(g) and g.intent in intents:
                g.status, g.closed_reason = "closed", "promo_changed"
                g.host_slot, g.on_host_since = "none", None
                g.version += 1
                await self.save_group(g)
                await self.emit("group.updated", g)
        s = await self.load_session()
        closed = {g.group_id for g in await self.groups() if g.status == "closed"}
        if any(sl.group_id in closed for sl in s.host_slots):
            s.host_slots = [sl for sl in s.host_slots if sl.group_id not in closed]
            await self.save_session(s)
            await self.emit("hostqueue.updated", {"slots": [sl.model_dump() for sl in s.host_slots]})
        await self.recompute_host_queue_locked()

    async def set_notice(self, text: str | None) -> Session:
        async with self.lock:
            s = await self.load_session()
            s.pinned_notice = text.strip() if text and text.strip() else None
            await self.save_session(s)
            await self.emit("notice.updated", {"pinned_notice": s.pinned_notice})
            return s

    # ---- snapshot (§11.1 /state) ---------------------------------------------------------------

    async def impact(self) -> dict[str, Any]:
        """D-240: live impact counters from logged state, each with its denominator."""
        store = self.ctx.store
        finals = [t for t in await store.query(self.path("transcripts"), Transcript) if t.is_final]
        alerted = {a.transcript_id for a in await self.alerts()
                   if a.kind == "compliance" and a.shown_at is not None and a.status != "dismissed"}
        groups = await self.groups()
        asked = sum(len(g.member_comment_ids) for g in groups)

        def askers(pred) -> int:
            return sum(len(g.member_comment_ids) for g in groups if pred(g))

        events = await store.query(self.path("events"), Event)
        calls = await store.query(self.path("agent_calls"), AgentCall)
        tokens = sum((c.usage or {}).get("prompt", 0) or 0 for c in calls) + sum(
            (c.usage or {}).get("output", 0) or 0 for c in calls)
        s = await self.load_session()
        hours = max((self.now() - s.started_at) / 3_600_000, 1 / 60) if s.started_at else None
        return {
            "risky_lines": {"alerted": len(alerted), "of_lines": len(finals)},
            "questions": {"ai": askers(lambda g: g.status == "auto_answered"),
                          "host": askers(lambda g: g.route == "HOST"),
                          "operator": askers(lambda g: g.route == "OPERATOR"),
                          "of_askers": asked},
            "operator_actions": sum(1 for e in events if e.type == "operator.action"
                                    and e.payload.get("actor") == "operator"),
            "llm": {"calls": len(calls), "tokens": tokens,
                    "tokens_per_hour": round(tokens / hours) if hours else None},
        }

    async def compute_metrics(self) -> dict[str, Any]:
        return {**await self._metrics(self.ctx.store), "impact": await self.impact()}  # D-240

    async def _metrics(self, store) -> dict[str, Any]:
        from ..logic.metrics import compute_metrics

        return compute_metrics(
            alerts=await self.alerts(),
            transcripts=await store.query(self.path("transcripts"), Transcript),
            agent_calls=await store.query(self.path("agent_calls"), AgentCall),
            messages=await store.query(self.path("messages"), Message),
            comments=await store.query(self.path("comments"), Comment),
            counters=dict(self.counters),
            reply_latencies={k: list(v) for k, v in self.reply_latencies.items()},
            triage_hits=self.triage_cache.hits,
            triage_misses=self.triage_cache.misses,
        )

    async def snapshot(self, role: str) -> dict[str, Any]:
        last_seq = await self.ctx.bus.last_seq(self.sid)  # read first: later events replay idempotently
        s = await self.load_session()
        store = self.ctx.store
        comments = await store.query(self.path("comments"), Comment, order_by="received_at")
        visible = [c for c in comments if c.visibility == "visible"][-SNAPSHOT_COMMENTS:]
        if role == "viewer":
            # the public chat and show state only, with the same fields as the viewer's event stream (bus.for_role)
            messages = await store.query(self.path("messages"), Message, order_by="created_at")
            return {
                "last_seq": last_seq,
                "server_time": self.now(),
                "session": viewer_session(s.model_dump(mode="json")),
                "segments": [x.model_dump(mode="json") for x in await self.segments()],
                # hidden ones too, without their text: the chat shows "hidden" in their place, also after a reload
                "comments": [viewer_comment(c.model_dump(mode="json")) for c in comments[-SNAPSHOT_COMMENTS:]],
                "messages": [m for m in (viewer_message(x.model_dump(mode="json")) for x in messages) if m is not None],
            }
        hidden = [c for c in comments if c.visibility == "hidden"][-SNAPSHOT_COMMENTS:] if role == "operator" else []
        shown = sorted(visible + hidden, key=lambda c: c.received_at)
        groups = await self.groups()
        answer_ids = {g.answer_id for g in groups if g.answer_id}
        answers = [a for a in await store.query(self.path("answers"), Answer) if a.answer_id in answer_ids]
        alerts = await self.alerts()
        finals = await store.query(self.path("transcripts"), Transcript, order_by="received_at")
        # D-439: the lines the alerts were raised and cleared on (their speech end times the "Shown in" and "Cleared in"
        # labels), also for the host and after a restart
        cited = {x for a in alerts for x in (a.transcript_id, a.corrected_by_transcript_id) if x}
        out: dict[str, Any] = {
            "last_seq": last_seq,
            "server_time": self.now(),
            "session": s.model_dump(mode="json"),
            "segments": [x.model_dump(mode="json") for x in await self.segments()],
            "groups": [g.model_dump(mode="json") for g in groups],
            "answers": {a.answer_id: a.model_dump(mode="json") for a in answers},
            "host_slots": [sl.model_dump() for sl in s.host_slots],
            "comments": [c.model_dump(mode="json") for c in shown],
            "messages": [m.model_dump(mode="json") for m in await store.query(self.path("messages"), Message, order_by="created_at")],
            # D-462: the host gets only the alerts shown to it (ALERT_GRACE holds a new one back for a moment)
            "alerts": [a.model_dump(mode="json") for a in alerts if role == "operator" or a.shown_at is not None],
            "transcripts": [t.model_dump(mode="json") for t in finals if t.transcript_id in cited],
            "prompter": await self.prompter_view_now(await self.current_segment()),
            "metrics": await self.compute_metrics(),
            "feed": self.feed.state(),
            "judge_health": {"degraded": list(self.utterances.degraded)},  # D-137
            "check_failures": self.utterances.check_failures(),  # D-412
            "market": {"market": self.pack.market.market, "name": self.pack.market.name, "lang": self.pack.lang,
                       "tier": self.tier,  # D-150
                       # D-228: no law pack covers this release's category: no compliance checks run
                       "law_checks": bool(self.pack.rules.rules or self.pack.rules.pack_ids), "category": self.pack.rules.category,
                       "retraction_phrase": self.pack.lang_pack.retraction_phrase},  # D-436
        }
        if role == "operator":
            ids = {c.comment_id for c in shown}
            out["analyses"] = {a.comment_id: a.model_dump(mode="json")
                               for a in await store.query(self.path("analyses"), CommentAnalysis) if a.comment_id in ids}
            last = {t.transcript_id for t in finals[-20:]}
            out["transcripts"] = [t.model_dump(mode="json") for t in finals if t.transcript_id in last | cited]
            calls = await store.query(self.path("agent_calls"), AgentCall, order_by="started_at")
            out["agent_calls"] = [c.model_dump(mode="json") for c in calls[-50:]]
        return out


async def create_session(ctx: "AppContext", runsheet_id: str, show_mode: str = "solo", assistant: bool = True,
                         market: str | None = None, lang: str | None = None, release_id: str | None = None,
                         release_ids: list[str] | None = None) -> Session:
    """§8.1.1: a new session in status `ready`."""
    from ..logic.catalog import DataPackError

    market = (market or ctx.settings.MARKET).upper()
    lang = lang or ctx.settings.BROADCAST_LANGUAGE
    try:
        pack, _ = ctx.pack_for(market, lang)  # D-142: fails when the market does not offer the language
    except (DataPackError, FileNotFoundError) as e:
        raise ActionError(400, "unknown_market_language", f"{market}/{lang}: {e}") from None
    if release_ids and len(release_ids) == 1:
        release_id, release_ids = release_ids[0], None
    if release_ids:  # D-279: a show of 2-3 releases
        from ..onboarding.show import MAX_RELEASES, show_id

        if len(release_ids) > MAX_RELEASES or len(set(release_ids)) != len(release_ids):
            raise ActionError(400, "bad_release_ids", f"2 to {MAX_RELEASES} different releases")
        try:
            pack, _ = ctx.pack_for(market, lang, tuple(release_ids))
        except FileNotFoundError as e:
            raise ActionError(404, "unknown_release", str(e)) from None
        except DataPackError as e:  # no price for this market, another currency, ...
            raise ActionError(400, "show_not_buildable", str(e)) from None
        runsheet_id = show_id(tuple(release_ids))
    elif release_id is not None:  # D-218: an onboarded product's one-segment show
        try:
            pack, _ = ctx.pack_for(market, lang, release_id)
        except DataPackError as e:
            raise ActionError(404, "unknown_release", str(e)) from None
        runsheet_id = release_id
    if pack.products.currency_symbol != ctx.pack.products.currency_symbol:
        # D-179: the sheets' index and /catalog are the server's market's; another currency needs MARKET=<it>
        raise ActionError(400, "market_needs_own_server",
                          f"{market} prices are in {pack.products.currency_symbol}; run the server with MARKET={market}")
    try:
        runsheet = pack.runsheet(runsheet_id)
    except DataPackError as e:
        raise ActionError(404, "unknown_runsheet", str(e)) from None
    glossary_version, points = 0, {}
    session = Session(
        session_id=ctx.ids.new("ses_"), runsheet_id=runsheet.runsheet_id, title=runsheet.title, status="ready",
        show_mode=show_mode, assistant=assistant, market=market, lang=lang, release_id=release_id,
        release_ids=list(release_ids or []),
        settings_snapshot=ctx.settings.snapshot(), doc_version=ctx.retriever.doc_version(),
        glossary_version=glossary_version, prompter_points=points, created_at=ctx.clock.now_ms(),
    )
    await ctx.store.put(SESSIONS, session.session_id, session)
    return session


async def latest_session(ctx: "AppContext") -> Session | None:
    found = await ctx.store.query(SESSIONS, Session, order_by="created_at", descending=True, limit=1)
    return found[0] if found else None


class Runtimes:
    """Registry of live session runtimes (one per session, one process, §4.1)."""

    def __init__(self, ctx: "AppContext") -> None:
        self.ctx = ctx
        self._by_id: dict[str, SessionRuntime] = {}

    async def get(self, session_id: str) -> SessionRuntime:
        rt = self._by_id.get(session_id)
        if rt is None:
            s = await self.ctx.store.get(SESSIONS, session_id, Session)
            if s is None:
                raise ActionError(404, "session_not_found", f"session {session_id} not found")
            rt = self._by_id.get(session_id)  # the load may have yielded to another caller
            if rt is None:
                rt = self._by_id[session_id] = SessionRuntime(self.ctx, s)
                if s.status == "live":  # D-361: read back by a new process (STORE=firestore): its timers again
                    await rt.rearm_timers()
        return rt

    async def session_loaded(self, session_id: str) -> None:
        """The store read this session back from Firestore (a restart, or it was evicted): counter ids (mock mode)
        continue after the ones the session already has. D-428: the event seq continues after the stored high-water
        mark (D-380/381), so no jump is added here."""
        for name in SUBCOLLECTIONS:
            for doc_id in self.ctx.store.document_ids(sub(session_id, name)):
                self.ctx.ids.observe(doc_id, session_id)

    async def evict(self, session_id: str) -> bool:
        """An ended session leaves memory (SESSION_EVICT_AFTER_SEC after its summary); Firestore keeps it and it is
        read back when someone opens it. A session that is not ended, or whose writes are not all in Firestore, stays."""
        store = self.ctx.store
        if not hasattr(store, "evict"):
            return False
        s = await store.get(SESSIONS, session_id, Session)
        if s is None or s.status != "ended":
            return False
        if not await store.evict(session_id):
            return False
        await self.drop(session_id)
        self.ctx.bus.forget_session(session_id)
        log.info("session %s left memory; Firestore keeps it", session_id)
        return True

    async def drop(self, session_id: str) -> None:
        rt = self._by_id.pop(session_id, None)
        if rt is not None:
            rt.shutdown()

    def shutdown(self) -> None:
        for rt in self._by_id.values():
            rt.shutdown()
        self._by_id.clear()
