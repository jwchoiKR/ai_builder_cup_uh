"""AI PD candidates and the deterministic fallback (PLANNING 5.1.1).

The AI PD never writes its own wording. Every candidate carries verified text: a suggested answer
that passed verify_answer, a promo's viewer text, or a fixed switch/wrap-up line with the missing
required prompter points verbatim. The model (or the rule fallback) only picks one candidate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models.data import PrompterPoint

HOLD_MS = 15_000  # a shown card is not replaced before this
Q_GAP_MS = 45_000  # D-113: question cards (answer, read-out, which product) start at least this far apart
SHOUT_GAP_MS = 30_000  # D-113: shout-out cards
SHOUT_MAX_AGE_MS = 120_000  # an older purchase or welcome comment is not read out any more
QUESTION_KINDS = frozenset({"answer_question", "read_question", "clarify_product"})
SHOUT_TEMPLATES = {
    "purchase": "Thank you {name} for your order!",
    "first_time": "Welcome {name}, great to have you here for the first time!",
    "compliment": "Thank you {name}, so glad you like it!",
}
SILENCE_MS = 8_000  # STT gives finals only, so 8 s without a final counts as a pause
# D-146 (sealed show replay: a beginner talks with 5-7 s gaps, so 7 host questions never got a card): a question
# that waited this long on the host's list gets its card at the next natural break, without a pause
CEILING_MS = 90_000
URGENT_CEILING_MS = 30_000  # sensitive questions and questions with 3+ askers
BREAK_MS = 2_000  # a natural break: right after a final
DUE_GAP_MS = 20_000  # a due card still waits this long after the last question card
# D-161 (local SEED1 replay: a red nobody corrected blocked every card for the rest of the show): a red alert
# blocks cards this long after it was created; then it stays on the prompter until corrected and cards resume
# below it (D-177: the escalation no longer restarts the block, so it is 20 s, not 25 s)
RED_BLOCK_MS = 20_000
PROMO_JUST_STARTED_MS = 30_000
PROMO_ENDING_MS = 60_000


@dataclass(frozen=True)
class Question:
    group_id: str
    question: str
    answer: str | None  # verified suggested answer; None for "which product?"
    kind: str = "answer"  # answer | read (AI already answered, many asked) | clarify (product unclear)
    askers: int = 1
    pushed: bool = False  # team show: the operator pushed it; it skips the time gap
    waiting_ms: int = 0  # D-146: time on the host's waiting list
    urgent: bool = False  # D-146: sensitive, or HOST_REPEAT_THRESHOLD+ askers: a shorter ceiling


@dataclass(frozen=True)
class ShoutOut:
    comment_id: str
    name: str
    kind: str  # purchase | first_time | compliment
    at: int


@dataclass(frozen=True)
class PromoState:
    promo_id: str
    viewer_text: str
    started_at: int
    ends_at: int


@dataclass
class PdState:
    now: int
    segment_id: str
    product_id: str
    product_name: str
    started_at: int
    planned_ms: int
    points: list[PrompterPoint]
    required_ids: list[str]
    covered_ids: list[str]
    next_product: tuple[str, str] | None  # (product_id, name)
    questions: list[Question] = field(default_factory=list)
    promos: list[PromoState] = field(default_factory=list)
    high_alert_active: bool = False
    last_final_at: int | None = None
    recent_lines: list[str] = field(default_factory=list)
    dismissed_refs: frozenset[str] = frozenset()
    product_names: list[str] = field(default_factory=list)  # run sheet order, for "which product?"
    last_question_card_at: int | None = None
    last_shout_at: int | None = None
    pull: bool = False  # the host pulled the top waiting question now (skips the gap and the pause)
    shoutouts: list[ShoutOut] = field(default_factory=list)

    @property
    def elapsed_ratio(self) -> float:
        return (self.now - self.started_at) / self.planned_ms if self.planned_ms else 0.0

    @property
    def silent(self) -> bool:
        return self.last_final_at is not None and self.now - self.last_final_at >= SILENCE_MS

    @property
    def pause(self) -> bool:
        """A good moment for a new card: the host paused, or has not spoken yet."""
        return self.last_final_at is None or self.silent

    @property
    def missing_required(self) -> list[PrompterPoint]:
        return [p for p in self.points if p.point_id in self.required_ids and p.point_id not in self.covered_ids]


@dataclass(frozen=True)
class Candidate:
    cid: str
    kind: str
    say: str
    detail: str | None
    ref_id: str
    priority: int  # rule fallback order, lower first
    askers: int | None = None
    forced: bool = False  # D-153: a pulled, pushed or due question: the model may not answer "none" to it


def red_blocks(alerts, now: int) -> bool:
    """D-161, D-177: an active HIGH compliance alert created less than RED_BLOCK_MS ago."""
    return any(a.kind == "compliance" and a.status == "active" and a.severity == "HIGH"
               and now - a.created_at < RED_BLOCK_MS for a in alerts)


def candidates(st: PdState) -> list[Candidate]:
    """Every card the AI PD may show now, in rule order. Empty during a red alert."""
    if st.high_alert_active:
        return []
    out: list[Candidate] = []
    for p in st.promos:
        if st.now - p.started_at <= PROMO_JUST_STARTED_MS:
            out.append(Candidate(f"promo:{p.promo_id}", "promo", p.viewer_text, "Promo just started", p.promo_id, 1))
        elif 0 < p.ends_at - st.now <= PROMO_ENDING_MS:
            secs = (p.ends_at - st.now) // 1000
            out.append(Candidate(f"promo:{p.promo_id}", "promo", p.viewer_text, f"Ends in {secs} s", p.promo_id, 1))
    # D-107: no "say this point" card. The prompter's highlighted next required point is the cue;
    # the switch and wrap-up cards name the required points still to say, verbatim.
    # D-113: one question card at a time, at a pause and at least Q_GAP_MS after the last one. An
    # operator push skips the gap (still at a pause); the host's pull takes the top one at once.
    gap_ok = st.last_question_card_at is None or st.now - st.last_question_card_at >= Q_GAP_MS
    waiting = [q for q in st.questions if q.group_id not in st.dismissed_refs]  # the host skipped these
    at_break = st.last_final_at is not None and st.now - st.last_final_at <= BREAK_MS
    due_gap_ok = st.last_question_card_at is None or st.now - st.last_question_card_at >= DUE_GAP_MS
    for i, q in enumerate(waiting):
        pulled = st.pull and i == 0
        due = q.waiting_ms >= (URGENT_CEILING_MS if q.urgent else CEILING_MS) and due_gap_ok and (at_break or st.pause)
        if not (pulled or due or (st.pause and (gap_ok or q.pushed))):
            continue
        prio = 0 if (pulled or q.pushed) else (1 if q.urgent else 2) if due else 3
        forced = prio < 3
        if q.kind == "clarify":
            say = f"Which product do you mean: {' or '.join(st.product_names)}?"
            cand = Candidate(f"question:{q.group_id}", "clarify_product", say, q.question, q.group_id, prio, q.askers,
                             forced)
        elif q.kind == "read" and q.answer:
            detail = f"{q.askers} people asked: {q.question}"
            cand = Candidate(f"question:{q.group_id}", "read_question", q.answer, detail, q.group_id, prio, q.askers,
                             forced)
        elif q.answer:
            cand = Candidate(f"question:{q.group_id}", "answer_question", q.answer, q.question, q.group_id, prio,
                             q.askers, forced)
        else:
            continue
        out.append(cand)
    # D-113: shout-outs only at a pause, never while questions are waiting, at least SHOUT_GAP_MS apart
    if (st.pause and not waiting and st.shoutouts
            and (st.last_shout_at is None or st.now - st.last_shout_at >= SHOUT_GAP_MS)):
        so = st.shoutouts[0]
        out.append(Candidate(f"shout:{so.comment_id}", "shout_out", SHOUT_TEMPLATES[so.kind].format(name=so.name),
                             None, so.comment_id, 6))
    if st.elapsed_ratio >= 0.8:
        missing = st.missing_required
        before = "; ".join(p.text.rstrip(". ") for p in missing)
        left = f"{len(missing)} required point{'s' if len(missing) != 1 else ''} left" if missing else None
        # the missing points are part of the id, so the card text is refreshed when one is said
        tag = "".join(f":{p.point_id}" for p in missing)
        if st.next_product:
            pid, name = st.next_product
            say = f"Before switching: {before}, then introduce {name}." if missing else f"Next up: {name}"
            out.append(Candidate(f"switch:{pid}{tag}", "switch_product", say, left or "Required points done", pid,
                                 2 if missing else 3))
        else:
            tail = "thank viewers and remind them of today's live price."
            say = f"Before wrapping up: {before}, then {tail}" if missing else f"Wrap up: {tail}"
            out.append(Candidate(f"wrap:{st.product_id}{tag}", "wrap_up", say,
                                 left or "Last product, time is nearly up", st.product_id, 2 if missing else 3))
    out = [c for c in out if c.ref_id not in st.dismissed_refs]
    return sorted(out, key=lambda c: c.priority)


def rule_pick(cands: list[Candidate]) -> Candidate | None:
    return cands[0] if cands else None
