"""Adding/removing a cocat event while the room is unavailable (offline or the
JWT expired, so ``Client.db`` returns ``None``) must NOT crash. Regression for:

    AttributeError: 'NoneType' object has no attribute 'get_catalogue'

raised from ``Room.get_catalogue`` -> ``self._client.db.get_catalogue(name)``
when ``add_event`` is triggered from a span. Instead the operation no-ops with a
clear warning.
"""
from datetime import datetime, timezone

import pytest

pytest.importorskip("cocat")


class _NoDBClient:
    """Stand-in for a Client whose db property is None (not logged in / not joined)."""
    db = None


def test_room_get_catalogue_returns_none_when_db_unavailable(qapp):
    from SciQLop.plugins.collaborative_catalogs.room import Room
    room = Room(room_id="t")
    room._client = _NoDBClient()
    assert room.get_catalogue("any") is None
    assert room.catalogues == []


def test_add_event_noops_and_warns_when_room_db_unavailable(qapp, monkeypatch):
    from SciQLop.plugins.collaborative_catalogs import cocat_provider as cp
    from SciQLop.plugins.collaborative_catalogs.room import Room
    from SciQLop.components.catalogs import Catalog, CatalogEvent

    provider = cp.CocatCatalogProvider()
    room = Room(room_id="r1")
    room._client = _NoDBClient()
    provider._rooms["r1"] = room

    cat = Catalog(uuid="u", name="c", provider=provider, path=["r1"])
    event = CatalogEvent(uuid="e", start=datetime(2020, 1, 1, tzinfo=timezone.utc),
                         stop=datetime(2020, 1, 1, 1, tzinfo=timezone.utc))

    warnings = []
    monkeypatch.setattr(cp.log, "warning", lambda *a, **k: warnings.append(a))

    provider.add_event(cat, event)      # must not raise
    provider.remove_event(cat, event)   # must not raise
    assert len(warnings) == 2, "expected a warning for each unavailable-room operation"
