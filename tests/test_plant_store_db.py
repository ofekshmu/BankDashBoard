"""Round-trip PlantStore against the real DATABASE_URL inside a rolled-back transaction.

Opt-in: set PLANT_DB_TESTS=1. Nothing is committed.
"""
import os
from datetime import date, datetime

import pytest

pytestmark = pytest.mark.skipif(os.getenv('PLANT_DB_TESTS') != '1',
                                reason='set PLANT_DB_TESTS=1 to run against DATABASE_URL')


@pytest.fixture
def store():
    from dotenv import load_dotenv
    load_dotenv()
    from database import DataBase
    from plant_store import PlantStore
    db = DataBase()
    s = PlantStore(db, autocommit=False)
    s.ensure()
    yield s
    db.connection.rollback()


def test_roundtrip(store):
    pid = store.add_plant({'name': '__plant_test__', 'plant_type': 'fern', 'color': '#1e9d8b',
                           'irrigation_mode': 'auto', 'interval_days': 2, 'auto_time': '07:00',
                           'created_at': date(2026, 10, 1)})
    p = store.get_plant(pid)
    assert p['plant_type'] == 'fern' and p['created_at'] == date(2026, 10, 1) and p['deleted_at'] is None

    blank = {'plant_id': pid, 'day': date(2026, 10, 1), 'soil_status': None, 'watered': False,
             'auto_expected': False, 'auto_confirmed': False}
    store.insert_days([blank])
    store.insert_days([dict(blank, soil_status='wet', watered=True)])  # conflict → ignored
    assert store.last_materialized_days([pid]) == {pid: date(2026, 10, 1)}

    store.upsert_day(pid, date(2026, 10, 1), soil_status='dry')
    store.upsert_day(pid, date(2026, 10, 2), watered=True)
    days = store.get_days([pid], date(2026, 10, 1), date(2026, 10, 2))[pid]
    assert [(r['soil_status'], r['watered']) for r in days] == [('dry', False), (None, True)]

    eid = store.add_event(pid, 'water', datetime(2026, 10, 2, 8, 30), 'manual', None)
    assert store.water_dates(pid) == [date(2026, 10, 2)]
    assert store.last_event_dates([pid], date(2026, 10, 3)) == {pid: {'water': date(2026, 10, 2)}}
    assert store.get_events([pid], date(2026, 10, 1), date(2026, 10, 3))[pid][0]['id'] == eid
    assert store.get_event(eid)['event_at'] == datetime(2026, 10, 2, 8, 30)

    store.update_plant(pid, {'interval_days': 4, 'season_ack': '2026-summer'})
    assert store.get_plant(pid)['interval_days'] == 4
    store.update_plant(pid, {'interval_changed_at': date(2026, 10, 2)})
    assert store.get_plant(pid)['interval_changed_at'] == date(2026, 10, 2)

    store.soft_delete_plant(pid)
    assert pid not in [x['id'] for x in store.list_plants()]
    assert pid in [x['id'] for x in store.list_plants(deleted=True)]
    store.restore_plant(pid)
    assert pid in [x['id'] for x in store.list_plants()]

    store.delete_event(eid)
    assert store.water_dates(pid) == [] and store.get_event(eid) is None
