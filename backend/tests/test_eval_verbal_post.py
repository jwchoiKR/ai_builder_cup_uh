"""Scorer of the spoken-answer auto-post eval (D-110); no model calls."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eval_verbal_post import load_cases, score, write_report  # noqa: E402

from .judge_fakes import judge_output  # noqa: E402

EMPTY = {"claims": [], "reason": ""}
# D-196: lines that answer two shown questions at once; the judge links the other one too (also_answered_group_ids)
MULTI = {"V14", "V46"}


def _also(c: dict, out: dict) -> dict:
    if c["case_id"] in MULTI:
        out["answer"]["also_answered_group_ids"] = [q["group_id"] for q in c["context"]["open_questions"]
                                                    if q["group_id"] != out["answer"]["matched_group_id"]]
    return out


def rows(judge_for) -> list[dict]:
    return [{"id": c["case_id"], "run": 0, "ctx_status": "ok", "judge": judge_for(c), "facts_validated": EMPTY}
            for c in load_cases()]


def test_a_judge_that_matches_the_labels_has_no_false_posts(tmp_path):
    def perfect(c):
        exp = c["expected"]
        return _also(c, judge_output(utterance_type="answer" if exp["post"] else "other",
                                     matched=exp.get("matched_group"), is_answer=exp["post"], consistent=exp["post"]))
    s = score(rows(perfect), load_cases())
    assert s["false_posts"] == [] and s["missed_posts"] == []
    write_report(s, load_cases(), tmp_path / "r.md")
    assert "**False posts: 0**" in (tmp_path / "r.md").read_text(encoding="utf-8")


def test_code_checks_catch_numbers_hedges_and_retractions_even_from_a_lenient_judge():
    def yes(c):  # links the right question (D-112: any open question), says yes to everything else
        target = c["expected"].get("matched_group") or c["shown_group_id"]
        return _also(c, judge_output(utterance_type="answer", matched=target, is_answer=True, consistent=True))
    s = score(rows(yes), load_cases())
    caught_by_code = {"wrong_number", "hedge", "retracted"}
    assert not [x for x in s["false_posts"] if x["category"] in caught_by_code]
    assert {x["category"] for x in s["false_posts"]} <= {
        "added_caveat", "question_back", "quote", "contradiction", "readout", "hypothetical"}
    assert s["missed_posts"] == []
