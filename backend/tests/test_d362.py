"""D-362: fixes from the codex re-review of 5cfe8b2..4d4a544."""
from __future__ import annotations

import json

import pytest

from app.agents.originals import Original
from app.logic.prompter import prompter_passages

from .judge_fakes import CREAM


class _View:
    """The demo catalog, with chosen set offers or a product with more cautions."""

    def __init__(self, cat, sets=None, cautions=None):
        self._cat, self._sets, self._cautions = cat, sets, cautions

    def __getattr__(self, name):
        return getattr(self._cat, name)

    @property
    def set_offers(self):
        return self._sets if self._sets is not None else self._cat.set_offers

    def get_product(self, pid):
        p = self._cat.get_product(pid)
        return p.model_copy(update={"cautions": self._cautions}) if self._cautions is not None else p


def test_d362_the_snapshot_holds_the_set_the_ui_shows_and_every_caution(catalog):
    from app.models.data import SetOffer

    sets = [SetOffer(set_id="s1", name="Duo", product_ids=[CREAM, "x"], live_price=50.0),
            SetOffer(set_id="s2", name="Trio", product_ids=[CREAM, "x", "y"], live_price=70.0)]
    cautions = [f"Caution {i}." for i in range(1, 7)]
    texts = [p.text for p in prompter_passages(_View(catalog, sets, cautions), CREAM)]
    assert sum(t.startswith("Set ") for t in texts) == 1 and any(t.startswith("Set Duo") for t in texts)
    assert all(c in texts for c in cautions)  # all six: the host can open "+N more"


async def test_d362_the_fact_note_hide_timer_is_re_armed_after_a_read_back():
    from app.pipelines.runtime import Runtimes

    from .helpers import live_runtime, make_ctx
    from .judge_fakes import ScriptedBackend, close_env, price_contradiction, speak

    llm = ScriptedBackend()
    line = "It's only thirty-two dollars today."
    llm.facts(line, price_contradiction("S$32"))
    ctx = make_ctx(backend=llm)
    rt = await live_runtime(ctx)
    await speak(rt, line)
    [a] = [a for a in await rt.alerts() if a.kind == "fact" and a.status == "active"]
    due = ctx.scheduler.due_at(rt.key(f"facthide:{a.alert_id}"))
    rt.shutdown()
    fresh = await Runtimes(ctx).get(rt.sid)
    try:
        assert ctx.scheduler.due_at(fresh.key(f"facthide:{a.alert_id}")) == due  # the same time, from when shown
    finally:
        await close_env(fresh)


def test_d362_a_pack_with_some_files_missing_is_not_kept(tmp_path):
    from app.agents.originals import _load
    from app.onboarding.files import store

    from .helpers import text_pdf

    (tmp_path / "lawpacks").mkdir()
    (tmp_path / "lawpacks" / "law_sg_p_v1.json").write_text(json.dumps({"pack_id": "law_sg_p_v1", "job_id": "jp"}))
    store(tmp_path, "jp", "part1.pdf", text_pdf("1 No cure claims."))
    store(tmp_path, "jp", "part2.pdf", text_pdf("2 No safety promises."))
    missing_file = next((tmp_path / "jp").glob("*.pdf"))
    data = missing_file.read_bytes()
    missing_file.unlink()
    found, missing = _load((("law_sg_p_v1", "", None),), str(tmp_path))
    assert len(found) == 1 and missing == ("law_sg_p_v1",)  # the file found is given; the pack is marked
    missing_file.write_bytes(data)
    found, missing = _load((("law_sg_p_v1", "", None),), str(tmp_path))  # looked up again, now complete
    assert len(found) == 2 and missing == ()


@pytest.mark.originals
async def test_d363_the_originals_load_once_per_show_and_stay_fixed():
    """D-363 (user): the originals are read once at show start; a later change is not re-read during the show, and
    the quote check uses that start-of-show snapshot."""
    from app.agents.utterance_judge import JudgeInput

    from .helpers import live_runtime, make_ctx
    from .judge_fakes import ScriptedBackend, close_env

    a = Original("regulation.txt", "A", "law_a", b"2.1 No cure claims.", "text/plain", "2.1 No cure claims.")
    line = "It cures arthritis."
    llm = ScriptedBackend()
    llm.outputs[("compliance_judge", line)] = {"alert_checks": [], "compliance": {"violations": [{
        "citation": "regulation.txt#2.1", "quote": "No cure claims", "span": "cures arthritis", "severity": "HIGH",
        "is_negated": False, "is_quoted": False, "say_instead": "x", "qualified_result_id": None}]}, "reason": "r"}
    rt = await live_runtime(make_ctx(backend=llm))
    judge = rt.utterances.compliance
    judge._docs = ((a,), ("law_b",))  # loaded at show start, one source missing
    try:
        res = await judge.run(JudgeInput(utterance=line, on_air=rt.catalog.order[0], session_id=rt.sid),
                              deadline_ms=2000)
        [v] = res.output.compliance.violations
        assert v.rule_id == "regulation#2-1" and res.meta["originals_missing"] == ["law_b"]
        assert judge._docs == ((a,), ("law_b",))  # never re-read during the show, even with a source missing
    finally:
        await close_env(rt)
