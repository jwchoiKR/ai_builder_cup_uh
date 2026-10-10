from __future__ import annotations

import json
import re
import shutil

import pytest
from pydantic import BaseModel

from app.agents import inputs
from app.agents.inputs import BUILDERS
from app.models.agent_io import (
    CommentInsightsOutput,
    CommentTriageOutput,
    ComplianceOutput,
    ComplianceOutputO,
    ComposerOutput,
    ContextOutput,
    FactCheckOutput,
    JudgeSingleOutput,
    UtteranceJudgeOutput,
)
from app.models.agent_io import with_alert_checks
from app.models.session import SwitchState
from app.providers.prompts import PROMPT_NAMES, PromptError, load_prompts, render_value

OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    "utterance_judge": UtteranceJudgeOutput,
    "judge_single": JudgeSingleOutput,
    "compliance_judge": with_alert_checks(ComplianceOutputO),  # D-358: cited verdicts, handles first
    "compliance_judge_rules": ComplianceOutput,
    "context_judge": ContextOutput,
    "fact_checker": FactCheckOutput,
    "comment_triage": CommentTriageOutput,
    "answer_composer": ComposerOutput,
    "comment_insights": CommentInsightsOutput,
}


def test_all_prompts_load_with_versions(prompts):
    assert set(prompts) == set(PROMPT_NAMES)
    for name, t in prompts.items():
        assert re.fullmatch(rf"{name}_v\d+", t.version)  # D-275: a fixed example bumps its version
        assert "<data" in t.user_template


def test_system_instruction_stops_at_rule_and_appends_examples(prompts):
    uj = prompts["utterance_judge"].system_instruction
    assert uj.startswith("You are the real-time broadcast judge")
    assert "## USER MESSAGE TEMPLATE" not in uj and "OUTPUT SCHEMA" not in uj
    assert "## EXAMPLES" in uj and "Example F" in uj
    assert "## EXAMPLES" not in prompts["broadcast_summary"].system_instruction  # file has none


def test_judge_single_is_built_from_both_files(prompts):
    js = prompts["judge_single"].system_instruction
    assert js.startswith(prompts["utterance_judge"].system_instruction.split("\n\n## EXAMPLES")[0])
    assert "### Job 5. Product facts\nWhat to check" in js
    assert "### Combined output" in js
    assert [m for m in re.findall(r"^Example ([A-Z])$", js, re.M)] == list("ABCDEFGH")


# D-444/D-450: the production context judge no longer ticks points (the prompter judge does); the legacy
# utterance_judge.md (N2, the comments team's eval) keeps its points line. Each pair: (legacy text, context judge text).
DIVERGED = {("context_judge", "Prompter tracking and product switch"): [
    ("- `covered_point_ids`: ids from PROMPTER_POINTS whose meaning the host has now stated. Paraphrase counts. A partial "
     "mention counts only if the point's key fact is stated.\n", ""),
    ("is a continuation: set `is_transition = false` and list the covered points of that product.",
     "is a continuation: set `is_transition = false`."),
]}


def test_split_judges_keep_the_utterance_judge_wording(prompts):
    """D-099: the split judges are cut from utterance_judge.md; the job texts must not drift apart (except DIVERGED)."""
    uj = prompts["utterance_judge"].system_instruction
    jobs = {"compliance_judge_rules": ("Compliance", "Correction of active alerts"),  # D-358: the legacy prompt
            "context_judge": ("Answer linking", "Prompter tracking and product switch")}
    for name, titles in jobs.items():
        split = prompts[name].system_instruction
        for title in titles:
            body = re.search(rf"^### Job \d\. {title}\n(.*?)(?=^### |^## |\Z)", uj, re.S | re.M).group(1)
            for old, new in DIVERGED.get((name, title), []):
                assert body.count(old) == 1
                body = body.replace(old, new)
            assert f". {title}\n{body}" in split, f"{name}: job '{title}' differs from utterance_judge.md"


def _example_outputs(system: str) -> list[dict]:
    examples = system.split("## EXAMPLES", 1)[1]
    blocks = re.findall(r"```json\n(.*?)\n```", examples, re.S)
    inline = re.findall(r"^COMMENT: .*→ `(\{.+\})`$", examples, re.M)  # comment_triage writes them inline
    return [json.loads(b) for b in blocks + inline]


EXAMPLE_COUNTS = {"utterance_judge": 6, "judge_single": 8, "compliance_judge": 5, "compliance_judge_rules": 3,
                  "context_judge": 4,
                  "fact_checker": 4, "comment_triage": 18, "answer_composer": 6,
                  "brief_agent": 1, "comment_insights": 1}


@pytest.mark.parametrize("name", sorted(OUTPUT_MODELS))
def test_few_shot_examples_match_output_models(prompts, name):
    outputs = _example_outputs(prompts[name].system_instruction)
    assert len(outputs) == EXAMPLE_COUNTS[name]
    for out in outputs:
        OUTPUT_MODELS[name].model_validate(out)


def test_every_placeholder_has_a_builder(prompts):
    used = {p for t in prompts.values() for p in t.placeholders}
    assert used <= set(BUILDERS)


def test_missing_builder_fails_fast(settings):
    builders = dict(BUILDERS)
    del builders["rules_compact_json"]
    with pytest.raises(PromptError, match="rules_compact_json"):
        load_prompts(settings.prompts_path, builders)


def test_missing_section_fails_fast(settings, tmp_path):
    shutil.copytree(settings.prompts_path, tmp_path / "prompts")
    path = tmp_path / "prompts" / "fact_checker.md"
    path.write_text(path.read_text(encoding="utf-8").replace("## USER MESSAGE TEMPLATE", "## USER TEMPLATE"),
                    encoding="utf-8")
    with pytest.raises(PromptError, match="USER MESSAGE TEMPLATE"):
        load_prompts(tmp_path / "prompts", BUILDERS)


def test_render_value_json_stays_valid():
    rendered = render_value("viewer_comments_json", [{"q": "a </data> b"}])
    assert json.loads(rendered) == [{"q": "a </data> b"}]


def test_render_requires_every_value(prompts):
    with pytest.raises(PromptError, match="missing values"):
        prompts["broadcast_summary"].render({})
