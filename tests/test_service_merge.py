from sqlalchemy import select

from app.db import session_factory
from app.models import Availability, Service, UserSub
from app.seed import merge_duplicate_services
from tests.conftest import run_sync_now


def test_duplicate_provider_folds_into_seeded_service(client):
    """Regression: TMDB's 'Tubi TV' must not shadow the seeded 'Tubi' — a tick
    on the checklist has to match the availability rows."""
    run_sync_now()
    with session_factory()() as db:
        tubi = db.scalar(select(Service).where(Service.key == "tubi"))
        # Simulate the pre-fix state: an auto-added duplicate holding availability.
        dup = Service(key="tubi_tv", name="Tubi TV", kind="video", tier=3,
                      auto_added=True, tmdb_provider_id=73, capabilities={})
        db.add(dup)
        db.flush()
        db.add(UserSub(service_id=dup.id, subscribed=False))
        avail = db.scalar(select(Availability))
        db.add(Availability(media_item_id=avail.media_item_id, service_id=dup.id,
                            country="US", offer_type="ads", tmdb_link=None))
        db.commit()
        dup_id, tubi_id = dup.id, tubi.id

        merge_duplicate_services(db)

        assert db.get(Service, dup_id) is None
        moved = db.scalar(select(Availability).where(Availability.service_id == tubi_id,
                                                     Availability.offer_type == "ads"))
        assert moved is not None
        assert db.scalar(select(Service).where(Service.key == "tubi")).tmdb_provider_id == 73
