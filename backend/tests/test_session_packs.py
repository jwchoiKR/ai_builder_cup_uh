"""D-142 (JAPAC B): each session holds its own (market, language) pack; the runtime takes it from there."""
from __future__ import annotations

import json
import shutil

import pytest

from app.pipelines.runtime import ActionError, create_session

from .helpers import make_ctx


async def test_a_session_takes_the_settings_pair_by_default():
    ctx = make_ctx()
    s = await create_session(ctx, "daon_skincare_demo")
    assert (s.market, s.lang) == ("SG", "en")
    rt = await ctx.runtimes.get(s.session_id)
    assert rt.pack is ctx.pack and rt.reflex is ctx.reflex
    ctx.runtimes.shutdown()


async def test_a_language_the_market_does_not_offer_is_refused():
    ctx = make_ctx()
    with pytest.raises(ActionError, match="unknown_market_language|does not offer|en|ko"):
        await create_session(ctx, "daon_skincare_demo", lang="ko")


async def test_two_sessions_two_languages_on_one_service(tmp_path, settings):
    """A second broadcast language of the same market: its own pack, reflex and STT code per session."""
    data = tmp_path / "data"
    shutil.copytree(settings.data_path, data)
    sg = json.loads((data / "markets" / "sg.json").read_text(encoding="utf-8"))
    sg["languages"].append({"lang": "en2", "stt_language": "en-GB", "tier": "preview"})
    (data / "markets" / "sg.json").write_text(json.dumps(sg), encoding="utf-8")
    en2 = json.loads((data / "lang" / "en.json").read_text(encoding="utf-8"))
    en2["lang"] = "en2"
    en2["lexicon"]["patterns"]["unsure"] = r"(?i)\bmungkin\b"
    (data / "lang" / "en2.json").write_text(json.dumps(en2), encoding="utf-8")

    ctx = make_ctx(DATA_DIR=str(data))
    a = await ctx.runtimes.get((await create_session(ctx, "daon_skincare_demo")).session_id)
    b = await ctx.runtimes.get((await create_session(ctx, "daon_skincare_demo", lang="en2")).session_id)
    assert (a.pack.lang, b.pack.lang) == ("en", "en2")
    assert (a.pack.stt_language, b.pack.stt_language) == ("en-US", "en-GB")
    assert a.reflex.lexicon.is_unsure("I think so") and not b.reflex.lexicon.is_unsure("I think so")
    assert b.catalog.lexicon.is_unsure("mungkin") and b.utterances.compliance.reflex is b.reflex
    assert ctx.pack_for("SG", "en2")[0] is b.pack  # loaded once
    ctx.runtimes.shutdown()


def test_d150_the_malaysia_pack_builds_but_waits_for_rm_products(settings):
    """D-150 (JAPAC step 1, option c): Malaysia's rules (ASEAN base + NPRA) build with English wording, but the
    pack refuses to load until products are priced in RM (D-129)."""
    from app.logic.catalog import DataPack, DataPackError, claim_rules
    from app.models.data import LangPack, MarketPack

    data = settings.data_path
    my = MarketPack.model_validate(json.loads((data / "markets" / "my.json").read_text(encoding="utf-8")))
    en = LangPack.model_validate(json.loads((data / "lang" / "en.json").read_text(encoding="utf-8")))
    rules = claim_rules(my, en)
    assert my.tier == "preview" and len(rules.rules) == 23
    assert {"MY-HALAL-UNVERIFIED", "MY-AUTHORITY-APPROVAL"} <= {r.rule_id for r in rules.rules}
    with pytest.raises(DataPackError, match="priced in S\$, market MY uses RM"):
        DataPack.load(data, "MY", "en")


async def test_d150_a_preview_language_posts_nothing_by_itself(tmp_path, settings):
    """Preview (no sealed eval yet): host cards only. An AUTO price question goes to the host, nothing is posted."""
    from .helpers import live_runtime, say

    data = tmp_path / "data"
    shutil.copytree(settings.data_path, data)
    sg = json.loads((data / "markets" / "sg.json").read_text(encoding="utf-8"))
    sg["languages"][0]["tier"] = "preview"
    (data / "markets" / "sg.json").write_text(json.dumps(sg), encoding="utf-8")
    ctx = make_ctx(DATA_DIR=str(data))
    rt = await live_runtime(ctx)
    try:
        assert not rt.live and (await rt.snapshot("host"))["market"]["tier"] == "preview"
        await say(rt, "Lee", "How much is the cream?")
        [g] = await rt.groups()
        assert (g.route, g.route_reason, g.status) == ("HOST", "preview", "ready")
        from app.models.session import Message
        assert await rt.ctx.store.query(rt.path("messages"), Message) == []
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
