"""Build local passages from product sheet PDFs (DEV_SPEC §9.2).

Splits each PDF by the section headings "1. Product overview" ... "8. Frequently asked questions";
table rows, cautions, claim lists and FAQ items become separate passages with ids
`CODE#section-slug#item-slug`. For the shipped demo PDFs the shipped passages.jsonl is used as is;
this tool reproduces it exactly and builds passages for new sheets.

    uv run python scripts/build_local_index.py ../data/products/*.pdf            # print a summary
    uv run python scripts/build_local_index.py sheet.pdf --out passages.jsonl     # write JSONL
    uv run python scripts/build_local_index.py --check                            # compare with the shipped file
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.logic.catalog import DataPack  # noqa: E402
from app.pipelines.setup import parse_sheet_text, pdf_text, product_code  # noqa: E402


def build(paths: list[Path]) -> list[dict]:
    pack = DataPack.load(get_settings().data_path)
    by_code = {p.code: p for p in pack.products.products}
    rows: list[dict] = []
    for path in paths:
        text, _ = pdf_text(path.read_bytes())
        code = product_code(text)
        product = by_code.get(code or "")
        if product is None:
            raise SystemExit(f"{path.name}: no product with code {code}")
        rows += [p.model_dump(exclude={"score"}) for p in
                 parse_sheet_text(text, doc=path.name, product_id=product.product_id, code=product.code)]
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="*", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--check", action="store_true", help="rebuild the shipped PDFs and diff with passages.jsonl")
    args = ap.parse_args()
    data_dir = get_settings().data_path
    if args.check:
        shipped = {json.loads(ln)["passage_id"]: json.loads(ln) for ln in
                   (data_dir / "products" / "passages.jsonl").read_text("utf-8").splitlines() if ln.strip()}
        built = {r["passage_id"]: r for r in build(sorted((data_dir / "products").glob("*.pdf")))}
        missing, extra = sorted(set(shipped) - set(built)), sorted(set(built) - set(shipped))
        changed = sorted(k for k in set(shipped) & set(built) if shipped[k] != built[k])
        print(f"shipped {len(shipped)} · built {len(built)} · missing {missing} · extra {extra} · changed {changed}")
        return 0 if not (missing or extra or changed) else 1
    rows = build(args.pdfs)
    if args.out:
        args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8",
                            newline="\n")
    for r in rows:
        print(f"{r['passage_id']}: {r['text'][:80]}")
    print(f"{len(rows)} passages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
