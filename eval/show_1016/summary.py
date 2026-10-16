"""Rebuild the README's per-show numbers from agent_calls.json (one show on the deployed app, 10/16 23:24 KST, 36 host
lines spoken through Chirp 3): judge call times and the cost per line and per hour.

Prices: Gemini API list prices, paid tier, checked 10/17 (ai.google.dev/gemini-api/docs/pricing); Speech-to-Text
chirp_3 $0.016 per audio minute, checked 10/11. 600 lines an hour (10 a minute) is an assumption, not measured.
Run: python eval/show_1016/summary.py"""
import json
from pathlib import Path

PRICE = {  # USD per 1M tokens: input, cached input, output (thinking included)
    "gemini-3.5-flash-lite": (0.30, 0.03, 2.50),
    "gemini-3.8-flash": (0.75, 0.075, 3.75),  # doubles from 2027-01-01
}
JUDGES = ("compliance_judge", "context_judge", "prompter_judge", "fact_checker")
LINES_PER_HOUR = 600
STT_PER_HOUR = 0.016 * 60

calls = json.loads((Path(__file__).parent / "agent_calls.json").read_text(encoding="utf-8"))["calls"]


def cost(c):
    u = c["usage"] or {}
    inp, cached = u.get("prompt") or 0, u.get("cached") or 0
    out = (u.get("output") or 0) + (u.get("thoughts") or 0)
    pi, pc, po = PRICE[c["model"]]
    return ((inp - cached) * pi + cached * pc + out * po) / 1e6


def p95(xs):
    xs = sorted(xs)
    return xs[max(0, -(-95 * len(xs) // 100) - 1)]  # nearest rank


total_line = 0.0
print(f"{'judge':18} {'calls':>5} {'p50 s':>6} {'p95 s':>6} {'max s':>6} {'$/line':>8} {'$/hour':>7}")
for a in JUDGES:
    cs = [c for c in calls if c["agent"] == a]
    ok = [c["latency_ms"] for c in cs if c["status"] == "ok"]
    lines = len(cs)
    per_line = sum(cost(c) for c in cs) / lines
    total_line += per_line
    print(f"{a:18} {lines:5} {sorted(ok)[len(ok) // 2] / 1000:6.1f} {p95(ok) / 1000:6.1f} {max(ok) / 1000:6.1f} "
          f"{per_line:8.4f} {per_line * LINES_PER_HOUR:7.2f}")
print(f"judges per line ${total_line:.4f}; per hour ${total_line * LINES_PER_HOUR:.2f} + speech-to-text "
      f"${STT_PER_HOUR:.2f} = ${total_line * LINES_PER_HOUR + STT_PER_HOUR:.2f}")
