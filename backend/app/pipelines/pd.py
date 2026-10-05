"""AI PD director (PLANNING 5.1.1): one action card for the host, chosen on broadcast events.

Red compliance alerts and fact notes never pass through here. The director listens to the events
the runtime already emits, builds verified candidates (`logic.pd`), lets the ADK agent pick one
(rule fallback on any failure, and always under the mock provider), and keeps the card stable:
it is not replaced before `hold_until`, and it ends when its condition is met.

`on_event` and `on_tick` are called while the runtime may hold `rt.lock`, so they only schedule
work; `_decide` takes the lock itself.
"""
from __future__ import annotations

import collections
import logging
from typing import TYPE_CHECKING

from ..logic import pd as pdl
from ..logic.prompter import points_of, required_ids
from ..models.session import PdCard

if TYPE_CHECKING:
    from .runtime import SessionRuntime

log = logging.getLogger(__name__)

TRIGGERS = frozenset({"transcript.final", "prompter.updated", "hostqueue.updated", "group.updated",
                      "promo.started", "promo.ended", "segment.started", "alert.created", "alert.updated"})
PD_DEADLINE_MS = 2500
MIN_GAP_MS = 1000  # at most one decision per second


class PdDirector:
    def __init__(self, rt: "SessionRuntime") -> None:
        self.rt = rt
        self.agent = None
        st = rt.settings
        if st.LLM_PROVIDER == "vertex":
            try:
                from ..agents.ai_pd import AiPd
                self.agent = AiPd(project=st.GCP_PROJECT, location=st.LLM_LOCATION, model=st.LLM_FAST_MODEL,
                                  thinking_level=st.LLM_FAST_THINKING, prompts_dir=st.prompts_path)
            except Exception as e:  # noqa: BLE001 - the rule fallback keeps the show running
                log.warning("AI PD agent unavailable, using rules: %s", e)
        self.recent: collections.deque[str] = collections.deque(maxlen=3)
        self.last_final_at: int | None = None
        self.dismissed: dict[str, set[str]] = collections.defaultdict(set)  # segment_id -> refs
        self.latencies: list[int] = []
        self.statuses: collections.Counter[str] = collections.Counter()
        self._running = False
        self._again = False
        self._last_decision_at = 0
        self._last_cands: tuple[str, ...] = ()
        # D-113 pacing
        self.mentioned: set[str] = set()  # groups the host named or read out (context judge)
        self.last_question_card_at: int | None = None
        self.last_shout_at: int | None = None
        self.used_shouts: set[str] = set()
        self._pull = False

    # ---- inputs (never take the lock here) ------------------------------------------------------

    def on_event(self, type_: str, payload) -> None:
        if type_ == "transcript.final":
            self.last_final_at = self.rt.now()
            text = getattr(payload, "judged_text", None) or getattr(payload, "text", None)
            if text:
                self.recent.append(text)
        if type_ in TRIGGERS:
            self.trigger()

    def on_tick(self) -> None:
        self.trigger()

    def trigger(self) -> None:
        if not self.rt.assistant:
            return  # D-139: no AI PD without the assistant
        if self._running:
            self._again = True
            return
        self._running = True
        self.rt.spawn(self._loop(), name=f"pd:{self.rt.sid}")

    async def _loop(self) -> None:
        try:
            while True:
                self._again = False
                await self._decide()
                if not self._again:
                    return
        except Exception:  # noqa: BLE001
            log.exception("AI PD decision failed")
        finally:
            self._running = False

    # ---- state ----------------------------------------------------------------------------------

    async def _state(self) -> pdl.PdState | None:
        rt = self.rt
        s = await rt.load_session()
        seg = await rt.current_segment()
        if s.status != "live" or seg is None:
            return None
        now = rt.now()
        groups = {g.group_id: g for g in await rt.groups()}
        questions = []
        deferrals = rt.pack.notices.host_deferrals
        solo = "_solo" if s.show_mode == "solo" else ""  # a solo host promises no chat reply
        for slot in s.host_slots:  # the host's waiting list, in order (D-113)
            g = groups.get(slot.group_id)
            if g is None or g.status in ("answered", "closed", "rejected") or g.host_verbal_answer_transcript_id:
                continue
            askers = len(g.unique_author_ids)
            # D-146: how long it has waited on the host's list, and whether it may not wait long
            extra = {"waiting_ms": now - (slot.on_host_since or now),
                     "urgent": rt.intent(g.intent).sensitive or askers >= rt.settings.HOST_REPEAT_THRESHOLD}
            if g.status == "needs_review" and g.route_reason == "unresolved_product":
                if g.group_id not in self.mentioned:
                    questions.append(pdl.Question(g.group_id, g.canonical_question, None, "clarify", askers,
                                                  slot.pinned, **extra))
                continue
            a = await rt.get_answer(g.answer_id)
            if g.route_reason == "general":
                # D-140: a general question gets the general deferral card only once enough viewers ask
                if askers >= rt.settings.HOST_REPEAT_THRESHOLD:
                    questions.append(pdl.Question(g.group_id, g.canonical_question,
                                                  deferrals["general" + solo], "answer", askers,
                                                  slot.pinned, **extra))
                continue
            if g.status == "needs_review" and g.route_reason == "no_verified_answer":
                # D-135: no verified answer: the host says so honestly instead of guessing
                kind = "sensitive" if rt.intent(g.intent).sensitive else "general"
                questions.append(pdl.Question(g.group_id, g.canonical_question, deferrals[kind + solo],
                                              "answer", askers, slot.pinned, **extra))
                continue
            if a is None or not a.verified:
                continue  # still drafting: it waits in the list, no card yet
            if g.status == "auto_answered":  # AI answered in chat, many asked: the host reads it out
                if g.group_id not in self.mentioned:
                    questions.append(pdl.Question(g.group_id, g.canonical_question, a.text, "read", askers,
                                                  slot.pinned, **extra))
            else:  # D-135: a sensitive question with a verified draft shows the draft (it is on the sheet)
                questions.append(pdl.Question(g.group_id, g.canonical_question, a.text, "answer", askers,
                                              slot.pinned, **extra))
        promos = []
        for ap in s.active_promos:
            p = rt.promo(ap.promo_id)
            if p is not None:
                promos.append(pdl.PromoState(ap.promo_id, p.viewer_text, ap.started_at, ap.ends_at))
        high = pdl.red_blocks(await rt.alerts(), now)
        nxt = rt.catalog.next_product(seg.product_id)
        return pdl.PdState(
            now=now, segment_id=seg.segment_id, product_id=seg.product_id,
            product_name=rt.catalog.get_product(seg.product_id).name, started_at=seg.started_at,
            planned_ms=seg.planned_duration_sec * 1000, points=points_of(rt.catalog, seg.product_id, rt.points),
            required_ids=required_ids(rt.catalog, seg.product_id), covered_ids=list(seg.covered_point_ids),
            next_product=(nxt, rt.catalog.get_product(nxt).name) if nxt else None, questions=questions,
            promos=promos, high_alert_active=high, last_final_at=self.last_final_at, recent_lines=list(self.recent),
            dismissed_refs=frozenset(self.dismissed[seg.segment_id]),
            product_names=[rt.catalog.get_product(i.product_id).name for i in rt.catalog.runsheet.items],
            last_question_card_at=self.last_question_card_at, last_shout_at=self.last_shout_at, pull=self._pull,
            shoutouts=[so for so in rt.shoutouts
                       if so.comment_id not in self.used_shouts and now - so.at <= pdl.SHOUT_MAX_AGE_MS])

    @staticmethod
    def is_done(card: PdCard, st: pdl.PdState) -> bool:
        if card.segment_id != st.segment_id:
            return True  # the product changed: every card of the old segment is over
        if card.kind == "cover_point":
            return card.ref_id in st.covered_ids
        if card.kind in pdl.QUESTION_KINDS:  # answered, read out or named by the host, or gone from the list
            return card.ref_id not in {q.group_id for q in st.questions}
        if card.kind == "promo":
            return card.ref_id not in {p.promo_id for p in st.promos}
        return False

    # ---- decision -------------------------------------------------------------------------------

    async def _decide(self) -> None:
        rt = self.rt
        async with rt.lock:
            st = await self._state()
            if st is None:
                return
            s = await rt.load_session()
            card = s.pd_card
            if card is not None and card.status == "active":
                if self.is_done(card, st):
                    await self._end_locked(card, "done")
                    card = None
                elif st.high_alert_active or st.now < card.hold_until:
                    return
            if st.high_alert_active:
                return
            cands = pdl.candidates(st)
            if card is not None and card.kind in pdl.QUESTION_KINDS:
                # D-113: a question card stays until it ends; only a pushed or pulled question or a promo replaces it
                cands = [c for c in cands if c.priority <= 1 and c.ref_id != card.ref_id]
            if not cands:
                return
            # D-153: the priority is part of the key, so a question that becomes due is decided again
            key = tuple((c.cid, c.priority) for c in cands)
            if key == self._last_cands:
                return  # nothing new since the last decision (a card or "none"): no repeated model calls
            if st.now - self._last_decision_at < MIN_GAP_MS:
                return  # the 1 s tick asks again; re-looping here spins forever under a frozen test clock
            self._last_decision_at, self._last_cands = st.now, key
            state = {"product": st.product_name, "elapsed_s": (st.now - st.started_at) // 1000,
                     "planned_s": st.planned_ms // 1000, "silent": st.silent, "recent_lines": st.recent_lines,
                     "next_product": st.next_product[1] if st.next_product else None,
                     "current_card": card.say if card else None}
            payload = [{"id": c.cid, "kind": c.kind, "say": c.say, "detail": c.detail} for c in cands]
        chosen, source, reason = None, "rule", "rule fallback"
        # D-163 (local SEED1 replay): a due card is offered only at a break; a model call longer than the break
        # (timeouts took ~2.1 s) made the re-check below drop it. A pulled, pushed or due question has no choice to
        # make (D-153: the rules show it anyway), so the rules decide at once.
        forced = any(c.forced for c in cands)
        if forced:
            reason = "due question"
        if self.agent is not None and not forced:
            choice, ms, status = await self.agent.choose(state, payload, PD_DEADLINE_MS)
            self.latencies.append(ms)
            self.statuses[status] += 1
            if choice is not None:
                if choice.choice == "none":
                    return
                chosen = next((c for c in cands if c.cid == choice.choice), None)
                source, reason = "ai", choice.reason
        if chosen is None:
            chosen = pdl.rule_pick(cands)
        if chosen is None:
            return
        async with rt.lock:
            st = await self._state()  # the show moved on while the model thought: re-check
            if st is None or st.high_alert_active or chosen.cid not in {c.cid for c in pdl.candidates(st)}:
                return
            s = await rt.load_session()
            old = s.pd_card
            if old is not None and old.status == "active":
                if old.ref_id == chosen.ref_id:
                    if old.say != chosen.say:  # same card, fewer points left (D-107): refresh its text
                        s = await rt.load_session()
                        s.pd_card = old.model_copy(update={"say": chosen.say, "detail": chosen.detail})
                        await rt.save_session(s)
                        await rt.emit("pd.card", s.pd_card)
                    return
                if st.now < old.hold_until and not self.is_done(old, st):
                    return
                await self._end_locked(old, "expired")
            new = PdCard(card_id=rt.new_id("pd_"), kind=chosen.kind, say=chosen.say, detail=chosen.detail,
                         ref_id=chosen.ref_id, created_at=st.now, hold_until=st.now + pdl.HOLD_MS,
                         source=source, reason=reason[:120], segment_id=st.segment_id, askers=chosen.askers)
            if chosen.kind in pdl.QUESTION_KINDS:
                self.last_question_card_at, self._pull = st.now, False
            elif chosen.kind == "shout_out":
                self.last_shout_at = st.now
                self.used_shouts.add(chosen.ref_id)
            s = await rt.load_session()
            s.pd_card = new
            await rt.save_session(s)
            await rt.emit("pd.card", new)

    async def _end_locked(self, card: PdCard, status: str) -> None:
        rt = self.rt
        ended = card.model_copy(update={"status": status})
        s = await rt.load_session()
        s.pd_card = None
        await rt.save_session(s)
        await rt.emit("pd.card", ended)

    def pull(self) -> None:
        """The host takes the top waiting question now: no gap, no pause needed (D-113)."""
        self._pull = True
        self._last_cands = ()
        self.trigger()

    def mention(self, group_id: str) -> None:
        """The context judge linked a host sentence to this question (answer, read-out or "which product")."""
        self.mentioned.add(group_id)
        self.trigger()

    async def dismiss(self, card_id: str) -> PdCard | None:
        rt = self.rt
        async with rt.lock:
            s = await rt.load_session()
            card = s.pd_card
            if card is None or card.card_id != card_id or card.status != "active":
                return None
            if card.segment_id:
                self.dismissed[card.segment_id].add(card.ref_id)
            self._last_cands = ()
            await self._end_locked(card, "dismissed")
        self.trigger()
        return card.model_copy(update={"status": "dismissed"})
