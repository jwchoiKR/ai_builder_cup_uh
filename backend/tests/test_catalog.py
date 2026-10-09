from __future__ import annotations

import json

import pytest

from app.logic.catalog import Catalog, DataPack, DataPackError

CREAM, AMPOULE = "cream_hydra_barrier", "ampoule_deep_hydration"


def test_catalog_unknown_product(catalog):
    with pytest.raises(KeyError):
        catalog.get_product("nope")
    assert isinstance(catalog, Catalog)


def _copy(tmp_path, settings):
    import shutil

    data = tmp_path / "data"
    shutil.copytree(settings.data_path, data)
    return data
