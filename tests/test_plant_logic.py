from datetime import date

from src_utils.plant_logic import (
    materialize_rows, plant_status, season_key, timeline_window, build_summary, is_expected_on,
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


def _auto_watered(day):
    return {'day': day, 'auto_expected': True, 'auto_confirmed': True, 'watered': True}


def test_build_summary_counts():
    plants = [{'id': 1, 'status': 'due', 'irrigation_mode': 'manual'},
              {'id': 2, 'status': 'overdue', 'irrigation_mode': 'manual'},
              {'id': 3, 'status': 'auto', 'irrigation_mode': 'auto'},
              {'id': 4, 'status': 'auto', 'irrigation_mode': 'auto'}]
    days = {3: [_auto_watered(date(2026, 10, 2)), _auto_watered(date(2026, 10, 3))],
            4: [_auto_watered(date(2026, 10, 2)),                       # yesterday only
                {'day': date(2026, 10, 3), 'auto_expected': False, 'auto_confirmed': False, 'watered': False}]}
    assert build_summary(plants, days, date(2026, 10, 3)) == {'due_today': 1, 'overdue': 1, 'auto_today': 1}


def test_build_summary_auto_today_counts_only_auto_plants():
    plants = [{'id': 1, 'status': 'ok', 'irrigation_mode': 'manual'},
              {'id': 2, 'status': 'auto', 'irrigation_mode': 'auto'}]
    days = {1: [_auto_watered(date(2026, 10, 3))],             # plant switched to manual since
            2: [_auto_watered(date(2026, 10, 3))],
            99: [_auto_watered(date(2026, 10, 3))]}            # plant absent from the list
    assert build_summary(plants, days, date(2026, 10, 3))['auto_today'] == 1


# ── Irrigation config schedules ────────────────────────────────────────────
def test_weekday_schedule_expects_selected_weekdays_only():
    # 2026-10-04 is a Sunday (0); weekdays use Sun=0 … Sat=6
    p = _plant(irrigation_mode='auto', created_at=date(2026, 10, 4))
    sched = {'style': 'weekdays', 'weekdays': [0, 2], 'interval_days': None, 'time': '07:00'}
    rows = materialize_rows(p, None, date(2026, 10, 17), set(), sched)
    assert [r['day'].day for r in rows if r['auto_expected']] == [4, 6, 11, 13]


def test_interval_schedule_from_config_overrides_plant_interval():
    p = _plant(irrigation_mode='auto', interval_days=3)
    sched = {'style': 'interval', 'interval_days': 2, 'weekdays': None, 'time': '07:00'}
    rows = materialize_rows(p, None, date(2026, 10, 6), set(), sched)
    assert [r['day'].day for r in rows if r['auto_expected']] == [3, 5]


def test_schedule_ignored_for_manual_plants():
    sched = {'style': 'weekdays', 'weekdays': list(range(7)), 'interval_days': None, 'time': '07:00'}
    rows = materialize_rows(_plant(), None, date(2026, 10, 5), set(), sched)
    assert not any(r['auto_expected'] for r in rows)


# ── Config start date: a fixed rhythm like a real timer ────────────────────
def test_interval_schedule_with_start_date_follows_fixed_rhythm():
    p = _plant(irrigation_mode='auto', created_at=date(2026, 10, 1))
    sched = {'style': 'interval', 'interval_days': 3, 'weekdays': None, 'time': '07:00',
             'start_date': date(2026, 9, 29)}            # started before the plant was added
    rows = materialize_rows(p, None, date(2026, 10, 10), {date(2026, 10, 3)}, sched)
    # 9/29 + 3k → 10/2, 10/5, 10/8 — a manual watering on 10/3 does not shift it
    assert [r['day'].day for r in rows if r['auto_expected']] == [2, 5, 8]


def test_start_date_in_future_means_nothing_expected_before_it():
    p = _plant(irrigation_mode='auto')
    sched = {'style': 'interval', 'interval_days': 2, 'weekdays': None, 'time': '07:00',
             'start_date': date(2026, 10, 5)}
    rows = materialize_rows(p, None, date(2026, 10, 8), set(), sched)
    assert [r['day'].day for r in rows if r['auto_expected']] == [5, 7]


def test_is_expected_helper_matches_materialize():
    sched = {'style': 'weekdays', 'weekdays': [3], 'interval_days': None, 'time': '07:00', 'start_date': None}
    assert is_expected_on(sched, _plant(irrigation_mode='auto'), date(2026, 10, 14), set()) is True
    assert is_expected_on(sched, _plant(irrigation_mode='auto'), date(2026, 10, 13), set()) is False
