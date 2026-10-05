"""Dataset-driven checks shared by isolated agents and runtime sequence evaluation."""
from __future__ import annotations

KNOWN_KEYS = frozenset({"compliance", "rule_id", "severity", "negated", "quoted", "fact", "field",
                        "correct_value", "answer", "matched_group", "consistent_with_suggested",
                        "covered_points", "switch", "target", "corrects_alert_ids", "note", "qualifier_ok"})
QUALIFIER_RULE = "BRAND-TEST-QUALIFIER"
PRICE_FIELDS = frozenset({"price", "set_price", "promo"})  # a time-sale price is filed as either (holdout H046)


def expectation_checks(expected: dict, judge: dict, facts: dict, same_value,
                       *, ids: dict[str, str] | None = None, continuation: bool | None = None) -> list[tuple[str, str, bool, str]]:
    """Return (area, check, passed, detail); omitted areas receive explicit leak checks.

    Supported/none facts mean no contradicted note, matching the host-visible contract.
    A read-out's matched_group remains a required context label even when answer is false.
    Notes are annotations; unknown labels fail loudly instead of silently inflating accuracy.
    """
    unknown = set(expected) - KNOWN_KEYS
    if unknown:
        raise ValueError(f"Unknown expected keys: {sorted(unknown)}")
    ids = ids or {}
    checks = []
    active = [v for v in (judge.get("compliance") or {}).get("violations", [])
              if not v.get("is_negated", False) and not v.get("is_quoted", False)]
    if expected.get("compliance") is True:
        ok = any(v.get("rule_id") == expected["rule_id"] and
                 ("severity" not in expected or v.get("severity") == expected["severity"]) for v in active)
        checks.append(("comp", "catches the violation (right rule)", ok, str(active)))
    else:
        name = "no alert on negated/quoted/approved wording" if "compliance" in expected else "leak: alert on a sentence with no compliance claim"
        # qualifier_ok: a lone BRAND-TEST-QUALIFIER MEDIUM is allowed here, not required; any other alert is a leak
        allowed = (expected.get("qualifier_ok") is True and len(active) == 1
                   and active[0].get("rule_id") == QUALIFIER_RULE and active[0].get("severity") == "MEDIUM")
        checks.append(("comp", name, not active or allowed, str(active)))
    if "corrects_alert_ids" in expected:
        got = (judge.get("correction") or {}).get("corrects_alert_ids", [])
        want = [ids.get(a, a) for a in expected["corrects_alert_ids"]]
        checks.append(("comp", "correction", set(want) <= set(got), str(got)))
    answer = judge.get("answer") or {}
    for key, actual in (("answer", "is_answer"), ("matched_group", "matched_group_id"),
                        ("consistent_with_suggested", "consistent_with_suggested")):
        if key in expected:
            want = ids.get(expected[key], expected[key]) if key == "matched_group" else expected[key]
            checks.append(("ctx", "answer linking", answer.get(actual) == want, f"{actual}={answer.get(actual)}"))
    prompter = judge.get("prompter") or {}
    if "covered_points" in expected:
        got = prompter.get("covered_point_ids", [])
        checks.append(("ctx", "prompter points", set(expected["covered_points"]) <= set(got), str(got)))
    if "switch" in expected:
        sw = prompter.get("switch") or {}
        want = expected["switch"]
        if want == "continuation":
            ok = continuation if continuation is not None else not sw.get("is_transition", False) and not sw.get("is_quote", False)
        elif isinstance(want, bool):
            transition = bool(sw.get("is_transition")) and not sw.get("is_quote", False)
            ok = transition == want and (not want or sw.get("target_product_id") == expected["target"])
        else:
            raise ValueError(f"Unknown switch expectation: {want!r}")
        checks.append(("ctx", "switch", bool(ok), str(sw)))
    wrong = [c for c in facts.get("claims", []) if c.get("verdict") == "contradicted"]
    verdict = expected.get("fact")
    if verdict == "contradicted":
        ok = any((c.get("field") == expected["field"] or {c.get("field"), expected["field"]} <= PRICE_FIELDS)
                 and same_value(c.get("correct_value"), expected["correct_value"]) for c in wrong)
        name = "catches the wrong fact"
    elif verdict in ("supported", "none", None):
        ok = not wrong
        name = "no note on a right fact" if verdict is not None else "leak: note on a sentence that is not about facts"
    else:
        raise ValueError(f"Unknown fact expectation: {verdict!r}")
    checks.append(("facts", name, ok, str(wrong)))
    return checks
