"""Prompter point coverage (DEV_SPEC §8.7.1). Covered points are never removed."""
from __future__ import annotations

from collections.abc import Sequence

from ..models.data import PrompterPoint
from ..models.session import Segment, Session
from .catalog import Catalog


def points_of(catalog: Catalog, product_id: str, overrides: dict[str, list[PrompterPoint]] | None = None) -> list[PrompterPoint]:
    return (overrides or {}).get(product_id) or catalog.get_product(product_id).prompter_points


def apply_coverage(
    covered_ids: Sequence[str], segment: Segment, session: Session, catalog: Catalog,
) -> tuple[list[str], dict[str, list[str]]]:
    """Add covered points: on-air product -> segment; next product -> session.pre_covered.
    Returns (newly covered on air, newly pre-covered by product)."""
    on_air = segment.product_id
    nxt = catalog.next_product(on_air)
    on_air_ids = {p.point_id for p in points_of(catalog, on_air)}
    next_ids = {p.point_id for p in points_of(catalog, nxt)} if nxt else set()
    added_on_air: list[str] = []
    added_next: dict[str, list[str]] = {}
    for pid in covered_ids:
        if pid in on_air_ids and pid not in segment.covered_point_ids:
            segment.covered_point_ids.append(pid)
            added_on_air.append(pid)
        elif pid in next_ids:
            pre = session.pre_covered.setdefault(nxt, [])
            if pid not in pre:
                pre.append(pid)
                added_next.setdefault(nxt, []).append(pid)
    return added_on_air, added_next


def required_ids(catalog: Catalog, product_id: str) -> list[str]:
    return list(catalog.runsheet_item(product_id).required_point_ids)


def missing_required(catalog: Catalog, segment: Segment) -> list[str]:
    return [p for p in required_ids(catalog, segment.product_id) if p not in segment.covered_point_ids]


def prompter_view(catalog: Catalog, segment: Segment | None) -> dict:
    """Payload of `prompter.updated` and the /state `prompter` block."""
    if segment is None:
        return {"product_id": None, "segment_id": None, "next_product_id": catalog.next_product(None), "points": [],
                "covered_point_ids": [], "required_total": 0, "required_covered": 0}
    required = required_ids(catalog, segment.product_id)
    covered = list(segment.covered_point_ids)
    return {
        "product_id": segment.product_id,
        "segment_id": segment.segment_id,
        "next_product_id": catalog.next_product(segment.product_id),
        "points": [{"point_id": p.point_id, "text": p.text, "required": p.point_id in required,
                    "covered": p.point_id in covered} for p in points_of(catalog, segment.product_id)],
        "covered_point_ids": covered,
        "required_total": len(required),
        "required_covered": sum(1 for p in required if p in covered),
    }
