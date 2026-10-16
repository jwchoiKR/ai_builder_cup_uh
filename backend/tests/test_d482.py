"""D-482: the viewer's comment projection carries triage's verdict ("kind") so the viewer's animals speak once it is
in; never the signal, armor or hide category, and a hidden comment keeps its five fields."""
from __future__ import annotations

from app.bus import viewer_comment
from app.models.session import Comment


def _doc(**over) -> dict:
    c = Comment(comment_id="cm_1", author_id="u_1", author_name="Amy", text="is it vegan?", received_at=1, source="viewer",
                kind="question", signal="injection", armor="unscreened", hide_category="spam", **over)
    return c.model_dump(mode="json")


def test_a_visible_comment_carries_its_kind_and_nothing_internal():
    out = viewer_comment(_doc())
    assert out["kind"] == "question"
    assert not {"signal", "armor", "hide_category", "analysis_id", "group_id", "source"} & out.keys()


def test_a_hidden_comment_carries_no_kind():
    out = viewer_comment(_doc(visibility="hidden"))
    assert set(out) == {"comment_id", "author_id", "author_name", "received_at", "visibility"}
