"""Question group score (DEV_SPEC §8.11). Weights come from intents.json."""
from __future__ import annotations

from ..models.data import Intent, RankingWeights
from ..models.session import QuestionGroup

# Operator desk order (§12.4.7): status bucket, then score.
STATUS_BUCKETS = {
    "needs_review": 0, "on_host": 1, "ready": 2, "new": 3, "composing": 3,
    "auto_answered": 4, "answered": 5, "rejected": 6, "closed": 6,
}


def score(g: QuestionGroup, intent: Intent, w: RankingWeights, on_air_product_id: str | None, now: int) -> float:
    wait_min = max(0.0, (now - g.first_at) / 60_000)
    return round(
        w.W_VIEWERS * len(g.unique_author_ids)
        + w.W_PURCHASE_IMPACT * intent.purchase_impact
        + w.CURRENT_PRODUCT_BONUS * (1 if g.product_id is not None and g.product_id == on_air_product_id else 0)
        + w.WAIT_TIEBREAK_PER_MIN * min(wait_min, w.WAIT_TIEBREAK_MAX_MIN),
        4,
    )


def desk_bucket(g: QuestionGroup) -> int:
    return STATUS_BUCKETS["on_host"] if g.host_slot == "on_host" else STATUS_BUCKETS.get(g.status, 9)
