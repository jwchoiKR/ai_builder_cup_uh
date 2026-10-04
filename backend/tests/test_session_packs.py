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
