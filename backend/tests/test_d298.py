"""D-298: two checks of the model's extraction against the text, before the freeze. The CK group must be said in the
line or the previous final; a quote or question in the previous final, rejected in this one, is no contradiction
when this line says the correction. Paired: each false-alert class next to the line that must still alert."""
from __future__ import annotations

import pytest


from .test_relation import ALL, V, _high, _validate_r


@pytest.mark.parametrize("line, prev, group, kept", [
    ("Ten-free means absolutely no harmful effects, guaranteed.", None, "everyone", False),
    ("Safe for everyone.", None, "everyone", True),
    ("After a patch test this oil is completely safe.", None, "sensitive skin", False),
    ("Gentle on sensitive skin.", None, "sensitive skin", True),
    ("This is totally safe.", "My little one has eczema.", "children with eczema", True),  # the previous final
    ("임산부도 안심하고 쓸 수 있어요.", None, "임산부", True),  # any script: the judge copies the line's words
])
def test_d298_ck_the_group_must_be_said(catalog, line, prev, group, kept):
    v = _high(V, line, "safety_promise", group)
    assert [x.rule_id for x in _validate_r(catalog, line, [v], ALL, prev)] == ([V] if kept else [])


PRICE = "Live broadcast price (50 mL): S$24.00"

