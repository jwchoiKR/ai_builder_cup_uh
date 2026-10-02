"""Accuracy of the code guardrail alone, before any LLM agent (no model calls).

For every utterance eval case (data/eval/utterance_cases.jsonl) this runs exactly what the
orchestrator runs before the judge, and what it falls back to when the judge fails (§8.4.3):
  1. Reflex scan (keyword phrases of claim_rules.json, negation and quote cues);
  2. provisional alerts (`provisional_from_reflex`), then `apply_judge_failure`:
     a HIGH hit that is neither negated nor quoted becomes an alert; everything else is cleared.

Ground truth: the case's `expected.compliance` (cases without it make no claim, so they are safe).

    uv run python scripts/eval_guardrails.py [--out ../docs/eval/guardrail-reflex.md]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import REPO_DIR, get_settings  # noqa: E402
from app.logic import alerts as alert_logic  # noqa: E402
from app.logic.catalog import DataPack  # noqa: E402
from app.logic.reflex import Reflex  # noqa: E402
from app.models.session import Transcript  # noqa: E402


def code_only(reflex: Reflex, text: str):
    hits = reflex.scan(text)
    t = Transcript(transcript_id="tr_x", text=text, is_final=True, speech_end_at=0, received_at=0,
                   source="injected", segment_id="seg_x")
    n = iter(range(1000))
    provisional = alert_logic.provisional_from_reflex(hits, t, "cream_hydra_barrier", [], lambda p: f"{p}{next(n)}", 0)
    after = alert_logic.apply_judge_failure(provisional, hits, "Say this instead.", 0)
    shown = [a for a in after if a.status == "active"]
    return hits, shown


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=REPO_DIR / "docs" / "eval" / "guardrail-reflex.md")
    args = ap.parse_args()
    settings = get_settings()
    pack = DataPack.load(settings.data_path)
    reflex = Reflex(pack.rules)
    severity = {r.rule_id: r.severity for r in pack.rules.rules}
    cases = [json.loads(x) for x in (settings.data_path / "eval" / "utterance_cases.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]

    rows, stats = [], {"labelled": [0, 0], "unlabelled": [0, 0]}
    counts = {"caught": 0, "missed_high": 0, "medium": 0, "false_alarm": 0, "safe_ok": 0}
    for c in cases:
        exp = c["expected"]
        labelled = "compliance" in exp
        violation = bool(exp.get("compliance"))
        rule = exp.get("rule_id")
        sev = severity.get(rule) if rule else None
        hits, shown = code_only(reflex, c["utterance"])
        alerted = bool(shown)
        if violation and sev == "HIGH":
            ok = alerted and any(a.rule_id == rule for a in shown)
            kind = "HIGH violation"
            counts["caught" if ok else "missed_high"] += 1
        elif violation:  # MEDIUM: the fallback never shows MEDIUM alerts (§8.4.3), only the judge can
            ok = not alerted
            kind = "MEDIUM violation"
            counts["medium"] += 1
        else:
            ok = not alerted
            kind = "safe" + (" (negated)" if exp.get("negated") else " (quoted)" if exp.get("quoted") else "")
            counts["safe_ok" if ok else "false_alarm"] += 1
        group = "labelled" if labelled else "unlabelled"
        stats[group][0] += ok
        stats[group][1] += 1
        hit_txt = ", ".join(f"'{h.phrase}' → {h.rule_id}" + (" (negated)" if h.negated else "") + (" (quoted)" if h.quoted else "")
                            for h in hits) or "no keyword"
        outcome = ("alert " + ", ".join(a.rule_id for a in shown)) if shown else "no alert"
        rows.append((c["case_id"], c["utterance"], kind + (f" · {rule}" if rule else ""), hit_txt, outcome, ok, labelled))

    lab_ok, lab_n = stats["labelled"]
    unl_ok, unl_n = stats["unlabelled"]
    high_n = counts["caught"] + counts["missed_high"]
    safe_n = counts["safe_ok"] + counts["false_alarm"]
    md = [
        f"# Code guardrail alone (Reflex, before the LLM) · {dt.date.today().isoformat()}",
        "",
        "**What runs:** for every utterance eval case, what the orchestrator does before the judge, and what it falls back to "
        "when the judge fails (§8.4.3). The Reflex keyword scan (claim_rules.json phrases, negation and quote cues) creates "
        "provisional alerts; `apply_judge_failure` shows a HIGH hit that is neither negated nor quoted, and clears the rest. "
        "No model is called. Script: `backend/scripts/eval_guardrails.py`.",
        "",
        "**Ground truth:** `data/eval/utterance_cases.jsonl`. Cases with `expected.compliance` are labelled; the others "
        "make no claim (prices, answers, transitions) and count as safe.",
        "",
        "## Result",
        f"- **Labelled cases ({lab_n}):** {lab_ok}/{lab_n} handled correctly by code alone ({100 * lab_ok / lab_n:.0f}%).",
        f"- **HIGH violations:** {counts['caught']}/{high_n} caught with the right rule; {counts['missed_high']} missed.",
        f"- **MEDIUM violations:** {counts['medium']}. The fallback never shows MEDIUM alerts, so only the judge can.",
        f"- **Safe sentences (labelled and unlabelled, {safe_n}):** {counts['safe_ok']} passed, {counts['false_alarm']} false alarms.",
        f"- **Unlabelled cases ({unl_n}):** {unl_ok}/{unl_n} correct (no alert).",
        "",
        "| Case | Sentence | Truth | Keyword hit | Code-only result | Correct |",
        "|---|---|---|---|---|---|",
        *[f"| {cid} | {u} | {k} | {h} | {o} | {'✓' if ok else '✗'} |" for cid, u, k, h, o, ok, _ in rows],
    ]
    args.out.write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
    for cid, u, k, h, o, ok, lab in rows:
        print(f"{'OK  ' if ok else 'MISS'} {cid} [{k}] {u}\n       keyword: {h} -> {o}")
    print(f"labelled {lab_ok}/{lab_n}; HIGH caught {counts['caught']}/{high_n}; false alarms {counts['false_alarm']}/{safe_n}")
    print(f"report: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
