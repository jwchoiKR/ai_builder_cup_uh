from __future__ import annotations

from app.logic.cache import AnswerCache, CachedAnswer, TriageCache, answer_cache_key, normalise_comment, triage_cache_key
from app.providers.retriever import LocalRetriever, tokenize

CREAM, AMPOULE = "cream_hydra_barrier", "ampoule_deep_hydration"


def test_answer_key_includes_promo_state_and_doc_version():
    base = dict(product_id=CREAM, intent="price", slots={"person_type": None}, canonical_question="How much is it?")
    k1 = answer_cache_key(**base, promo_state="none", doc_version=0)
    assert k1 == answer_cache_key(**{**base, "canonical_question": "how much is it"}, promo_state="none", doc_version=0)
    assert k1 != answer_cache_key(**base, promo_state="promo_time_sale_10", doc_version=0)
    assert k1 != answer_cache_key(**base, promo_state="none", doc_version=1)
    assert k1 != answer_cache_key(**{**base, "slots": {"person_type": "oily"}}, promo_state="none", doc_version=0)


def test_answer_cache_invalidation_by_intent():
    c = AnswerCache()
    c.put("a", CachedAnswer("ans_1", "price"))
    c.put("b", CachedAnswer("ans_2", "fragrance"))
    assert c.invalidate_intents(frozenset({"price", "set_price", "promo"})) == 1
    assert c.get("a") is None and c.get("b") is not None


def test_triage_normalisation():
    assert normalise_comment("  How much is the   CREAM??  ") == "how much is the cream??"
    # D-211: punctuation and emoji are part of the key
    assert normalise_comment("price? 😍😍") == "price? 😍😍"
    assert triage_cache_key("nice!", "p") != triage_cache_key("nice?", "p")
    assert triage_cache_key("How much is the  cream?", CREAM) == triage_cache_key("how much is the cream?", CREAM)
    assert triage_cache_key("price?", CREAM) != triage_cache_key("price?", AMPOULE)
    t = TriageCache()
    t.put("k", {"kind": "question", "group_candidate_id": "grp_1"})
    assert t.get("k")["group_candidate_id"] is None and t.get("x") is None
    assert (t.hits, t.misses) == (1, 1)


def test_tokenize_keeps_percent():
    assert tokenize("Niacinamide: 4%. S$36.00 price") == ["niacinamide", "4%", "s", "36.00", "price"]
