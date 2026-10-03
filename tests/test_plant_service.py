from datetime import date, datetime

import pytest

import plant_service as svc
from tests.plant_fakes import FakePlantStore

T = date(2026, 10, 14)


def _mk(store, **kw):
    body = {'name': 'פיקוס', 'plant_type': 'fern', 'irrigation_mode': 'manual', 'interval_days': 3}
    body.update(kw)
    return svc.create_plant(store, body, T)


def _backdate(store, pid, d):
    store.plants[pid]['created_at'] = d


def test_create_validates():
    s = FakePlantStore()
    for bad in ({'name': '', 'plant_type': 'fern'},
                {'name': 'x', 'plant_type': 'palm'},
                {'name': 'x' * 41, 'plant_type': 'fern'}):
        with pytest.raises(svc.PlantError):
            svc.create_plant(s, bad, T)
    with pytest.raises(svc.PlantError):
        _mk(s, interval_days=0)
    with pytest.raises(svc.PlantError):
        _mk(s, irrigation_mode='auto', auto_time='25:00')
    with pytest.raises(svc.PlantError):
        _mk(s, color='teal')
    assert s.plants == {}


def test_create_defaults_color_and_auto_time():
    s = FakePlantStore()
    pid = _mk(s, irrigation_mode='auto')
    p = s.get_plant(pid)
    assert p['color'] == svc.PALETTE[0] and p['auto_time'] == '07:00' and p['created_at'] == T
    assert s.get_plant(_mk(s))['color'] == svc.PALETTE[1]


def test_payload_materializes_once_and_is_idempotent():
    s = FakePlantStore()
    pid = _mk(s)
    _backdate(s, pid, date(2026, 10, 1))
    p1 = svc.build_payload(s, T)
    p2 = svc.build_payload(s, T)
    assert len(s.days) == 14 and p1 == p2
    assert p1['today'] == '2026-10-14' and len(p1['window']) == 14
    assert [d['day'] for d in p1['days'][str(pid)]][-1] == '2026-10-14'
    assert p1['plants'][0]['status'] == 'overdue' and p1['plants'][0]['last_water'] is None


def test_payload_fills_gap_days_after_absence():
    s = FakePlantStore()
    pid = _mk(s)
    _backdate(s, pid, date(2026, 10, 1))
    svc.build_payload(s, date(2026, 10, 3))
    svc.build_payload(s, T)
    assert sorted(d for (_, d) in s.days) == [date(2026, 10, i) for i in range(1, 15)]


def test_interval_change_does_not_rewrite_history():
    s = FakePlantStore()
    pid = _mk(s, irrigation_mode='auto', interval_days=2)
    _backdate(s, pid, date(2026, 10, 1))
    svc.build_payload(s, date(2026, 10, 6))
    before = {d: r['auto_expected'] for (_, d), r in s.days.items()}
    svc.update_plant(s, pid, {'interval_days': 5}, date(2026, 10, 6))
    svc.build_payload(s, date(2026, 10, 8))
    after = {d: r['auto_expected'] for (_, d), r in s.days.items() if d <= date(2026, 10, 6)}
    assert before == after


def test_water_event_marks_day_and_delete_unmarks():
    s = FakePlantStore()
    pid = _mk(s)
    svc.build_payload(s, T)
    eid = svc.add_event(s, pid, {'event_type': 'water', 'event_at': '2026-10-14T08:15'}, T)
    assert s.days[(pid, T)]['watered'] is True
    assert s.events[eid]['event_at'] == datetime(2026, 10, 14, 8, 15) and s.events[eid]['source'] == 'manual'
    svc.delete_event(s, eid)
    assert s.days[(pid, T)]['watered'] is False


def test_event_validation():
    s = FakePlantStore()
    pid = _mk(s)
    with pytest.raises(svc.PlantError):
        svc.add_event(s, pid, {'event_type': 'water', 'event_at': '2026-10-15T08:00'}, T)
    with pytest.raises(svc.PlantError):
        svc.add_event(s, pid, {'event_type': 'sing', 'event_at': '2026-10-14T08:00'}, T)
    with pytest.raises(svc.PlantError) as e:
        svc.add_event(s, 999, {'event_type': 'water'}, T)
    assert e.value.status == 404
    with pytest.raises(svc.PlantError) as e:
        svc.delete_event(s, 999)
    assert e.value.status == 404


def test_event_defaults_to_now():
    s = FakePlantStore()
    pid = _mk(s)
    eid = svc.add_event(s, pid, {'event_type': 'fertilize', 'note': ' דשן נוזלי '}, date.today())
    assert s.events[eid]['event_at'].date() == date.today() and s.events[eid]['note'] == 'דשן נוזלי'


def test_set_soil():
    s = FakePlantStore()
    pid = _mk(s)
    svc.build_payload(s, T)
    svc.set_soil(s, pid, {'day': '2026-10-14', 'soil_status': 'wet'}, T)
    assert s.days[(pid, T)]['soil_status'] == 'wet'
    svc.set_soil(s, pid, {'day': '2026-10-14', 'soil_status': None}, T)
    assert s.days[(pid, T)]['soil_status'] is None
    with pytest.raises(svc.PlantError):
        svc.set_soil(s, pid, {'day': '2026-10-14', 'soil_status': 'muddy'}, T)
    with pytest.raises(svc.PlantError):
        svc.set_soil(s, pid, {'day': '2026-10-15', 'soil_status': 'dry'}, T)


def test_confirm_auto_creates_event_at_auto_time():
    s = FakePlantStore()
    pid = _mk(s, irrigation_mode='auto', auto_time='06:30')
    svc.build_payload(s, T)
    svc.confirm_auto(s, pid, {'day': '2026-10-14'}, T)
    e = list(s.events.values())[0]
    assert e['event_at'] == datetime(2026, 10, 14, 6, 30) and e['source'] == 'auto_confirmed'
    assert s.days[(pid, T)]['auto_confirmed'] and s.days[(pid, T)]['watered']
    svc.delete_event(s, e['id'])
    assert not s.days[(pid, T)]['auto_confirmed'] and not s.days[(pid, T)]['watered']


def test_confirm_auto_rejected_for_manual():
    s = FakePlantStore()
    pid = _mk(s)
    with pytest.raises(svc.PlantError):
        svc.confirm_auto(s, pid, {'day': '2026-10-14'}, T)


def test_water_due_only_waters_due_plants():
    s = FakePlantStore()
    a = _mk(s, name='a')
    _mk(s, name='b')
    _backdate(s, a, date(2026, 10, 1))
    n = svc.water_due(s, {'event_at': '2026-10-14T09:00'}, T)
    assert n == 1 and [e['plant_id'] for e in s.events.values()] == [a]


def test_soft_delete_and_restore():
    s = FakePlantStore()
    pid = _mk(s)
    svc.delete_plant(s, pid)
    assert svc.build_payload(s, T)['plants'] == []
    assert [p['id'] for p in svc.deleted_plants(s)] == [pid]
    with pytest.raises(svc.PlantError):
        svc.update_plant(s, pid, {'name': 'x'}, T)
    svc.restore_plant(s, pid)
    assert [p['id'] for p in svc.build_payload(s, T)['plants']] == [pid]


def test_update_switching_to_auto_gets_default_time():
    s = FakePlantStore()
    pid = _mk(s)
    svc.update_plant(s, pid, {'irrigation_mode': 'auto'}, T)
    assert s.plants[pid]['auto_time'] == '07:00'


def test_dismiss_season():
    s = FakePlantStore()
    pid = _mk(s)
    svc.dismiss_season(s, pid, date(2026, 7, 1))
    assert s.plants[pid]['season_ack'] == '2026-summer'
    with pytest.raises(svc.PlantError):
        svc.dismiss_season(s, pid, date(2026, 10, 1))


def test_payload_suggestions_sorted_alert_first():
    s = FakePlantStore()
    pid = _mk(s)
    _backdate(s, pid, date(2026, 10, 1))
    levels = [x['level'] for x in svc.build_payload(s, T)['suggestions']]
    assert levels[0] == 'alert' and levels == sorted(levels, key=['alert', 'warn', 'info'].index)


def test_event_default_time_uses_client_today():
    s = FakePlantStore()
    pid = _mk(s)
    svc.build_payload(s, T)
    eid = svc.add_event(s, pid, {'event_type': 'water'}, T)
    assert s.events[eid]['event_at'].date() == T
    assert s.days[(pid, T)]['watered'] is True


def test_rejects_days_before_window():
    s = FakePlantStore()
    pid = _mk(s, irrigation_mode='auto')
    _backdate(s, pid, date(2026, 10, 1))
    svc.build_payload(s, T)
    # T = 2026-10-14, window start = 2026-10-01
    # 2026-09-30 is before window start (T - 14), should be rejected
    with pytest.raises(svc.PlantError):
        svc.add_event(s, pid, {'event_type': 'water', 'event_at': '2026-09-30T08:00'}, T)
    with pytest.raises(svc.PlantError):
        svc.set_soil(s, pid, {'day': '2026-09-30', 'soil_status': 'dry'}, T)
    with pytest.raises(svc.PlantError):
        svc.confirm_auto(s, pid, {'day': '2026-09-30'}, T)
    # 2026-10-01 is the window start (T - 13), should be accepted
    eid = svc.add_event(s, pid, {'event_type': 'water', 'event_at': '2026-10-01T08:00'}, T)
    assert s.events[eid]['event_at'].date() == date(2026, 10, 1)
