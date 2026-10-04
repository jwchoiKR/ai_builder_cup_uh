"""AI PD candidates and the deterministic fallback (PLANNING 5.1.1).

The AI PD never writes its own wording. Every candidate carries verified text: a suggested answer
that passed verify_answer, a promo's viewer text, or a fixed switch/wrap-up line with the missing
required prompter points verbatim. The model (or the rule fallback) only picks one candidate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models.data import PrompterPoint

HOLD_MS = 15_000  # a shown card is not replaced before this
SILENCE_MS = 8_000  # STT gives finals only, so 8 s without a final counts as a pause
PROMO_JUST_STARTED_MS = 30_000
PROMO_ENDING_MS = 60_000


@dataclass(frozen=True)
class Question:
    group_id: str
    question: str
    answer: str  # verified suggested answer


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

    @property
    def elapsed_ratio(self) -> float:
        return (self.now - self.started_at) / self.planned_ms if self.planned_ms else 0.0

    @property
    def silent(self) -> bool:
        return self.last_final_at is not None and self.now - self.last_final_at >= SILENCE_MS

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
    for q in st.questions:
        out.append(Candidate(f"question:{q.group_id}", "answer_question", q.answer, q.question, q.group_id, 3))
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
