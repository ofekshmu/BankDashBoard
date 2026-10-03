from datetime import date, timedelta

from src_utils.plant_suggestions import build_suggestions

T = date(2026, 10, 14)  # October: no season key, outside fertilize season (Mar–Sep)


def _plant(**kw):
    p = {'id': 1, 'name': 'פיקוס', 'irrigation_mode': 'manual', 'interval_days': 3,
         'auto_time': None, 'created_at': date(2026, 9, 1), 'season_ack': None}
    p.update(kw)
    return p


def _rows(spec, today=T):
    """spec: {days_ago: {field: value}} → 14 rows ending at `today`."""
    out = []
    for i in range(14):
        r = {'day': today - timedelta(days=i), 'soil_status': None, 'watered': False,
             'auto_expected': False, 'auto_confirmed': False}
        r.update(spec.get(i, {}))
        out.append(r)
    return out


def _one_row(day):
    return [{'day': day, 'soil_status': 'humid', 'watered': False,
             'auto_expected': False, 'auto_confirmed': False}]


def _kinds(s):
    return [x['kind'] for x in s]


def _get(s, kind):
    return [x for x in s if x['kind'] == kind][0]


WATERED_YESTERDAY = {'water': T - timedelta(days=1)}
SOIL_TODAY = {0: {'soil_status': 'humid'}}


def test_quiet_plant_has_no_suggestions():
    assert build_suggestions(_plant(), _rows(SOIL_TODAY), WATERED_YESTERDAY, T) == []


def test_overdue():
    s = build_suggestions(_plant(), _rows(SOIL_TODAY), {'water': T - timedelta(days=5)}, T)
    o = _get(s, 'overdue')
    assert o['level'] == 'alert' and '2' in o['text'] and o['action'] == {'type': 'water_now'}
    assert o['plant_id'] == 1


def test_dries_fast_suggests_shorter_interval():
    rows = _rows({0: {'soil_status': 'dry'}, 1: {'watered': True},
                  5: {'soil_status': 'dry'}, 6: {'watered': True}})
    s = build_suggestions(_plant(), rows, WATERED_YESTERDAY, T)
    assert _get(s, 'dries_fast')['action'] == {'type': 'set_interval', 'value': 2}


def test_dries_fast_needs_two_occurrences():
    rows = _rows({0: {'soil_status': 'dry'}, 1: {'watered': True}})
    assert 'dries_fast' not in _kinds(build_suggestions(_plant(), rows, WATERED_YESTERDAY, T))


def test_dries_fast_not_below_one_day():
    rows = _rows({0: {'soil_status': 'dry'}, 1: {'watered': True},
                  5: {'soil_status': 'dry'}, 6: {'watered': True}})
    s = build_suggestions(_plant(interval_days=1), rows, {'water': T}, T)
    assert 'dries_fast' not in _kinds(s)


def test_overwatering():
    rows = _rows({i: {'soil_status': 'wet'} for i in range(3)})
    s = build_suggestions(_plant(), rows, WATERED_YESTERDAY, T)
    w = _get(s, 'overwater')
    assert w['level'] == 'warn' and w['action'] == {'type': 'set_interval', 'value': 4}


def test_auto_unconfirmed_points_at_latest_missed_day():
    p = _plant(irrigation_mode='auto', auto_time='07:00')
    rows = _rows({0: {'soil_status': 'humid'}, 2: {'auto_expected': True},
                  5: {'auto_expected': True}, 8: {'auto_expected': True,
                                                  'auto_confirmed': True, 'watered': True}})
    a = _get(build_suggestions(p, rows, WATERED_YESTERDAY, T), 'auto_unconfirmed')
    assert '2' in a['text']
    assert a['action'] == {'type': 'confirm_auto', 'day': (T - timedelta(days=2)).isoformat()}


def test_auto_expected_today_is_not_flagged_yet():
    p = _plant(irrigation_mode='auto', auto_time='07:00')
    rows = _rows({0: {'soil_status': 'humid', 'auto_expected': True}})
    assert 'auto_unconfirmed' not in _kinds(build_suggestions(p, rows, WATERED_YESTERDAY, T))


def test_seasonal_summer_and_ack():
    t = date(2026, 7, 10)
    le = {'water': t - timedelta(days=1), 'fertilize': t - timedelta(days=3)}
    s = build_suggestions(_plant(interval_days=4), _one_row(t), le, t)
    assert _get(s, 'seasonal')['action'] == {'type': 'set_interval', 'value': 3,
                                             'season_key': '2026-summer'}
    s2 = build_suggestions(_plant(interval_days=4, season_ack='2026-summer'), _one_row(t), le, t)
    assert 'seasonal' not in _kinds(s2)


def test_seasonal_winter_longer():
    t = date(2027, 1, 10)
    s = build_suggestions(_plant(interval_days=4), _one_row(t), {'water': t - timedelta(days=1)}, t)
    assert _get(s, 'seasonal')['action']['value'] == 5


def test_seasonal_skipped_when_no_change():
    t = date(2027, 1, 10)
    s = build_suggestions(_plant(interval_days=1), _one_row(t), {'water': t}, t)
    assert 'seasonal' not in _kinds(s)


def test_fertilize_reminder_in_growing_season():
    t = date(2026, 4, 10)
    p = _plant(created_at=date(2026, 1, 1))
    s = build_suggestions(p, _one_row(t), {'water': t - timedelta(days=1)}, t)
    assert _get(s, 'fertilize')['action'] == {'type': 'fertilize_now'}
    s2 = build_suggestions(p, _one_row(t), {'water': t - timedelta(days=1),
                                            'fertilize': t - timedelta(days=10)}, t)
    assert 'fertilize' not in _kinds(s2)


def test_fertilize_skipped_for_new_plants():
    t = date(2026, 4, 10)
    s = build_suggestions(_plant(created_at=t - timedelta(days=5)), _one_row(t),
                          {'water': t - timedelta(days=1)}, t)
    assert 'fertilize' not in _kinds(s)


def test_no_soil_data():
    s = build_suggestions(_plant(), _rows({}), WATERED_YESTERDAY, T)
    assert _get(s, 'no_soil') == {'plant_id': 1, 'kind': 'no_soil', 'level': 'info',
                                  'text': 'פיקוס: לא עודכן מצב אדמה בשבוע האחרון',
                                  'action': {'type': 'set_soil'}}


def test_same_day_dry_and_water_is_not_dries_fast():
    # "check soil -> dry -> water" on the same day is the normal routine, not a fast-drying signal
    rows = _rows({0: {'soil_status': 'dry', 'watered': True}, 5: {'soil_status': 'dry', 'watered': True}})
    assert 'dries_fast' not in _kinds(build_suggestions(_plant(), rows, WATERED_YESTERDAY, T))


def test_overdue_not_suggested_for_auto_plant():
    p = _plant(irrigation_mode='auto', auto_time='07:00')
    s = build_suggestions(p, _rows(SOIL_TODAY), {'water': T - timedelta(days=9)}, T)
    assert 'overdue' not in _kinds(s)


# ── F1: a suggestion that was applied must not fire again ──────────────────
DRIES_FAST_ROWS = {0: {'soil_status': 'dry'}, 1: {'watered': True},
                   5: {'soil_status': 'dry'}, 6: {'watered': True}}


def test_dries_fast_ignores_history_before_interval_change():
    # the 5/6 pair predates the change, so only one qualifying occurrence remains
    p = _plant(interval_changed_at=T - timedelta(days=3))
    s = build_suggestions(p, _rows(DRIES_FAST_ROWS), WATERED_YESTERDAY, T)
    assert 'dries_fast' not in _kinds(s)


def test_dries_fast_watered_day_must_also_be_after_interval_change():
    # dry day 0 is after the change, but its watered day (T-1) equals the change day -> not counted
    p = _plant(interval_changed_at=T - timedelta(days=1))
    assert 'dries_fast' not in _kinds(build_suggestions(p, _rows(DRIES_FAST_ROWS), WATERED_YESTERDAY, T))


def test_dries_fast_counts_history_after_interval_change():
    p = _plant(interval_changed_at=T - timedelta(days=7))
    s = build_suggestions(p, _rows(DRIES_FAST_ROWS), WATERED_YESTERDAY, T)
    assert _get(s, 'dries_fast')['action']['value'] == 2


def test_overwater_requires_all_three_days_after_interval_change():
    rows = _rows({i: {'soil_status': 'wet'} for i in range(3)})
    assert 'overwater' not in _kinds(build_suggestions(
        _plant(interval_changed_at=T - timedelta(days=1)), rows, WATERED_YESTERDAY, T))
    assert 'overwater' not in _kinds(build_suggestions(
        _plant(interval_changed_at=T - timedelta(days=2)), rows, WATERED_YESTERDAY, T))
    assert 'overwater' in _kinds(build_suggestions(
        _plant(interval_changed_at=T - timedelta(days=3)), rows, WATERED_YESTERDAY, T))


def test_overwater_not_suggested_at_max_interval():
    rows = _rows({i: {'soil_status': 'wet'} for i in range(3)})
    s = build_suggestions(_plant(interval_days=60), rows, {'water': T - timedelta(days=1)}, T)
    assert 'overwater' not in _kinds(s)


def test_seasonal_skipped_when_interval_already_changed_this_season():
    t = date(2026, 7, 10)
    le = {'water': t - timedelta(days=1), 'fertilize': t - timedelta(days=3)}
    p = _plant(interval_days=4, interval_changed_at=date(2026, 6, 20))
    assert 'seasonal' not in _kinds(build_suggestions(p, _one_row(t), le, t))


def test_seasonal_still_offered_when_interval_changed_in_a_previous_season():
    t = date(2026, 7, 10)
    le = {'water': t - timedelta(days=1), 'fertilize': t - timedelta(days=3)}
    p = _plant(interval_days=4, interval_changed_at=date(2026, 3, 1))
    assert _get(build_suggestions(p, _one_row(t), le, t), 'seasonal')['action']['value'] == 3


def test_seasonal_winter_value_is_clamped_to_60():
    t = date(2027, 1, 10)
    s = build_suggestions(_plant(interval_days=50), _one_row(t), {'water': t - timedelta(days=1)}, t)
    assert _get(s, 'seasonal')['action']['value'] == 60


def test_seasonal_skipped_when_clamped_value_equals_interval():
    t = date(2027, 1, 10)
    s = build_suggestions(_plant(interval_days=60), _one_row(t), {'water': t - timedelta(days=1)}, t)
    assert 'seasonal' not in _kinds(s)
