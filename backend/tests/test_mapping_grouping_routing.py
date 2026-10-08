from __future__ import annotations

from app.logic.grouping import join_group, normalise_question, ttl_expired
from app.logic.product_mapping import attribute_product
from app.logic.routing import is_composable, route_for
from app.logic.segments import segment_at
from app.models.agent_io import CommentTriageOutput, ConditionSlots
from app.models.session import QuestionGroup, Segment

CREAM, AMPOULE = "cream_hydra_barrier", "ampoule_deep_hydration"
NO_SLOTS = {"person_type": None, "life_stage": None, "condition": None, "combined_with": None, "time_of_day": None}


def triage(pid=None, basis="unknown", intent="price") -> CommentTriageOutput:
    return CommentTriageOutput(kind="question", hide_category=None, product_id=pid, product_basis=basis,
                               intent=intent, condition_slots=ConditionSlots(**NO_SLOTS), canonical_question="q",
                               group_candidate_id=None, reason="")


# ---- product mapping -------------------------------------------------------------------------


def test_alias_match_wins(catalog, pack):
    intent = pack.intents_by_name["price"]
    assert attribute_product("How much is the ampoule?", triage(CREAM, "context"), CREAM, catalog, intent) == (AMPOULE, "explicit")


def test_triage_basis_used_without_alias(catalog, pack):
    intent = pack.intents_by_name["price"]
    assert attribute_product("price pls", triage(CREAM, "context"), AMPOULE, catalog, intent) == (AMPOULE, "context")
    assert attribute_product("does it have niacinamide", triage(AMPOULE, "content"), CREAM, catalog,
                             pack.intents_by_name["ingredients"]) == (AMPOULE, "content")
    # D-135: no product named and triage unsure: the product on air ("ml?", "SPF?")
    assert attribute_product("price?", triage(None, "unknown"), CREAM, catalog, intent) == (CREAM, "context")
    assert attribute_product("price?", triage(None, "context"), None, catalog, intent) == (None, "unknown")


def test_general_and_multi_intents(catalog, pack):
    assert attribute_product("Do you ship the cream to Malaysia?", triage(CREAM, "explicit", "shipping"), CREAM,
                             catalog, pack.intents_by_name["shipping"]) == (None, "unknown")
    multi = pack.intents_by_name["product_comparison"]
    assert attribute_product("which one should I buy first, cream or ampoule?", triage(None, "unknown",
                             "product_comparison"), CREAM, catalog, multi) == (None, "explicit")


def test_grace_window_at_switch_boundary():
    t0 = 1_000_000
    segs = [Segment(segment_id="s1", product_id=CREAM, order=1, started_at=t0, ended_at=t0 + 60_000,
                    start_reason="session_start", planned_duration_sec=900),
            Segment(segment_id="s2", product_id=AMPOULE, order=2, started_at=t0 + 60_000,
                    start_reason="auto_speech", planned_duration_sec=600)]
    grace = 2000
    assert segment_at(segs, t0 + 61_000 - grace).product_id == CREAM  # 1 s after the commit: previous product
    assert segment_at(segs, t0 + 62_500 - grace).product_id == AMPOULE
    assert segment_at(segs, t0 - 1) is None
    segs[1].ended_at = t0 + 90_000
    assert segment_at(segs, t0 + 500_000).product_id == AMPOULE  # after the end: last segment


# ---- grouping ---------------------------------------------------------------------------------


def group(gid, intent="suitability", slots=None, q="Is it suitable for oily skin?", pid=CREAM, status="ready", last_at=0):
    return QuestionGroup(group_id=gid, product_id=pid, intent=intent, condition_slots=slots or {"person_type": "oily"},
                         canonical_question=q, member_comment_ids=["c1"], unique_author_ids=["u1"], first_at=0,
                         last_at=last_at, route="HOST", route_reason="intent", status=status)


def test_unique_authors_and_ttl():
    g = group("g1")
    assert join_group(g, "c2", "u2", 10) is True
    assert join_group(g, "c3", "u1", 20) is False  # same author again
    assert g.member_comment_ids == ["c1", "c2", "c3"] and g.unique_author_ids == ["u1", "u2"] and g.last_at == 20
    assert ttl_expired(g, 20 + 600_000, 600)
    assert not ttl_expired(g, 20 + 599_999, 600)
    g.host_slot = "on_host"
    assert not ttl_expired(g, 20 + 700_000, 600)


# ---- routing ----------------------------------------------------------------------------------


def test_routes(pack):
    i = pack.intents_by_name
    assert route_for(i["price"], CREAM) == ("AUTO", "intent")
    assert route_for(i["price"], None) == ("HOST", "unresolved_product")  # D-113: "Which product?"
    assert route_for(i["suitability"], CREAM) == ("HOST", "intent")
    assert route_for(i["pregnancy_breastfeeding"], CREAM) == ("HOST", "sensitive")  # D-113
    assert route_for(i["shipping"], None) == ("OPERATOR", "intent")
    assert route_for(i["product_comparison"], None) == ("HOST", "intent")
    assert is_composable(i["product_comparison"], None)
    assert not is_composable(i["shipping"], None)
    assert not is_composable(i["price"], None)


def test_a_set_question_always_uses_the_on_air_product(catalog, pack):
    """D-147 (comment-flow CF10): "cream and serum set" with the ampoule on air was attributed to the cream
    (named first), the other set questions to the ampoule: two groups and two drafts for one set."""
    set_price = pack.intents_by_name["set_price"]
    assert attribute_product("how much for cream and serum set?", triage(CREAM, "explicit", "set_price"), AMPOULE,
                             catalog, set_price) == (AMPOULE, "context")
    assert attribute_product("both together price pls", triage(None, "unknown", "set_price"), AMPOULE,
                             catalog, set_price) == (AMPOULE, "context")
    first = catalog.order[0]
    assert attribute_product("set price?", triage(None, "unknown", "set_price"), None, catalog, set_price)[0] == first


def test_d213_triage_decides_the_product_and_aliases_are_only_candidates(catalog, pack):
    intent = pack.intents_by_name["price"]
    # triage named the ampoule; the alias "cream" in the text does not override it
    assert attribute_product("Is it cheaper than the cream?", triage(AMPOULE, "explicit"), CREAM, catalog,
                             intent) == (AMPOULE, "explicit")
    # no product from triage: the one alias candidate is used
    assert attribute_product("how much is the cream?", triage(None, "unknown"), AMPOULE, catalog,
                             intent) == (CREAM, "explicit")
