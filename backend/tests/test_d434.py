"""D-434 (test migration, user go 10/10): tests run the production live path. A drift guard: the live-path settings a
test gets by default equal production's (the code defaults plus deploy/cloudrun.sh --set-env-vars), nothing reaches
them from the environment or a .env, and the temporary `legacy_live` marker is used only by the files not migrated
yet (the list shrinks with each batch and ends empty)."""
from __future__ import annotations

import os
import re
from pathlib import Path

from app.config import Settings, get_settings

from .conftest import LIVE_PATH_KEYS
from .helpers import make_settings

REPO = Path(__file__).resolve().parents[2]
TESTS = Path(__file__).resolve().parent

# The files that still use `legacy_live`; a batch removes its files here when it migrates them. Never add to it.
LEGACY_LIVE_FILES = {
    "test_alerts.py", "test_d338.py", "test_prompter_segments.py", "test_split_judges.py",
    "test_utterance_concurrency.py", "test_utterance_merge.py", "test_utterance_pipeline.py",
}


def production_settings() -> Settings:
    """The code defaults plus deploy/cloudrun.sh's --set-env-vars (its ${...} names filled with placeholders)."""
    script = (REPO / "deploy" / "cloudrun.sh").read_text(encoding="utf-8")
    [env] = re.findall(r'--set-env-vars="([^"]+)"', script)
    pairs = dict(item.split("=", 1) for item in env.split(","))
    pairs = {k: re.sub(r"\$\{\w+\}", "placeholder", v) for k, v in pairs.items()}
    return Settings(_env_file=None, **pairs)


def test_d434_the_tests_default_live_path_is_production_s():
    prod, tests = production_settings(), make_settings()
    differ = {k: (getattr(prod, k), getattr(tests, k)) for k in LIVE_PATH_KEYS if getattr(prod, k) != getattr(tests, k)}
    assert differ == {}, differ
    # the deployed values the live path depends on (was test_d305's "shipped defaults")
    assert (prod.JUDGE_MODE, prod.FACT_RELATION, prod.FACT_PROMPT, prod.FACT_MODE) == (
        "split3", True, "v5", "prompter")
    assert (prod.STT_ENDPOINTING, prod.DESIGN_ARM) == ("STANDARD", "A")


def test_d434_no_live_path_setting_comes_from_the_environment_or_a_dotenv():
    assert not {k for k in LIVE_PATH_KEYS if k in os.environ}
    assert Settings.model_config.get("env_file") is None
    s = get_settings()
    assert all(getattr(s, k) == Settings.model_fields[k].default for k in LIVE_PATH_KEYS)


def test_d434_the_compliance_judge_runs_the_originals_path_by_default():
    from app.agents import split_judges

    assert split_judges.LEGACY_RULES is False


def test_d434_legacy_live_is_used_only_by_the_files_not_migrated_yet():
    users = {p.name for p in TESTS.glob("test_*.py")
             if p.name != Path(__file__).name and "legacy_live" in p.read_text(encoding="utf-8")}
    assert users <= LEGACY_LIVE_FILES, sorted(users - LEGACY_LIVE_FILES)
    assert LEGACY_LIVE_FILES <= users, sorted(LEGACY_LIVE_FILES - users)  # a migrated file leaves the list too


async def test_d434_each_production_judge_gets_its_addenda():
    """D-434 (review): a design_arms.md section a production judge needs must exist; a missing one would be dropped in
    silence (the lookup returns None). Production: compliance = its prompt file alone (D-358); context = QHOLD and
    SWITCH; the fact checker = F1 and F5 (FACT_FIXES), PAIR and NOTES, on fact_relation_v5."""
    from app.agents import arms

    from .helpers import live_runtime, make_ctx
    from .judge_fakes import ScriptedBackend, close_env

    rt = await live_runtime(make_ctx(backend=ScriptedBackend()))
    try:
        u = rt.utterances
        add = arms._addenda(str(rt.ctx.settings.prompts_path))
        needed = {"context_judge": ("QHOLD", "SWITCH"), "fact_checker": ("F1", "F5", "PAIR", "NOTES")}
        for agent, layers in needed.items():
            for layer in layers:
                assert add.get((layer, agent)), (layer, agent)
        assert u.compliance.system_instruction == rt.ctx.prompts["compliance_judge"].system_instruction
        for layer in needed["context_judge"]:
            assert add[(layer, "context_judge")] in u.context.system_instruction, layer
        assert u.facts.prompt is rt.ctx.prompts["fact_relation_v5"]
        for layer in needed["fact_checker"]:
            assert add[(layer, "fact_checker")] in u.facts.system_instruction, layer
    finally:
        await close_env(rt)
