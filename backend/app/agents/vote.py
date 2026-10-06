"""D-302 (JUDGE_ARM=vote): the semantic code drops replaced by model votes. The first pass (code drops off, as the
R2 flagger) runs as today; a line with a candidate gets two more runs of the same agent in parallel, and a
candidate is kept by the votes: 3/3 at the rule's severity, 2/3 capped at MEDIUM, 1/3 dropped ("vote: 1/3"). An
extra run that fails is no vote; when both fail, the candidate is kept, unverified."""
from __future__ import annotations

import logging
import re

from ..logic.catalog import Catalog
from ..models.agent_io import ComplianceOutput, FactCheckOutput
from ..providers.llm import AgentResult
from .fact_checker import _drop, _numbers
from .utterance_judge import _cdrop

log = logging.getLogger(__name__)


def _words(text: str | None) -> set[str]:
    return {w[:5] for w in re.findall(r"\w+", (text or "").casefold()) if len(w) >= 3}


def _overlap(a: str | None, b: str | None) -> bool:
    """Two spans of one line overlap: one holds the other, or they share a word."""
    x, y = (a or "").casefold(), (b or "").casefold()
    return bool(x and y) and (x in y or y in x or bool(_words(x) & _words(y)))


def _ok(extras: list[AgentResult]) -> list:
    return [r.output for r in extras if r.status == "ok" and r.output is not None]


def compliance_votes(first: ComplianceOutput, extras: list[AgentResult], catalog: Catalog) -> ComplianceOutput:
    rules = catalog.pack.rules_by_id
    runs = _ok(extras)
    cat = lambda rid: rules[rid].category if rid in rules else ""  # noqa: E731
    dropped = set()
    for v in first.compliance.violations:
        if v.is_negated or v.is_quoted:
            continue
        if not runs:
            v._votes, v._unverified = 1, True
            log.info("vote: both extra runs failed, kept unverified | rule=%s span=%r", v.rule_id, v.span)
            continue
        same = lambda w: ((w.rule_id == v.rule_id or (cat(w.rule_id) and cat(w.rule_id) == cat(v.rule_id)))  # noqa: E731
                          and not w.is_negated and not w.is_quoted and _overlap(w.span, v.span))
        v._votes = 1 + sum(any(same(w) for w in run.compliance.violations) for run in runs)
        if v._votes >= 3:
            continue
        if v._votes == 2:
            v._severity = "MEDIUM"  # 2/3: capped
        else:
            _cdrop(v, "vote: 1/3")
            dropped.add(id(v))
    first.compliance.violations = [v for v in first.compliance.violations if id(v) not in dropped]
    return first


def _same_correction(lex, a: str | None, b: str | None) -> bool:
    na, nb = _numbers(lex, a), _numbers(lex, b)
    if na or nb:
        return na == nb
    wa, wb = _words(a), _words(b)
    return bool(wa and wb) and len(wa & wb) >= 0.5 * min(len(wa), len(wb))


def fact_votes(first: FactCheckOutput, extras: list[AgentResult], catalog: Catalog) -> FactCheckOutput:
    lex = catalog.lexicon
    runs = _ok(extras)
    for c in first.claims:
        if c.verdict != "contradicted":
            continue
        if not runs:
            c._votes, c._unverified = 1, True
            log.info("vote: both extra runs failed, kept unverified | field=%s stated=%r", c.field, c.stated_value)
            continue
        same = lambda d: (d.verdict == "contradicted" and d.field == c.field  # noqa: E731
                          and _same_correction(lex, d.correct_value, c.correct_value))
        c._votes = 1 + sum(any(same(d) for d in run.claims) for run in runs)
        if c._votes < 2:
            _drop(c, "vote: 1/3")
    return first


def candidates(out, kind: str) -> bool:
    if out is None:
        return False
    if kind == "compliance":
        return any(not v.is_negated and not v.is_quoted for v in out.compliance.violations)
    return any(c.verdict == "contradicted" for c in out.claims)
