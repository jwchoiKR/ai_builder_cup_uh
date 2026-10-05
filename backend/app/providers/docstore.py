"""Whole-file document store for design arms F1 and F2 (D-192): one product sheet or one rule set per file.

Files are named `products/<product_id>.md` and `rules/<market>/<category>.md`. This local store builds them from the
loaded pack (the data/ copies, already priced for the market), so the text is what the other arms read too.
"""
from __future__ import annotations

from ..logic.catalog import Catalog


class LocalDocStore:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    @property
    def market(self) -> tuple[str, str]:
        m = self.catalog.pack.market
        return (m.market, m.category) if m is not None else ("default", "cosmetics")

    def list_documents(self) -> list[dict]:
        market, category = self.market
        return [{"path": f"products/{p.product_id}.md", "product_id": p.product_id, "name": p.name}
                for p in self.catalog.products] + [
            {"path": f"rules/{market}/{category}.md", "market": market, "category": category}]

    def get_product(self, product_id: str) -> str | None:
        if product_id not in {p.product_id for p in self.catalog.products}:
            return None
        out = [f"# {self.catalog.get_product(product_id).name}"]
        section = None
        for p in self.catalog.pack.passages:
            if p.product_id != product_id:
                continue
            if p.section != section:
                section = p.section
                out.append(f"\n## {section}")
            out.append(p.text)
        return "\n".join(out) + "\n"

    def get_rules(self, market: str, category: str) -> str | None:
        if (market.lower(), category.lower()) != tuple(x.lower() for x in self.market):
            return None
        out = [f"# Advertising rules: {market} {category}"]
        for r in self.catalog.pack.rules.rules:
            out.append(f"\n## {r.rule_id}: {r.title} ({r.severity})\n{r.description}")
            if r.unacceptable_examples:
                out.append("Not acceptable: " + " | ".join(r.unacceptable_examples))
        return "\n".join(out) + "\n"
