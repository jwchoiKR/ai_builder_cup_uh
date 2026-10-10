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
import dataclasses
import logging
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ..agents import arms
from ..agents.fact_checker import FactChecker, FactInput
from ..agents.prompter_judge import PrompterInput, PrompterJudge
from ..agents.split_judges import ComplianceJudge, ContextJudge
from ..agents.utterance_judge import JudgeInput, UtteranceJudge, build_judge_values
from ..logic import alerts as alert_logic
from ..logic import facts as fact_logic
from ..logic import publish as publish_logic
from ..logic.prompter import apply_coverage, missing_required, points_of, tick_item
from ..models.agent_io import ContextOutput, FactCheckOutput, PrompterJudgement, UtteranceJudgeOutput
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
EXPECTS_WAIT_S = 0.3  # D-335: how long the next final waits for the previous line's context verdict
_KEEP_JUDGED = 20  # judgments remembered for merging (only the last one is ever needed)
LATE_CORRECTION_MS = 10_000  # D-352: a line this soon after an alert's line may correct it before it turned active
LATE_CORRECTION_LINES = 2
MIN_CONTEXT_RETRY_MS = 1_000  # D-351: a context retry needs at least this much of its total deadline
MIN_FACT_RETRY_MS = 1_000  # D-411: a fact retry needs at least this much left of the fact deadline from the line end
FAILURE_WINDOW_MS = 300_000  # D-412: the operator's rolling count of failed checks covers the last 5 minutes


def failure_cause(res: AgentResult) -> str:
    """D-412: what the screens say about a failed check: "busy" (429, shared capacity), "timeout" (a deadline, ours or
    the server's 504), "invalid" (an answer that could not be read) or "error" (anything else)."""
    kind = res.meta.get("failure")
    if res.status == "invalid":
        return "invalid"
    if kind == "http_429":
        return "busy"
    if res.status == "timeout" or kind == "http_504":
        return "timeout"
    return "error"


def ends_sentence(text: str) -> bool:
    """True when a final ends with . ? or ! (closing quotes and brackets ignored)."""
    return text.rstrip().rstrip("\"'”’)]").endswith(SENTENCE_END)


def asks(text: str) -> bool:
    """D-334: the final ends with a question mark (closing quotes and brackets ignored)."""
    return text.rstrip().rstrip("\"'”’)]").endswith("?")


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
    pair: str | None = None  # D-335: a question or report and its answer, as two marked lines: what triggered it


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
        self.facts = FactChecker(ctx.llm, ctx.prompts["fact_relation_v5"], rt.catalog)  # D-296; D-331
        self.prompter = PrompterJudge(ctx.llm, ctx.prompts["prompter_judge"], rt.catalog)  # D-450
        # D-137, D-144: per judge, the times it failed (timeout, error, invalid) within HEALTH_WINDOW_MS
        self._failures: dict[str, list[int]] = {}
        self._amber: set[str] = set()
        self.degraded: list[str] = []
        self._main_tail: asyncio.Task | None = None
        self._side_tail: asyncio.Task | None = None
        self._context_tail: asyncio.Task | None = None
        self._pending: set[asyncio.Task] = set()
        self._sequence: dict[str, int] = {}
        self._questions: dict[str, int] = {}  # D-334: held question finals -> when the hold began
        self._ready: dict[str, asyncio.Future] = {}  # D-335: each final's context verdict, as it comes
        self._question_finals = 0  # D-334: finals that end with "?" (a log of STT punctuation)
        self._prepared: dict[str, tuple[Transcript, str, Merge | None]] = {}
        self._applied: set[tuple[str, str]] = set()
        # D-401: (line, kind) whose verdict succeeded and was applied; only these supersede their merge chain
        self._verdict_ok: set[tuple[str, str]] = set()
        self._segment_generation = 0
        self._generations: dict[str, int] = {}
        self._segments: dict[str, str] = {}
        self._last: Transcript | None = None  # previous final in the main chain
        self._judged: dict[str, Judged] = {}
        self._held: dict[str, tuple] = {}  # D-334: questions waiting for their answer (the next final)
        self._inputs: dict[str, JudgeInput] = {}  # D-146: kept with the judged prefix, for a later recheck
        # D-146: a spoken answer to a question whose draft was still being written: group -> what was said
        self._early: dict[str, EarlyAnswer] = {}
        self._fact_shown: dict[str, set[str]] = {}  # D-363: line -> the fact notes its fact check was shown
        # D-412/D-416/D-420: the failure events of the last FAILURE_WINDOW_MS, one per (line, agent), and every failure
        # event of the lines still unchecked (line -> agent -> event, no time cut); each event has an order number `n`
        # that breaks `at` ties; the snapshot rebuilds exactly what the live stream showed
        self.failures: dict[tuple[str, str], dict] = {}
        self.unchecked: dict[str, dict[str, dict]] = {}
        self._failure_n = 0
        self._fact_inputs: dict[str, FactInput] = {}  # D-364: line -> its fact check's input (a re-check reuses it)

    def _claim_application(self, t: Transcript, kind: str) -> bool:
        key = (t.transcript_id, kind)
        if key in self._applied:
            return False
        self._applied.add(key)
        return True

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
        for tid in list(self._held):  # D-334: no more finals are coming, so a held question is judged now
            self.rt.ctx.scheduler.cancel(self.rt.key(f"hold:{tid}"))
            await self._release(tid)
        await asyncio.gather(*tuple(self._pending), return_exceptions=True)

    # ---- steps 1-4 -----------------------------------------------------------------------------

    async def _expects_resolution(self, prev: Transcript | None) -> bool:
        """D-335: the context judge's verdict that the previous final (judged alone) asks or relays something the next
        line is expected to answer; waited for at most 300 ms."""
        if prev is None or prev.transcript_id in self._held:
            return False
        fut = self._ready.get(prev.transcript_id)
        if fut is None:
            return False
        if not fut.done():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(fut), EXPECTS_WAIT_S)
        return fut.done() and not fut.cancelled() and bool(getattr(fut.result(), "expects_resolution", False))

    def _merge_for(self, t: Transcript, expects: bool = False) -> Merge | None:
        """D-088: join with the previous final if it arrived within the window and is unfinished. D-334/335: a
        question held for its answer ("?"), or a line the context judge says expects one ("model"), joins the next
        final as a marked pair."""
        prev = self._last
        window = self.rt.settings.UTTERANCE_MERGE_WINDOW_MS
        pair = None
        if prev is not None and (prev.transcript_id in self._questions or expects):
            window = self.rt.settings.QUESTION_HOLD_MS
            asked = prev.transcript_id in self._questions or asks(prev.text)
            pair = "both" if asked and expects else "?" if asked else "model"
        elif prev is not None and ends_sentence(prev.text):
            return None
        if (prev is None or window <= 0 or t.received_at - prev.received_at > window
                or prev.segment_id != t.segment_id
                or self._generations.get(prev.transcript_id) != self._generations.get(t.transcript_id)):
            return None
        judged = self._judged.get(prev.transcript_id)
        chain = judged.chain if judged else [prev.transcript_id]
        if len(chain) >= MAX_MERGED_FINALS:
            return None
        base = judged.text if judged else prev.text
        if pair:  # D-335: two marked lines, so who endorsed or rejected what stays clear
            return Merge(prev=prev, chain=list(chain), text=f"[previous line] {base}\n[this line] {t.text}", pair=pair)
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

    def _remember(self, t: Transcript, merge: Merge | None, text: str) -> None:
        self._last = t
        self._judged[t.transcript_id] = Judged(chain=[*(merge.chain if merge else []), t.transcript_id], text=text)
        self._sequence[t.transcript_id] = len(self._sequence) + 1
        self._prepared[t.transcript_id] = (t, text, merge)

    async def _main(self, prev: asyncio.Task | None, t: Transcript, scenario: str) -> None:
        if prev is not None:
            await asyncio.gather(prev, return_exceptions=True)
        rt = self.rt
        merge = self._merge_for(t, await self._expects_resolution(self._last))
        text = merge.text if merge else t.text
        if merge:
            t.merged_from_transcript_id, t.judged_text = merge.prev.transcript_id, text
        self._remember(t, merge, text)
        # 1. store, emit
        await rt.ctx.store.put(rt.path("transcripts"), t.transcript_id, t)
        # D-162: the exact STT split of a replay, for probing a false alert (D-158 lines carry the transcript id)
        log.info("final %s %s: %r%s", rt.sid, t.transcript_id, t.text[:100],
                 f" (merged with {merge.prev.transcript_id})" if merge else "")
        await rt.emit("transcript.final", t)
        if not rt.assistant:
            return  # D-139: no reflex chip, no judge, no prompter coverage
        if merge is not None and merge.prev.transcript_id in self._held:  # D-334: the held question joins this one
            self._held.pop(merge.prev.transcript_id)
            rt.ctx.scheduler.cancel(rt.key(f"hold:{merge.prev.transcript_id}"))
            if self._questions.pop(merge.prev.transcript_id, None) is not None:
                await rt.emit("hold.ended", {"transcript_id": merge.prev.transcript_id})
        if merge is not None and merge.pair:  # D-335: the trigger and the wait of every pair
            log.info("pair %s + %s trigger=%s after %d ms: judged as one", merge.prev.transcript_id, t.transcript_id,
                     merge.pair, t.received_at - merge.prev.received_at)
        if asks(t.text):  # D-334: how often speech-to-text ends a line with "?" (is its punctuation reliable?)
            self._question_finals += 1
            log.info("question final %s %s (%d of %d finals)", rt.sid, t.transcript_id, self._question_finals,
                     len(self._sequence))
        if (asks(t.text) and rt.settings.QUESTION_HOLD_MS > 0
                and len((merge.chain if merge else [])) + 1 < MAX_MERGED_FINALS):
            # D-334: a question is not judged alone: its answer, the next final, joins it into one utterance
            self._held[t.transcript_id] = (t, text, merge, scenario)
            self._questions[t.transcript_id] = rt.now()
            rt.ctx.scheduler.call_later(rt.key(f"hold:{t.transcript_id}"), rt.settings.QUESTION_HOLD_MS,
                                        lambda tid=t.transcript_id: self._release(tid))
            # D-335: the operator sees "collecting context" while it waits (nothing on the host screen)
            await rt.emit("hold.started", {"transcript_id": t.transcript_id, "max_ms": rt.settings.QUESTION_HOLD_MS})
            return
        await self._judge(t, text, merge, scenario)

    async def _release(self, tid: str) -> None:
        """D-334: no answer joined the held question within its wait: it is judged on its own."""
        held = self._held.pop(tid, None)
        if held is not None:
            began = self._questions.pop(tid, None)
            if began is not None:  # D-334
                log.info("question %s judged alone: no answer within %d ms", tid, self.rt.now() - began)
                await self.rt.emit("hold.ended", {"transcript_id": tid})
            await self._judge(*held)

    async def _judge(self, t: Transcript, text: str, merge: Merge | None, scenario: str) -> None:
        rt = self.rt
        # D-410 (user): no regex pre-scan and no provisional alert; only the judge raises an alert
        async with rt.lock:
            seg = await rt.get_segment(t.segment_id) if t.segment_id else await rt.current_segment()
            on_air = seg.product_id if seg else rt.catalog.order[0]
            judge_input, offered = await self._judge_input_locked(t, text, merge, on_air, scenario)
            self._inputs[t.transcript_id] = judge_input
        # Only preparation waits for the previous final.
        ready = asyncio.Future()
        self._ready[t.transcript_id] = ready  # D-335: the next final may wait for this line's context verdict
        previous_context = self._context_tail
        self._context_tail = rt.spawn(self._ordered_context(previous_context, ready, t, merge),
                                      name=f"context-apply:{t.transcript_id}")
        inference = rt.spawn(self._infer(t, on_air, judge_input, merge, scenario, ready),
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
                self._fact_shown.pop(tid, None)
                self._fact_inputs.pop(tid, None)
                self._ready.pop(tid, None)

    async def _infer(self, t, on_air, inp, merge, scenario, ready):
        rt = self.rt
        comp = ctx = facts = None
        waiting = set()
        try:
            if self.single:
                inp.passages = await self._fact_passages(inp.utterance, on_air, inp.switch, inp.promo)
            if self.split3:
                values = build_judge_values(rt.catalog, inp)
                comp_task = rt.spawn(self._once_more(  # D-309: the compliance judge's 5 s
                    lambda: self.compliance.run(inp, deadline_ms=rt.settings.VERIFY_TIMEOUT_MS, values=values)),
                    name=f"compliance:{t.transcript_id}")
                ctx_task = rt.spawn(self._context_once_more(inp, values), name=f"context:{t.transcript_id}")
                # D-450: the prompter judge ticks the line's points; nothing waits on it (only drain, at the end)
                prompter_task = rt.spawn(self._run_prompter(t, inp), name=f"prompter:{t.transcript_id}")
                self._pending.add(prompter_task)
                prompter_task.add_done_callback(self._pending.discard)
            else:
                comp_task = rt.spawn(self.judge.run(inp, deadline_ms=rt.settings.JUDGE_TIMEOUT_MS),
                                     name=f"judge:{t.transcript_id}")
                ctx_task = None
            parts = ([self._prepared[tid][0].text for tid in merge.chain if tid in self._prepared] + [t.text]
                     if merge and not merge.pair else [])  # D-335: a pair is read as its two marked lines
            facts_task = None if self.single else rt.spawn(self._run_facts(inp.utterance, on_air, inp, scenario, parts,
                                                                           t.transcript_id),
                                                           name=f"facts:{t.transcript_id}")
            waiting = {task for task in (comp_task, ctx_task, facts_task) if task is not None}
            failed = False  # D-412: a check of this line failed
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
                    failed = failed or output is None  # D-416: the context judge's failure counts too
                    if task is comp_task:
                        comp = output
                        async with rt.lock:
                            await self._apply_compliance_locked(t, on_air, res, merge)
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
                        if output is None:  # D-416: shown like the other judges' failures
                            async with rt.lock:
                                await self._check_failed_locked(t, merge.text if merge else t.text, res, "context_judge")
                    else:
                        facts = output
                        if facts is not None:
                            async with rt.lock:
                                await self._apply_facts_locked(t, facts, set(merge.chain) if merge else set())
                        else:  # D-408: a failed fact check shows the judge-failed state at once, as a failed judge
                            async with rt.lock:
                                await self._check_failed_locked(t, merge.text if merge else t.text, res, "fact_checker")
            if not failed and self.unchecked:
                # D-412/D-416: the judges answered this line normally again: the unchecked lines said at or before it
                # are cleared; a line said after it (a late success of an earlier line) stays
                seq = self._sequence.get(t.transcript_id, 0)
                cleared = [x for x in self.unchecked if self._sequence.get(x, 0) <= seq]
                if cleared:
                    async with rt.lock:
                        for x in cleared:
                            self.unchecked.pop(x, None)
                        await rt.emit("checks.recovered", {"transcript_id": t.transcript_id, "cleared": cleared,
                                                           "at": rt.now()})
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
                # D-450: the context part carries no points (the prompter judge ticks them); its cues and switch as they are
                prompter = PrompterJudgement.model_construct(covered_point_ids=[], covered_cue_ids=ctx.prompter.covered_cue_ids,
                                                             switch=ctx.prompter.switch)
                comp = UtteranceJudgeOutput(compliance=comp.compliance, correction=comp.correction,
                                            answer=ctx.answer, prompter=prompter,
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
        tail = await rt.ctx.store.query(rt.path("transcripts"), Transcript, order_by="received_at", descending=True,
                                        limit=len(inside) + 4)
        previous = [x.text for x in reversed(tail) if x.transcript_id not in inside][-2:]
        questions = await self._open_questions_locked(s, on_air)
        promo = rt.promo(s.active_promo_id)
        # D-112: the first question slot (D-429: no answer card on screen any more)
        on_screen = s.host_slots[0].group_id if s.host_slots else None
        inp = JudgeInput(utterance=text, on_air=on_air, active_alerts=alerts, open_questions=questions,
                         cue=s.cue, previous=previous, points_by_product=rt.points or None,
                         session_id=rt.sid, scenario=scenario,
                         switch=self._scoped(s.switch), promo=promo, on_screen_group_id=on_screen,
                         run_sheet_types={}, now=rt.now(),
                         chain=list(merge.chain) if merge and not merge.pair else [])
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

    def _scoped(self, switch: SwitchState) -> SwitchState:
        """D-349: the product that just left the air stays in the judges' scope only inside its window."""
        if switch.previous_product_id and (switch.previous_until or 0) > self.rt.now():
            return switch
        return switch.model_copy(update={"previous_product_id": None, "previous_until": None})

    async def _fact_passages(self, text: str, on_air: str, switch: SwitchState, promo=None):
        rt = self.rt
        # D-360: only what the host prompter shows, the previous product's snapshot too inside the dual scope after a
        # switch (D-349)
        from ..logic.prompter import prompter_passages

        pids = [on_air, *([switch.previous_product_id] if switch.previous_product_id
                          and switch.previous_product_id != on_air else [])]
        return [x for pid in pids for x in prompter_passages(rt.catalog, pid, rt.points, promo)]

    def _by_judge(self) -> bool:
        """D-187 arm B, or D-304 VERBAL_CHECK=judge: a spoken answer's numbers and hedges come from the context judge."""
        return arms.meaning_to_llm(self.rt.settings.DESIGN_ARM) or self.rt.settings.VERBAL_CHECK == "judge"

    async def _context_once_more(self, inp, values):
        """D-351 immediate switch arm (the switch hangs on the context verdict): a failed context call (timeout, error,
        invalid, a 429 included) is made once more, inside one total deadline, CONTEXT_RETRY_TOTAL_MS from the first
        call. These calls skip the LLM layer's own 429 wait, so the two retries never stack. Worst case: the verdict
        comes CONTEXT_RETRY_TOTAL_MS - JUDGE_TIMEOUT_MS later than without the retry (4.0 - 2.5 = 1.5 s by default)."""
        st = self.rt.settings
        start = self.rt.ctx.clock.now_ms()
        res = await self.context.run(inp, deadline_ms=st.JUDGE_TIMEOUT_MS, values=values, retry_429=False)
        left = st.CONTEXT_RETRY_TOTAL_MS - (self.rt.ctx.clock.now_ms() - start)
        if res.status in ("timeout", "error", "invalid") and left >= MIN_CONTEXT_RETRY_MS:
            log.info("context check %s: once more within %d ms", res.status, left)
            res = await self.context.run(inp, deadline_ms=min(st.JUDGE_TIMEOUT_MS, left), values=values,
                                         retry_429=False)
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
        """D-310: the compliance judge's rules-and-documents cache, made at session start (D-435: the fact checker
        sends no files, so it has no cache to warm)."""
        if self.compliance.with_docs:
            self.rt.spawn(self.compliance.warm(on_air, self.rt.sid), name=f"compliance-cache:{on_air}")

    async def _run_facts(self, text: str, on_air: str, judge_input: JudgeInput, scenario: str,
                         parts: list[str] | None = None, transcript_id: str | None = None) -> AgentResult:
        # D-411/D-417/D-421: one fact deadline for the line, FACT_LATE_MS from its end (D-144: on time is
        # FACT_TIMEOUT_MS), taken once in wall time; the time spent after that is measured on the monotonic clock, so a
        # wall-clock step changes nothing. It is checked before the lookups and again right before the call.
        clock = self.rt.ctx.clock
        mono = getattr(clock, "monotonic_ms", clock.now_ms)
        line = self._prepared.get(transcript_id or "")
        budget = (line[0].speech_end_at if line is not None else self.rt.now()) + self.rt.settings.FACT_LATE_MS \
            - self.rt.now()
        start = mono()

        def left() -> int:
            return budget - (mono() - start)

        def expired() -> AgentResult:
            log.info("fact check for %r: not called, the line's fact deadline passed %d ms ago", text[:80], -left())
            return AgentResult(status="timeout", output=None, latency_ms=0, call_id="", error="line deadline passed",
                               meta={"failure": "client_timeout"})

        if left() <= 0:
            return expired()
        # D-172: a product the last lines named stays citable ("the ampoule on its own is $32," / "list price 42")
        passages = await self._fact_passages(" ".join([*judge_input.previous[-1:], text]), on_air, judge_input.switch,
                                             judge_input.promo)
        s = await self.rt.load_session()
        offers = [p for p in (self.rt.promo(ap.promo_id) for ap in s.active_promos) if p is not None and not p.changes_prices]
        notes = sorted((a for a in await self.rt.alerts() if a.kind == "fact" and a.status == "active"),
                       key=lambda a: a.created_at, reverse=True)  # D-363; D-398: every one, newest first
        if transcript_id is not None:
            self._fact_shown[transcript_id] = {a.alert_id for a in notes}
        inp = FactInput(utterance=text, on_air=on_air, switch=judge_input.switch, promo=judge_input.promo,
                        passages=passages, previous=judge_input.previous,
                        session_id=self.rt.sid, scenario=scenario,
                        offers=offers, parts=parts or [], notes=notes, now=self.rt.now(), chain=judge_input.chain)
        if transcript_id is not None:
            self._fact_inputs[transcript_id] = inp
        if left() <= 0:  # the lookups took the rest
            return expired()
        res = await self.facts.run(inp, deadline_ms=left())
        remaining = left()  # D-417/D-421: on the monotonic clock, so the call's audit save counts too
        if res.status in ("error", "invalid") and remaining < MIN_FACT_RETRY_MS:
            log.info("fact check %s (%s) for %r: no retry, %d ms left of the fact deadline", res.status, res.error,
                     text[:80], remaining)
        elif res.status in ("error", "invalid"):
            # D-203/D-388: one fresh call, for every line. D-408 (codex): only after a fast failure; an invalid answer is
            # asked again without JUDGE_SEED (the same seed tends to repeat it). A timeout is not retried: its failure
            # shows at once. The result's latency counts both calls. D-411: the retry gets only the time left
            first = res
            log.info("fact check %s (%s) for %r: once more within %d ms%s", res.status, res.error, text[:80],
                     remaining, ", without the seed" if res.status == "invalid" else "")
            res = await self.facts.run(inp, deadline_ms=remaining, seeded=first.status != "invalid")
            res.latency_ms += first.latency_ms
            res.meta["first_failure"] = first.status
        if res.status != "ok":
            log.info("fact check failed (%s: %s) for %r after %d ms%s", res.status, res.error, text[:80],
                     res.latency_ms, f", first {res.meta['first_failure']}" if "first_failure" in res.meta else "")
        return res

    async def _apply_compliance_locked(self, t: Transcript, on_air: str, res: AgentResult,
                                       merge: Merge | None = None) -> None:
        """§8.4.1 alerts and §8.4.5 corrections, or the judge-failed card. `res.output` is a ComplianceOutput or a full
        judge output."""
        rt = self.rt
        if not self._claim_application(t, "compliance"):
            return
        now = rt.now()
        alerts = await rt.alerts()
        # D-088: alerts raised by the fragments inside a merged utterance are never resolved by it
        protected = set(merge.chain) if merge else set()
        text = merge.text if merge else t.text
        judge = res.output if res.status == "ok" else None
        if judge is None:
            # D-288 (A1), D-410: a failed judge raises no alert; the host and the operator are told the line is unchecked
            await self._check_failed_locked(t, text, res, "compliance_judge")
        else:
            # D-397: a verdict on a line that a later merged line already judged (an older state of the chain) is
            # not applied; the merged line's verdict stands
            # D-401: only a merged verdict that succeeded counts (a failed one never blocks the fragment's)
            later = next((x for x, j in self._judged.items() if x != t.transcript_id
                          and t.transcript_id in j.chain and (x, "compliance") in self._verdict_ok), None)
            if later is not None:
                log.info("compliance %s t=%s: not applied, the merged line %s was judged after it", rt.sid,
                         t.transcript_id, later)
                return
            self._verdict_ok.add((t.transcript_id, "compliance"))
            # D-387 (user): every violation is its own alert. D-403/D-406 (user, option A): only on a merged line's
            # re-judgment (a line speech-to-text split), a violation the model marks as repeating an alert of that
            # line's own chain and product (`same_as`) keeps that alert, or leaves it closed; any other same_as is a
            # new alert
            split = set(merge.chain) if merge and not merge.pair else set()
            listed = {a.alert_id: a for a in alerts if a.kind == "compliance" and a.transcript_id in split}
            for v in judge.compliance.violations:
                same = getattr(v, "same_as", None)
                if same is not None and (same not in listed
                                         or listed[same].product_id != (getattr(v, "product_id", None) or on_air)):
                    log.info("compliance %s t=%s: same_as %s is not an alert of this merged line's chain and product: "
                             "a new alert", rt.sid, t.transcript_id, same)
                    v.same_as = None
            changed, created, closed = alert_logic.apply_judge_compliance(
                judge, t, on_air, rt.new_id, now, listed=listed)
            kept = {a.alert_id for a in changed if a.transcript_id != t.transcript_id}
            if kept or closed:
                log.info("compliance %s t=%s: same_as kept %s; not raised again (closed): %s", rt.sid, t.transcript_id,
                         sorted(kept), closed)
            # D-397/D-401/D-403: the merged line's verdict replaces the alerts its chain's lines raised: the ones it
            # neither repeats (same_as) nor corrects are cleared. Only transcript ids and the model's handles decide it
            chain = [a for a in alerts if a.kind == "compliance" and a.transcript_id in protected
                     and a.status == "active" and a.alert_id not in kept]
            fixed = set(judge.correction.corrects_alert_ids)
            for old in [x for x in chain if x.alert_id not in fixed]:  # one the verdict lists as fixed is corrected
                old.status, old.resolved_at = "cleared", now
                rt.ctx.scheduler.cancel(rt.key(f"escalate:{old.alert_id}"))
                changed.append(old)
            if protected:
                log.info("compliance %s t=%s: merged verdict over %s", rt.sid, t.transcript_id, sorted(protected))
            for a in created:
                await rt.save_alert(a)
                await rt.emit("alert.created", a)
                self._schedule_escalation(a)
                await self._on_active_locked(a)
            for a in changed:
                await self._save_alert_change_locked(a)
                if a.alert_id not in kept:  # D-403: a kept active one stays as is
                    await self._on_active_locked(a)
            # D-089: an apology alone does not correct a compliance alert
            await self._apply_corrections_locked(t, judge.correction.corrects_alert_ids, now)

    async def _apply_context_locked(self, t: Transcript, judge: ContextOutput | UtteranceJudgeOutput,
                                    merge: Merge | None = None) -> None:
        """§8.7.1 prompter points and cues, §8.7.2 switch."""
        rt = self.rt
        if not self._claim_application(t, "context"):
            return
        sw = judge.prompter.switch  # D-341 (review H18): the context verdict, for tracing a switch or a missed cue
        # D-450: production's context judge ticks no points (the prompter judge does); the legacy one-call judges do
        legacy_points = getattr(judge.prompter, "covered_point_ids", None) or []
        log.info("context %s t=%s: type=%s answer=%s points=%s cues=%s transition=%s quote=%s target=%s conf=%s%s",
                 rt.sid, t.transcript_id, judge.answer.utterance_type, judge.answer.matched_group_id,
                 legacy_points, judge.prompter.covered_cue_ids, sw.is_transition, sw.is_quote,
                 sw.target_product_id, sw.confidence,
                 f" expects_resolution={judge.expects_resolution}" if hasattr(judge, "expects_resolution") else "")
        if legacy_points:
            await self._apply_points_locked(t, legacy_points, "context")
        s = await rt.load_session()
        seg = await rt.current_segment()
        stale = (seg is None or seg.segment_id != t.segment_id
                 or self._generations.get(t.transcript_id) != self._segment_generation)
        if stale:
            log.info("context %s t=%s: said before a switch or undo; its points count, its cue and switch do not",
                     rt.sid, t.transcript_id)
            return
        if s.cue is not None and s.cue.status == "active" and s.cue.cue_id in judge.prompter.covered_cue_ids:
            s.cue.status, s.cue.done_by_transcript_id = "done", t.transcript_id
            await rt.save_session(s)
            await rt.emit("cue.updated", s.cue)
        if seg is not None:
            await self._switch_now_locked(judge, t, seg.product_id)

    async def _apply_points_locked(self, t: Transcript, point_ids: list[str], judge: str) -> None:
        """D-388 (user): the points a judge marked covered always count, on the line's own segment (as D-373 does for
        ticks), never on a product switched to later; the next product's go to pre_covered. An id that is not a point
        of the on-air or the next product is skipped (apply_coverage)."""
        rt = self.rt
        s = await rt.load_session()
        seg = await rt.current_segment()
        own = seg if seg is not None and seg.segment_id == t.segment_id else await rt.get_segment(t.segment_id)
        if own is None:
            log.info("%s %s t=%s: covered points %s skipped (cannot apply: the line's segment is gone)", judge, rt.sid,
                     t.transcript_id, point_ids)
            return
        added, pre = apply_coverage(point_ids, own, s, rt.catalog, rt.points)
        if added:
            await rt.save_segment(own)
            if seg is not None and own.segment_id == seg.segment_id:
                await rt.emit("prompter.updated", await rt.prompter_view_now(seg))
        if pre:
            await rt.save_session(s)

    async def _run_prompter(self, t: Transcript, inp: JudgeInput) -> None:
        """D-450: the prompter judge on this line (its own call; D-455: gemini-3.8-flash LOW, no deadline); its ticks go
        to the line's own segment whenever they come. A failure shows nothing on the host screen: it only counts for
        the operator."""
        rt = self.rt
        res = await self.prompter.run(PrompterInput(utterance=inp.utterance, on_air=inp.on_air,
                                                    previous=list(inp.previous), points=inp.points_by_product,
                                                    session_id=rt.sid, scenario=inp.scenario),
                                      deadline_ms=None)
        async with rt.lock:
            if res.status != "ok" or res.output is None:
                await self._prompter_failed_locked(t, res)
                return
            covered = res.output.covered
            log.info("prompter %s t=%s: covered %s", rt.sid, t.transcript_id,
                     [(c.point_id, c.host_words) for c in covered])
            if covered:
                await self._apply_points_locked(t, list(dict.fromkeys(c.point_id for c in covered)), "prompter")

    async def _prompter_failed_locked(self, t: Transcript, res: AgentResult) -> None:
        """D-450: a failed prompter check is counted with the other failures of the last 5 minutes (the operator's
        counts, D-412); it never makes the line unchecked and never shows the host's "AI busy" strip."""
        rt = self.rt
        now, cause = rt.now(), failure_cause(res)
        self.failures = {k: v for k, v in self.failures.items() if now - v["at"] < FAILURE_WINDOW_MS}
        self._failure_n += 1
        event = {"transcript_id": t.transcript_id, "agent": "prompter_judge", "cause": cause, "at": now,
                 "n": self._failure_n}
        self.failures[(t.transcript_id, "prompter_judge")] = event
        log.info("prompter check failed %s t=%s: %s (%s)", rt.sid, t.transcript_id, cause, res.meta.get("failure"))
        await rt.emit("prompter.failed", event)

    async def _check_failed_locked(self, t: Transcript, text: str, res: AgentResult, agent: str) -> None:
        """D-288/D-408/D-412: a check of this line failed. The events say why (`cause`). D-416: each failure event
        (line, agent) counts once in the last 5 minutes; the line stays unchecked until a line said at or after it is
        answered normally."""
        rt = self.rt
        now, cause = rt.now(), failure_cause(res)
        self.failures = {k: v for k, v in self.failures.items() if now - v["at"] < FAILURE_WINDOW_MS}
        self._failure_n += 1
        event = {"transcript_id": t.transcript_id, "agent": agent, "cause": cause, "at": now, "n": self._failure_n}
        self.failures[(t.transcript_id, agent)] = event
        first = t.transcript_id not in self.unchecked
        self.unchecked.setdefault(t.transcript_id, {})[agent] = event
        log.info("check failed %s t=%s: %s %s (%s)", rt.sid, t.transcript_id, agent, cause, res.meta.get("failure"))
        if first:  # D-416: the line is unchecked once, whichever judges failed on it
            await rt.emit("line.check", {"transcript_id": t.transcript_id, "text": text, "rule_ids": [], "phrases": [],
                                         "cause": cause, "at": now})
        await rt.emit("judge.failed", {"transcript_id": t.transcript_id, "agent": agent, "cause": cause, "at": now,
                                       "n": event["n"]})

    def check_failures(self) -> dict:
        """D-412/D-416/D-420: the snapshot's block, by the live stream's rule: the last 5 minutes' failure events (for
        the per-cause count) and every failure event of the lines still unchecked (whatever their age), each in
        (at, n) order; the screens derive the strip's latest cause from the second list."""
        now = self.rt.now()
        order = lambda v: (v["at"], v["n"])  # noqa: E731
        recent = sorted((v for v in self.failures.values() if now - v["at"] < FAILURE_WINDOW_MS), key=order)
        return {"recent": recent, "unchecked": sorted((v for line in self.unchecked.values() for v in line.values()),
                                                      key=order)}

    async def _apply_corrections_locked(self, t: Transcript, listed: list[str], now: int) -> None:
        """D-304/D-390: the alerts the compliance judge says this line fixes (by handle), applied as given; no word
        check, no replacement match, no merge protection (a line may fix an alert of its own merged fragments)."""
        rt = self.rt
        earlier = [a for a in await rt.alerts()
                   if self._sequence.get(a.transcript_id, 0) < self._sequence.get(t.transcript_id, 1)]
        ids = {a.alert_id for a in earlier if a.kind == "compliance"}
        accepted = [i for i in dict.fromkeys(listed) if i in ids]
        self._log_corrections(t, listed, accepted)
        if not accepted:
            return
        for a in alert_logic.apply_corrections(earlier, accepted, t, now):
            rt.ctx.scheduler.cancel(rt.key(f"escalate:{a.alert_id}"))
            await rt.save_alert(a)
            await rt.emit("alert.updated", a)

    def _log_corrections(self, t: Transcript, listed: list[str], accepted: list[str]) -> None:
        """D-352: per alert the judge was shown or listed: was it in ACTIVE_ALERTS, did the judge list it, the result."""
        inp = self._inputs.get(t.transcript_id)
        shown = {a.alert_id for a in inp.active_alerts if a.kind == "compliance"} if inp is not None else set()
        for aid in sorted(shown | set(listed)):
            result = ("applied" if aid in accepted else "not an alert of an earlier line" if aid in listed
                      else "not listed")
            log.info("correction %s t=%s: alert=%s in_active_alerts=%s listed=%s -> %s", self.rt.sid,
                     t.transcript_id, aid, aid in shown, aid in listed, result)

    async def _on_active_locked(self, a: Alert) -> None:
        """D-352: an alert just turned active. The later lines judged without this alert (at most 2, within LATE_CORRECTION_MS of
        its line, any segment) are asked once each, by the compliance judge, whether they correct it or say it again
        with the qualifier. A failed call is never a correction. D-357: "judged without it" means the line's judge
        input was built before the alert existed, whether or not that line's own verdict has come back yet (it often
        has not); every trigger decision is logged."""
        rt = self.rt
        if a.kind != "compliance" or a.status != "active":
            return
        origin = self._prepared.get(a.transcript_id)
        seq = self._sequence.get(a.transcript_id, 0)
        since = origin[0].received_at if origin else a.created_at
        later = sorted((x for x, _, _ in self._prepared.values() if self._sequence.get(x.transcript_id, 0) > seq),
                       key=lambda x: self._sequence[x.transcript_id])
        fire = []
        for x in later:
            inp = self._inputs.get(x.transcript_id)
            if x.received_at - since > LATE_CORRECTION_MS:
                why = f"more than {LATE_CORRECTION_MS} ms after the alert's line"
            elif inp is None:
                why = "not judged yet (its judgment will show this alert)"
            elif any(b.alert_id == a.alert_id for b in inp.active_alerts):
                why = "its judgment already showed this alert"
            elif len(fire) >= LATE_CORRECTION_LINES:
                why = f"only the first {LATE_CORRECTION_LINES} lines are asked"
            else:
                fire.append(x)
                why = None
            log.info("correction %s re-check trigger: alert=%s rule=%s t=%s -> %s", rt.sid, a.alert_id, a.rule_id,
                     x.transcript_id, "fired" if why is None else f"skipped ({why})")
        if not later:
            log.info("correction %s re-check trigger: alert=%s rule=%s -> no later line", rt.sid, a.alert_id,
                     a.rule_id)
        for x in fire:
            task = rt.spawn(self._recheck_correction(a.alert_id, x, origin[1] if origin else None),
                            name=f"recheck:{a.alert_id}:{x.transcript_id}")
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)

    async def _correct_locked(self, a: Alert, t: Transcript) -> None:
        rt = self.rt
        for x in alert_logic.apply_corrections([a], [a.alert_id], t, rt.now()):
            rt.ctx.scheduler.cancel(rt.key(f"escalate:{x.alert_id}"))
            await rt.save_alert(x)
            await rt.emit("alert.updated", x)

    async def _recheck_correction(self, alert_id: str, t: Transcript, alert_line: str | None) -> None:
        """D-352: one compliance-judge call on a line judged before `alert_id` existed: does it correct it?"""
        rt = self.rt
        async with rt.lock:
            a = await rt.get_alert(alert_id)
            if a is None or a.status != "active":
                return
            seg = await rt.get_segment(t.segment_id) if t.segment_id else await rt.current_segment()
            text = self._prepared[t.transcript_id][1] if t.transcript_id in self._prepared else t.text
            inp = JudgeInput(utterance=text, on_air=seg.product_id if seg else a.product_id, active_alerts=[a],
                             previous=[alert_line] if alert_line else [], session_id=rt.sid)
        res = await self.compliance.run(inp, deadline_ms=rt.settings.VERIFY_TIMEOUT_MS)
        listed = res.output.correction.corrects_alert_ids if res.status == "ok" and res.output is not None else []
        log.info("correction %s re-check: alert=%s t=%s status=%s listed=%s", rt.sid, alert_id, t.transcript_id,
                 res.status, alert_id in listed)
        if alert_id not in listed:
            return
        async with rt.lock:
            a = await rt.get_alert(alert_id)
            if a is not None and a.status == "active":
                await self._correct_locked(a, t)

    async def _save_alert_change_locked(self, a: Alert) -> None:
        await self.rt.save_alert(a)
        await self.rt.emit("alert.updated", a)
        if a.status == "active":
            self._schedule_escalation(a)

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

    async def _switch_now_locked(self, judge: ContextOutput | UtteranceJudgeOutput, t: Transcript, on_air: str) -> None:
        """D-349 (D-415: the only switch): the context judge's transition verdict alone switches, at once. D-351 (the
        user's rule): the host says they move on AND names the next product (its name, short name or type word), as
        the model judged it (`moving_to_next_named`; no code string match). The target is only the next product in
        the run sheet; naming any other product does not switch, and nothing recovers a missed switch (the operator
        switches by hand). No confirming line, no pending countdown; the host gets an Undo bar and the 60 s undo
        stays. A verdict on a line said before a switch or an undo is never applied (`_apply_context_locked` drops
        it by its segment generation), so a switch is never applied twice."""
        rt = self.rt
        sw = judge.prompter.switch
        nxt = rt.catalog.next_product(on_air)
        named = getattr(sw, "moving_to_next_named", False)
        # the model's one decision; code checks only that it is not a quote and that the target is the next product
        # (a line that answers a viewer and then moves on can switch; there is no confidence threshold)
        go = nxt is not None and named and not sw.is_quote and sw.target_product_id == nxt
        if not (sw.is_transition or named or go):
            return
        decision = {"transcript_id": t.transcript_id, "switch": go, "on_air": on_air, "target_product_id":
                    sw.target_product_id, "confidence": sw.confidence, "is_quote": sw.is_quote, "named": named,
                    "utterance_type": judge.answer.utterance_type, "reason": judge.reason}
        log.info("switch decision %s t=%s: switch=%s on_air=%s next=%s target=%s named=%s conf=%s quote=%s type=%s "
                 "reason=%r", rt.sid, t.transcript_id, go, on_air, nxt, sw.target_product_id, named, sw.confidence,
                 sw.is_quote, judge.answer.utterance_type, judge.reason)
        await rt.emit("segment.switch_decided", decision)
        if go:
            await commit_switch_locked(rt, nxt, "auto_speech")

    # ---- steps 5-6 -----------------------------------------------------------------------------

    async def _apply_facts_locked(self, t: Transcript, facts: FactCheckOutput, protected: set[str]) -> None:
        rt = self.rt
        if not self._claim_application(t, "facts"):
            return
        for c in facts.claims:  # D-158: the only trace of a cloud replay (no session data is kept)
            log.info("facts %s t=%s: %s %s said=%r verdict=%s correct=%r", rt.sid, t.transcript_id, c.product_id,
                     c.field, c.stated_value, c.verdict, c.correct_value)
        # D-398: a verdict on a line that a later merged line already judged (an older state of the chain) is not applied
        later = next((x for x, j in self._judged.items() if x != t.transcript_id
                      and t.transcript_id in j.chain and (x, "facts") in self._verdict_ok), None)
        if later is not None:
            log.info("facts %s t=%s: not applied, the merged line %s was judged after it", rt.sid, t.transcript_id,
                     later)
            return
        self._verdict_ok.add((t.transcript_id, "facts"))  # D-401: only a verdict that came back is applied here
        # D-374 (user, 10/9): every claim of the verdict is applied as given (no D-117 per-subject ordering drop)
        claims = list(facts.claims)
        fresh = await self._fact_alerts_locked(t, claims, protected, getattr(facts, "_corrects", []))
        await self._correct_fact_notes_locked(t, getattr(facts, "_corrects", []), fresh)
        await self._tick_prompter_locked(t, facts.claims)  # D-373: every supported claim of the line

    async def _fact_alerts_locked(self, t: Transcript, claims: list, protected: set[str], corrects=()) -> set[str]:
        """D-398: one note per contradicted claim. D-403 (user, option A): a contradiction the model marks as repeating
        a listed note (`same_as`) raises nothing new: an active note is kept (its words take the new verdict), a closed
        one stays closed. A merged line's verdict replaces the notes its chain's lines raised (`protected`, transcript
        ids only): the ones it neither repeats nor marks fixed (`corrects`) are cleared. Returns the ids it showed."""
        rt = self.rt
        now = rt.now()
        alerts = await rt.alerts()
        # D-406: only a note of this merged line's own chain and product can be repeated; any other same_as is new
        by_id = {a.alert_id: a for a in alerts if a.kind == "fact" and a.transcript_id in protected}
        rest, kept, closed = [], [], []
        for c in claims:
            sid = getattr(c, "same_as", None) if c.verdict == "contradicted" else None
            same = by_id.get(sid or "")
            if same is not None and same.product_id != c.product_id:
                same = None
            if sid is not None and same is None:
                log.info("facts %s t=%s: same_as %s is not a note of this merged line's chain and product: a new note",
                         rt.sid, t.transcript_id, sid)
            if same is None:
                rest.append(c)
            elif same.status == "active":
                same.span, same.stated_value, same.say = c.span, c.stated_value, c.say or same.say
                kept.append(same)
            else:
                closed.append(same.alert_id)
        if kept or closed:
            log.info("facts %s t=%s: same_as kept %s; not raised again (closed): %s", rt.sid, t.transcript_id,
                     [a.alert_id for a in kept], closed)
        created = fact_logic.apply_fact_check(rest, t, rt.new_id, now)
        keep = {a.alert_id for a in kept} | set(corrects)
        chain = [a for a in alerts if a.kind == "fact" and a.status == "active" and a.transcript_id in protected
                 and a.alert_id not in keep]
        for a in kept:
            await rt.save_alert(a)
            await rt.emit("alert.updated", a)
        for old in chain:
            old.status, old.resolved_at = "cleared", now
            await rt.save_alert(old)
            await rt.emit("alert.updated", old)
        if protected and chain:
            log.info("facts %s t=%s: merged verdict over %s: cleared %s", rt.sid, t.transcript_id,
                     sorted(protected), [a.alert_id for a in chain])
        for a in created:
            await rt.save_alert(a)
            await rt.emit("alert.created", a)
            self._on_fact_note_active(a)
        return {a.alert_id for a in created} | {a.alert_id for a in kept}

    async def _correct_fact_notes_locked(self, t: Transcript, note_ids, fresh=()) -> None:
        """D-363: the fact notes the model marked fixed (by handle), and nothing else. D-364: in line order: a fix
        from a line said before the note's latest showing (T1 wrong, T2 fix, T3 wrong again, T2's verdict last) never
        closes it."""
        rt = self.rt
        seq = self._sequence.get(t.transcript_id, 0)
        alerts = await rt.alerts()
        stale = {a.alert_id for a in alerts if a.alert_id in note_ids and self._sequence.get(a.transcript_id, 0) > seq}
        if stale:
            log.info("fact notes %s t=%s: fix of %s skipped, the note was shown again by a later line", rt.sid,
                     t.transcript_id, sorted(stale))
        for a in fact_logic.correct_notes(set(note_ids) - stale, alerts, t, rt.now(), fresh):
            await rt.save_alert(a)
            await rt.emit("alert.updated", a)

    async def _tick_prompter_locked(self, t: Transcript, claims: list) -> None:
        """D-372: the prompter items (price lines, ingredient amounts, cautions) a supported claim cites are ticked as
        said. A contradiction ticks nothing; reported speech never reaches `supported` (v5). D-373: routed by the
        line's own segment (captured with its input), not by what is on air when the verdict arrives: that segment for
        its product; for the product that had just left the air in the line's scope, that product's segment before it;
        when the line's segment is gone (an undone switch), the product's open segment, else its pre_covered."""
        rt = self.rt
        inp = self._fact_inputs.get(t.transcript_id)
        if inp is None:
            return
        shown = {p.passage_id: p.product_id for p in inp.passages}  # the snapshot this check read
        cited: dict[str, list[str]] = {}
        for c in claims:
            if c.verdict != "supported":
                continue
            for pid in getattr(c, "_cited", None) or ([c.passage_id] if c.passage_id else []):
                if tick_item(pid) and pid in shown:
                    cited.setdefault(shown[pid], []).append(pid)
        if not cited:
            return
        s, segs = await rt.load_session(), await rt.segments()
        seg = next((x for x in segs if x.ended_at is None), None)  # on air now
        line_seg = next((x for x in segs if x.segment_id == t.segment_id), None)
        for product_id, ids in cited.items():
            target = None
            if line_seg is None:  # the line's segment was undone: the product's open segment, else pre_covered
                target = seg if seg is not None and seg.product_id == product_id else None
            elif line_seg.product_id == product_id:
                target = line_seg
            else:
                # D-377: the product that just left the air (its latest segment closed within the dual scope before
                # the line) gets that segment, whatever the run-sheet order; otherwise (a product to come) its segment
                # opened after the line, else pre_covered. Never an older segment (D-376).
                scope_ms = rt.settings.SWITCH_DUAL_SCOPE_SEC * 1000
                left = max((x for x in segs if x.product_id == product_id and x.ended_at is not None
                            and x.started_at < line_seg.started_at), key=lambda x: x.started_at, default=None)
                # D-381: a segment that ended before the line's segment was reopened by an undo did not just leave:
                # the product that left is the undone one (its segment is gone)
                # D-382: the reopen state when the line was said (a later undo does not change it)
                reopen = max((r for r in line_seg.reopen_times if r <= t.received_at), default=None)
                stale = reopen is not None and left is not None and left.ended_at < reopen
                if left is not None and not stale and 0 <= t.received_at - left.ended_at <= scope_ms:
                    target = left
                elif seg is not None and seg.product_id == product_id and seg.started_at > line_seg.started_at:
                    target = seg
            if target is not None:
                new = [i for i in dict.fromkeys(ids) if i not in target.ticked_item_ids]
                if new:
                    target.ticked_item_ids.extend(new)
                    await rt.save_segment(target)
                    if target is seg:
                        await rt.emit("prompter.updated", await rt.prompter_view_now(seg))
                log.info("prompter ticks %s t=%s: %s +%s", rt.sid, t.transcript_id, product_id, new)
            else:  # no segment of it to tick: kept for when it goes on air
                pre = s.pre_covered.setdefault(product_id, [])
                pre.extend(i for i in dict.fromkeys(ids) if i not in pre)
                await rt.save_session(s)
                log.info("prompter ticks %s t=%s: %s has no segment for this line; pre-ticked %s", rt.sid,
                         t.transcript_id, product_id, ids)

    def _on_fact_note_active(self, a: Alert) -> None:
        """D-363 (as D-357 for compliance): a fact note just appeared; the later lines whose fact check was shown no
        such note (at most 2, within LATE_CORRECTION_MS of its line) are asked once each whether they fix it."""
        rt = self.rt
        origin = self._prepared.get(a.transcript_id)
        seq = self._sequence.get(a.transcript_id, 0)
        since = origin[0].received_at if origin else a.created_at
        fire = []
        for x in sorted((x for x, _, _ in self._prepared.values() if self._sequence.get(x.transcript_id, 0) > seq),
                        key=lambda x: self._sequence[x.transcript_id]):
            shown = self._fact_shown.get(x.transcript_id)
            if x.received_at - since > LATE_CORRECTION_MS:
                why = f"more than {LATE_CORRECTION_MS} ms after the note's line"
            elif shown is None:
                why = "not checked yet (its check will show this note)"
            elif a.alert_id in shown:
                why = "its check already showed this note"
            elif len(fire) >= LATE_CORRECTION_LINES:
                why = f"only the first {LATE_CORRECTION_LINES} lines are asked"
            else:
                fire.append(x)
                why = None
            log.info("fact note %s re-check trigger: note=%s t=%s -> %s", rt.sid, a.alert_id, x.transcript_id,
                     "fired" if why is None else f"skipped ({why})")
        for x in fire:
            task = rt.spawn(self._recheck_fact_note(a.alert_id, x), name=f"factcheck:{a.alert_id}:{x.transcript_id}")
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)

    async def _recheck_fact_note(self, note_id: str, t: Transcript) -> None:
        """D-363: one fact-check call on a line checked before the note existed: does it fix this note?"""
        rt = self.rt
        async with rt.lock:
            a = await rt.get_alert(note_id)
            if a is None or a.status != "active":
                return
        original = self._fact_inputs.get(t.transcript_id)
        if original is None:
            log.info("fact note %s re-check: note=%s t=%s skipped (its fact-check input is gone)", rt.sid, note_id,
                     t.transcript_id)
            return
        # D-364: the line's own context (its on-air product, previous lines, switch state, passages), only the note
        # added; never rebuilt from the current product (a line about B after a switch is not re-checked as A)
        inp = dataclasses.replace(original, notes=[a], now=rt.now())
        res = await self.facts.run(inp, deadline_ms=rt.settings.FACT_LATE_MS)
        fixed = res.status == "ok" and res.output is not None and note_id in getattr(res.output, "_corrects", [])
        log.info("fact note %s re-check: note=%s t=%s status=%s fixed=%s", rt.sid, note_id, t.transcript_id,
                 res.status, fixed)
        if fixed:
            async with rt.lock:
                await self._correct_fact_notes_locked(t, [note_id])
        if res.status == "ok" and res.output is not None:  # D-373: the re-check's supported claims tick too
            async with rt.lock:
                await self._tick_prompter_locked(t, res.output.claims)

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
    if old is not None:
        old.ended_at = now
        await rt.save_segment(old)
    item = rt.catalog.runsheet_item(target)
    new = Segment(segment_id=rt.new_id("seg_"), product_id=target, order=item.order, started_at=now,
                  start_reason=reason, planned_duration_sec=item.planned_duration_sec,
                  covered_point_ids=[x for x in s.pre_covered.get(target, []) if not tick_item(x)],
                  ticked_item_ids=[x for x in s.pre_covered.pop(target, []) if tick_item(x)])  # D-372
    await rt.save_segment(new)
    s.current_segment_id = new.segment_id
    s.switch = SwitchState(last_commit={"closed_segment_id": old.segment_id if old else None,
                                        "opened_segment_id": new.segment_id, "at": now})
    if old is not None:  # D-349: the judges get both products for a few seconds
        s.switch.previous_product_id = old.product_id
        s.switch.previous_until = now + rt.settings.SWITCH_DUAL_SCOPE_SEC * 1000
    s.switch.last_commit["immediate"] = reason == "auto_speech"  # the host's "Switched to … · Undo" bar
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
        closed.reopen_times.append(now)  # D-381/382
        await rt.save_segment(closed)
        await rt.ctx.store.delete(rt.path("segments"), opened.segment_id)
        if opened.covered_point_ids or opened.ticked_item_ids:  # D-372: the ticks go back with the points
            pre = s.pre_covered.setdefault(opened.product_id, [])
            pre.extend(p for p in opened.covered_point_ids + opened.ticked_item_ids if p not in pre)
        s.current_segment_id, s.switch = closed.segment_id, SwitchState()
        s.switch.previous_product_id = opened.product_id  # D-349: both products for a few seconds after an undo
        s.switch.previous_until = now + rt.settings.SWITCH_DUAL_SCOPE_SEC * 1000
        await rt.save_session(s)
        await rt.emit("segment.undone", {"segment_id": opened.segment_id})
        await rt.emit("segment.started", closed)
        await rt.emit("prompter.updated", await rt.prompter_view_now(closed))
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
        await rt.save_alert(a)
        await rt.emit("alert.updated", a)
        await rt.emit("operator.action", {"actor": "operator", "action": "dismiss_alert", "alert_id": aid, "at": rt.now()})


async def correction_cue(rt: "SessionRuntime", aid: str) -> HostCue:
    async with rt.lock:
        a = await _alert_or_404(rt, aid)
        # D-436: a red claim is taken back first: the language pack's retraction phrase, then say_instead
        say = " ".join(x for x in (rt.pack.lang_pack.retraction_phrase, a.say_instead or "") if x)
        text = f"Take it back, then say: '{say}'" if a.kind == "compliance" else f"Say: {a.correct_value}"
        cue = await set_cue_locked(rt, text, None)
        await rt.emit("operator.action", {"actor": "operator", "action": "alert_cue", "alert_id": aid, "at": rt.now()})
        return cue


async def resend_fact(rt: "SessionRuntime", pipeline: UtterancePipeline, aid: str) -> None:
    """D-402: a note never leaves the host until it is closed; resending makes it the newest (first in the stack)."""
    async with rt.lock:
        a = await _alert_or_404(rt, aid)
        if a.kind != "fact" or a.status != "active":
            raise ActionError(409, "invalid_state", "only an active fact note can be resent")
        a.shown_at = rt.now()
        await rt.save_alert(a)
        await rt.emit("alert.updated", a)
        await rt.emit("operator.action", {"actor": "operator", "action": "resend", "alert_id": aid, "at": rt.now()})


async def post_notice(rt: "SessionRuntime", aid: str, text: str) -> Message:
    async with rt.lock:
        await _alert_or_404(rt, aid)
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
