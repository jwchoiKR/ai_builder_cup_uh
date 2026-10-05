"""P0 onboarding steps 1-3: immutable storage, file conversion, the read call and code normalisation."""
from __future__ import annotations

import io

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
    ("5", "Vitamin C 5,000 mg per serving", None),  # a number not in its own quote is dropped
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
