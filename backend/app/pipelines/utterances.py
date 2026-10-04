"""Utterance pipeline (DEV_SPEC §8.2) and host-side operator actions (alerts, cues, switch, undo).

Preparation runs in transcript order. All finals infer concurrently; compliance and facts apply
immediately under the runtime lock. Context and all-verdict publication each have an ordered chain.

Judges (D-101): with `JUDGE_MODE=split3` (default) the ComplianceJudge, the ContextJudge and the
FactChecker read each final in parallel. The compliance verdict is applied the moment it arrives
(red alerts, corrections); context verdicts (prompter, cues, switch) apply in transcript order. The
host-answer publish decision waits for all three and is skipped if either judge failed. With
`JUDGE_MODE=split` one UtteranceJudge does both judges' jobs (rollback).

Split sentences (D-088): speech-to-text can end a final in mid-sentence ("…it does not" / "treat
acne."). When the previous final arrived within UTTERANCE_MERGE_WINDOW_MS and does not end with
. ? or !, the new final is judged together with it: reflex, judge and fact checker get the joined
text. Nothing waits; the previous final was already judged on its own, and the merged judgment
replaces that judgment for switch cues and host-answer linking. Alerts raised by the fragments are
never resolved by the merged judgment, and their rules get no second alert. Prompter coverage only
adds (covered points are never removed, §6).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..agents.fact_checker import FactChecker, FactInput, gather_fact_passages
from ..agents.split_judges import ComplianceJudge, ContextJudge
from ..agents.utterance_judge import JudgeInput, UtteranceJudge, build_judge_values, say_instead_fallback
from ..logic import alerts as alert_logic
from ..logic import facts as fact_logic
from ..logic.corrections import check_correction, says_the_replacement
from ..logic import publish as publish_logic
from ..logic import qualifier
from ..logic.prompter import apply_coverage, missing_required, points_of, prompter_view
from ..logic.segments import classify_switch, expire, names_product, replace_cue, step_switch, withdraw_cue
from ..models.agent_io import ComplianceOutput, ContextOutput, FactCheckOutput, UtteranceJudgeOutput
from ..models.session import Alert, Answer, HostCue, Message, QuestionGroup, Segment, SwitchState, Transcript
from ..providers.llm import AgentResult
from .comments import answer_key
from .runtime import ActionError

if TYPE_CHECKING:
    from .runtime import SessionRuntime

log = logging.getLogger(__name__)


def _result(task: asyncio.Task) -> AgentResult:
    """A finished judge task's result; a crash counts as a failed call."""
    try:
        return task.result()
    except Exception as e:  # noqa: BLE001 - one judge crashing must not stop the pipeline
        log.exception("judge task crashed")
        return AgentResult(status="error", output=None, latency_ms=0, call_id="", error=repr(e))

SENTENCE_END = (".", "?", "!")
MAX_MERGED_FINALS = 3  # a merged judgment covers at most this many finals
_KEEP_JUDGED = 20  # judgments remembered for merging (only the last one is ever needed)


def ends_sentence(text: str) -> bool:
    """True when a final ends with . ? or ! (closing quotes and brackets ignored)."""
    return text.rstrip().rstrip("\"'”’)]").endswith(SENTENCE_END)


@dataclass
class Merge:
    """The previous final(s) a new final is judged with (D-088)."""
    prev: Transcript
    chain: list[str]  # transcript ids already inside `text`, oldest first
    text: str  # joined text that reflex, judge and fact checker read


@dataclass
class Judged:
    """What one transcript's judgment covered and changed, so a merged judgment can replace it."""
    chain: list[str]  # transcript ids whose words were judged, ending with this one
    text: str
    publish: tuple[str, str] | None = None  # (group_id, action) applied by this judgment


class UtterancePipeline:
    def __init__(self, rt: "SessionRuntime") -> None:
        self.rt = rt
        ctx = rt.ctx
        self.single = rt.settings.JUDGE_MODE == "single"
        self.split3 = rt.settings.JUDGE_MODE == "split3"
        self.judge = UtteranceJudge(ctx.llm, ctx.prompts, rt.catalog, ctx.reflex, single=self.single)
        self.compliance = ComplianceJudge(ctx.llm, ctx.prompts, rt.catalog, ctx.reflex)
        self.context = ContextJudge(ctx.llm, ctx.prompts, rt.catalog, ctx.reflex)
        self.facts = FactChecker(ctx.llm, ctx.prompts["fact_checker"], rt.catalog)
        self._main_tail: asyncio.Task | None = None
        self._side_tail: asyncio.Task | None = None
        self._context_tail: asyncio.Task | None = None
        self._pending: set[asyncio.Task] = set()
        self._sequence: dict[str, int] = {}
        self._prepared: dict[str, tuple[Transcript, str, Merge | None]] = {}
        self._applied: set[tuple[str, str]] = set()
        self._fact_sequence: dict[tuple[str, str], tuple[int, str, str]] = {}
        self._segment_generation = 0
        self._generations: dict[str, int] = {}
        self._segments: dict[str, str] = {}
        self._last: Transcript | None = None  # previous final in the main chain
        self._judged: dict[str, Judged] = {}

    def _claim_application(self, t: Transcript, kind: str) -> bool:
        key = (t.transcript_id, kind)
        if key in self._applied:
            return False
        self._applied.add(key)
        return True

    def _reconcile_late_alert(self, a: Alert, t: Transcript, now: int) -> None:
        if a.kind != "compliance" or a.status != "active":
            return
        for later, text, merge in self._prepared.values():
            if (self._sequence[later.transcript_id] <= self._sequence[t.transcript_id]
                    or later.segment_id != t.segment_id or (merge and t.transcript_id in merge.chain)):
                continue
            check = check_correction(text, a, self.rt.catalog.get_product(a.product_id).approved_claims,
                                     self.rt.ctx.reflex)
            if check.ok:
                alert_logic.apply_corrections([a], [a.alert_id], later, now)
                return

    # ---- intake --------------------------------------------------------------------------------

    async def submit(self, text: str, *, source: str, speech_end_at: int | None = None,
                     speech_start_at: int | None = None, scenario: str = "default") -> Transcript:
        rt = self.rt
        text = text.strip()
        if not text:
            raise ActionError(400, "empty_transcript", "transcript text is empty")
        s = await rt.load_session()
        if s.status != "live":
            raise ActionError(409, "invalid_state", "transcripts are accepted only while live")
        seg = await rt.current_segment()
        now = rt.now()
        t = Transcript(transcript_id=rt.new_id("tr_"), text=text, is_final=True, speech_start_at=speech_start_at,
                       speech_end_at=speech_end_at or now, received_at=now, source=source,
                       segment_id=seg.segment_id if seg else "")
        self._generations[t.transcript_id] = self._segment_generation
        self._segments[t.transcript_id] = t.segment_id
        prev = self._main_tail
        self._main_tail = rt.spawn(self._main(prev, t, scenario), name=f"utterance:{t.transcript_id}")
        return t

    async def drain(self) -> None:
        if self._main_tail is not None:
            await asyncio.gather(self._main_tail, return_exceptions=True)
        await asyncio.gather(*tuple(self._pending), return_exceptions=True)

    # ---- steps 1-4 -----------------------------------------------------------------------------

    def _merge_for(self, t: Transcript) -> Merge | None:
        """D-088: join with the previous final if it arrived within the window and is unfinished."""
        prev = self._last
        window = self.rt.settings.UTTERANCE_MERGE_WINDOW_MS
        if (prev is None or window <= 0 or t.received_at - prev.received_at > window or ends_sentence(prev.text)
                or prev.segment_id != t.segment_id
                or self._generations.get(prev.transcript_id) != self._generations.get(t.transcript_id)):
            return None
        judged = self._judged.get(prev.transcript_id)
        chain = judged.chain if judged else [prev.transcript_id]
        if len(chain) >= MAX_MERGED_FINALS:
            return None
        base = judged.text if judged else prev.text
        return Merge(prev=prev, chain=list(chain), text=f"{base} {t.text}")

    def _remember(self, t: Transcript, merge: Merge | None, text: str) -> None:
        self._last = t
        self._judged[t.transcript_id] = Judged(chain=[*(merge.chain if merge else []), t.transcript_id], text=text)
        self._sequence[t.transcript_id] = len(self._sequence) + 1
        self._prepared[t.transcript_id] = (t, text, merge)

    async def _main(self, prev: asyncio.Task | None, t: Transcript, scenario: str) -> None:
        if prev is not None:
            await asyncio.gather(prev, return_exceptions=True)
        rt = self.rt
        merge = self._merge_for(t)
        text = merge.text if merge else t.text
        if merge:
            t.merged_from_transcript_id, t.judged_text = merge.prev.transcript_id, text
        self._remember(t, merge, text)
        # 1. store, emit
        await rt.ctx.store.put(rt.path("transcripts"), t.transcript_id, t)
        await rt.emit("transcript.final", t)
        # 2. reflex -> provisional alerts
        hits = rt.ctx.reflex.scan(text)
        async with rt.lock:
            seg = await rt.get_segment(t.segment_id) if t.segment_id else await rt.current_segment()
            on_air = seg.product_id if seg else rt.catalog.order[0]
            alerts = await rt.alerts()
            provisional = alert_logic.provisional_from_reflex(hits, t, on_air, alerts, rt.new_id, rt.now())
            for a in provisional:
                await rt.save_alert(a)
                await rt.emit("alert.created", a)
            judge_input, offered = await self._judge_input_locked(t, text, merge, on_air, scenario)
        # Only preparation waits for the previous final.
        ready = asyncio.Future()
        previous_context = self._context_tail
        self._context_tail = rt.spawn(self._ordered_context(previous_context, ready, t, merge),
                                      name=f"context-apply:{t.transcript_id}")
        inference = rt.spawn(self._infer(t, on_air, judge_input, hits, merge, scenario, ready),
                             name=f"inference:{t.transcript_id}")
        self._side_tail = rt.spawn(self._ordered_publish(self._side_tail, inference, self._context_tail,
                                                       t, offered, merge), name=f"publish:{t.transcript_id}")
        for task in (inference, self._context_tail, self._side_tail):
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)

    async def _ordered_context(self, previous, ready, t, merge) -> None:
        verdict = await ready
        if previous is not None:
            await asyncio.gather(previous, return_exceptions=True)
        if verdict is not None:
            async with self.rt.lock:
                await self._apply_context_locked(t, verdict, merge)

    async def _ordered_publish(self, previous, inference, context, t, offered, merge) -> None:
        judge, facts = await inference
        await asyncio.gather(context, return_exceptions=True)
        if previous is not None:
            await asyncio.gather(previous, return_exceptions=True)
        if judge is not None:
            async with self.rt.lock:
                await self._publish_locked(t, judge, facts, offered, merge)
        # Publication is ordered, so its completed prefix is no longer needed for merging.
        cutoff = self._sequence[t.transcript_id] - _KEEP_JUDGED
        for tid in list(self._judged):
            if self._sequence[tid] < cutoff:
                self._judged.pop(tid, None)
                self._prepared.pop(tid, None)

    async def _infer(self, t, on_air, inp, hits, merge, scenario, ready):
        rt = self.rt
        comp = ctx = facts = None
        waiting = set()
        try:
            if self.single:
                inp.passages = await self._fact_passages(inp.utterance, on_air, inp.switch)
            if self.split3:
                values = build_judge_values(rt.catalog, inp)
                comp_task = rt.spawn(self.compliance.run(inp, deadline_ms=rt.settings.JUDGE_TIMEOUT_MS,
                                                         values=values), name=f"compliance:{t.transcript_id}")
                ctx_task = rt.spawn(self.context.run(inp, deadline_ms=rt.settings.JUDGE_TIMEOUT_MS,
                                                     values=values), name=f"context:{t.transcript_id}")
            else:
                comp_task = rt.spawn(self.judge.run(inp, deadline_ms=rt.settings.JUDGE_TIMEOUT_MS),
                                     name=f"judge:{t.transcript_id}")
                ctx_task = None
            facts_task = None if self.single else rt.spawn(self._run_facts(inp.utterance, on_air, inp, scenario),
                                                           name=f"facts:{t.transcript_id}")
            waiting = {task for task in (comp_task, ctx_task, facts_task) if task is not None}
            while waiting:
                done, waiting = await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
                for task in sorted(done, key=lambda task: (task is not comp_task, task is not facts_task)):
                    res = _result(task)
                    output = res.output if res.status == "ok" else None
                    if task is comp_task:
                        comp = output
                        async with rt.lock:
                            await self._apply_compliance_locked(t, on_air, res, hits, merge)
                        if not self.split3:
                            ctx = output
                            ready.set_result(ctx)
                            if self.single:
                                facts = output.facts if output is not None else None
                                if facts is not None:
                                    async with rt.lock:
                                        await self._apply_facts_locked(t, facts, set(merge.chain) if merge else set())
                    elif task is ctx_task:
                        ctx = output
                        ready.set_result(ctx)
                    else:
                        facts = output
                        if facts is not None:
                            async with rt.lock:
                                await self._apply_facts_locked(t, facts, set(merge.chain) if merge else set())
            if comp is None or ctx is None:
                return None, facts
            if self.split3:
                comp = UtteranceJudgeOutput(compliance=comp.compliance, correction=comp.correction,
                                            answer=ctx.answer, prompter=ctx.prompter,
                                            reason=f"{comp.reason} | {ctx.reason}")
            return comp, facts
        finally:
            if waiting:
                await asyncio.gather(*waiting, return_exceptions=True)
            if not ready.done():
                ready.set_result(None)

    async def _judge_input_locked(self, t: Transcript, text: str, merge: Merge | None, on_air: str,
                                  scenario: str) -> tuple[JudgeInput, dict[str, Answer | None]]:
        rt = self.rt
        s = await rt.load_session()
        alerts = [a for a in await rt.alerts() if a.transcript_id != t.transcript_id]
        finals = await rt.ctx.store.query(rt.path("transcripts"), Transcript, order_by="received_at")
        inside = {t.transcript_id, *(merge.chain if merge else [])}  # already in the utterance text
        previous = [x.text for x in finals if x.transcript_id not in inside][-2:]
        questions = await self._open_questions_locked(s, on_air)
        promo = rt.promo(s.active_promo_id)
        card = s.pd_card  # D-112: the answer card on screen, else the first question slot
        on_screen = (card.ref_id if card is not None and card.status == "active" and card.kind == "answer_question"
                     else s.host_slots[0].group_id if s.host_slots else None)
        inp = JudgeInput(utterance=text, on_air=on_air, active_alerts=alerts, open_questions=questions,
                         cue=s.cue, previous=previous, points_by_product=rt.points or None, session_id=rt.sid, scenario=scenario,
                         switch=s.switch, promo=promo, on_screen_group_id=on_screen)
        # D-110: remember which verified answer was shown with each question, to bind a spoken-answer post
        offered: dict[str, Answer | None] = {}
        for g, _ in questions:
            ans = await rt.get_answer(g.answer_id)
            offered[g.group_id] = ans if ans is not None and ans.verified else None
        return inp, offered

    async def _open_questions_locked(self, s, on_air: str) -> list[tuple[QuestionGroup, str | None]]:
        """§7.3: groups on the host screen first, then the best HOST/AUTO candidates of the product."""
        rt = self.rt
        limit = rt.settings.JUDGE_MAX_OPEN_QUESTIONS
        groups = {g.group_id: g for g in await rt.groups()}
        chosen = [groups[sl.group_id] for sl in s.host_slots if sl.group_id in groups]
        rest = [g for g in groups.values()
                if g.group_id not in {c.group_id for c in chosen} and g.product_id == on_air
                and g.route in ("HOST", "AUTO") and g.status in ("ready", "auto_answered")
                and g.host_verbal_answer_transcript_id is None]
        rest.sort(key=lambda g: g.score, reverse=True)
        out = []
        for g in (chosen + rest)[:limit]:
            answer = await rt.get_answer(g.answer_id)
            out.append((g, answer.text if answer is not None and answer.verified else None))
        return out

    async def _fact_passages(self, text: str, on_air: str, switch: SwitchState):
        rt = self.rt
        rt.sync_doc_version()
        return await gather_fact_passages(rt.ctx.retriever, rt.catalog, rt.prefetched, utterance=text, on_air=on_air,
                                          switch=switch, search_timeout_ms=rt.settings.FACT_SEARCH_TIMEOUT_MS)

    async def _run_facts(self, text: str, on_air: str, judge_input: JudgeInput, scenario: str) -> AgentResult:
        passages = await self._fact_passages(text, on_air, judge_input.switch)
        return await self.facts.run(
            FactInput(utterance=text, on_air=on_air, switch=judge_input.switch, promo=judge_input.promo,
                      passages=passages, previous=judge_input.previous, session_id=self.rt.sid, scenario=scenario),
            deadline_ms=self.rt.settings.FACT_TIMEOUT_MS,
        )

    async def _apply_compliance_locked(self, t: Transcript, on_air: str, res: AgentResult, hits,
                                       merge: Merge | None = None) -> None:
        """§8.4.1 alerts and §8.4.5 corrections, or §8.4.3 fail toward warning. `res.output` is a
        ComplianceOutput or a full judge output."""
        rt = self.rt
        if not self._claim_application(t, "compliance"):
            return
        now = rt.now()
        alerts = await rt.alerts()
        provisional = [a for a in alerts if a.transcript_id == t.transcript_id and a.status == "provisional"]
        # D-088: alerts raised by the fragments inside a merged utterance are never resolved by it
        protected = set(merge.chain) if merge else set()
        text = merge.text if merge else t.text
        high_before = alert_logic.high_alert_active(alerts)
        judge = res.output if res.status == "ok" else None
        duplicate_rules = {a.rule_id for a in alerts if a.kind == "compliance" and a.status == "active"
                           and (a.transcript_id in protected or
                                (a.transcript_id != t.transcript_id and
                                 t.transcript_id in self._judged.get(a.transcript_id, Judged([], "")).chain))}
        if judge is None:
            # §8.4.3 judge failed: fail toward warning
            changed = alert_logic.apply_judge_failure(provisional, hits, say_instead_fallback(rt.catalog, on_air), now)
            for a in changed:
                if a.rule_id in duplicate_rules:
                    a.status = "cleared"
                self._reconcile_late_alert(a, t, now)
                await self._save_alert_change_locked(a)
            await rt.emit("judge.failed", {"transcript_id": t.transcript_id, "status": res.status,
                                           "alert_ids": [a.alert_id for a in changed if a.status == "active"]})
            # D-098: the replacement wording still corrects an alert without the judge
            await self._apply_corrections_locked(t, text, [], protected, now)
        else:
            # D-088 dedupe: a rule already active from a fragment inside this merged utterance is the
            # same spoken claim, so no second alert. Separate sentences keep §8.4.2.
            active_rules = {a.rule_id for a in alerts
                            if a.kind == "compliance" and a.status == "active"
                            and (a.transcript_id in protected or
                                 t.transcript_id in self._judged.get(a.transcript_id, Judged([], "")).chain)}
            active_rules.update(a.rule_id for a in alerts if a.transcript_id == t.transcript_id
                                and a.status in ("corrected", "dismissed"))
            judge = judge.model_copy(deep=True)  # D-108: no second card while the same result's alert is active
            judge.compliance.violations = [
                v for v in judge.compliance.violations
                if not (v.rule_id == qualifier.RULE_ID and qualifier.is_repeat(v.say_instead or None, alerts, on_air))]
            changed, created = alert_logic.apply_judge_compliance(judge, t, on_air, provisional, rt.ctx.pack.rules_by_id,
                                                                  rt.new_id, now, active_rule_ids=active_rules)
            for a in created:
                self._reconcile_late_alert(a, t, now)
                await rt.save_alert(a)
                await rt.emit("alert.created", a)
                self._schedule_escalation(a)
            for a in changed:
                self._reconcile_late_alert(a, t, now)
                await self._save_alert_change_locked(a)
            # D-089: an apology alone does not correct a compliance alert
            await self._apply_corrections_locked(t, text, judge.correction.corrects_alert_ids, protected, now)
        # §8.4.7 a new HIGH alert resets switch counting and cancels a pending switch
        await self._high_alert_switch_reset_locked(high_before)

    async def _apply_context_locked(self, t: Transcript, judge: ContextOutput | UtteranceJudgeOutput,
                                    merge: Merge | None = None) -> None:
        """§8.7.1 prompter points and cues, §8.7.2 switch."""
        rt = self.rt
        if not self._claim_application(t, "context"):
            return
        s = await rt.load_session()
        seg = await rt.current_segment()
        if (seg is None or seg.segment_id != t.segment_id
                or self._generations.get(t.transcript_id) != self._segment_generation):
            return
        if seg is not None and judge.prompter.covered_point_ids:
            added, pre = apply_coverage(judge.prompter.covered_point_ids, seg, s, rt.catalog, rt.points)
            if added:
                await rt.save_segment(seg)
                await rt.emit("prompter.updated", prompter_view(rt.catalog, seg, rt.points))
            if pre:
                await rt.save_session(s)
        if s.cue is not None and s.cue.status == "active" and s.cue.cue_id in judge.prompter.covered_cue_ids:
            s.cue.status, s.cue.done_by_transcript_id = "done", t.transcript_id
            await rt.save_session(s)
            await rt.emit("cue.updated", s.cue)
        # §8.4.7 while a HIGH alert is active, counting resets and a pending switch cancels
        high_now = alert_logic.high_alert_active(await rt.alerts())
        if seg is not None:
            await self._switch_locked(judge, t, seg, high_became_active=high_now,
                                      replaces=merge.prev.transcript_id if merge else None,
                                      text=merge.text if merge else t.text)

    async def _apply_corrections_locked(self, t: Transcript, text: str, listed: list[str], protected: set[str],
                                        now: int) -> None:
        """Alerts the judge listed and the utterance really corrects (D-089), plus active alerts whose
        "Say this instead" wording the host just said, even if the judge missed it (D-098)."""
        rt = self.rt
        correctable = [a for a in await rt.alerts() if a.transcript_id not in protected
                       and self._sequence.get(a.transcript_id, 0) < self._sequence.get(t.transcript_id, 1)]
        accepted = self._substantive_corrections(correctable, listed, text) if listed else []
        for a in correctable:
            if (a.kind == "compliance" and a.status == "active" and a.transcript_id != t.transcript_id
                    and self._segments.get(a.transcript_id) == t.segment_id
                    and a.alert_id not in accepted and says_the_replacement(text, a)):
                log.info("correction of %s by its replacement wording: %r", a.alert_id, text)
                accepted.append(a.alert_id)
        if not accepted:
            return
        for a in alert_logic.apply_corrections(correctable, accepted, t, now):
            rt.ctx.scheduler.cancel(rt.key(f"escalate:{a.alert_id}"))
            await rt.save_alert(a)
            await rt.emit("alert.updated", a)

    def _substantive_corrections(self, alerts: list[Alert], listed: list[str], text: str) -> list[str]:
        """The listed compliance alerts that the utterance really corrects (D-089)."""
        rt = self.rt
        accepted: list[str] = []
        for a in alerts:
            if a.alert_id not in listed or a.kind != "compliance":
                continue
            check = check_correction(text, a, rt.catalog.get_product(a.product_id).approved_claims, rt.ctx.reflex)
            if check.ok:
                accepted.append(a.alert_id)
            else:
                log.info("correction of %s not accepted (%s): %r", a.alert_id, check.reason, text)
        return accepted

    async def _save_alert_change_locked(self, a: Alert) -> None:
        await self.rt.save_alert(a)
        await self.rt.emit("alert.updated", a)
        if a.status == "active":
            self._schedule_escalation(a)

    async def _high_alert_switch_reset_locked(self, high_before: bool) -> None:
        rt = self.rt
        if alert_logic.high_alert_active(await rt.alerts()) and not high_before:
            s = await rt.load_session()
            if s.switch.status != "idle":
                was_pending = s.switch.status == "pending"
                s.switch = SwitchState(last_commit=s.switch.last_commit)
                await rt.save_session(s)
                rt.ctx.scheduler.cancel(rt.key("switch-commit"))
                if was_pending:
                    await rt.emit("segment.switch_cancelled", {"reason": "compliance_alert"})

    def _schedule_escalation(self, a: Alert) -> None:
        """§8.4.4: a HIGH alert still active after COMPLIANCE_ESCALATE_SEC is escalated. No auto-expiry."""
        if a.kind != "compliance" or a.severity != "HIGH" or a.status != "active" or a.shown_at is None:
            return
        rt = self.rt

        async def escalate() -> None:
            async with rt.lock:
                cur = await rt.get_alert(a.alert_id)
                if cur is not None and cur.status == "active" and cur.escalated_at is None:
                    cur.escalated_at = rt.now()
                    await rt.save_alert(cur)
                    await rt.emit("alert.escalated", cur)

        rt.ctx.scheduler.call_at(rt.key(f"escalate:{a.alert_id}"),
                                 a.shown_at + rt.settings.COMPLIANCE_ESCALATE_SEC * 1000, escalate)

    def _product_names(self, product_id: str) -> list[str]:
        """Names that count as naming a product (D-090): full name and short name ("ampoule")."""
        p = self.rt.catalog.get_product(product_id)
        return [p.name, p.short_name.removeprefix("the ").strip()]

    async def _switch_locked(self, judge: ContextOutput | UtteranceJudgeOutput, t: Transcript, seg: Segment, *, high_became_active: bool,
                             replaces: str | None = None, text: str | None = None) -> None:
        rt = self.rt
        text = text if text is not None else t.text
        s = await rt.load_session()
        st = rt.settings
        on_air = seg.product_id
        nxt = rt.catalog.next_product(on_air)
        replacing = replaces is not None and replaces in s.switch.cue_transcript_ids
        # A merged judgment is classified as if its fragment's cue had not been counted (D-088).
        base = withdraw_cue(s.switch, replaces)[0] if replacing else s.switch
        kind = classify_switch(
            judge, expire(base, rt.now(), st.SWITCH_CUE_WINDOW_SEC), on_air=on_air, next_product=nxt,
            on_air_points={p.point_id for p in points_of(rt.catalog, on_air, rt.points)},
            next_points={p.point_id for p in points_of(rt.catalog, nxt, rt.points)} if nxt else set(),
            high_alert_became_active=high_became_active,
            next_named=bool(nxt) and names_product(text, self._product_names(nxt)),
        )
        if replacing and kind != "cancel":
            # D-088: the merged judgment replaces the fragment's cue. Never count the same cue twice.
            if kind == "cue":
                s.switch = replace_cue(s.switch, replaces, t.transcript_id)
                await rt.save_session(s)
                await rt.emit("segment.switch_counting", {
                    "target_product_id": s.switch.target_product_id, "cue_count": s.switch.cue_count,
                    "transcript_id": t.transcript_id, "replaces_transcript_id": replaces})
                return
            new_state, event = withdraw_cue(s.switch, replaces)
            was_pending = s.switch.status == "pending"
            s.switch = new_state
            await rt.save_session(s)
            if was_pending:
                rt.ctx.scheduler.cancel(rt.key("switch-commit"))
            if event == "cancelled":
                await rt.emit("segment.switch_cancelled", {"reason": "merged", "withdrawn_transcript_id": replaces})
            if new_state.status == "counting":
                await rt.emit("segment.switch_counting", {
                    "target_product_id": new_state.target_product_id, "cue_count": new_state.cue_count,
                    "transcript_id": None, "withdrawn_transcript_id": replaces})
            return
        st = rt.settings
        new_state, event = step_switch(s.switch, kind, transcript_id=t.transcript_id, next_product=nxt, now=rt.now(),
                                       cues_needed=st.SWITCH_CONSECUTIVE_CUES, window_sec=st.SWITCH_CUE_WINDOW_SEC,
                                       cancel_window_sec=st.SWITCH_CANCEL_WINDOW_SEC)
        if new_state == s.switch:
            return
        s.switch = new_state
        await rt.save_session(s)
        if event == "counting":
            await rt.emit("segment.switch_counting", {"target_product_id": new_state.target_product_id,
                                                      "cue_count": new_state.cue_count, "transcript_id": t.transcript_id})
        elif event == "pending":
            await rt.emit("segment.switch_counting", {"target_product_id": new_state.target_product_id,
                                                      "cue_count": new_state.cue_count, "transcript_id": t.transcript_id})
            await rt.emit("segment.switch_pending", {"target_product_id": new_state.target_product_id,
                                                     "commit_at": new_state.commit_at})
            rt.ctx.scheduler.call_at(rt.key("switch-commit"), new_state.commit_at, self._commit_timer)
        elif event == "cancelled":
            rt.ctx.scheduler.cancel(rt.key("switch-commit"))
            await rt.emit("segment.switch_cancelled", {"reason": "speech", "transcript_id": t.transcript_id})

    async def _commit_timer(self) -> None:
        rt = self.rt
        async with rt.lock:
            s = await rt.load_session()
            if s.status != "live" or s.switch.status != "pending" or s.switch.target_product_id is None:
                return
            await commit_switch_locked(rt, s.switch.target_product_id, "auto_speech")

    # ---- steps 5-6 -----------------------------------------------------------------------------

    async def _apply_facts_locked(self, t: Transcript, facts: FactCheckOutput, protected: set[str]) -> None:
        rt = self.rt
        if not self._claim_application(t, "facts"):
            return
        seq = self._sequence.get(t.transcript_id, 0)
        claims = []
        for claim in facts.claims:
            key = (claim.product_id, claim.field)
            latest = self._fact_sequence.get(key)
            if latest is not None and seq < latest[0]:
                newer = self._judged.get(latest[1])
                if not (latest[2] == "supported" and newer is not None
                        and t.transcript_id in newer.chain):
                    continue
            if claim.verdict in ("supported", "contradicted"):
                if latest is None or seq >= latest[0]:
                    self._fact_sequence[key] = (seq, t.transcript_id, claim.verdict)
            claims.append(claim)
        created, reshown, corrected = fact_logic.apply_fact_check(claims, await rt.alerts(), t, rt.new_id, rt.now(),
                                                                  protected=protected)
        for a in created:
            await rt.save_alert(a)
            await rt.emit("alert.created", a)
            self.schedule_fact_hide(a)
        for a in reshown:
            await rt.save_alert(a)
            await rt.emit("alert.updated", a)
            self.schedule_fact_hide(a)
        for a in corrected:
            rt.ctx.scheduler.cancel(rt.key(f"facthide:{a.alert_id}"))
            await rt.save_alert(a)
            await rt.emit("alert.updated", a)

    def schedule_fact_hide(self, a: Alert) -> None:
        """§8.5: the host stops showing an uncorrected note after FACT_NOTE_HOST_MAX_SEC."""
        rt = self.rt

        async def hide() -> None:
            async with rt.lock:
                cur = await rt.get_alert(a.alert_id)
                if cur is not None and cur.status == "active" and cur.host_hidden_at is None:
                    cur.host_hidden_at = rt.now()
                    await rt.save_alert(cur)
                    await rt.emit("alert.updated", cur)

        rt.ctx.scheduler.call_later(rt.key(f"facthide:{a.alert_id}"), rt.settings.FACT_NOTE_HOST_MAX_SEC * 1000, hide)

    async def _publish_locked(self, t: Transcript, judge: UtteranceJudgeOutput, facts: FactCheckOutput | None,
                              offered: dict[str, Answer | None], merge: Merge | None = None) -> None:
        rt = self.rt
        if not self._claim_application(t, "publish"):
            return
        seg = await rt.current_segment()
        if (seg is None or seg.segment_id != t.segment_id
                or self._generations.get(t.transcript_id) != self._segment_generation):
            return
        gid = judge.answer.matched_group_id
        if gid is not None and gid in offered:
            rt.pd.mention(gid)  # D-113: a read-out or "which product" card ends when the host takes it up
        group = await rt.get_group(gid) if gid else None
        answer = await rt.get_answer(group.answer_id) if group is not None else None
        decision = publish_logic.decide(judge, offered, group, answer,
                                        high_alert_active=alert_logic.high_alert_active(await rt.alerts()), facts=facts,
                                        utterance=merge.text if merge else t.text,
                                        current_key=await answer_key(rt, group) if group is not None else None)
        mine = self._judged.get(t.transcript_id)
        before = self._judged.get(merge.prev.transcript_id) if merge else None
        if before is not None and before.publish is not None:
            # D-088: the merged judgment replaces the fragment's host-answer link. Never publish twice.
            if decision.group_id == before.publish[0] and decision.action == before.publish[1]:
                await self._relink_locked(before.publish, merge.prev, t)
                if mine is not None:
                    mine.publish = before.publish
                return
            undone = await self._unlink_locked(before.publish, merge.prev)
            if not undone and before.publish[1] == "post" and decision.group_id == before.publish[0]:
                return  # the fragment's reply is already published: nothing more for this group
            before.publish = None
        if decision.action == "none" or group is None:
            return
        if decision.action == "post":
            await post_host_answer_locked(rt, group, answer)
        elif decision.action == "confirm_ai":
            group.host_confirmed = True
        else:
            group.host_verbal_answer_transcript_id = t.transcript_id
        group.version += 1
        await rt.save_group(group)
        await rt.emit("group.updated", group)
        await rt.recompute_host_queue_locked()
        if mine is not None:
            mine.publish = (group.group_id, decision.action)

    async def _relink_locked(self, link: tuple[str, str], old: Transcript, new: Transcript) -> None:
        """Same group, same action: keep the fragment's effect (no second post), credit the merged final."""
        gid, action = link
        if action != "verbal_not_posted":
            return
        g = await self.rt.get_group(gid)
        if g is not None and g.host_verbal_answer_transcript_id == old.transcript_id:
            g.host_verbal_answer_transcript_id = new.transcript_id
            g.version += 1
            await self.rt.save_group(g)
            await self.rt.emit("group.updated", g)

    async def _unlink_locked(self, link: tuple[str, str], old: Transcript) -> bool:
        """Undo the fragment's host-answer link that the merged judgment does not repeat. A post still
        in its cancel window is cancelled; a published reply cannot be taken back and stays.
        Returns whether anything was undone."""
        rt = self.rt
        gid, action = link
        g = await rt.get_group(gid)
        if g is None:
            return False
        if action == "post":
            pending = [m for m in await rt.ctx.store.query(rt.path("messages"), Message,
                                                           where=[("idempotency_key", "==", f"host_answer:{gid}")])
                       if m.state == "pending"]
            for m in pending:
                m.state = "cancelled"
                await rt.save_message(m)
                rt.ctx.scheduler.cancel(rt.key(f"publish:{m.message_id}"))
                await rt.emit("message.cancelled", m)
            if not pending:
                return False
        elif action == "confirm_ai":
            if not g.host_confirmed:
                return False
            g.host_confirmed = False
        else:
            if g.host_verbal_answer_transcript_id != old.transcript_id:
                return False
            g.host_verbal_answer_transcript_id = None
        g.version += 1
        await rt.save_group(g)
        await rt.emit("group.updated", g)
        await rt.recompute_host_queue_locked()
        return True


# ---- host answer publishing (§8.6) ---------------------------------------------------------------


async def post_host_answer_locked(rt: "SessionRuntime", group: QuestionGroup, answer) -> Message:
    msg = await rt.publish_message_locked(
        kind="host_answer", text=answer.text, group=group, comment_ids=list(group.member_comment_ids),
        citations=answer.citations, idempotency_key=f"host_answer:{group.group_id}",
        pending_until=rt.now() + rt.settings.PUBLISH_CANCEL_WINDOW_MS,
    )
    if msg.state == "pending":
        async def publish() -> None:
            async with rt.lock:
                await finish_pending_locked(rt, msg.message_id)

        rt.ctx.scheduler.call_at(rt.key(f"publish:{msg.message_id}"), msg.publish_at, publish)
    return msg


async def finish_pending_locked(rt: "SessionRuntime", message_id: str) -> None:
    m = await rt.get_message(message_id)
    if m is None or m.state != "pending":
        return
    now = rt.now()
    m.state, m.published_at = "published", now
    await rt.save_message(m)
    await rt.emit("message.published", m)
    if m.group_id:
        g = await rt.get_group(m.group_id)
        if g is not None:
            g.status, g.published_message_id = "answered", m.message_id
            g.version += 1
            await rt.save_group(g)
            await rt.emit("group.updated", g)
            for cid in m.reply_to_comment_ids:
                c = await rt.get_comment(cid)
                if c is not None:
                    rt.reply_latencies["host"].append(now - c.received_at)
    await rt.recompute_host_queue_locked()


async def cancel_message(rt: "SessionRuntime", message_id: str) -> None:
    async with rt.lock:
        m = await rt.get_message(message_id)
        if m is None:
            raise ActionError(404, "message_not_found", f"message {message_id} not found")
        if m.state != "pending":
            raise ActionError(409, "invalid_state", "only a pending post can be cancelled")
        m.state = "cancelled"
        await rt.save_message(m)
        rt.ctx.scheduler.cancel(rt.key(f"publish:{message_id}"))
        await rt.emit("message.cancelled", m)
        await rt.emit("operator.action", {"actor": "operator", "action": "cancel_post", "message_id": message_id,
                                          "at": rt.now()})


# ---- segments: commit, operator switch, undo, cancel (§8.7.2) ------------------------------------


async def commit_switch_locked(rt: "SessionRuntime", target: str, reason: str) -> Segment:
    rt.utterances._segment_generation += 1
    s = await rt.load_session()
    old = await rt.current_segment()
    now = rt.now()
    rt.ctx.scheduler.cancel(rt.key("switch-commit"))
    if old is not None:
        old.ended_at = now
        await rt.save_segment(old)
    item = rt.catalog.runsheet_item(target)
    new = Segment(segment_id=rt.new_id("seg_"), product_id=target, order=item.order, started_at=now,
                  start_reason=reason, planned_duration_sec=item.planned_duration_sec,
                  covered_point_ids=list(s.pre_covered.pop(target, [])))
    await rt.save_segment(new)
    s.current_segment_id = new.segment_id
    s.switch = SwitchState(last_commit={"closed_segment_id": old.segment_id if old else None,
                                        "opened_segment_id": new.segment_id, "at": now})
    await rt.save_session(s)
    await rt.emit("segment.started", new)
    if old is not None:
        missing = missing_required(rt.catalog, old)
        if missing:
            texts = {p.point_id: p.text for p in points_of(rt.catalog, old.product_id, rt.points)}
            await rt.emit("segment.missing_points", {"segment_id": old.segment_id, "product_id": old.product_id,
                                                     "missing_point_ids": missing,
                                                     "missing_texts": [texts[p] for p in missing]})
    await rt.after_segment_started_locked(new)
    nxt = rt.catalog.next_product(target)
    if nxt is not None and nxt not in rt.prefetched:
        rt.spawn(rt.prefetch(nxt), name="prefetch")
    return new


async def operator_switch(rt: "SessionRuntime", product_id: str) -> Segment:
    async with rt.lock:
        s = await rt.load_session()
        if s.status != "live":
            raise ActionError(409, "invalid_state", "switch only while live")
        seg = await rt.current_segment()
        if product_id not in rt.catalog.order or (seg is not None and seg.product_id == product_id):
            raise ActionError(409, "invalid_product", "choose another run-sheet product")
        new = await commit_switch_locked(rt, product_id, "operator")
        await rt.emit("operator.action", {"actor": "operator", "action": "switch", "product_id": product_id, "at": rt.now()})
        return new


async def cancel_switch(rt: "SessionRuntime", by: str) -> None:
    async with rt.lock:
        s = await rt.load_session()
        if s.switch.status != "pending":
            raise ActionError(409, "no_pending_switch", "no switch is pending")
        s.switch = SwitchState(last_commit=s.switch.last_commit)
        await rt.save_session(s)
        rt.ctx.scheduler.cancel(rt.key("switch-commit"))
        await rt.emit("segment.switch_cancelled", {"reason": by})


async def undo_switch(rt: "SessionRuntime") -> Segment:
    from ..models.session import CommentAnalysis

    async with rt.lock:
        s = await rt.load_session()
        lc = s.switch.last_commit
        now = rt.now()
        if not lc or lc.get("closed_segment_id") is None or now - lc["at"] > rt.settings.UNDO_SWITCH_WINDOW_SEC * 1000:
            raise ActionError(409, "undo_window_over", "There is no switch to undo.")
        closed = await rt.get_segment(lc["closed_segment_id"])
        opened = await rt.get_segment(lc["opened_segment_id"])
        if closed is None or opened is None:
            raise ActionError(409, "undo_window_over", "There is no switch to undo.")
        rt.utterances._segment_generation += 1
        closed.ended_at = None
        await rt.save_segment(closed)
        await rt.ctx.store.delete(rt.path("segments"), opened.segment_id)
        if opened.covered_point_ids:
            pre = s.pre_covered.setdefault(opened.product_id, [])
            pre.extend(p for p in opened.covered_point_ids if p not in pre)
        s.current_segment_id, s.switch = closed.segment_id, SwitchState()
        await rt.save_session(s)
        await rt.emit("segment.undone", {"segment_id": opened.segment_id})
        await rt.emit("segment.started", closed)
        await rt.emit("prompter.updated", prompter_view(rt.catalog, closed, rt.points))
        # Groups whose product came from context during the undone segment move back (§8.7.2).
        moved = set()
        for a in await rt.ctx.store.query(rt.path("analyses"), CommentAnalysis):
            if a.product_basis != "context" or a.product_id != opened.product_id:
                continue
            c = await rt.get_comment(a.comment_id)
            if c is None or c.received_at < opened.started_at or c.group_id is None or c.group_id in moved:
                continue
            g = await rt.get_group(c.group_id)
            if g is not None and g.product_id == opened.product_id:
                g.product_id = closed.product_id
                g.version += 1
                await rt.save_group(g)
                await rt.emit("group.updated", g)
                moved.add(g.group_id)
        await rt.recompute_host_queue_locked()
        await rt.emit("operator.action", {"actor": "operator", "action": "undo_switch", "at": now})
        return closed


# ---- cues and alert actions (§8.13) ----------------------------------------------------------------


async def set_cue_locked(rt: "SessionRuntime", text: str, preset_id: str | None) -> HostCue:
    s = await rt.load_session()
    if s.cue is not None and s.cue.status == "active":
        s.cue.status = "cleared"
        await rt.emit("cue.updated", s.cue)
    cue = HostCue(cue_id=rt.new_id("cue_"), text=text, preset_id=preset_id, created_at=rt.now(), status="active")
    s.cue = cue
    await rt.save_session(s)
    await rt.emit("cue.updated", cue)
    return cue


async def send_cue(rt: "SessionRuntime", text: str | None, preset_id: str | None) -> HostCue:
    async with rt.lock:
        if preset_id:
            preset = next((p for p in rt.ctx.pack.notices.host_cue_presets if p.cue_id == preset_id), None)
            if preset is None:
                raise ActionError(404, "unknown_preset", f"cue preset {preset_id} not found")
            seg = await rt.current_segment()
            missing = []
            if seg is not None:
                texts = {p.point_id: p.text for p in points_of(rt.catalog, seg.product_id, rt.points)}
                missing = [texts[p] for p in missing_required(rt.catalog, seg)]
            text = preset.text.replace("{missing_points}", "; ".join(missing) or "all required points are covered")
        if not text or not text.strip():
            raise ActionError(400, "empty_cue", "cue text is empty")
        cue = await set_cue_locked(rt, text.strip(), preset_id)
        await rt.emit("operator.action", {"actor": "operator", "action": "cue", "cue_id": cue.cue_id, "at": rt.now()})
        return cue


async def clear_cue(rt: "SessionRuntime", cue_id: str) -> None:
    async with rt.lock:
        s = await rt.load_session()
        if s.cue is None or s.cue.cue_id != cue_id:
            raise ActionError(404, "cue_not_found", f"cue {cue_id} is not the current cue")
        s.cue.status = "cleared"
        await rt.save_session(s)
        await rt.emit("cue.updated", s.cue)


async def _alert_or_404(rt: "SessionRuntime", aid: str) -> Alert:
    a = await rt.get_alert(aid)
    if a is None:
        raise ActionError(404, "alert_not_found", f"alert {aid} not found")
    return a


async def dismiss_alert(rt: "SessionRuntime", aid: str) -> None:
    async with rt.lock:
        a = await _alert_or_404(rt, aid)
        if not alert_logic.dismiss(a, rt.now()):
            raise ActionError(409, "invalid_state", f"alert is {a.status}")
        rt.ctx.scheduler.cancel(rt.key(f"escalate:{aid}"))
        rt.ctx.scheduler.cancel(rt.key(f"facthide:{aid}"))
        await rt.save_alert(a)
        await rt.emit("alert.updated", a)
        await rt.emit("operator.action", {"actor": "operator", "action": "dismiss_alert", "alert_id": aid, "at": rt.now()})


async def correction_cue(rt: "SessionRuntime", aid: str) -> HostCue:
    async with rt.lock:
        a = await _alert_or_404(rt, aid)
        text = f"Correct now: say '{a.say_instead}'" if a.kind == "compliance" else f"Say: {a.correct_value}"
        cue = await set_cue_locked(rt, text, None)
        await rt.emit("operator.action", {"actor": "operator", "action": "alert_cue", "alert_id": aid, "at": rt.now()})
        return cue


async def resend_fact(rt: "SessionRuntime", pipeline: UtterancePipeline, aid: str) -> None:
    async with rt.lock:
        a = await _alert_or_404(rt, aid)
        if a.kind != "fact" or a.status != "active":
            raise ActionError(409, "invalid_state", "only an active fact note can be resent")
        a.host_hidden_at, a.shown_at = None, rt.now()
        await rt.save_alert(a)
        await rt.emit("alert.updated", a)
        pipeline.schedule_fact_hide(a)
        await rt.emit("operator.action", {"actor": "operator", "action": "resend", "alert_id": aid, "at": rt.now()})


async def post_notice(rt: "SessionRuntime", aid: str, text: str) -> Message:
    async with rt.lock:
        a = await _alert_or_404(rt, aid)
        if not text.strip():
            raise ActionError(400, "empty_notice", "notice text is empty")
        msg = await rt.publish_message_locked(kind="correction_notice", text=text.strip(), group=None, comment_ids=[],
                                              citations=[], idempotency_key=f"correction_notice:{aid}:{rt.now()}")
        await rt.emit("operator.action", {"actor": "operator", "action": "notice", "alert_id": aid,
                                          "message_id": msg.message_id, "at": rt.now()})
        return msg


async def render_ack(rt: "SessionRuntime", aid: str) -> None:
    async with rt.lock:
        a = await _alert_or_404(rt, aid)
        if a.host_rendered_at is None and a.shown_at is not None:
            a.host_rendered_at = rt.now()
            await rt.save_alert(a)
            await rt.emit("alert.updated", a)


def notice_template(rt: "SessionRuntime", a: Alert) -> str:
    """Prefilled 'Post notice' text from templates/notices.json (§8.5, §8.13)."""
    notices = rt.ctx.pack.notices
    sets = {o.set_id: o.name for o in rt.catalog.set_offers}  # a set price note names the set
    name = sets.get(a.product_id) or rt.catalog.get_product(a.product_id).name
    if a.kind == "compliance":
        t = next(n for n in notices.correction_notices if n.template_id == "compliance_correction")
        return t.text.replace("{product_name}", name)
    if a.field in ("price", "set_price", "promo"):
        t = next(n for n in notices.correction_notices if n.template_id == "fact_correction_price")
        return t.text.replace("{product_name}", name).replace("{correct_value}", a.correct_value or "")
    t = next(n for n in notices.correction_notices if n.template_id == "fact_correction_generic")
    label = notices.field_labels.get(a.field or "", a.field or "")
    return (t.text.replace("{product_name}", name).replace("{field_label}", label)
            .replace("{correct_value}", a.correct_value or ""))
