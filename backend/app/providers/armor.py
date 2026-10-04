"""Model Armor screening of viewer comments (D-125). Order: deterministic prefilter, then Armor on every
remaining comment, then triage; an answer-cache hit never skips it.

Verdicts: "pass", "blocked" (prompt injection, jailbreak or malicious URL found), "unscreened" (Armor
failed or was too slow). The template holds the filters (PI/jailbreak MEDIUM_AND_ABOVE, malicious URL,
RAI HIGH); this client only asks it.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal, Protocol

from ..config import Settings

log = logging.getLogger(__name__)

Verdict = Literal["pass", "blocked", "unscreened"]


class Armor(Protocol):
    async def screen(self, text: str) -> tuple[Verdict, str]: ...
    async def warm_up(self) -> None: ...


class NoArmor:
    """Model Armor switched off (`MODEL_ARMOR_ENABLED=false`): every comment passes."""

    async def screen(self, text: str) -> tuple[Verdict, str]:
        return "pass", "armor off"

    async def warm_up(self) -> None:
        return None


class ModelArmorClient:
    """sanitizeUserPrompt on the regional Model Armor endpoint, with the service account's credentials."""

    def __init__(self, project: str, location: str, template: str) -> None:
        import httpx

        self._url = (f"https://modelarmor.{location}.rep.googleapis.com/v1/projects/{project}/locations/{location}"
                     f"/templates/{template}:sanitizeUserPrompt")
        self._http = httpx.AsyncClient()
        self._creds = None

    async def _token(self) -> str:
        import google.auth
        from google.auth.transport.requests import Request

        if self._creds is None:  # sync lookup (metadata server on Cloud Run): off the event loop
            self._creds, _ = await asyncio.to_thread(
                google.auth.default, scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not self._creds.valid:
            await asyncio.to_thread(self._creds.refresh, Request())
        return self._creds.token

    async def screen(self, text: str) -> tuple[Verdict, str]:
        r = await self._http.post(self._url, json={"userPromptData": {"text": text}},
                                  headers={"Authorization": f"Bearer {await self._token()}"})
        r.raise_for_status()
        result = r.json().get("sanitizationResult", {})
        if result.get("filterMatchState") == "MATCH_FOUND":
            # "NO_MATCH_FOUND" contains "MATCH_FOUND": compare the whole matchState value
            found = [name for name, f in (result.get("filterResults") or {}).items()
                     if '"matchState": "MATCH_FOUND"' in json.dumps(f)]
            return "blocked", ", ".join(found) or "match found"
        return "pass", "no match"

    async def warm_up(self) -> None:
        """At startup: the first call fetches a token and opens the connection, which can take longer than
        MODEL_ARMOR_TIMEOUT_MS and would leave the first viewer comment unscreened (seen on Cloud Run)."""
        try:
            await self.screen("warm up")
        except Exception as e:  # noqa: BLE001
            log.warning("Model Armor warm-up failed: %s", e)


def make_armor(settings: Settings) -> Armor:
    if not settings.MODEL_ARMOR_ENABLED:
        return NoArmor()
    return ModelArmorClient(settings.GCP_PROJECT, settings.MODEL_ARMOR_LOCATION, settings.MODEL_ARMOR_TEMPLATE)


async def screen(armor: Armor, text: str, timeout_ms: int) -> tuple[Verdict, str]:
    """Fail policy: an error or a timeout leaves the comment unscreened (shown, never answered)."""
    try:
        return await asyncio.wait_for(armor.screen(text), timeout=timeout_ms / 1000)
    except Exception as e:  # noqa: BLE001
        log.warning("Model Armor unavailable, comment unscreened: %s", e)
        return "unscreened", type(e).__name__
