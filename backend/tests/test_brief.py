"""BriefAgent (DEV_SPEC §7.7): post-validation and the rule-based mock fallback."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.brief import BriefAgent, BriefInput, post_validate, rule_based_brief
from app.logic.reflex import Reflex
from app.models.agent_io import BriefOutput

from .helpers import make_ctx

DOC = "DAON LAB Hydra Barrier Cream contains Panthenol 5% and Ceramide NP 1%. Measured with a corneometer."


@pytest.fixture(scope="module")
def reflex(pack):
    return Reflex(pack.rules)


def term(t: str, kind: str = "ingredient") -> dict:
    return {"term": t, "kind": kind, "spoken_forms": [t.lower()], "source_section": "Key ingredients"}


def test_drops_terms_not_in_document_and_duplicates(reflex):
    out = BriefOutput(product_id="other", glossary=[term("Panthenol"), term("panthenol"), term("Niacinamide"),
                                                    term("corneometer", "technical"), term("  ")],
                      prompter_points=[], reason="")
    v = post_validate(out, "cream_hydra_barrier", DOC, reflex)
    assert v.product_id == "cream_hydra_barrier"
    assert [t.term for t in v.glossary] == ["Panthenol", "corneometer"]


def test_drops_long_or_restricted_points_and_caps(reflex):
    points = [{"text": "Ceramide NP 1%, panthenol 5%.", "required": True, "source_section": "Key ingredients"},
              {"text": "x" * 91, "required": False, "source_section": "x"},
              {"text": "It cures eczema overnight.", "required": False, "source_section": "x"},
              *[{"text": f"Point {i}.", "required": False, "source_section": "x"} for i in range(8)]]
    out = BriefOutput(product_id="cream_hydra_barrier", glossary=[term("Panthenol")] * 50, prompter_points=points, reason="")
    v = post_validate(out, "cream_hydra_barrier", DOC, reflex)
    assert len(v.prompter_points) == 6 and v.prompter_points[0].text.startswith("Ceramide")
    assert all(len(p.text) <= 90 and "cure" not in p.text for p in v.prompter_points)
    terms = [term(f"T{i}") for i in range(50)]
    many = BriefOutput(product_id="x", glossary=terms, prompter_points=[], reason="")
    assert len(post_validate(many, "x", " ".join(f"t{i}" for i in range(50)), reflex).glossary) == 40


def test_rule_based_fallback_reads_the_sheet(settings, reflex):
    md = (settings.data_path / "products" / "DAON_LAB_Hydra_Barrier_Cream.md").read_text(encoding="utf-8")
    out = BriefOutput.model_validate(rule_based_brief("cream_hydra_barrier", md, reflex))
    terms = {t.term for t in out.glossary}
    assert {"DAON LAB", "Hydra Barrier Cream", "Panthenol", "Ceramide NP", "Sodium Hyaluronate"} <= terms
    assert out.prompter_points and all(len(p.text) <= 90 for p in out.prompter_points)


async def test_agent_runs_with_mock_fallback(tmp_path, settings):
    ctx = make_ctx(tmp_path)
    md = (settings.data_path / "products" / "DAON_LAB_Deep_Hydration_Ampoule.md").read_text(encoding="utf-8")
    agent = BriefAgent(ctx.llm, ctx.prompts["brief_agent"], ctx.reflex)
    res = await agent.run(BriefInput(product_id="ampoule_deep_hydration", document_text=md), deadline_ms=5000)
    assert res.status == "ok" and res.output.product_id == "ampoule_deep_hydration"
    assert any(t.term == "Niacinamide" for t in res.output.glossary)
    assert agent.model == ctx.llm.quality.model


def test_recorded_fixtures_exist_for_s01():
    from app.providers.llm import MockBackend

    mock = MockBackend()
    for pid in ("cream_hydra_barrier", "ampoule_deep_hydration"):
        path: Path = mock.fixture_path("brief_agent", pid, "S01")
        assert path.is_file(), f"record the S01 Brief Agent fixture for {pid}"
