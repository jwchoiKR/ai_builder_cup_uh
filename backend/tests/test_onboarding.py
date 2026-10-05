"""P0 onboarding steps 1-3: immutable storage, file conversion, the read call and code normalisation."""
from __future__ import annotations

import io
import json

import pytest

from app.onboarding.files import UnsupportedFile, model_part, store
from app.onboarding.read import normalise, read_product
from app.onboarding.record import ProductRecord

from .helpers import make_ctx
from .judge_fakes import ScriptedBackend

EV = [{"file": "spec.docx", "locator": "paragraph 1", "quote": "P 30 ml, S$36.00; Zinc 0.5 mg"}]


def test_store_is_content_addressed_and_never_overwrites(tmp_path):
    a = store(tmp_path, "d1", "spec.txt", b"one")
    again = store(tmp_path, "d1", "spec.txt", b"one")
    b = store(tmp_path, "d1", "spec.txt", b"two")  # a new version is a new file
    assert a.path == again.path and a.path != b.path and a.path.read_bytes() == b"one"
    with pytest.raises(UnsupportedFile):
        store(tmp_path, "d1", "virus.exe", b"x")


def test_docx_and_xlsx_become_located_text():
    import docx
    import openpyxl

    d = docx.Document()
    d.add_paragraph("Warnings: patch test first.")
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Niacin", "2%"
    buf = io.BytesIO()
    d.save(buf)
    text = model_part("spec.docx", buf.getvalue()).data.decode()
    assert "[paragraph 1] Warnings: patch test first." in text and "[table 1 row 1] Niacin | 2%" in text
    wb = openpyxl.Workbook()
    wb.active.title = "Prices"
    wb.active.append(["SKU", "Price"])
    wb.active.append(["X-1", "S$10.00"])
    buf = io.BytesIO()
    wb.save(buf)
    part = model_part("prices.xlsx", buf.getvalue())
    assert part.mime == "text/plain" and "[sheet Prices row 2] X-1 | S$10.00" in part.data.decode()
    assert model_part("label.jpg", b"\xff\xd8").mime == "image/jpeg"


def _record(**kw) -> dict:
    base = {"brand": "B", "product_name": "P", "short_names": ["p"], "generic_word": "Serum", "category": "Cosmetic",
            "category_evidence": EV, "language": "en",
            "variants": [{"variant_id": "A", "name": "P 30", "size_value": "30.0 ml", "size_unit": "mL",
                          "market": "sg", "prices": [{"currency": "S$", "minor": 3600, "kind": "live", "market": "sg",
                                                       "evidence": EV},
                                                      {"currency": "??", "minor": 1, "kind": "list", "market": None,
                                                       "evidence": EV}], "evidence": EV},
                         {"variant_id": "A", "name": "P 50", "size_value": None, "size_unit": None, "market": None,
                          "prices": [], "evidence": EV},
                         {"variant_id": "Z", "name": "made up", "size_value": None, "size_unit": None, "market": None,
                          "prices": [], "evidence": []}],
            "offers": [], "ingredients": [{"name": "Zinc", "amount_value": "0.50", "amount_unit": "MG", "purpose": None,
                                           "evidence": EV}],
            "ingredient_list_complete": False, "approved_claims": [], "not_approved_claims": [],
            "avoid_saying": [], "qualified_results": [], "cautions": [{"text": "Patch test.", "evidence": []}],
            "how_to_use": [], "key_facts": [], "missing": [], "conflicts": []}
    return base | kw


def test_normalise_currency_units_identity_and_evidence():
    r, notes = normalise(ProductRecord.model_validate(_record()))
    v = r.variants
    assert [x.variant_id for x in v] == ["A", "A_2"]  # the one without evidence is dropped, ids are unique
    assert (v[0].size_value, v[0].size_unit, v[0].market) == ("30", "ml", "SG")
    assert [(m.currency, m.minor, m.market) for m in v[0].prices] == [("SGD", 3600, "SG")]
    assert (r.ingredients[0].amount_value, r.ingredients[0].amount_unit) == ("0.5", "mg")
    assert r.cautions == [] and r.generic_word == "serum" and r.category == "cosmetic"
    assert any("unknown currency" in n for n in notes) and any("cautions" in n for n in notes)


def test_every_field_is_required_in_the_model_schema():
    schema = ProductRecord.model_json_schema()
    assert set(schema["required"]) == set(schema["properties"])
    assert set(schema["$defs"]["Variant"]["required"]) == set(schema["$defs"]["Variant"]["properties"])


async def test_read_product_sends_every_file_and_normalises(tmp_path):
    backend = ScriptedBackend()
    backend.outputs[("onboarding_read", "spec.txt|label.jpg")] = _record()
    seen = []
    original = backend.generate

    async def capture(req, timeout_ms):
        seen.append(req)
        return await original(req, timeout_ms)

    backend.generate = capture
    ctx = make_ctx(backend=backend)
    try:
        res = await read_product(ctx.llm, [model_part("spec.txt", b"hello"), model_part("label.jpg", b"\xff\xd8")])
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
    [req] = [r for r in seen if r.agent == "onboarding_read"]
    assert [m for _, m in req.parts] == ["text/plain", "text/plain", "text/plain", "image/jpeg"]
    assert [r.agent for r in seen if r.agent != "onboarding_read"] == ["onboarding_cautions"]  # D-226
    assert res.method == "gemini_whole" and res.record.variants[0].prices[0].currency == "SGD"


def test_d217_the_upload_api_runs_the_same_pipeline(tmp_path):
    import time

    from fastapi.testclient import TestClient

    from app.main import create_app

    from .helpers import make_settings

    backend = ScriptedBackend()
    backend.outputs[("onboarding_read", "spec.txt")] = _record()
    with TestClient(create_app(make_settings(ONBOARDING_DIR=str(tmp_path)), llm_backend=backend)) as c:
        def wait(job: str) -> dict:
            for _ in range(100):
                got = c.get(f"/api/onboarding/jobs/{job}").json()
                if got["status"] in ("done", "failed"):
                    return got
                time.sleep(0.02)
            return got

        r = c.post("/api/onboarding/jobs", files=[("files", ("spec.txt", b"hello", "text/plain"))])
        got = wait(r.json()["job_id"])
        assert got["status"] == "done" and got["result"]["record"]["variants"][0]["prices"][0]["currency"] == "SGD"
        assert (tmp_path / r.json()["job_id"] / "result.json").exists()
        bad = c.post("/api/onboarding/jobs", files=[("files", ("x.exe", b"MZ", "application/octet-stream"))])
        assert wait(bad.json()["job_id"])["status"] == "failed"


async def test_d218_a_release_runs_its_own_one_segment_show(tmp_path):
    from app.onboarding.release import product_key, save_release
    from app.pipelines.runtime import create_session

    rec, _ = normalise(ProductRecord.model_validate(_record(
        cautions=[{"text": "Patch test first.", "evidence": EV}],
        approved_claims=[{"text": "Helps skin feel soft.", "evidence": EV}])))
    rid = save_release(tmp_path, rec, "job1")
    assert save_release(tmp_path, rec, "job2") == rid.replace("_v1", "_v2")  # every approval is a new version
    ctx = make_ctx(ONBOARDING_DIR=str(tmp_path))
    try:
        s = await create_session(ctx, "ignored", release_id=rid)
        rt = await ctx.runtimes.get(s.session_id)
        pid = product_key(rec)
        assert s.release_id == rid and rt.catalog.order == [pid] and rt.catalog.brand == "B"
        assert rt.catalog.money(rt.catalog.live_price_value(pid)) == "S$36.00"
        assert [p.text for p in ctx.retriever.passages_of(pid) if p.section == "Cautions"] == ["Patch test first."]
        assert rt.pack.rules.rules  # a cosmetic: the market's law pack applies
        shipped = await create_session(ctx, "daon_skincare_demo")  # the shipped catalog is untouched
        assert (await ctx.runtimes.get(shipped.session_id)).catalog.order != [pid]
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


async def test_d222_the_eval_scripts_run_cases_on_a_release(tmp_path, monkeypatch):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import eval_adversarial

    from app.onboarding.release import save_release

    from .judge_fakes import violation

    rec, _ = normalise(ProductRecord.model_validate(_record()))
    rid = save_release(tmp_path, rec, "job")
    monkeypatch.setattr(eval_adversarial, "RELEASE", rid)
    real_sleep = __import__("asyncio").sleep
    monkeypatch.setattr(__import__("asyncio"), "sleep", lambda _s: real_sleep(0))
    llm = ScriptedBackend()
    llm.judge("It cures eczema.", violations=[violation("ASEAN-2D-DISEASE", "cures eczema")])
    ctx = make_ctx(backend=llm, ONBOARDING_DIR=str(tmp_path))
    case = {"case_id": "R1", "type": "t", "current_product_id": "the product", "utterance": "It cures eczema.",
            "expected": {"risky": True, "kind": "compliance", "rule_id": "ASEAN-2D-DISEASE"}}
    try:
        row = await eval_adversarial.run_case(ctx, case, 0)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
    assert [a["rule_id"] for a in row["alerts"]] == ["ASEAN-2D-DISEASE"]


def test_d223_promo_prices_are_computed_in_code_from_the_stated_terms():
    from decimal import Decimal

    from app.onboarding.release import _rounded, promos_from_offers

    money = {"currency": "SGD", "minor": 6000, "kind": "promo", "market": "SG", "evidence": EV}
    offers = [
        {"offer_id": "o1", "kind": "percent_off", "title": "Extra 15% off", "variant_ids": [], "percent": "15",
         "amount": None, "buy": None, "get": None, "gift": None, "rounding": "rounded to the nearest 10 cents",
         "starts": None, "ends": None, "duration_min": 10, "evidence": EV},
        {"offer_id": "o2", "kind": "spend_threshold_gift", "title": "Free pouch over S$60", "variant_ids": [],
         "percent": None, "amount": money, "buy": None, "get": None, "gift": "pouch", "rounding": None,
         "starts": None, "ends": None, "duration_min": None, "evidence": EV},
        {"offer_id": "o3", "kind": "percent_off", "title": "Other size only", "variant_ids": ["B"], "percent": "50",
         "amount": None, "buy": None, "get": None, "gift": None, "rounding": None, "starts": None, "ends": None,
         "duration_min": None, "evidence": EV},
    ]
    rec = ProductRecord.model_validate(_record(offers=offers))
    sale, gift = promos_from_offers(rec, "p", "A", Decimal("36.00"), "SGD", "SG")  # o3 is for another variant
    assert sale.changes_prices and sale.promo_prices == {"p": 30.6} and sale.duration_sec == 600  # 30.60 to 10 cents
    assert not gift.changes_prices and gift.min_spend == 60.0
    assert _rounded(Decimal("30.66"), None) == Decimal("30.66") and _rounded(Decimal("30.66"), "round down to the dollar") == 30


@pytest.mark.parametrize("written, quote, kept", [
    ("5,000 mg", "Vitamin C 5,000 mg per serving", "5000"),  # D-225: thousands separator, not "5"
    ("5", "Vitamin C 5,000 mg per serving", "5000"),  # D-243: the quote's one number wins, and a person checks it
    ("7", "Vitamin C 5,000 mg and 2 tablets", None),  # not in its quote, and the quote is ambiguous: dropped
    ("0,5", "Vitamin C 0,5 mg", None),  # a decimal comma in an English record is not guessed
])
def test_d225_numbers_must_match_their_evidence(written, quote, kept):
    ev = [{"file": "f", "locator": "l", "quote": quote}]
    rec = ProductRecord.model_validate(_record(ingredients=[{"name": "Vitamin C", "amount_value": written,
                                                             "amount_unit": "mg", "purpose": None, "evidence": ev}]))
    r, notes = normalise(rec)
    assert r.ingredients[0].amount_value == kept
    assert (kept is None) == any("Vitamin C" in m for m in r.missing)


def test_d225_a_decimal_comma_language_reads_commas_as_decimals():
    ev = [{"file": "f", "locator": "l", "quote": "Zink 0,5 mg"}]
    rec = ProductRecord.model_validate(_record(language="de", ingredients=[
        {"name": "Zink", "amount_value": "0,5", "amount_unit": "mg", "purpose": None, "evidence": ev}]))
    assert normalise(rec)[0].ingredients[0].amount_value == "0.5"


async def test_d226_the_caution_pass_adds_what_the_full_read_missed():
    backend = ScriptedBackend()
    backend.outputs[("onboarding_read", "spec.txt")] = _record(cautions=[{"text": "Patch test first.", "evidence": EV}])
    backend.outputs[("onboarding_cautions", "cautions")] = {"cautions": [
        {"text": "patch test first", "evidence": EV},  # already there
        {"text": "Avoid the eye area.", "evidence": EV},
        {"text": "Use sunscreen during the day.", "evidence": []}]}  # no evidence: dropped
    ctx = make_ctx(backend=backend)
    try:
        res = await read_product(ctx.llm, [model_part("spec.txt", b"hello")])
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
    assert [c.text for c in res.record.cautions] == ["Patch test first.", "Avoid the eye area."]


def test_d227_ids_in_any_script_are_distinct(tmp_path):
    from app.onboarding.release import product_key, save_release

    a = ProductRecord.model_validate(_record(brand="한빛", product_name="수분 크림"))
    b = ProductRecord.model_validate(_record(brand="한빛", product_name="진정 앰플"))
    assert product_key(a) != product_key(b) and product_key(a).startswith("p_")
    assert save_release(tmp_path, a, "j") != save_release(tmp_path, b, "j")


async def test_d227_a_category_without_a_law_pack_gets_no_law_rules(tmp_path):
    from app.onboarding.release import save_release
    from app.pipelines.runtime import create_session

    rec, _ = normalise(ProductRecord.model_validate(_record(category="apparel")))
    rid = save_release(tmp_path, rec, "j")
    ctx = make_ctx(ONBOARDING_DIR=str(tmp_path))
    try:
        rt = await ctx.runtimes.get((await create_session(ctx, "x", release_id=rid)).session_id)
        assert rt.pack.rules.rules == [] and rt.reflex.scan("This shirt cures eczema.") == []
        assert ctx.pack.rules.rules  # the shipped pack keeps its rules
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


async def test_d229_an_approved_law_pack_covers_a_category_the_market_pack_does_not(tmp_path):
    from app.onboarding.lawpack import LawPackRecord, normalise_pack, save_lawpack
    from app.onboarding.release import save_release
    from app.pipelines.runtime import create_session

    law, notes = normalise_pack(LawPackRecord.model_validate({
        "name": "Supplement advertising", "regulator": "Example authority", "covers": ["Food Supplement"],
        "language": "en", "rules": [
            {"rule_id": "supp disease", "title": "No disease claims", "description": "No cure or treatment claims.",
             "severity": "HIGH", "rule_category": "Disease", "unacceptable_examples": ["It cures arthritis."],
             "say_instead_hint": "Describe the nutrient's normal function.", "evidence": EV},
            {"rule_id": "X", "title": "t", "description": "d", "severity": "MEDIUM", "rule_category": "c",
             "unacceptable_examples": [], "say_instead_hint": "", "evidence": []}]}))
    assert [r.rule_id for r in law.rules] == ["SUPP-DISEASE"] and law.covers == ["food_supplement"] and notes
    save_lawpack(tmp_path, "SG", law, "j")
    rec, _ = normalise(ProductRecord.model_validate(_record(category="food_supplement")))
    rid = save_release(tmp_path, rec, "j")
    ctx = make_ctx(ONBOARDING_DIR=str(tmp_path))
    try:
        rt = await ctx.runtimes.get((await create_session(ctx, "x", release_id=rid)).session_id)
        assert [r.rule_id for r in rt.pack.rules.rules] == ["SUPP-DISEASE"]
        assert rt.pack.rules_by_id["SUPP-DISEASE"].severity == "HIGH"
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


def test_d230_upload_approve_start_shows_the_new_product_on_the_session(tmp_path):
    """The user flow end to end: upload, read, approve, start a show; the session's catalog, prompter and run sheet
    are the new product's (not the shipped demo's)."""
    import time

    from fastapi.testclient import TestClient

    from app.main import create_app

    from .helpers import make_settings

    backend = ScriptedBackend()
    backend.outputs[("onboarding_read", "spec.txt")] = _record(
        brand="Lumen", product_name="Night Serum",
        approved_claims=[{"text": "Helps skin look smoother by morning.", "evidence": EV}])
    with TestClient(create_app(make_settings(ONBOARDING_DIR=str(tmp_path)), llm_backend=backend)) as c:
        job = c.post("/api/onboarding/jobs", files=[("files", ("spec.txt", b"hello", "text/plain"))]).json()["job_id"]
        for _ in range(100):
            if c.get(f"/api/onboarding/jobs/{job}").json()["status"] == "done":
                break
            time.sleep(0.02)
        rid = c.post(f"/api/onboarding/jobs/{job}/approve", json={}).json()["release_id"]
        sid = c.post("/api/sessions", json={"release_id": rid}).json()["session_id"]
        cat = c.get(f"/api/catalog?session={sid}").json()
        assert cat["brand"] == "Lumen" and [p["name"] for p in cat["products"]] == ["Night Serum"]
        assert cat["products"][0]["live_price_display"] == "S$36.00"
        assert [rs["title"] for rs in cat["runsheets"]] == ["Lumen · Night Serum"]
        assert c.get("/api/catalog").json()["brand"] != "Lumen"  # the shipped catalog is unchanged
        c.post(f"/api/sessions/{sid}/start")
        state = c.get(f"/api/sessions/{sid}/state?role=host").json()
        # the host prompter is on the new product (its name comes from the session's catalog above)
        assert state["prompter"]["product_id"] == cat["products"][0]["product_id"]
        assert [p["text"] for p in state["prompter"]["points"]] == ["Helps skin look smoother by morning."]


async def test_d232_host_lines_come_in_the_show_language_or_not_at_all(tmp_path):
    from app.onboarding.release import save_release
    from app.pipelines.runtime import create_session

    from .judge_fakes import speak, violation

    rec, _ = normalise(ProductRecord.model_validate(_record(
        language="ms", approved_claims=[{"text": "Membantu kulit kelihatan licin.", "evidence": EV}])))
    with_t = save_release(tmp_path, rec, "j", {"en": {"approved_claims": [{"text": "Helps skin look smooth.",
                                                                          "reviewed": True}],
                                                      "cautions": [], "avoid_saying": []}})
    unreviewed = save_release(tmp_path, rec, "j3", {"en": {"approved_claims": [{"text": "Helps skin look smooth.",
                                                                              "reviewed": False}],
                                                           "cautions": [], "avoid_saying": []}})
    without = save_release(tmp_path, rec, "j2")
    llm = ScriptedBackend()
    llm.judge("It cures eczema.", violations=[violation("ASEAN-2D-DISEASE", "cures eczema", say="Model's own line.")])
    ctx = make_ctx(backend=llm, ONBOARDING_DIR=str(tmp_path))
    try:
        for rid, say in [(with_t, "Helps skin look smooth."),
                         (unreviewed, "Helps skin look smooth. (unreviewed translation)"),  # D-233: marked
                         (without, "(no approved wording in en)")]:
            rt = await ctx.runtimes.get((await create_session(ctx, "x", release_id=rid)).session_id)
            await rt.start()
            await speak(rt, "It cures eczema.")
            assert [a.say_instead for a in await rt.alerts() if a.kind == "compliance"] == [say]
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


async def test_d233_an_answer_from_an_unreviewed_translation_is_never_auto_posted(tmp_path):
    from app.onboarding.release import UNREVIEWED_DOC, release_pack

    rec, _ = normalise(ProductRecord.model_validate(_record(
        language="ms", cautions=[{"text": "Jangan guna pada kulit luka.", "evidence": EV}],
        qualified_results=[{"statement": "21 of 24 saw smoother skin", "numbers": ["21", "24"],
                            "provenance": "third_party_lab", "qualifier": "tested by Kestrel Labs", "marker": "†",
                            "evidence": EV}],
        approved_claims=[{"text": "Kulit lebih licin dalam 4 minggu†", "evidence": EV}],
        ingredients=[{"name": "Zinc", "amount_value": "0.5", "amount_unit": "mg", "purpose": None, "evidence": EV}])))
    ctx = make_ctx()
    try:
        tr = {"en": {"approved_claims": [{"text": "Smoother skin in 4 weeks†", "reviewed": True}],
                     "cautions": [{"text": "Do not use on broken skin.", "reviewed": False}], "avoid_saying": []}}
        pack = release_pack(ctx.pack, rec, "rel_x_v1", None, tr)
        product = pack.products.products[0]
        assert product.approved_claims == ["Smoother skin in 4 weeks (tested by Kestrel Labs)"]  # marker -> qualifier
        assert product.key_facts == {"zinc": "0.5mg"}  # the prompter's ingredient panel
        [caution] = [p for p in pack.passages if p.section == "Cautions"]
        assert caution.doc == UNREVIEWED_DOC
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


def test_d236_risk_mode_checks_only_what_reaches_the_show():
    from app.onboarding.checks import check_items, summary
    from app.onboarding.record import OnboardingResult

    rec, _ = normalise(ProductRecord.model_validate(_record(
        cautions=[{"text": "Patch test first.", "evidence": EV}, {"text": "Avoid the eye area.", "evidence": EV}],
        how_to_use=[{"text": "Apply at night.", "evidence": EV}],
        approved_claims=[{"text": "Helps skin feel soft.", "evidence": EV}],
        conflicts=[{"field": "variants[0].prices[0].minor", "values": ["3600", "3400"], "evidence": EV,
                    "effective_dates": [None, None], "note": ""}])))
    result = OnboardingResult(record=rec, method="gemini_whole", seconds=1, caution_pass_added=["Avoid the eye area."])
    full = check_items(result, "full", law="15 rules")
    risk = check_items(result, "risk", law="15 rules", caution_pass_only=result.caution_pass_added)
    assert len(risk) < len(full)
    groups = summary(risk)["by_group"]
    assert groups["product"] == 2 and groups["safety"] == 1 and groups["audit"] == 2  # the conflict, a size with no price
    assert not any(x["label"] == "Apply at night." for x in risk)  # prose is checked live, not here
    assert any(x["reason"].startswith("no law pack") for x in check_items(result, "risk", law="no law checks"))


def test_d238_test_drive_reads_the_sample_approves_and_starts_a_live_show(tmp_path, monkeypatch):
    import time

    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.pipelines import testdrive as td

    from .helpers import make_settings

    monkeypatch.setattr(td, "_starts", [])
    monkeypatch.setattr(td, "MAX_PER_HOUR", 1)
    played = []

    async def no_scene(rt):
        played.append(rt.sid)

    monkeypatch.setattr(td, "play", no_scene)
    backend = ScriptedBackend()
    settings = make_settings(ONBOARDING_DIR=str(tmp_path))
    names = "|".join(n for n, _ in td.sample_files(settings.data_path))
    backend.outputs[("onboarding_read", names)] = _record(brand="Lumen", product_name="Night Serum")
    with TestClient(create_app(settings, llm_backend=backend)) as c:
        start = c.post("/api/testdrive/start").json()
        assert not start["cached"] and len(start["files"]) == 4
        for _ in range(100):
            if c.get(f"/api/onboarding/jobs/{start['job_id']}").json()["status"] == "done":
                break
            time.sleep(0.02)
        go = c.post(f"/api/testdrive/{start['job_id']}/go").json()
        state = c.get(f"/api/sessions/{go['session_id']}/state?role=host").json()
        assert state["session"]["status"] == "live" and played == [go["session_id"]]
        assert c.post("/api/testdrive/start").status_code == 429  # the hourly cap
        monkeypatch.setattr(td, "_starts", [])
        again = c.post("/api/testdrive/start").json()
        assert again["cached"] and again["status"] == "done"  # the sample is read once, then reused


async def test_d240_impact_counts_come_with_their_denominators():
    from .helpers import live_runtime, say
    from .judge_fakes import speak, violation

    llm = ScriptedBackend()
    ctx = make_ctx(backend=llm)
    rt = await live_runtime(ctx)
    try:
        llm.judge("It cures eczema.", violations=[violation("ASEAN-2D-DISEASE", "cures eczema")])
        await speak(rt, "It cures eczema.")
        await speak(rt, "It feels light.")
        await say(rt, "Lee", "How much is the cream?")
        i = (await rt.compute_metrics())["impact"]
        assert i["risky_lines"] == {"alerted": 1, "of_lines": 2}
        assert i["questions"]["of_askers"] == 1 and i["questions"]["ai"] + i["questions"]["host"] + i["questions"]["operator"] >= 1
        assert i["operator_actions"] == 0 and i["llm"]["calls"] > 0
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


async def test_d241_brand_rules_only_add_restrictions(tmp_path):
    from app.onboarding.lawpack import LawPackRecord, normalise_pack, save_brandpack
    from app.onboarding.release import release_pack

    brand, _ = normalise_pack(LawPackRecord.model_validate({
        "name": "B guidelines", "regulator": "B", "covers": ["cosmetic"], "language": "en", "rules": [
            {"rule_id": "NO-CELEB", "title": "No celebrity comparisons", "description": "Never compare to a celebrity.",
             "severity": "MEDIUM", "rule_category": "comparison", "unacceptable_examples": ["Skin like a movie star."],
             "say_instead_hint": "Describe the product itself.", "evidence": EV}]}))
    save_brandpack(tmp_path, "B", brand, "j")
    rec, _ = normalise(ProductRecord.model_validate(_record()))  # brand "B", a cosmetic
    ctx = make_ctx()
    try:
        law = release_pack(ctx.pack, rec, "rel_x_v1", None).rules.rules
        both = release_pack(ctx.pack, rec, "rel_x_v1", tmp_path).rules.rules
        assert [r.rule_id for r in both] == [r.rule_id for r in law] + ["BR-NO-CELEB"]  # law kept, brand added
        other = rec.model_copy(update={"brand": "Other"})
        assert len(release_pack(ctx.pack, other, "rel_y_v1", tmp_path).rules.rules) == len(law)
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


def test_d242_record_mode_gives_the_fact_checker_every_size_market_offer_and_superseded_value():
    from app.onboarding.release import release_pack

    ev = EV
    rec, _ = normalise(ProductRecord.model_validate(_record(
        variants=[{"variant_id": "A", "name": "P 30", "size_value": "30", "size_unit": "ml", "market": None,
                   "prices": [{"currency": "SGD", "minor": 3600, "kind": "live", "market": "SG", "evidence": ev},
                              {"currency": "MYR", "minor": 11900, "kind": "live", "market": "MY",
                               "evidence": [{"file": "f", "locator": "l", "quote": "RM119"}]}], "evidence": ev}],
        offers=[{"offer_id": "o1", "kind": "buy_x_get_y", "title": "Buy 2 get 1", "variant_ids": [], "percent": None,
                 "amount": None, "buy": 2, "get": 1, "gift": None, "rounding": None, "starts": None, "ends": None,
                 "duration_min": None, "evidence": ev}],
        conflicts=[{"field": "P 30 live price", "values": ["S$38.00", "S$36.00"],
                    "effective_dates": ["2026-09-01", "2026-10-01"], "note": "", "evidence": ev}])))
    ctx = make_ctx()
    try:
        sheet = release_pack(ctx.pack, rec, "rel_x_v1", None, fact_mode="sheet")
        record = release_pack(ctx.pack, rec, "rel_x_v1", None, fact_mode="record")
        assert not [p for p in sheet.passages if p.section == "Record facts"]
        facts = [p.text for p in record.passages if p.section == "Record facts"]
        assert "P 30 (30 ml) · MY live price: MYR 119.00" in facts and "P 30 (30 ml) · SG live price: S$36.00" in facts
        assert any(t.startswith("Superseded: P 30 live price was S$38.00") for t in facts)
        assert any(t.startswith("Offer: Buy 2 get 1") and "buy 2 get 1" in t for t in facts)
        assert "Live broadcast price (30 ml): S$36.00" in [p.text for p in record.passages]
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()


@pytest.mark.parametrize("quote, written, currency, kept_minor", [
    ("가격 이만 구천 원", "290", "KRW", 29000),  # D-243: Korean words; the model's misread is replaced
    ("Harga dua puluh sembilan ringgit", "29", "MYR", 2900),  # Malay words
    ("售价二万九千", "29000", "KRW", 29000),  # Chinese numerals
    ("Now only 2만 9천원", "29000", "KRW", 29000),  # mixed digits and Korean scale words
    ("Price: twenty-nine dollars", "29", "SGD", 2900),
])
def test_d243_prices_written_in_words_are_read_in_code(quote, written, currency, kept_minor):
    from app.onboarding.record import to_minor

    ev = [{"file": "f", "locator": "l", "quote": quote}]
    rec = ProductRecord.model_validate(_record(variants=[{
        "variant_id": "A", "name": "P", "size_value": None, "size_unit": None, "market": None,
        "prices": [{"currency": currency, "minor": to_minor(currency, written), "kind": "list", "market": None,
                    "evidence": ev}], "evidence": ev}]))
    r, notes = normalise(rec)
    assert r.variants[0].prices[0].minor == kept_minor


def test_d243_zero_decimal_currencies_keep_the_whole_amount():
    from app.onboarding.record import money_value, to_minor

    assert money_value("KRW", 29000) == 29000 and to_minor("KRW", "29000") == 29000
    assert money_value("SGD", 3600) == 36 and to_minor("SGD", "36") == 3600


async def test_d243_routing_turns_tests_and_certifications_into_qualified_results_and_limitations_into_cautions():
    backend = ScriptedBackend()
    backend.outputs[("onboarding_read", "spec.txt")] = _record(
        key_facts=[{"text": "Tested by Kestrel Labs: 21 of 24 felt softer skin.", "evidence": EV}],
        approved_claims=[{"text": "Certified vegan by the Vegan Society.", "evidence": EV}],
        how_to_use=[{"text": "Results may vary between users.", "evidence": EV},
                    {"text": "Keep the applicator clean.", "evidence": EV}])
    backend.outputs[("onboarding_route", "route|P")] = {"items": [
        {"id": "key_facts[0]", "kind": "test_result", "statement": "21 of 24 felt softer skin",
         "provenance": "third_party_lab", "qualifier": "tested by Kestrel Labs", "marker": None},
        {"id": "approved_claims[0]", "kind": "certification", "statement": "Certified vegan",
         "provenance": "other", "qualifier": "certified by the Vegan Society", "marker": None},
        {"id": "how_to_use[0]", "kind": "limitation", "statement": None, "provenance": None, "qualifier": None,
         "marker": None},
        {"id": "nope[9]", "kind": "test_result", "statement": "x", "provenance": "other", "qualifier": "q",
         "marker": None}]}
    # D-243 F3: the caution pass lists a hygiene line that also stays in the directions
    backend.outputs[("onboarding_cautions", "cautions")] = {"cautions": [{"text": "Keep the applicator clean.",
                                                                           "evidence": EV}]}
    ctx = make_ctx(backend=backend)
    try:
        res = await read_product(ctx.llm, [model_part("spec.txt", b"hello")])
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
    r = res.record
    assert [(q.statement, q.provenance, q.qualifier) for q in r.qualified_results] == [
        ("21 of 24 felt softer skin", "third_party_lab", "tested by Kestrel Labs"),
        ("Certified vegan", "other", "certified by the Vegan Society")]
    assert r.qualified_results[0].numbers == ["21", "24"] and r.qualified_results[0].evidence == r.key_facts[0].evidence
    assert [c.text for c in r.cautions] == ["Keep the applicator clean.", "Results may vary between users."]
    assert "Keep the applicator clean." in [h.text for h in r.how_to_use]  # kept in the directions too


def test_d244_l1_a_contradiction_without_a_source_value_is_unverifiable(pack, catalog):
    from app.agents.fact_checker import post_validate
    from app.models.agent_io import FactCheckOutput

    cream = "cream_hydra_barrier"
    quote = "Live broadcast price: S$36.00"
    pid = "DL-CR-01#key-facts#live-broadcast-price"
    claim = {"span": "x", "field": "other", "product_id": cream, "stated_value": "5 mg vitamin E",
             "verdict": "contradicted", "correct_value": "not disclosed", "passage_id": pid, "quote": quote}
    out = FactCheckOutput.model_validate({"claims": [claim | {"field": "ingredient_amount"}], "reason": "t"})
    assert post_validate(out, pack.passages, catalog, None).claims[0].verdict == "not_in_sources"


def test_d244_l2_l3_offer_totals_and_written_terms_reach_the_fact_checker():
    from app.onboarding.release import release_pack

    ev = [{"file": "f", "locator": "l", "quote": "Buy 2 get 1 free; not combinable with other offers"}]
    rec, _ = normalise(ProductRecord.model_validate(_record(offers=[
        {"offer_id": "o1", "kind": "buy_x_get_y", "title": "Buy 2 get 1", "variant_ids": [], "percent": None,
         "amount": None, "buy": 2, "get": 1, "gift": None, "rounding": None, "starts": None, "ends": None,
         "duration_min": None, "evidence": ev}])))
    ctx = make_ctx()
    try:
        facts = [p.text for p in release_pack(ctx.pack, rec, "rel_x_v1", None).passages if p.section == "Record facts"]
    finally:
        ctx.runtimes.shutdown()
        ctx.scheduler.shutdown()
    [offer] = [t for t in facts if t.startswith("Offer:")]
    assert "pay for 2 = S$72.00 for 3 items" in offer and "not combinable with other offers" in offer
    assert "Live unit price S$36.00; 2 units S$72.00; 3 units S$108.00" in facts


def test_d244_l7_naming_the_lab_is_saying_the_qualifier(pack):
    from app.agents.utterance_judge import names_the_source

    say = "21 of 24 saw smoother texture (tested by Kestrel Dermal Labs)"
    assert names_the_source("Kestrel Dermal Labs found 21 of 24 saw smoother texture", say, pack.lexicon)
    assert not names_the_source("21 of 24 saw smoother texture", say, pack.lexicon)
    assert not names_the_source("our test: 45% more", "Hydration +45% (in our in-house test)", pack.lexicon)


def test_d244_l4_to_l6_and_presence_rules_reach_the_fact_checker():
    from app.agents import arms
    from app.config import get_settings

    fr = arms._addenda(str(get_settings().prompts_path))[("FR", "fact_checker")]
    for rule in ("never with\n  the unit price", "Every number with a unit", "Price terms", "describing an old value",
                 "Free from", "Only contradict with a value SOURCE states"):
        assert rule in fr


def test_d244_l8_a_bare_field_word_becomes_the_source_line(pack, catalog):
    from app.agents.fact_checker import _from_quote, post_validate
    from app.models.agent_io import FactCheckOutput

    p = next(p for p in pack.passages if p.product_id == "cream_hydra_barrier")
    quote = p.text[:30]
    word = quote.split()[0]
    claim = {"span": f"no {word} in it", "field": "ingredient", "product_id": "cream_hydra_barrier",
             "stated_value": f"no {word}", "verdict": "contradicted", "correct_value": word,
             "passage_id": p.passage_id, "quote": quote}
    [c] = post_validate(FactCheckOutput.model_validate({"claims": [claim], "reason": "t"}),
                        pack.passages, catalog, None).claims
    assert c.verdict == "contradicted" and c.correct_value == quote
    # a statement in the quote's words passes; "not disclosed" does not, in any script
    assert _from_quote("It does contain fragrance", "Ingredients: Water, Glycerin, Fragrance")
    assert not _from_quote("not disclosed", "Live broadcast price: S$36.00")
    assert _from_quote("향료 함유", "전성분: 정제수, 글리세린, 향료")
    assert not _from_quote("공개되지 않음", "라이브 가격: 36,000원")
