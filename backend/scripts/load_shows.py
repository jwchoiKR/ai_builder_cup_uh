"""How many live shows can one server carry? Load eval against a running server (planning/eval, 10/6).

Each show: a session from an onboarded release, host lines injected every LINE_SEC (one in three is a line any market pack
flags, e.g. a cure claim), scripted viewer comments at COMMENTS_PER_MIN with one 5x burst minute, and an operator SSE stream.
Measured per level of N parallel shows: alert latency (transcript POST -> alert.created on SSE), alerts missing after 10 s,
HTTP errors, published replies. Pass for a level: alert p95 <= 3.0 s, missing 0, errors <= 1%.

    uv run python scripts/load_shows.py --base http://localhost:8080 --releases rel_a,rel_b --levels 1,3,5,10 --minutes 3
The server needs DEMO_TOOLS_ENABLED (transcript and comment injection). Output: JSON per level on stdout and --out.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from pathlib import Path

import httpx

RISKY = ["Honestly this cures eczema in a week, no doctor needed.", "It is clinically proven to heal acne for good.",
         "This treats diabetes, you can stop your medicine.", "It works better than any prescription cream on the market."]
SAFE = ["Thanks for joining everyone, welcome to the live.", "Let me show you the packaging up close.",
        "Drop your questions in the chat, we read them all.", "I use it every morning before work.",
        "Let's look at the texture on my hand.", "Stay till the end for the offer details."]
COMMENTS = ["how much is it?", "is it suitable for kids?", "what is the size?", "can I use it every day?",
            "where is it made?", "is there any discount now?", "love this!", "hi from Singapore"]


def p(xs: list[float], q: float) -> float | None:
    return round(sorted(xs)[min(len(xs) - 1, int(q * len(xs)))], 2) if xs else None


async def show(cl: httpx.AsyncClient, base: str, release: str, secs: float, a: argparse.Namespace, st: dict) -> None:
    try:
        r = await cl.post(f"{base}/api/sessions", json={"release_id": release}); r.raise_for_status()
        sid = r.json()["id"]
        (await cl.post(f"{base}/api/sessions/{sid}/start")).raise_for_status()
    except Exception as e:  # noqa: BLE001
        st["errors"] += 1; st["err_kinds"].append(f"create: {type(e).__name__}"); return
    sent: dict[str, float] = {}
    got: dict[str, float] = {}

    async def listen() -> None:
        try:
            async with cl.stream("GET", f"{base}/api/sessions/{sid}/events", params={"role": "operator"}, timeout=None) as resp:
                ev = None
                async for line in resp.aiter_lines():
                    if line.startswith("event: "):
                        ev = line[7:]
                    elif line.startswith("data: ") and ev == "alert.created":
                        tid = json.loads(line[6:]).get("transcript_id")
                        if tid and tid not in got:
                            got[tid] = time.monotonic()
                    elif line.startswith("data: ") and ev == "message.published":
                        st["replies"] += 1
        except Exception:  # noqa: BLE001  (cancelled at the end, or the stream dropped)
            pass

    lt = asyncio.create_task(listen())
    await asyncio.sleep(1.0)
    end = time.monotonic() + secs
    k = 0

    async def comments() -> None:
        burst_at = secs * 0.5
        t0 = time.monotonic()
        while time.monotonic() < end:
            rate = a.comments_per_min * (5 if burst_at <= time.monotonic() - t0 < burst_at + 60 else 1)
            await asyncio.sleep(60.0 / rate * random.uniform(0.5, 1.5))
            try:
                r = await cl.post(f"{base}/api/sessions/{sid}/demo/comments",
                                  json={"author": f"v{random.randint(1, 999)}", "text": random.choice(COMMENTS)})
                st["calls"] += 1
                if r.status_code >= 400 and r.status_code != 429:  # 429 = the app's own rate limit, by design
                    st["errors"] += 1; st["err_kinds"].append(f"comment {r.status_code}")
            except Exception as e:  # noqa: BLE001
                st["calls"] += 1; st["errors"] += 1; st["err_kinds"].append(f"comment {type(e).__name__}")

    ct = asyncio.create_task(comments())
    while time.monotonic() < end:
        risky = k % 3 == 1
        text = random.choice(RISKY if risky else SAFE)
        t = time.monotonic()
        try:
            r = await cl.post(f"{base}/api/sessions/{sid}/transcripts", json={"text": text})
            st["calls"] += 1
            if r.status_code >= 400:
                st["errors"] += 1; st["err_kinds"].append(f"line {r.status_code}")
            elif risky:
                sent[r.json()["id"]] = t
        except Exception as e:  # noqa: BLE001
            st["calls"] += 1; st["errors"] += 1; st["err_kinds"].append(f"line {type(e).__name__}")
        k += 1
        await asyncio.sleep(a.line_sec)
    await ct
    await asyncio.sleep(10.0)  # late alerts still count; after 10 s an alert is missing
    lt.cancel()
    for tid, t in sent.items():
        if tid in got:
            st["lat"].append(got[tid] - t)
        else:
            st["missing"] += 1
    st["risky"] += len(sent)
    try:
        await cl.post(f"{base}/api/sessions/{sid}/end")
    except Exception:  # noqa: BLE001
        pass


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://localhost:8080")
    ap.add_argument("--releases", required=True, help="comma-separated release ids; shows cycle through them")
    ap.add_argument("--levels", default="1,3,5,10")
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--line-sec", type=float, default=6.0)
    ap.add_argument("--comments-per-min", type=float, default=30.0)
    ap.add_argument("--token", default=None, help="IAP or bearer token for a deployed service")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    rel = a.releases.split(",")
    headers = {"Authorization": f"Bearer {a.token}"} if a.token else {}
    results = []
    async with httpx.AsyncClient(headers=headers, timeout=30.0, limits=httpx.Limits(max_connections=400)) as cl:
        for n in [int(x) for x in a.levels.split(",")]:
            st = {"lat": [], "missing": 0, "risky": 0, "errors": 0, "calls": 0, "replies": 0, "err_kinds": []}
            t0 = time.time()
            await asyncio.gather(*(show(cl, a.base, rel[i % len(rel)], a.minutes * 60, a, st) for i in range(n)))
            res = {"shows": n, "minutes": a.minutes, "risky_lines": st["risky"], "alert_p50_s": p(st["lat"], 0.5),
                   "alert_p95_s": p(st["lat"], 0.95), "alert_max_s": round(max(st["lat"]), 2) if st["lat"] else None,
                   "missing": st["missing"], "calls": st["calls"], "errors": st["errors"],
                   "error_rate": round(st["errors"] / max(1, st["calls"]), 4), "replies": st["replies"],
                   "err_kinds": sorted(set(st["err_kinds"]))[:8], "started": time.strftime("%H:%M:%S", time.localtime(t0))}
            res["pass"] = bool(st["lat"]) and res["alert_p95_s"] <= 3.0 and res["missing"] == 0 and res["error_rate"] <= 0.01
            print(json.dumps(res), flush=True)
            results.append(res)
    if a.out:
        a.out.write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    print("statistics:", "max passing level", max([r["shows"] for r in results if r["pass"]], default=0),
          "| median p95", statistics.median([r["alert_p95_s"] for r in results if r["alert_p95_s"]] or [0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
