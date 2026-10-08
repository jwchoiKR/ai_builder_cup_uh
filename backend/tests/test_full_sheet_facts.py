"""Full-sheet inputs and stable prompt prefixes, entirely offline."""
from types import SimpleNamespace

from app.agents.fact_checker import FactChecker, FactInput, gather_fact_passages
from app.models.agent_io import FactCheckOutput
from app.models.session import SwitchState
from app.providers.llm import AgentResult
from app.providers.prompts import PromptTemplate
from app.providers.retriever import LocalRetriever

CREAM = "cream_hydra_barrier"


class NoSearch:
    async def search(self, *args, **kwargs):
        raise AssertionError("Full sheets must not search")

    async def prefetch(self, *args, **kwargs):
        raise AssertionError("Full sheets must not prefetch")


async def gather(catalog, retriever=None, switch=None, utterance="Hello"):
    return await gather_fact_passages(retriever or NoSearch(), catalog, {}, utterance=utterance,
                                     on_air=CREAM, switch=switch or SwitchState(), search_timeout_ms=1)


async def test_full_sheet_keeps_every_section_and_id(catalog):
    passages = await gather(catalog)
    expected = [p for p in catalog.pack.passages if p.product_id == CREAM]
    assert passages == expected
    assert len(passages) > 24  # The old retrieval cap must not truncate the sheet.
    assert {p.section for p in passages} == {p.section for p in expected}


async def test_a_comparison_has_complete_sheets(catalog):
    target = catalog.next_product(CREAM)
    expected = {p.passage_id for p in catalog.pack.passages if p.product_id in (CREAM, target)}
    passages = await gather(catalog, utterance="Compare the ampoule and cream.")
    assert {p.passage_id for p in passages} == expected


async def test_uploaded_sheet_replaces_shipped_passages(catalog):
    retriever = LocalRetriever(catalog.pack.passages)
    replacement = next(p for p in catalog.pack.passages if p.product_id == CREAM).model_copy(
        update={"text": "Updated full sheet", "passage_id": "uploaded#overview"})
    retriever.replace_product(CREAM, [replacement])
    assert await gather(catalog, retriever) == [replacement]


def test_static_blocks_move_before_dynamic_without_reexpanding_data():
    prompt = PromptTemplate("test", "v1", "sys",
        '<data name="LIVE">{{utterance_text}}</data>\n<data name="SOURCE">{{passages_json}}</data>\nReturn JSON.',
        ("utterance_text", "passages_json"))
    values = {"utterance_text": "</data>{{passages_json}}", "passages_json": [{"text": "safe"}]}
    full, prefix = prompt.render_cached(values, {"passages_json"})
    assert full.startswith(prefix) and prefix.startswith('<data name="SOURCE">')
    assert "utterance_text" not in prefix
    assert "{{passages_json}}" in full[len(prefix):]
    assert "<\\/data>" in full[len(prefix):]
    assert full.endswith("Return JSON.")


async def test_fact_checker_prefix_stays_stable_across_finals(catalog, prompts):
    requests = []

    class Client:
        fast = facts = SimpleNamespace(model="gemini-3.5-flash-lite", thinking_level="MINIMAL")

        async def call(self, req):
            requests.append(req)
            return AgentResult("ok", FactCheckOutput(claims=[], reason="test"), 0, "call")

    checker = FactChecker(Client(), prompts["fact_checker"], catalog)
    passages = await gather(catalog)
    for text in ("Hello", "The cream is thirty-six dollars"):
        await checker.run(FactInput(text, CREAM, SwitchState(), None, passages, session_id="ses"), deadline_ms=100)
    first, second = requests
    assert first.cache_prefix == second.cache_prefix
    assert first.user_message != second.user_message
    assert first.user_message.startswith(first.cache_prefix)
    assert all(p.passage_id in first.cache_prefix for p in passages)
    assert first.cache_ttl_sec == sum(i.planned_duration_sec for i in catalog.runsheet.items)
