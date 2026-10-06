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
import contextlib
import logging
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ..agents import arms
from ..agents.fact_checker import FactChecker, FactInput, fixes_of, gather_fact_passages
from ..agents.split_judges import ComplianceJudge, ContextJudge
from ..agents import vote
from ..agents.verifier import Verifier
from ..agents.utterance_judge import JudgeInput, UtteranceJudge, build_judge_values, say_instead_fallback
from ..logic import alerts as alert_logic
from ..logic import facts as fact_logic
from ..logic.corrections import check_correction, says_the_replacement
from ..logic import publish as publish_logic
from ..logic import qualifier
from ..logic.prompter import apply_coverage, missing_required, points_of, prompter_view
from ..logic.reflex import normalise
from ..logic.segments import classify_switch, expire, names_product, replace_cue, step_switch, withdraw_cue
from ..models.agent_io import ComplianceOutput, ContextOutput, FactCheckOutput, UtteranceJudgeOutput
from ..models.session import Alert, Answer, HostCue, Message, QuestionGroup, Segment, SwitchState, Transcript
from ..providers.llm import AgentResult
from .comments import answer_key, move_previous_product_questions_locked
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


# D-285 Q5: an English final that ends on one of these, or on a bare number, stops mid-clause ("The bottle at SGD 158
# contains"); with the flag it is held until the next final joins it. ponytail: English words only; another language
# gets no hold until its language pack names its own
DANGLING = frozenset("""a an the of for at with and or to in on by from is are was were has have had contains contain
includes include costs cost about than its our your their this that these those per under over into as like only
just around nearly almost up down plus minus""".split())


def mid_clause(text: str) -> bool:
    """D-285 Q5: the final has no end mark and ends on a dangling word or a number."""
    if ends_sentence(text):
        return False
    words = text.rstrip(" ,;:-").lower().split()
    return bool(words) and (words[-1].strip("\"'") in DANGLING or words[-1].replace(".", "").replace(",", "").isdigit()
                            or words[-1].startswith(("s$", "rm", "$")))


LATE_QUALIFIER_MS = 10_000  # D-151: a qualifier add-on fixes a qualifier alert at most this old
ADDENDUM_MAX_WORDS = 10
EARLY_ANSWER_MS = 30_000  # D-146: a draft verified later than this after the spoken answer is not posted


@dataclass
class EarlyAnswer:
    """D-146: a spoken answer given before its question's draft existed."""
    transcript: Transcript
    judge: UtteranceJudgeOutput
    facts: FactCheckOutput | None
    inp: "JudgeInput"
    utterance: str
    at: int


HEALTH_STREAK = 2  # D-137: failures of one judge that turn the health dot amber ...
HEALTH_WINDOW_MS = 60_000  # D-144: ... within this window (LT055: two timeouts 58 s apart)


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
        self.judge = UtteranceJudge(ctx.llm, ctx.prompts, rt.catalog, rt.reflex, single=self.single)
        self.compliance = ComplianceJudge(ctx.llm, ctx.prompts, rt.catalog, rt.reflex)
        self.context = ContextJudge(ctx.llm, ctx.prompts, rt.catalog, rt.reflex)
        self.facts = FactChecker(ctx.llm, ctx.prompts["fact_relation" if rt.settings.FACT_RELATION else "fact_checker"],
                                 rt.catalog)  # D-296
        self.compliance.docs = self.facts.files  # D-310: the same documents for COMPLIANCE_DOCS
        # D-300 R2: one verifier call per candidate alert, after the flaggers (their code drops off)
        self.verifier = (Verifier(ctx.llm, ctx.prompts["verifier"], rt.catalog, self.facts.files)
                         if rt.settings.JUDGE_ARM == "verify" else None)
        # D-137, D-144: per judge, the times it failed (timeout, error, invalid) within HEALTH_WINDOW_MS
        self._failures: dict[str, list[int]] = {}
        self._amber: set[str] = set()
        self.degraded: list[str] = []
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
        self._held: dict[str, tuple] = {}  # D-285 Q5: fragments waiting for the next final
        self._inputs: dict[str, JudgeInput] = {}  # D-146: kept with the judged prefix, for a later recheck
        # D-146: a spoken answer to a question whose draft was still being written: group -> what was said
        self._early: dict[str, EarlyAnswer] = {}
        self._addenda: dict[str, Transcript] = {}  # D-151: finals that only add "in our in-house test"

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
            if arms.meaning_to_llm(self.rt.settings.DESIGN_ARM) or self.rt.settings.CORRECTION_CHECK == "judge":
                return  # D-187 arm B: only the judge's quoted corrections count; D-304: only its listed ones
            # D-117 B2: no judge decision here, so only the alert's own replacement or a retraction counts
            check = check_correction(text, a, [], self.rt.reflex)
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
        for tid in list(self._held):  # D-285 Q5: no more finals are coming, so a held fragment is judged now
            self.rt.ctx.scheduler.cancel(self.rt.key(f"hold:{tid}"))
            await self._release(tid)
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

    def recent_host_line(self, at: int, max_age_ms: int, segment_id: str | None) -> str | None:
        """D-157: what the host said last before `at` (a merged sentence as judged), in this segment."""
        best: tuple[Transcript, str] | None = None
        for t, text, _ in self._prepared.values():
            if (t.received_at <= at and at - t.received_at <= max_age_ms
                    and (segment_id is None or t.segment_id == segment_id)
                    and (best is None or t.received_at > best[0].received_at)):
                best = (t, text)
        return best[1] if best else None

    def _previous_final(self, t: Transcript) -> Transcript | None:
        """The final just before `t` in transcript order (still kept for merging)."""
        seq = self._sequence.get(t.transcript_id, 0) - 1
        return next((p for p, _, _ in self._prepared.values() if self._sequence.get(p.transcript_id) == seq), None)

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
        if self._qualifier_addendum(t.text):  # D-155: the final itself, also when it is merged with a fragment
            self._addenda[t.transcript_id] = t  # D-151: "That's from our in-house test." after a number
        # 1. store, emit
        await rt.ctx.store.put(rt.path("transcripts"), t.transcript_id, t)
        # D-162: the exact STT split of a replay, for probing a false alert (D-158 lines carry the transcript id)
        log.info("final %s %s: %r%s", rt.sid, t.transcript_id, t.text[:100],
                 f" (merged with {merge.prev.transcript_id})" if merge else "")
        await rt.emit("transcript.final", t)
        if not rt.assistant:
            return  # D-139: no reflex chip, no judge, no prompter coverage
        if merge is not None and merge.prev.transcript_id in self._held:  # D-285 Q5: the held fragment joins this one
            self._held.pop(merge.prev.transcript_id)
            rt.ctx.scheduler.cancel(rt.key(f"hold:{merge.prev.transcript_id}"))
        window = rt.settings.UTTERANCE_MERGE_WINDOW_MS
        if ("Q5" in fixes_of(rt.settings.FACT_FIXES) and window > 0 and mid_clause(t.text)
                and len((merge.chain if merge else [])) + 1 < MAX_MERGED_FINALS):
            # D-285 Q5: a fragment that stops mid-clause is judged with the next final, or alone when none comes
            self._held[t.transcript_id] = (t, text, merge, scenario)
            rt.ctx.scheduler.call_later(rt.key(f"hold:{t.transcript_id}"), window,
                                        lambda tid=t.transcript_id: self._release(tid))
            return
        await self._judge(t, text, merge, scenario)

    async def _release(self, tid: str) -> None:
        """D-285 Q5: no final joined the held fragment within the window: it is judged on its own."""
        held = self._held.pop(tid, None)
        if held is not None:
            log.info("held fragment %s judged alone after the merge window", tid)
            await self._judge(*held)

    async def _judge(self, t: Transcript, text: str, merge: Merge | None, scenario: str) -> None:
        rt = self.rt
        # 2. reflex -> provisional alerts (D-189 arm C: no pre-scan, so no provisional chip and no fallback alert when
        # the judge fails; reflex still guards drafts through the restricted phrases of verify_answer)
        hits = [] if arms.no_reflex(rt.settings.DESIGN_ARM) or not rt.settings.REFLEX_SCAN else rt.reflex.scan(text)
        async with rt.lock:
            seg = await rt.get_segment(t.segment_id) if t.segment_id else await rt.current_segment()
            on_air = seg.product_id if seg else rt.catalog.order[0]
            if rt.pack.rule_products is not None and hits:  # D-279: no reflex chip from another product's law
                s = await rt.load_session()
                target = s.switch.target_product_id if s.switch.status in ("counting", "pending") else None
                line = (set(rt.catalog.order) if rt.settings.JUDGE_PRODUCTS == "all"  # D-304
                        else rt.catalog.line_products(on_air, target, [text]))
                allowed = {r.rule_id for r in rt.catalog.rules_for(line)}
                hits = [h for h in hits if h.rule_id in allowed]
            alerts = await rt.alerts()
            provisional = alert_logic.provisional_from_reflex(hits, t, on_air, alerts, rt.new_id, rt.now())
            for a in provisional:
                await rt.save_alert(a)
                await rt.emit("alert.created", a)
            judge_input, offered = await self._judge_input_locked(t, text, merge, on_air, scenario)
            self._inputs[t.transcript_id] = judge_input
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
                self._inputs.pop(tid, None)
                self._addenda.pop(tid, None)

    async def _infer(self, t, on_air, inp, hits, merge, scenario, ready):
        rt = self.rt
        comp = ctx = facts = None
        waiting = set()
        try:
            if self.single:
                inp.passages = await self._fact_passages(inp.utterance, on_air, inp.switch)
            if self.split3:
                values = build_judge_values(rt.catalog, inp)
                comp_task = rt.spawn(self._vote_compliance(self._verify_compliance(self._once_more(
                    lambda: self.compliance.run(inp, deadline_ms=(rt.settings.VERIFY_TIMEOUT_MS  # D-309: the strong
                                                                  if rt.settings.JUDGE_ARM == "single"  # model's 5 s
                                                                  else rt.settings.JUDGE_TIMEOUT_MS), values=values)),
                    inp, on_air, t.transcript_id), inp, values), name=f"compliance:{t.transcript_id}")
                ctx_task = rt.spawn(self.context.run(inp, deadline_ms=rt.settings.JUDGE_TIMEOUT_MS,
                                                     values=values), name=f"context:{t.transcript_id}")
            else:
                comp_task = rt.spawn(self.judge.run(inp, deadline_ms=rt.settings.JUDGE_TIMEOUT_MS),
                                     name=f"judge:{t.transcript_id}")
                ctx_task = None
            parts = [self._prepared[tid][0].text for tid in merge.chain if tid in self._prepared] + [t.text] if merge else []
            facts_task = None if self.single else rt.spawn(self._run_facts(inp.utterance, on_air, inp, scenario, parts,
                                                                           t.transcript_id),
                                                           name=f"facts:{t.transcript_id}")
            waiting = {task for task in (comp_task, ctx_task, facts_task) if task is not None}
            while waiting:
                done, waiting = await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
                for task in sorted(done, key=lambda task: (task is not comp_task, task is not facts_task)):
                    res = _result(task)
                    late = task is facts_task and res.latency_ms > rt.settings.FACT_TIMEOUT_MS
                    await self._note_health(
                        "fact_checker" if task is facts_task else "context_judge" if task is ctx_task
                        else "compliance_judge" if self.split3 else "utterance_judge",
                        "timeout" if late else res.status)
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
            if comp is None:
                return None, facts
            if ctx is None and self.split3:
                # D-175: the context judge ran out; the answer links nothing, so a line that seems to answer one
                # waiting draft is asked about once more (compliance still decides any post)
                ctx = UtteranceJudgeOutput.model_validate({
                    "compliance": {"violations": []}, "correction": {"corrects_alert_ids": []},
                    "answer": {"utterance_type": "other", "matched_group_id": None, "is_answer": False,
                               "consistent_with_suggested": False},
                    "prompter": {"covered_point_ids": [], "covered_cue_ids": [],
                                 "switch": {"is_transition": False, "is_quote": False, "target_product_id": None,
                                            "confidence": "low"}},
                    "reason": "context judge unavailable"})
            elif ctx is None:
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

    async def _note_health(self, agent: str, status: str) -> None:
        """D-137: "silence must not look like safety". A judge that failed HEALTH_STREAK times within
        HEALTH_WINDOW_MS (D-144: not only on finals in a row) turns the host's health dot amber; its next
        answer on time turns it back."""
        now = self.rt.now()
        if status == "ok":
            self._amber.discard(agent)  # an on-time answer clears the dot; the failure times stay for the window
        else:
            self._failures[agent] = [t for t in self._failures.get(agent, []) if now - t < HEALTH_WINDOW_MS] + [now]
            if len(self._failures[agent]) >= HEALTH_STREAK:
                self._amber.add(agent)
        degraded = sorted(self._amber)
        if degraded != self.degraded:
            self.degraded = degraded
            async with self.rt.lock:
                await self.rt.emit("judge.health", {"degraded": degraded, "at": self.rt.now()})

    async def _judge_input_locked(self, t: Transcript, text: str, merge: Merge | None, on_air: str,
                                  scenario: str) -> tuple[JudgeInput, dict[str, Answer | None]]:
        rt = self.rt
        s = await rt.load_session()
        alerts = [a for a in await rt.alerts() if a.transcript_id != t.transcript_id]
        inside = {t.transcript_id, *(merge.chain if merge else [])}  # already in the utterance text
        # D-117 B9: a bounded tail, not every transcript of the session
        window = rt.settings.CONTEXT_WINDOW_MS  # D-303: the finals of the last N ms, in place of the last two
        tail = await rt.ctx.store.query(rt.path("transcripts"), Transcript, order_by="received_at", descending=True,
                                        limit=len(inside) + (30 if window else 4))
        previous = [x.text for x in reversed(tail) if x.transcript_id not in inside][-2:]
        recent = ([x.text for x in reversed(tail) if x.transcript_id not in inside and x.is_final
                   and x.received_at >= t.received_at - window] if window else None)
        questions = await self._open_questions_locked(s, on_air)
        promo = rt.promo(s.active_promo_id)
        card = s.pd_card  # D-112: the answer card on screen, else the first question slot
        on_screen = (card.ref_id if card is not None and card.status == "active" and card.kind == "answer_question"
                     else s.host_slots[0].group_id if s.host_slots else None)
        inp = JudgeInput(utterance=text, on_air=on_air, active_alerts=alerts, open_questions=questions,
                         cue=s.cue, previous=previous, recent=recent, points_by_product=rt.points or None,
                         all_products=rt.settings.JUDGE_PRODUCTS == "all",
                         session_id=rt.sid, scenario=scenario,
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
                                          switch=switch, search_timeout_ms=rt.settings.FACT_SEARCH_TIMEOUT_MS,
                                          all_products=rt.settings.JUDGE_PRODUCTS == "all")

    @contextlib.asynccontextmanager
    async def _verifying(self, transcript_id: str | None, kind: str):
        """D-306: the host sees a grey "checking" chip while the verifier works on a line's candidates (no alert yet;
        a HIGH overlay only after it confirms); the operator's count of verifier calls with no answer, by cause."""
        rt = self.rt
        before = dict(self.verifier.failures)
        async with rt.lock:
            await rt.emit("verify.started", {"transcript_id": transcript_id, "kind": kind})
        try:
            yield
        finally:
            async with rt.lock:
                await rt.emit("verify.done", {"transcript_id": transcript_id, "kind": kind})
                if self.verifier.failures != before:
                    await rt.emit("verify.health", self.verify_health())

    def verify_health(self) -> dict:
        """D-306: verifier calls with no answer this show, in total and by failure type."""
        by = dict(self.verifier.failures) if self.verifier is not None else {}
        return {"no_answer": sum(by.values()), "by": by}

    def _by_judge(self) -> bool:
        """D-187 arm B, or D-304 VERBAL_CHECK=judge: a spoken answer's numbers and hedges come from the context judge."""
        return arms.meaning_to_llm(self.rt.settings.DESIGN_ARM) or self.rt.settings.VERBAL_CHECK == "judge"

    def _vote_opts(self) -> dict:
        t = self.rt.settings.VOTE_TEMPERATURE
        return {"temperature": float(t) if t else None, "hedge": False}

    async def _vote_compliance(self, call, inp: JudgeInput, values: dict):
        """D-302 vote: a line with a compliance candidate gets two more runs of the judge, in parallel."""
        res = await call
        if self.rt.settings.JUDGE_ARM != "vote" or res.status != "ok" or not vote.candidates(res.output, "compliance"):
            return res
        start = self.rt.ctx.clock.now_ms()
        extras = await asyncio.gather(*(self.compliance.run(inp, deadline_ms=self.rt.settings.JUDGE_TIMEOUT_MS,
                                                            values=values, **self._vote_opts()) for _ in range(2)))
        res.output = vote.compliance_votes(res.output, list(extras), self.rt.catalog)
        log.info("vote: compliance added %d ms", self.rt.ctx.clock.now_ms() - start)
        return res

    async def _verify_compliance(self, call, inp: JudgeInput, on_air: str, transcript_id: str | None = None):
        """D-300 R2: the compliance verdicts, each checked by the verifier (in parallel)."""
        res = await call
        if self.verifier is not None and res.status == "ok" and vote.candidates(res.output, "compliance"):
            start = self.rt.ctx.clock.now_ms()
            async with self._verifying(transcript_id, "compliance"):
                res.output = await self.verifier.check_compliance(res.output, inp.utterance,
                                                                  inp.recent if inp.recent is not None else inp.previous,
                                                                  on_air, self.rt.sid)
            log.info("verifier: compliance added %d ms", self.rt.ctx.clock.now_ms() - start)
        return res

    @staticmethod
    async def _once_more(call):
        """D-260 (candidate aa995d1: one compliance call failed, so a negated caution got no alert): a compliance call
        that times out, errors or comes back invalid is made once more, like the fact check (D-203)."""
        res = await call()
        if res.status in ("timeout", "error", "invalid"):
            log.info("compliance check %s: once more", res.status)
            res = await call()
        return res

    async def warm_facts_cache(self, on_air: str) -> None:
        """D-247 arm FD: the fact checker's files cache, made at session start for the first product."""
        if self.verifier is not None:  # D-301: and the verifier's documents cache
            self.rt.spawn(self.verifier.warm(on_air, self.rt.sid), name=f"verifier-cache:{on_air}")
        if self.compliance.with_docs:  # D-310: and the compliance judge's rules-and-documents cache
            self.rt.spawn(self.compliance.warm(on_air, self.rt.sid), name=f"compliance-cache:{on_air}")
        if self.facts._parts(on_air):
            switch = SwitchState()
            await self.facts.warm_cache(FactInput(utterance="", on_air=on_air, switch=switch, promo=None,
                                                  passages=await self._fact_passages("", on_air, switch),
                                                  session_id=self.rt.sid))

    async def _run_facts(self, text: str, on_air: str, judge_input: JudgeInput, scenario: str,
                         parts: list[str] | None = None, transcript_id: str | None = None) -> AgentResult:
        # D-172: a product the last lines named stays citable ("the ampoule on its own is $32," / "list price 42")
        passages = await self._fact_passages(" ".join([*judge_input.previous[-1:], text]), on_air, judge_input.switch)
        s = await self.rt.load_session()
        offers = [p for p in (self.rt.promo(ap.promo_id) for ap in s.active_promos) if p is not None and not p.changes_prices]
        inp = FactInput(utterance=text, on_air=on_air, switch=judge_input.switch, promo=judge_input.promo,
                        passages=passages, previous=judge_input.previous, recent=judge_input.recent,
                        session_id=self.rt.sid, scenario=scenario,
                        offers=offers, parts=parts or [])
        res = await self.facts.run(inp, deadline_ms=self.rt.settings.FACT_LATE_MS)  # D-144: on time is FACT_TIMEOUT_MS
        if res.status in ("timeout", "error") and self.rt.catalog.lexicon.spoken_numbers(text):
            # D-203: a line that states a number posts only after a completed check (D-195): one fresh call with its
            # own deadline; the publish decision waits for it
            log.info("fact check %s for %r: once more", res.status, text[:80])
            res = await self.facts.run(inp, deadline_ms=self.rt.settings.FACT_LATE_MS)
        if self.rt.settings.JUDGE_ARM == "vote" and res.status == "ok" and vote.candidates(res.output, "facts"):
            start = self.rt.ctx.clock.now_ms()  # D-302: two more runs of the fact check, in parallel
            extras = await asyncio.gather(*(self.facts.run(inp, deadline_ms=self.rt.settings.FACT_LATE_MS,
                                                           **self._vote_opts()) for _ in range(2)))
            res.output = vote.fact_votes(res.output, list(extras), self.rt.catalog)
            log.info("vote: facts added %d ms", self.rt.ctx.clock.now_ms() - start)
        if self.verifier is not None and res.status == "ok" and vote.candidates(res.output, "facts"):
            start = self.rt.ctx.clock.now_ms()  # D-300 R2
            async with self._verifying(transcript_id, "fact"):
                res.output = await self.verifier.check_facts(res.output, text,
                                                             inp.recent if inp.recent is not None else inp.previous,
                                                             on_air, [*passages, *self.facts.all_file_passages],
                                                             self.rt.sid)
            log.info("verifier: facts added %d ms", self.rt.ctx.clock.now_ms() - start)
        return res

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
        if judge is None and rt.settings.REFLEX_ON_FAIL == "card":
            # D-288 (A1): no rule alert from a regex alone ("suitable for eczema-prone skin" is approved wording); the
            # host and the operator get a neutral card to check the line, counted apart from alerts
            for a in provisional:
                a.status = "cleared"
                await self._save_alert_change_locked(a)
            live = [h for h in hits if not h.negated and not h.quoted]
            if live or not rt.settings.REFLEX_SCAN:  # D-304: with no pre-scan, every failed line gets the card
                await rt.emit("line.check", {"transcript_id": t.transcript_id, "text": text,
                                             "rule_ids": sorted({h.rule_id for h in live}),
                                             "phrases": sorted({h.phrase for h in live})})
            await rt.emit("judge.failed", {"transcript_id": t.transcript_id, "status": res.status, "alert_ids": []})
            await self._apply_corrections_locked(t, text, [], protected, now)
        elif judge is None:
            # §8.4.3 judge failed: fail toward warning
            changed = alert_logic.apply_judge_failure(provisional, hits, say_instead_fallback(rt.catalog, on_air), now)
            for a in changed:
                if a.unverified and not a.unverified_reason:  # D-309: the judge's own failure type, shown honestly
                    a.unverified_reason = res.meta.get("failure")
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
            # D-118: the previous final, inside the merge window, already raised this rule: the same claim
            # continuing ("treats acne." / "so you'll never break out again."), not a second card
            prev = self._previous_final(t)
            if (prev is not None and prev.segment_id == t.segment_id
                    and t.received_at - prev.received_at <= rt.settings.UTTERANCE_MERGE_WINDOW_MS):
                active_rules.update(a.rule_id for a in alerts if a.kind == "compliance"
                                    and a.status in ("active", "provisional") and a.transcript_id == prev.transcript_id)
            judge = judge.model_copy(deep=True)  # D-108: no second card while the same result's alert is active
            late_addendum = self._addendum_after(t)  # D-151: the qualifier came in the next final, judged first
            judge.compliance.violations = [
                v for v in judge.compliance.violations
                if not (v.rule_id == qualifier.RULE_ID and (late_addendum is not None
                                                            or qualifier.is_repeat(v.say_instead or None, alerts, on_air)))]
            changed, created = alert_logic.apply_judge_compliance(judge, t, on_air, provisional, rt.pack.rules_by_id,
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
            await self._apply_corrections_locked(t, text, judge.correction.corrects_alert_ids, protected, now,
                                                 quotes=getattr(judge.correction, "quotes", None))
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
                                        now: int, quotes=None) -> None:
        """Alerts the judge listed and the utterance really corrects (D-089), plus active alerts whose
        "Say this instead" wording the host just said, even if the judge missed it (D-098)."""
        rt = self.rt
        earlier = [a for a in await rt.alerts()
                   if self._sequence.get(a.transcript_id, 0) < self._sequence.get(t.transcript_id, 1)]
        correctable = [a for a in earlier if a.transcript_id not in protected]
        if arms.meaning_to_llm(rt.settings.DESIGN_ARM):
            # D-187 arm B: the judge says which alert the line corrects and quotes the words; code only checks that
            # the quote (two words or more) is in what the host said. No word overlap, no replacement match.
            heard = normalise(text)
            ids = {a.alert_id for a in correctable if a.kind == "compliance"}
            if arms.agents_decide(rt.settings.DESIGN_ARM):  # D-191 arms D and E: the judge's ids, unchecked
                accepted = [i for i in dict.fromkeys(listed) if i in ids]
            else:
                accepted = list(dict.fromkeys(q.alert_id for q in (quotes or []) if q.alert_id in ids
                                              and len(normalise(q.quote).split()) >= 2 and normalise(q.quote) in heard))
            if accepted:
                for a in alert_logic.apply_corrections(earlier, accepted, t, now):
                    rt.ctx.scheduler.cancel(rt.key(f"escalate:{a.alert_id}"))
                    await rt.save_alert(a)
                    await rt.emit("alert.updated", a)
            return
        if rt.settings.CORRECTION_CHECK == "judge":
            # D-304: the compliance judge's listed alerts, with no word check and no replacement match
            ids = {a.alert_id for a in correctable if a.kind == "compliance"}
            accepted = [i for i in dict.fromkeys(listed) if i in ids]
        else:
            accepted = self._substantive_corrections(correctable, listed, text) if listed else []
            for a in correctable:
                if (a.kind == "compliance" and a.status == "active" and a.transcript_id != t.transcript_id
                        and self._segments.get(a.transcript_id) == t.segment_id
                        and a.alert_id not in accepted and says_the_replacement(text, a, rt.reflex)):
                    log.info("correction of %s by its replacement wording: %r", a.alert_id, text)
                    accepted.append(a.alert_id)
        if self._qualifier_addendum(t.text):
            # D-151 (sealed round 3): "Redness went down 30% after two weeks." then "That's from our in-house
            # test." The judge saw the fix but listed nothing; the add-on corrects the qualifier alert just before.
            # D-155 (00007 show replays): also the alert of the fragment it completes ("... one application," then
            # "in our in-house test."), although a merged judgment never resolves its fragments' alerts otherwise
            for a in earlier:
                if (a.kind == "compliance" and a.rule_id == qualifier.RULE_ID and a.status in ("active", "provisional")
                        and a.alert_id not in accepted and self._segments.get(a.transcript_id) == t.segment_id
                        and now - a.created_at <= LATE_QUALIFIER_MS):
                    accepted.append(a.alert_id)
        if not accepted:
            return
        for a in alert_logic.apply_corrections(earlier, accepted, t, now):
            rt.ctx.scheduler.cancel(rt.key(f"escalate:{a.alert_id}"))
            await rt.save_alert(a)
            await rt.emit("alert.updated", a)

    def _qualifier_addendum(self, text: str) -> bool:
        """D-151: a short final that only names our test ("That's from our in-house test."), no number of its own."""
        return (self.rt.settings.QUALIFIER_ADDON  # D-304: off, no late add-on
                and self.rt.catalog.lexicon.is_qualified(text) and not any(ch.isdigit() for ch in text)
                and len(text.split()) <= ADDENDUM_MAX_WORDS)

    def _addendum_after(self, t: Transcript) -> Transcript | None:
        """A qualifier add-on that followed `t` within LATE_QUALIFIER_MS in the same segment."""
        seq = self._sequence.get(t.transcript_id, 0)
        return next((a for a in self._addenda.values()
                     if self._sequence.get(a.transcript_id, 0) > seq and a.segment_id == t.segment_id
                     and 0 <= a.received_at - t.received_at <= LATE_QUALIFIER_MS), None)

    def _substantive_corrections(self, alerts: list[Alert], listed: list[str], text: str) -> list[str]:
        """The listed compliance alerts that the utterance really corrects (D-089)."""
        rt = self.rt
        accepted: list[str] = []
        for a in alerts:
            if a.alert_id not in listed or a.kind != "compliance":
                continue
            check = check_correction(text, a, rt.catalog.get_product(a.product_id).approved_claims, rt.reflex)
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
            # D-304 SWITCH_ARM_NAME=false: the context judge's target and confidence alone arm the switch
            next_named=bool(nxt) and (not st.SWITCH_ARM_NAME or names_product(text, self._product_names(nxt))),
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
        for c in facts.claims:  # D-158: the only trace of a cloud replay (no session data is kept)
            log.info("facts %s t=%s: %s %s said=%r verdict=%s correct=%r", rt.sid, t.transcript_id, c.product_id,
                     c.field, c.stated_value, c.verdict, c.correct_value)
        seq = self._sequence.get(t.transcript_id, 0)
        claims = []
        for claim in facts.claims:
            # D-117 B3: ordered per subject; a claim without a passage also counts for the whole field
            key = fact_logic.subject_key(claim.product_id, claim.field, claim.passage_id)
            wide = fact_logic.subject_key(claim.product_id, claim.field, "*")
            seen = [x for x in (self._fact_sequence.get(key), self._fact_sequence.get(wide)) if x is not None]
            latest = max(seen, key=lambda x: x[0]) if seen else None
            if latest is not None and seq < latest[0]:
                newer = self._judged.get(latest[1])
                if not (latest[2] == "supported" and newer is not None
                        and t.transcript_id in newer.chain):
                    continue
            if claim.verdict in ("supported", "contradicted"):
                if latest is None or seq >= latest[0]:
                    self._fact_sequence[key] = (seq, t.transcript_id, claim.verdict)
                    if claim.passage_id is None:
                        self._fact_sequence[wide] = (seq, t.transcript_id, claim.verdict)
            claims.append(claim)
        created, reshown, corrected = fact_logic.apply_fact_check(claims, await rt.alerts(), t, rt.new_id, rt.now(),
                                                                  protected=protected, lex=rt.catalog.lexicon)
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
                                        lex=rt.catalog.lexicon, by_judge=self._by_judge(),
                                        numbers_gate=not arms.agents_decide(rt.settings.DESIGN_ARM),
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
        if decision.action == "none" and gid is None and offered and t.transcript_id in self._inputs:
            if self._by_judge():
                # D-187 arm B: no code guess of which draft the line answers; the context judge is asked once more
                # with every offered draft
                cands = [g for g, a in offered.items() if a is not None]
            else:
                # D-175: the judge linked nothing, but the line seems to answer one offered draft: ask about that one
                cand = publish_logic.relink_candidate(merge.text if merge else t.text,
                                                      {g: a.text for g, a in offered.items() if a is not None},
                                                      rt.catalog.lexicon)
                cands = [cand] if cand is not None else []
            if cands:
                rt.spawn(self._relink(t, judge, facts, self._inputs[t.transcript_id], cands,
                                      merge.text if merge else t.text), name=f"relink:{t.transcript_id}")
        if judge.answer.also_answered_group_ids:
            await self._publish_also_locked(judge, facts, offered, merge.text if merge else t.text)
        if decision.action == "none" or group is None:
            return
        if (decision.action == "verbal_not_posted" and offered.get(group.group_id) is None
                and group.status in ("new", "composing") and t.transcript_id in self._inputs):
            # D-146: the host answered before the draft existed; check again once it is verified
            self._early[group.group_id] = EarlyAnswer(t, judge, facts, self._inputs[t.transcript_id],
                                                      merge.text if merge else t.text, rt.now())
        if decision.action == "post" and not rt.live:
            decision = publish_logic.PublishDecision("verbal_not_posted", group.group_id, "preview: never auto-posted")
        # D-153: why a spoken answer was or was not posted (00007: verified drafts answered aloud, not posted)
        log.info("host answer %s %s: %s (%s)", rt.sid, group.group_id, decision.action, decision.reason or "-")
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

    async def _publish_also_locked(self, judge: UtteranceJudgeOutput, facts: FactCheckOutput | None,
                                   offered: dict[str, Answer | None], utterance: str) -> None:
        """D-196: one sentence that answers several shown questions. Each other group the judge linked is checked on
        its own (its draft's numbers all said, every number said in a linked draft, facts complete) and posted on its
        own; a hold leaves its card as it is."""
        rt = self.rt
        a = judge.answer
        for gid in a.also_answered_group_ids:
            group = await rt.get_group(gid) if gid in offered else None
            if group is None:
                continue
            rt.pd.mention(gid)
            answer = await rt.get_answer(group.answer_id)
            link = a.model_copy(update={"matched_group_id": gid, "consistent_with_suggested": True,
                                        "also_answered_group_ids": [a.matched_group_id,
                                                                    *(g for g in a.also_answered_group_ids if g != gid)]})
            decision = publish_logic.decide(
                judge.model_copy(update={"answer": link}), offered, group, answer,
                high_alert_active=alert_logic.high_alert_active(await rt.alerts()), facts=facts,
                lex=rt.catalog.lexicon, by_judge=self._by_judge(),
                numbers_gate=not arms.agents_decide(rt.settings.DESIGN_ARM), utterance=utterance,
                current_key=await answer_key(rt, group))
            log.info("host answer (same line) %s %s: %s (%s)", rt.sid, gid, decision.action, decision.reason or "-")
            if decision.action != "post" or not rt.live:
                continue
            await post_host_answer_locked(rt, group, answer)
            group.version += 1
            await rt.save_group(group)
            await rt.emit("group.updated", group)
            await rt.recompute_host_queue_locked()

    async def recheck_early(self, group_id: str) -> None:
        """D-146 (sealed show replay): the host answered a question aloud while its draft was being written.
        Once the draft is verified, ask the context judge again with that draft and post it when the same
        rules as a normal spoken answer allow it (D-110, D-112: consistent, verified, no alert, not stale)."""
        rt = self.rt
        early = self._early.pop(group_id, None)
        if early is None or rt.now() - early.at > EARLY_ANSWER_MS:
            return
        async with rt.lock:
            g = await rt.get_group(group_id)
            answer = await rt.get_answer(g.answer_id) if g is not None else None
            if g is None or answer is None or not answer.verified or g.published_message_id is not None:
                return
        inp = replace(early.inp, open_questions=[(g, answer.text)], on_screen_group_id=group_id)
        agent = self.context if self.split3 else self.judge
        res = await agent.run(inp, deadline_ms=rt.settings.JUDGE_TIMEOUT_MS)
        if res.status != "ok" or res.output is None:
            return
        judge = early.judge.model_copy(update={"answer": res.output.answer})
        async with rt.lock:
            g = await rt.get_group(group_id)
            if g is None or g.answer_id != answer.answer_id:
                return
            decision = publish_logic.decide(
                judge, {group_id: answer}, g, answer,
                high_alert_active=alert_logic.high_alert_active(await rt.alerts()), facts=early.facts,
                lex=rt.catalog.lexicon, utterance=early.utterance, current_key=await answer_key(rt, g),
                by_judge=self._by_judge(),
                numbers_gate=not arms.agents_decide(rt.settings.DESIGN_ARM))
            log.info("early spoken answer for %s: %s (%s)", group_id, decision.action, decision.reason)
            if decision.action != "post" or not rt.live:  # D-150: a preview market posts nothing by itself
                return
            await post_host_answer_locked(rt, g, answer)
            g.version += 1
            await rt.save_group(g)
            await rt.emit("group.updated", g)
            await rt.recompute_host_queue_locked()

    async def _relink(self, t: Transcript, judge, facts, inp, group_ids: list[str], utterance: str) -> None:
        """D-175: ask the context judge once more with only the question the line seems to answer (D-187 arm B: with
        every offered draft), and post only when it now links the line to one of them and every usual check passes
        (numbers, compliance, staleness)."""
        rt = self.rt
        shown: dict[str, tuple[QuestionGroup, Answer]] = {}
        async with rt.lock:
            for group_id in group_ids:
                g = await rt.get_group(group_id)
                answer = await rt.get_answer(g.answer_id) if g is not None and g.answer_id else None
                if g is not None and answer is not None and answer.verified and g.published_message_id is None:
                    shown[group_id] = (g, answer)
        if not shown:
            return
        agent = self.context if self.split3 else self.judge
        res = await agent.run(replace(inp, open_questions=[(g, a.text) for g, a in shown.values()],
                                      on_screen_group_id=next(iter(shown)) if len(shown) == 1 else None),
                              deadline_ms=rt.settings.JUDGE_TIMEOUT_MS)
        if res.status != "ok" or res.output is None or res.output.answer.matched_group_id not in shown:
            return
        group_id = res.output.answer.matched_group_id
        answer = shown[group_id][1]
        second = judge.model_copy(update={"answer": res.output.answer})
        async with rt.lock:
            g = await rt.get_group(group_id)
            if g is None or g.answer_id != answer.answer_id:
                return
            decision = publish_logic.decide(
                second, {gid: a for gid, (_, a) in shown.items()}, g, answer,
                high_alert_active=alert_logic.high_alert_active(await rt.alerts()), facts=facts,
                lex=rt.catalog.lexicon, utterance=utterance, current_key=await answer_key(rt, g),
                by_judge=self._by_judge(),
                numbers_gate=not arms.agents_decide(rt.settings.DESIGN_ARM))
            log.info("relinked spoken answer %s %s: %s (%s)", t.transcript_id, group_id, decision.action, decision.reason)
            if decision.action != "post" or not rt.live:
                return
            await post_host_answer_locked(rt, g, answer)
            g.version += 1
            await rt.save_group(g)
            await rt.emit("group.updated", g)
            await rt.recompute_host_queue_locked()

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
        # D-117 B4: bound to the answer and the promo/document state of now
        expect = (answer.answer_id, await answer_key(rt, group))

        async def publish() -> None:
            async with rt.lock:
                await finish_pending_locked(rt, msg.message_id, expect)

        rt.ctx.scheduler.call_at(rt.key(f"publish:{msg.message_id}"), msg.publish_at, publish)
    return msg


async def _still_valid(rt: "SessionRuntime", group_id: str | None, expect: tuple[str, str] | None) -> bool:
    if expect is None or group_id is None:
        return True
    g = await rt.get_group(group_id)
    return (g is not None and g.status not in ("closed", "rejected", "answered") and g.answer_id == expect[0]
            and await answer_key(rt, g) == expect[1])


async def finish_pending_locked(rt: "SessionRuntime", message_id: str,
                                expect: tuple[str, str] | None = None) -> None:
    m = await rt.get_message(message_id)
    if m is None or m.state != "pending":
        return
    if not await _still_valid(rt, m.group_id, expect):
        # the question was closed or its answer, promo or document changed in the cancel window
        m.state = "cancelled"
        await rt.save_message(m)
        await rt.emit("message.cancelled", m)
        log.info("pending host answer %s dropped: its question changed", message_id)
        return
    if m.kind == "host_answer" and alert_logic.high_alert_active(await rt.alerts()):
        # D-204: the safety state is checked again at the moment of posting; a red alert raised in the cancel
        # window stops the post, and the card stays for the host
        m.state = "cancelled"
        await rt.save_message(m)
        await rt.emit("message.cancelled", m)
        log.info("pending host answer %s dropped: a HIGH alert is active", message_id)
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
        await move_previous_product_questions_locked(rt, old.product_id)  # D-178
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
            preset = next((p for p in rt.pack.notices.host_cue_presets if p.cue_id == preset_id), None)
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
    notices = rt.pack.notices
    sets = {o.set_id: o.name for o in rt.catalog.set_offers}  # a set price note names the set
    name = sets.get(a.product_id) or rt.catalog.get_product(a.product_id).name
    if a.kind == "compliance":
        t = next(n for n in notices.correction_notices if n.template_id == "compliance_correction")
        return t.text.replace("{brand}", rt.catalog.brand).replace("{product_name}", name)  # D-278: the release's brand
    if a.field in ("price", "set_price", "promo"):
        t = next(n for n in notices.correction_notices if n.template_id == "fact_correction_price")
        return t.text.replace("{product_name}", name).replace("{correct_value}", a.correct_value or "")
    t = next(n for n in notices.correction_notices if n.template_id == "fact_correction_generic")
    label = notices.field_labels.get(a.field or "", a.field or "")
    return (t.text.replace("{product_name}", name).replace("{field_label}", label)
            .replace("{correct_value}", a.correct_value or ""))
