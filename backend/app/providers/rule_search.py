"""Design arm E (D-194): the compliance rules for one spoken line, retrieved from Vertex AI Search.

One long-lived client per process, warmed at session start. The search only picks rule ids; the rule text the judge
reads still comes from the pack. A failure or timeout returns None and the judge gets every rule (counted).
"""
from __future__ import annotations

import asyncio
import logging
import statistics
import time
from typing import Any

log = logging.getLogger(__name__)

STATS: dict[str, Any] = {"calls": 0, "failures": 0, "ms": [], "queries": []}


def summary() -> dict:
    ms = sorted(STATS["ms"])
    return {"calls": STATS["calls"], "failures": STATS["failures"],
            "p50_ms": statistics.median(ms) if ms else None,
            "p95_ms": ms[min(len(ms) - 1, int(len(ms) * 0.95))] if ms else None,
            "queries": STATS["queries"]}


class RuleSearch:
    def __init__(self, serving_config: str, quota_project: str, page_size: int, timeout_ms: int) -> None:
        self.url = f"https://discoveryengine.googleapis.com/v1/{serving_config}:search"
        self.quota_project = quota_project
        self.page_size = page_size
        self.timeout_ms = timeout_ms
        self._client = None
        self._creds = None

    async def _token(self) -> str:
        import google.auth
        import google.auth.transport.requests

        if self._creds is None:
            self._creds, _ = await asyncio.to_thread(
                google.auth.default, scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not self._creds.valid:
            await asyncio.to_thread(self._creds.refresh, google.auth.transport.requests.Request())
        return self._creds.token

    async def warm_up(self) -> None:
        await self.search("warm up", "SG", record=False)

    async def search(self, text: str, market: str, *, record: bool = True) -> list[str] | None:
        import httpx

        if self._client is None:
            self._client = httpx.AsyncClient(http2=False)
        t0 = time.perf_counter()
        try:
            r = await asyncio.wait_for(self._client.post(self.url, headers={
                "Authorization": f"Bearer {await self._token()}", "x-goog-user-project": self.quota_project,
            }, json={
                "query": text, "pageSize": self.page_size, "filter": f'market: ANY("{market}")',
                "relevanceThreshold": "LOWEST", "queryExpansionSpec": {"condition": "DISABLED"},
                "spellCorrectionSpec": {"mode": "SUGGESTION_ONLY"},
            }), timeout=self.timeout_ms / 1000)
            r.raise_for_status()
            ids = [x["document"].get("structData", {}).get("rule_id") for x in r.json().get("results", [])]
            ids = [i for i in ids if i]
        except Exception as e:  # noqa: BLE001 - any failure means every rule
            ids = None
            log.warning("rule search failed (%s: %s); the judge gets every rule", type(e).__name__, e)
        ms = round((time.perf_counter() - t0) * 1000)
        if record:
            STATS["calls"] += 1
            STATS["failures"] += ids is None
            STATS["ms"].append(ms)
            STATS["queries"].append({"text": text, "rule_ids": ids, "ms": ms})
            log.info("rule search %d ms for %r: %s", ms, text[:80], ids)
        return ids


_INSTANCE: RuleSearch | None = None


def for_settings(settings) -> RuleSearch | None:
    """The process's one client; None when the LLM is not Vertex (tests, mock runs: every rule)."""
    global _INSTANCE
    if settings.LLM_PROVIDER != "vertex":
        return None
    if _INSTANCE is None:
        _INSTANCE = RuleSearch(settings.RULE_SEARCH_SERVING_CONFIG, settings.GCP_PROJECT,
                               settings.RULE_SEARCH_PAGE_SIZE, settings.RULE_SEARCH_TIMEOUT_MS)
    return _INSTANCE
