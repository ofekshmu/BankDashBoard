from datetime import date

from src_utils.plant_logic import (
    materialize_rows, plant_status, season_key, timeline_window, build_summary,
)


def _plant(**kw):
    p = {'id': 1, 'name': 'פיקוס', 'irrigation_mode': 'manual', 'interval_days': 3,
         'auto_time': None, 'created_at': date(2026, 10, 1), 'season_ack': None}
    p.update(kw)
    return p


def test_materialize_from_creation_when_no_rows():
    rows = materialize_rows(_plant(), None, date(2026, 10, 3), set())
    assert [r['day'] for r in rows] == [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)]
    assert all(r['soil_status'] is None and not r['watered'] and not r['auto_confirmed'] for r in rows)
    assert all(r['plant_id'] == 1 for r in rows)


def test_materialize_fills_only_gap_after_last_day():
    rows = materialize_rows(_plant(), date(2026, 10, 2), date(2026, 10, 4), set())
    assert [r['day'] for r in rows] == [date(2026, 10, 3), date(2026, 10, 4)]


def test_materialize_nothing_when_up_to_date():
    assert materialize_rows(_plant(), date(2026, 10, 3), date(2026, 10, 3), set()) == []


def test_materialize_marks_watered_days():
    rows = materialize_rows(_plant(), None, date(2026, 10, 3), {date(2026, 10, 2)})
    assert [r['watered'] for r in rows] == [False, True, False]


def test_auto_expected_every_interval_from_creation():
    p = _plant(irrigation_mode='auto', interval_days=2, auto_time='07:00')
    rows = materialize_rows(p, None, date(2026, 10, 6), set())
    assert [r['day'].day for r in rows if r['auto_expected']] == [3, 5]


def test_auto_expected_reanchors_on_last_water():
    p = _plant(irrigation_mode='auto', interval_days=3, auto_time='07:00')
    rows = materialize_rows(p, None, date(2026, 10, 8), {date(2026, 10, 2)})
    # anchor is the creation day until the 2nd is watered, then the 2nd → 5th and 8th
    assert [r['day'].day for r in rows if r['auto_expected']] == [5, 8]


def test_manual_plants_never_auto_expected():
    rows = materialize_rows(_plant(interval_days=1), None, date(2026, 10, 5), set())
    assert not any(r['auto_expected'] for r in rows)


def test_plant_status():
    p = _plant(interval_days=3)
    assert plant_status(p, date(2026, 10, 10), date(2026, 10, 12)) == (2, 'ok')
    assert plant_status(p, date(2026, 10, 10), date(2026, 10, 13)) == (3, 'due')
    assert plant_status(p, date(2026, 10, 10), date(2026, 10, 15)) == (5, 'overdue')
    assert plant_status(p, None, date(2026, 10, 4)) == (3, 'due')  # never watered → counts from creation


def test_season_key():
    assert season_key(date(2026, 7, 1)) == '2026-summer'
    assert season_key(date(2026, 12, 5)) == '2027-winter'
    assert season_key(date(2027, 2, 28)) == '2027-winter'
    assert season_key(date(2026, 10, 3)) is None


def test_timeline_window_is_14_days_ending_today():
    w = timeline_window(date(2026, 10, 14))
    assert len(w) == 14 and w[0] == date(2026, 10, 1) and w[-1] == date(2026, 10, 14)


def _unconfirmed(day):
    return {'day': day, 'auto_expected': True, 'auto_confirmed': False, 'watered': False}


def test_build_summary_counts():
    plants = [{'id': 1, 'status': 'due', 'irrigation_mode': 'manual'},
              {'id': 2, 'status': 'overdue', 'irrigation_mode': 'manual'},
              {'id': 3, 'status': 'auto', 'irrigation_mode': 'auto'}]
    days = {3: [
        _unconfirmed(date(2026, 10, 2)),
        {'day': date(2026, 10, 3), 'auto_expected': True, 'auto_confirmed': True, 'watered': True},
    ]}
    assert build_summary(plants, days, date(2026, 10, 3)) == {
        'due_today': 1, 'overdue': 1, 'auto_pending_confirm': 1}


def test_build_summary_pending_counts_only_auto_plants():
    plants = [{'id': 1, 'status': 'ok', 'irrigation_mode': 'manual'},
              {'id': 2, 'status': 'auto', 'irrigation_mode': 'auto'}]
    days = {1: [_unconfirmed(date(2026, 10, 2))],            # plant switched to manual since
            2: [_unconfirmed(date(2026, 10, 3))],
            99: [_unconfirmed(date(2026, 10, 3))]}           # plant absent from the list
    assert build_summary(plants, days, date(2026, 10, 3))['auto_pending_confirm'] == 1
