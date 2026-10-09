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
