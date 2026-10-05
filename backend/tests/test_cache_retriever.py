from __future__ import annotations

from app.logic.cache import AnswerCache, CachedAnswer, TriageCache, answer_cache_key, normalise_comment, triage_cache_key
from app.providers.retriever import LocalRetriever, tokenize

CREAM, AMPOULE = "cream_hydra_barrier", "ampoule_deep_hydration"


def test_answer_key_includes_promo_state_and_doc_version():
    base = dict(product_id=CREAM, intent="price", slots={"skin_type": None}, canonical_question="How much is it?")
    k1 = answer_cache_key(**base, promo_state="none", doc_version=0)
    assert k1 == answer_cache_key(**{**base, "canonical_question": "how much is it"}, promo_state="none", doc_version=0)
    assert k1 != answer_cache_key(**base, promo_state="promo_time_sale_10", doc_version=0)
    assert k1 != answer_cache_key(**base, promo_state="none", doc_version=1)
    assert k1 != answer_cache_key(**{**base, "slots": {"skin_type": "oily"}}, promo_state="none", doc_version=0)


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


async def test_bm25_filters_by_product(pack):
    r = LocalRetriever(pack.passages)
    hits = await r.search("Hydra Barrier Cream Is it suitable for oily skin?", product_filter=CREAM, top_k=6, timeout_ms=500)
    assert hits and all(h.product_id == CREAM for h in hits)
    assert hits[0].passage_id == "DL-CR-01#frequently-asked-questions#is-it-suitable-for-oily-skin"
    amp = await r.search("how much niacinamide", product_filter=AMPOULE, top_k=3, timeout_ms=500)
    assert amp[0].passage_id.startswith("DL-AM-01#") and "niacinamide" in amp[0].passage_id
    assert await r.search("anything", product_filter="nope", top_k=3, timeout_ms=500) == []


async def test_prefetch_sections(pack):
    r = LocalRetriever(pack.passages)
    pre = await r.prefetch(CREAM)
    assert {p.section for p in pre} == {"Key facts", "Key ingredients", "How to use", "Cautions", "In-house test results"}
    assert all(p.product_id == CREAM for p in pre)


async def test_a_how_to_use_question_always_gets_the_how_to_use_steps(pack):
    """D-153 (00007 show replays): BM25 never ranked "Apply two to three drops ..." for "How many drops?", so
    the composer answered nothing."""
    from app.agents.answer_composer import gather_passages
    from app.logic.catalog import Catalog

    r = LocalRetriever(pack.passages)
    for intent in ("how_to_use", "routine_order"):
        got = await gather_passages(r, Catalog(pack), {}, product_id=AMPOULE, intent=intent,
                                    canonical_question="How many drops?", promo=None, top_k=6)
        assert "DL-AM-01#how-to-use#steps" in {p.passage_id for p in got}
