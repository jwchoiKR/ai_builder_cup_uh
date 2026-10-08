"""D-360: the fact checker flags only facts the host prompter shows (FACT_MODE=prompter, the default): its passages are
the prompter's display snapshot. A fact that is in the record but not on the prompter, said wrongly, gives no alert.
Also: the regulation originals lookup never caches a miss, and logs where it looked. Demo products; scripted model."""
from __future__ import annotations

import json
import re

from app.logic.prompter import prompter_passages

from .judge_fakes import AMPOULE, CREAM, ScriptedBackend, close_env, speak


def test_d360_the_snapshot_is_what_the_prompter_shows(catalog):
    texts = {p.section: [] for p in prompter_passages(catalog, CREAM)}
    for p in prompter_passages(catalog, CREAM):
        texts[p.section].append(p.text)
    product = catalog.get_product(CREAM)
    assert texts["Price & offers"][:2] == [f"Live price: {catalog.money(product.live_price)}",
                                           f"List price: {catalog.money(product.list_price)}"]
    assert 1 <= len(texts["Ingredients"]) <= 4 and all("%" in t or "mg" in t for t in texts["Ingredients"])
    assert texts["Cautions"] == product.cautions
    assert "Approved on-air claims" in texts  # the points, never a correction source (D-338)
    every = " ".join(t for ts in texts.values() for t in ts)
    assert "Volume" not in every and product.volume not in every  # the prompter shows no size line


class _Facts(ScriptedBackend):
    """The fact checker contradicts a price or a volume, citing the sentence that states it, if SOURCE has one."""

    def __init__(self):
        super().__init__()
        self.requests = []

    async def generate(self, req, timeout_ms):
        if req.agent != "fact_checker":
            return await super().generate(req, timeout_ms)
        from app.providers.llm import RawReply

        self.requests.append(req)
        line = req.mock_primary_text
        field, label, stated = (("price", "Live price", "S$32") if "thirty-two" in line
                                else ("volume", "Volume", "30 mL"))
        m = re.search(r'\["(S\d+)",\s*"' + label, req.user_message)
        pid = re.search(r'"product_id":"([^"]+)"', req.user_message).group(1)
        claims = [] if m is None else [{
            "span": stated, "stance": "HOST_ASSERTS", "product_id": pid, "field": field, "stated_value": stated,
            "evidence": [m.group(1)], "source_value": "x", "relation": "contradicts", "correct_value": "S$36.00"}]
        return RawReply(json.dumps({"claims": claims}), model_version="scripted")


async def _facts_alerts(line: str, **settings):
    from .helpers import live_runtime, make_ctx

    llm = _Facts()
    rt = await live_runtime(make_ctx(backend=llm, FACT_MODE="prompter", FACT_RELATION=True, FACT_PROMPT="v5",
                                     JUDGE_ARM="single", **settings))
    try:
        await speak(rt, line)
        await rt.utterances.drain()
        return [a for a in await rt.alerts() if a.kind == "fact"], llm
    finally:
        await close_env(rt)


async def test_d360_a_fact_on_the_prompter_said_wrongly_alerts():
    alerts, llm = await _facts_alerts("It's only thirty-two dollars today.")
    assert len(alerts) == 1
    assert "Live price" in llm.requests[-1].user_message and "Volume" not in llm.requests[-1].user_message


async def test_d360_a_fact_in_the_record_but_not_on_the_prompter_gives_no_alert():
    alerts, llm = await _facts_alerts("You get a big 30 mL tube of it.")
    assert alerts == []  # the volume is in the record, not on the prompter: the checker never sees it


async def test_d360_the_previous_product_s_snapshot_is_there_in_the_dual_scope():
    from .helpers import live_runtime, make_ctx

    llm = _Facts()
    rt = await live_runtime(make_ctx(backend=llm, FACT_MODE="prompter", FACT_RELATION=True, FACT_PROMPT="v5",
                                     JUDGE_ARM="single", SWITCH_MODE="immediate"))
    try:
        move = "Okay, moving on, let me show you the ampoule."
        llm.judge(move, utterance_type="transition", transition=True, target=AMPOULE, confidence="high", named=True)
        await speak(rt, move)
        assert (await rt.current_segment()).product_id == AMPOULE
        await speak(rt, "It's only thirty-two dollars today.")
        msg = llm.requests[-1].user_message
        assert msg.count("Live price") == 2  # the ampoule's and, in the 10 s window, the cream's
        assert f'"product_id":"{CREAM}"' in msg and f'"product_id":"{AMPOULE}"' in msg
    finally:
        await close_env(rt)


def test_d360_a_missing_original_is_looked_up_again_and_logged(tmp_path, caplog):
    import logging

    from app.agents.originals import _load
    from app.onboarding.files import store

    from .helpers import text_pdf

    sources = (("law_sg_x_v1", "", None),)
    with caplog.at_level(logging.WARNING):
        found, missing = _load(sources, str(tmp_path))
    assert found == () and missing == ("law_sg_x_v1",) and "no law or brand pack law_sg_x_v1" in caplog.text
    (tmp_path / "lawpacks").mkdir()
    (tmp_path / "lawpacks" / "law_sg_x_v1.json").write_text(json.dumps({"pack_id": "law_sg_x_v1", "job_id": "jx"}))
    with caplog.at_level(logging.WARNING):
        assert _load(sources, str(tmp_path))[1] == ("law_sg_x_v1",)
    assert "no " + str(tmp_path / "jx" / "files.json") in caplog.text  # says exactly what it looked for
    store(tmp_path, "jx", "code.pdf", text_pdf("2.1 No cure claims."))
    found, missing = _load(sources, str(tmp_path))  # the earlier miss was not cached
    assert [d.name for d in found] == ["code.pdf"] and missing == ()
