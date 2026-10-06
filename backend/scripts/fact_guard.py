"""D-280: the fact fixes' guard on saved real model outputs (no model calls).

Re-applies the fact post-validation to the raw fact outputs saved by eval_agents (docs/eval/agents-*.json and
holdout-*.json, on the demo test pack) with each fix switched on, and scores the result against the cases' labels:
a line labelled "contradicted" should alert, any other line should not. It prints, per fix, caught, missed and false
alerts, and the code drops by reason, so a fix that loses a correct drop shows up as a new false alert.

    uv run python scripts/fact_guard.py
"""
from __future__ import annotations

import asyncio
import collections
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.conftest import test_data_dir  # noqa: E402  (the demo pack the saved outputs were made on)

os.environ["DATA_DIR"] = str(test_data_dir())
sys.path.insert(0, str(ROOT / "scripts"))

from eval_agents import case_switch_promo, gather_fact_passages  # noqa: E402

from app.agents.fact_checker import DROPS, post_validate  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.logic.catalog import Catalog, DataPack  # noqa: E402
from app.models.agent_io import FactCheckOutput  # noqa: E402
from app.providers.retriever import LocalRetriever  # noqa: E402

RAW = [("agents-split3-prod.json", "utterance_cases.jsonl"), ("agents-split3-1005-v2.json", "utterance_cases.jsonl"),
       ("holdout-split3.json", "holdout_cases.jsonl"), ("holdout-split3-cache.json", "holdout_cases.jsonl")]
FIXES = ["", "F1", "F2", "F3", "F4", "F5", "R1", "F1,F2,F3,F4,F5,R1"]


async def main() -> None:
    settings = get_settings()
    pack = DataPack.load(settings.data_path)
    catalog, retriever = Catalog(pack), LocalRetriever(pack.passages)
    data = settings.data_path
    rows = []
    for raw_name, case_name in RAW:
        cases = {c["case_id"]: c for c in map(json.loads, (data / "eval" / case_name).read_text("utf-8").splitlines())
                 if c}
        for x in json.loads((ROOT.parent / "docs" / "eval" / raw_name).read_text(encoding="utf-8")):
            if x.get("facts_raw") is not None and x["id"] in cases:
                rows.append((cases[x["id"]], x["facts_raw"]))
    env: dict = {}
    prefetched: dict = {}
    for case, _ in rows:
        if case["case_id"] not in env:
            switch, promo = case_switch_promo(case, pack)
            env[case["case_id"]] = (await gather_fact_passages(
                retriever, catalog, prefetched, utterance=case["utterance"], on_air=case["current_product_id"],
                switch=switch, search_timeout_ms=10_000), promo)
    print(f"{len(rows)} saved fact outputs on {len(env)} lines")
    base_alerts = None
    for fixes in FIXES:
        score, drops, alerts = collections.Counter(), collections.Counter(), []
        for case, raw in rows:
            passages, promo = env[case["case_id"]]
            sink: list = []
            DROPS.set(sink)
            out = post_validate(FactCheckOutput.model_validate(raw), passages, catalog, promo, case["utterance"],
                                fixes=frozenset(x for x in fixes.split(",") if x))
            alert = any(c.verdict == "contradicted" for c in out.claims)
            alerts.append(alert)
            risky = case["expected"].get("fact") == "contradicted"
            score["caught" if risky and alert else "missed" if risky else "false" if alert else "quiet"] += 1
            drops.update(d["reason"].split(":")[0] for d in sink)
        changed = "" if base_alerts is None else f" · lines changed vs base {sum(a != b for a, b in zip(alerts, base_alerts))}"
        base_alerts = base_alerts or alerts
        print(f"{fixes or 'base':16} caught {score['caught']:3} missed {score['missed']:3} false {score['false']:3} "
              f"quiet {score['quiet']:3}{changed}")
        print("   drops:", dict(drops.most_common()))


if __name__ == "__main__":
    asyncio.run(main())
