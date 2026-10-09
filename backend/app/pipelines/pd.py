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
from ..logic.promos import promo_cue
from ..logic.prompter import points_of, required_ids
from ..models.session import PdCard

if TYPE_CHECKING:
    from .runtime import SessionRuntime

log = logging.getLogger(__name__)

TRIGGERS = frozenset({"transcript.final", "prompter.updated", "hostqueue.updated", "group.updated",
                      "promo.started", "promo.ended", "segment.started", "alert.created", "alert.updated"})
PD_DEADLINE_MS = 4000  # D-166: gemini-3.8-flash LOW (p95 ~4 s direct); the rules decide on a timeout
MIN_GAP_MS = 1000  # at most one decision per second


class PdDirector:
    def __init__(self, rt: "SessionRuntime") -> None:
        self.rt = rt
        self.agent = None
        st = rt.settings
        if st.LLM_PROVIDER == "vertex":
            try:
                from ..agents.ai_pd import AiPd
                # D-166: the quality model at PD_THINKING (flash-lite chose no better than the rules)
                self.agent = AiPd(project=st.GCP_PROJECT, location=st.LLM_LOCATION, model=st.LLM_QUALITY_MODEL,
                                  thinking_level=st.PD_THINKING, prompts_dir=st.prompts_path)
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
        self.last_shout_at: int | None = None
        self.used_shouts: set[str] = set()

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
        # D-429: no question cards; a shout-out still waits while a question is open on the host's list
        waiting = any((g := groups.get(slot.group_id)) is not None and g.status not in ("answered", "closed", "rejected")
                      and not g.host_verbal_answer_transcript_id for slot in s.host_slots)
        promos = []
        price, offers = await rt.active_price_promo(), await rt.active_offers()
        for ap in s.active_promos:
            p = rt.promo(ap.promo_id)
            # D-210: the card text is built from the live state (prices, time left); a stale notice is not shown
            text = promo_cue(p, rt.catalog, price, ap.ends_at, now, offers) if p is not None else None
            if text is not None:
                promos.append(pdl.PromoState(ap.promo_id, text, ap.started_at, ap.ends_at))
        block = pdl.alert_blocks(await rt.alerts(), now)
        nxt = rt.catalog.next_product(seg.product_id)
        return pdl.PdState(
            now=now, segment_id=seg.segment_id, product_id=seg.product_id,
            product_name=rt.catalog.get_product(seg.product_id).name, started_at=seg.started_at,
            planned_ms=seg.planned_duration_sec * 1000, points=points_of(rt.catalog, seg.product_id, rt.points),
            required_ids=required_ids(rt.catalog, seg.product_id), covered_ids=list(seg.covered_point_ids),
            next_product=(nxt, rt.catalog.get_product(nxt).name) if nxt else None, questions_waiting=waiting,
            promos=promos, alert_block=block, last_final_at=self.last_final_at, recent_lines=list(self.recent),
            dismissed_refs=frozenset(self.dismissed[seg.segment_id]), last_shout_at=self.last_shout_at,
            shoutouts=[so for so in rt.shoutouts
                       if so.comment_id not in self.used_shouts and now - so.at <= pdl.SHOUT_MAX_AGE_MS])

    @staticmethod
    def is_done(card: PdCard, st: pdl.PdState) -> bool:
        if card.segment_id != st.segment_id:
            return True  # the product changed: every card of the old segment is over
        if card.kind in ("answer_question", "read_question", "clarify_product"):
            return True  # D-431: a question card stored before D-429; nothing else would end it
        if card.kind == "cover_point":
            return card.ref_id in st.covered_ids
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
                elif st.alert_block or st.now < card.hold_until:
                    return
            if st.alert_block:
                return
            cands = pdl.candidates(st)
            if not cands:
                return
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
        if self.agent is not None:
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
            if st is None or st.alert_block or chosen.cid not in {c.cid for c in pdl.candidates(st)}:
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
                         source=source, reason=reason[:120], segment_id=st.segment_id)
            if chosen.kind == "shout_out":
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
