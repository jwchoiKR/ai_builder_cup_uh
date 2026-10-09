"""Offline routing scoring checks. No provider construction or model calls."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "eval_routing_experiment", Path(__file__).resolve().parents[1] / "scripts" / "eval_routing.py")
routing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(routing)


def test_regex_spoken_numbers_catalog_names_and_boundaries():
    product = SimpleNamespace(name="Demo Cream", short_name="cream", aliases=["gel-cream"],
                              key_facts={"ceramide_np": "1%", "texture": "watery"})
    pattern = routing.fact_pattern(SimpleNamespace(products=SimpleNamespace(products=[product], set_offers=[])))
    for text in ("thirty-two dollars", "ten percent", "contains ceramide NP", "gel-cream", "50 mL"):
        assert pattern.search(text), text
    for text in ("Welcome everyone", "someone joined", "stone", "alone"):
        assert not pattern.search(text), text


def test_metrics_count_repeated_misses_and_regex_na():
    rows = [{"id": "A", "needs": {"facts": True}, "route": {"facts": False, "context": None}},
            {"id": "A", "needs": {"facts": True}, "route": {"facts": False, "context": None}},
            {"id": "B", "needs": {"facts": False}, "route": {"facts": True, "context": None}}]
    result = routing.metrics(rows, "facts")
    assert result["recall"] == 0
    assert result["precision"] == 0
    assert result["miss_count"] == 2
    assert result["miss_case_ids"] == ["A"]
    assert result["misses_by_case"] == {"A": 2}
    assert result["calls_saved"] == 2
    assert routing.metrics(rows, "context") is None


def test_sweep_retains_fail_open_with_overrides_off():
    needs = {s: True for s in routing.SPECIALISTS}
    rows = [{"id": "failed", "router": "jev", "router_status": "timeout", "router_ms": 301,
             "route_probs": None, "needs": needs, "forced": {s: False for s in needs}, "route": needs},
            {"id": "forced", "router": "jev", "router_status": "ok", "router_ms": 12,
             "route_probs": {s: .01 for s in needs}, "needs": needs, "forced": needs, "route": needs}]
    summary = routing.summarize(rows)
    for sweep in summary["jev_sweep"]:
        assert sweep["specialists"]["facts"]["miss_case_ids"] == ([] if sweep["overrides_on"] else ["forced"])
    assert summary["jev"]["statuses"] == {"timeout": 1, "ok": 1}


def test_cases_optional_file_and_explicit_label_validation(tmp_path):
    data = tmp_path / "eval"
    data.mkdir()
    (data / "utterance_cases.jsonl").write_text(
        json.dumps({"case_id": "U39"}) + "\n" + json.dumps({"case_id": "U32", "expected": {"covered_points": ["p1"]}}),
        encoding="utf-8")
    cases, extra = routing.load_cases(tmp_path)
    assert not extra
    assert cases[0]["needs"]["facts"]
    assert cases[1]["needs"]["context"]
    (data / "route_cases.jsonl").write_text(json.dumps({"case_id": "R1", "needs": {"facts": "false"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid explicit needs"):
        routing.load_cases(tmp_path)


@pytest.mark.parametrize("selected", ["regex", "gemini_purpose", "jev", "llm"])
async def test_router_subset_initializes_only_selected_clients(monkeypatch, settings, selected):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from experiments import gemini_router, jev_router
    import eval_common  # D-435: the helpers moved from run_eval

    created, closed = [], []
    case = {"case_id": "test", "utterance": "Hello everyone!", "current_product_id": "cream_hydra_barrier",
            "category": "greeting", "needs": dict.fromkeys(routing.SPECIALISTS, False)}
    monkeypatch.setattr(routing, "get_settings", lambda: settings)
    monkeypatch.setattr(routing, "load_cases", lambda path: ([case], True))

    class FakeRouter:
        def __init__(self, name):
            assert name == selected
            created.append(name)
            self.name = name

        async def warm_up(self):
            return None, 0, "ok"

        async def route(self, state):
            return dict.fromkeys(routing.SPECIALISTS, 0.0), 2, "ok"

        async def aclose(self):
            closed.append(self.name)

    class FakeClient(FakeRouter):
        def __init__(self):
            super().__init__("llm")
            self._settings = settings
            self.fast = SimpleNamespace(model="mock-fast", thinking_level="MINIMAL")
            self.backend = SimpleNamespace(warm_up=self.warm_backend)

        async def warm_backend(self, model, timeout):
            return None

        async def call(self, request):
            output = routing.RouterOutput(compliance=False, facts=False, context=False, reason="greeting")
            return SimpleNamespace(output=output, status="ok", latency_ms=2)

    monkeypatch.setattr(jev_router, "JevRouter", lambda: FakeRouter("jev"))
    monkeypatch.setattr(gemini_router, "GeminiRouter", lambda: FakeRouter("gemini_purpose"))
    monkeypatch.setattr(eval_common, "make_client", lambda record: (FakeClient(), None))

    def threshold():
        assert selected == "jev", "excluded Jev configuration must not be read"
        return 0

    monkeypatch.setattr(jev_router, "get_threshold", threshold)
    monkeypatch.setenv("JEV_THRESHOLD", "invalid")
    report = await routing.run(1, 1, [selected])
    assert created == ([] if selected == "regex" else [selected])
    assert closed == created
    assert report["routers"] == [selected]
    assert report["summary"][selected]["samples"] == 1
    if selected == "gemini_purpose":
        assert not any(report["raw"][0]["route"].values())
        assert report["deadlines_ms"] == {"gemini_purpose": 1500}
        assert "gemini_purpose: 1500 ms" in routing.markdown(report)
        assert "deadline 300 ms" not in routing.markdown(report)
