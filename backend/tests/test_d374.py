"""D-374 (user, 10/9): the model's verdict is applied as given on the live path. The only skip is a verdict that
cannot be applied (a product id that is not in the show), logged. Demo catalog."""
from __future__ import annotations

import logging

from app.agents.utterance_judge import validate_original
from app.logic.facts import correct_notes
from app.models.agent_io import ComplianceOutputO, with_product
from app.models.session import Alert, Transcript

from .judge_fakes import AMPOULE, CREAM


def _out(product_id: str) -> ComplianceOutputO:
    return with_product(ComplianceOutputO).model_validate({"compliance": {"violations": [{
        "citation": "guideline.pdf#3", "quote": "a summary", "span": "cures acne", "severity": "HIGH",
        "is_negated": False, "is_quoted": False, "say_instead": "x", "qualified_result_id": None,
        "product_id": product_id}]}, "correction": {"corrects_alert_ids": []}, "reason": "r"})


def test_d374_only_a_product_not_in_the_show_is_skipped(catalog, caplog):
    values = {"current_product_json": {"product_id": CREAM}, "active_alerts_json": [], "scope_product_ids": [CREAM]}
    with caplog.at_level(logging.INFO):
        [v] = validate_original(_out(AMPOULE), catalog, values, ()).compliance.violations  # in the show: as given
        assert validate_original(_out("no_such_product"), catalog, values, ()).compliance.violations == []
    assert v.product_id == AMPOULE and v.rule_id == "guideline#3"
    assert "is not in the show" in caplog.text


def test_d374_a_note_the_model_marks_fixed_is_corrected_even_by_the_line_that_re_showed_it():
    note = Alert(alert_id="fx_1", kind="fact", status="active", transcript_id="t2", product_id=CREAM,
                 field="price", created_at=0)
    t = Transcript(transcript_id="t2", text="Thirty-six, sorry.", is_final=True, segment_id="seg_1", received_at=0,
                   speech_end_at=0, source="injected")
    assert [a.alert_id for a in correct_notes({"fx_1"}, [note], t, 1, fresh={"fx_1"})] == ["fx_1"]
