"""The demo as onboarded releases (D-278): `data/demo_release` holds the demo products' releases, briefs, brand pack
and stored files, made once by the real onboarding and frozen. The demo tools copy them into ONBOARDING_DIR (and so to
the bucket) when a demo show starts; a release show never reads anything else of the demo."""
from __future__ import annotations

import json
import shutil

from .storage import persisted


def is_demo_show(settings, release_ids) -> bool:
    """D-375: the session is the demo show (its releases are the demo's), so the demo feed and bursts apply."""
    show = settings.data_path / "demo_release" / "show.json"
    return bool(release_ids) and show.is_file() and (
        list(release_ids) == json.loads(show.read_text(encoding="utf-8"))["release_ids"])


def demo_release_ids(ctx) -> list[str]:
    src = ctx.settings.data_path / "demo_release"
    root = ctx.settings.onboarding_path
    for f in sorted(p for p in src.rglob("*") if p.is_file() and p.name != "show.json"):
        dst = root / f.relative_to(src)
        if not dst.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
            persisted(dst, create_only=True)
    return json.loads((src / "show.json").read_text(encoding="utf-8"))["release_ids"]
