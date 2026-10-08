"""D-336 (review H6): the code defaults are the measured config, and the cloud deploy states them explicitly."""
from __future__ import annotations

from pathlib import Path

from app.config import Settings

MEASURED = {"JUDGE_ARM": "single", "SINGLE_MODEL": "gemini-3.5-flash-lite", "SINGLE_THINKING": "LOW",  # D-360
            "SINGLE_FACTS_THINKING": "LOW", "FACT_PROMPT": "v5", "JUDGE_SEED": "7", "STT_ENDPOINTING": "STANDARD",
            "QUESTION_HOLD": True,  # D-343
            "FACT_MODE": "prompter"}  # D-360; D-415: SWITCH_MODE is gone (the immediate switch is the only one)


def test_d336_the_defaults_are_the_measured_config():
    assert {k: Settings.model_fields[k].default for k in MEASURED} == MEASURED


def test_d336_the_deploy_states_them():
    script = (Path(__file__).resolve().parents[2] / "deploy" / "cloudrun.sh").read_text(encoding="utf-8")
    for k, v in MEASURED.items():
        assert f"{k}={str(v).lower() if isinstance(v, bool) else v}" in script, k
