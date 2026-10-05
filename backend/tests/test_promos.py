"""D-210: promo card texts from the live state."""
from __future__ import annotations


def test_d210_promo_cards_are_built_from_the_live_state(catalog):
    from app.logic.promos import promo_cue

    sale = catalog.pack.promos_by_id["promo_time_sale_10"]
    gift = catalog.pack.promos_by_id["promo_gift_pouch"]
    notice = catalog.pack.promos_by_id["promo_set_reminder"]
    text = promo_cue(sale, catalog, sale, ends_at=45_000, now=0)
    assert "45 s left" in text and "10 minutes" not in text and "S$32.40" in text and "S$55.80" in text
    assert promo_cue(gift, catalog, None, ends_at=150_000, now=0).endswith("3 min left.")
    assert promo_cue(notice, catalog, None, ends_at=60_000, now=0) == notice.viewer_text  # S$62 is the set price now
    assert promo_cue(notice, catalog, sale, ends_at=60_000, now=0) is None  # not during the time sale (S$55.80)
