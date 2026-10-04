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


def test_scheduled_auto_days_are_recorded_without_approval():
    s = FakePlantStore()
    pid = _mk(s, irrigation_mode='auto', auto_time='06:30', interval_days=3)
    _backdate(s, pid, date(2026, 10, 5))
    p = svc.build_payload(s, T)                     # scheduled: 10/8, 10/11, 10/14 (today counts too)
    evs = sorted(s.events.values(), key=lambda e: e['event_at'])
    assert [e['event_at'] for e in evs] == [datetime(2026, 10, d, 6, 30) for d in (8, 11, 14)]
    assert {e['source'] for e in evs} == {svc.AUTO_SOURCE}
    assert all(s.days[(pid, date(2026, 10, d))]['watered'] and s.days[(pid, date(2026, 10, d))]['auto_confirmed']
               for d in (8, 11, 14))
    assert p['summary'] == {'due_today': 0, 'overdue': 0, 'auto_today': 1}
    assert p['plants'][0]['last_water'] == '2026-10-14'
    svc.build_payload(s, T)
    assert len(s.events) == 3                       # idempotent


def test_auto_recording_uses_plan_time_and_skips_manual_plants():
    s = FakePlantStore()
    auto, manual = _mk(s), _mk(s, name='ידני')
    _backdate(s, auto, date(2026, 10, 10))
    _backdate(s, manual, date(2026, 10, 10))
    _cfg(s, style='weekdays', weekdays=[3], plant_ids=[auto])   # Wednesdays; 2026-10-14 is a Wednesday
    svc.build_payload(s, T)
    assert [(e['plant_id'], e['event_at']) for e in s.events.values()] == [(auto, datetime(2026, 10, 14, 6, 30))]


def test_deleting_an_auto_watering_skips_the_day_for_good():
    s = FakePlantStore()
    pid = _mk(s, irrigation_mode='auto', interval_days=2)
    _backdate(s, pid, date(2026, 10, 12))
    svc.build_payload(s, T)
    e = list(s.events.values())[0]
    svc.delete_event(s, e['id'])
    row = s.days[(pid, T)]
    assert not row['watered'] and not row['auto_confirmed'] and not row['auto_expected']
    p = svc.build_payload(s, T)
    assert s.events == {} and p['summary']['auto_today'] == 0


def test_days_older_than_the_window_are_not_backfilled():
    s = FakePlantStore()
    pid = _mk(s, irrigation_mode='auto', interval_days=2)
    s.insert_days([{'plant_id': pid, 'day': date(2026, 9, 20), 'soil_status': None, 'watered': False,
                    'auto_expected': True, 'auto_confirmed': False}])
    svc.record_auto_waterings(s, T)
    assert s.events == {}


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
    # 2026-10-01 is the window start (T - 13), should be accepted
    eid = svc.add_event(s, pid, {'event_type': 'water', 'event_at': '2026-10-01T08:00'}, T)
    assert s.events[eid]['event_at'].date() == date(2026, 10, 1)


# ── F1: applying a suggested interval must not re-trigger the same suggestion ──
def _kinds(payload):
    return [x['kind'] for x in payload['suggestions']]


def _suggestion(payload, kind):
    return [x for x in payload['suggestions'] if x['kind'] == kind][0]


def test_update_plant_stamps_interval_changed_at_only_on_a_real_change():
    s = FakePlantStore()
    pid = _mk(s)  # interval 3
    assert s.plants[pid]['interval_changed_at'] is None
    svc.update_plant(s, pid, {'interval_days': 3, 'name': 'x'}, T)
    svc.update_plant(s, pid, {'name': 'y'}, T)
    assert s.plants[pid]['interval_changed_at'] is None
    svc.update_plant(s, pid, {'interval_days': 5}, T)
    assert s.plants[pid]['interval_changed_at'] == T
    svc.update_plant(s, pid, {'interval_changed_at': '2020-01-01'}, date(2026, 10, 15))  # not client-settable
    assert s.plants[pid]['interval_changed_at'] == T


def test_applied_dries_fast_suggestion_does_not_fire_again():
    s = FakePlantStore()
    pid = _mk(s)
    _backdate(s, pid, date(2026, 10, 1))
    svc.build_payload(s, T)
    for at in ('2026-10-09T08:00', '2026-10-13T08:00'):
        svc.add_event(s, pid, {'event_type': 'water', 'event_at': at}, T)
    for day in ('2026-10-10', '2026-10-14'):  # dry the day after each watering
        svc.set_soil(s, pid, {'day': day, 'soil_status': 'dry'}, T)
    suggestion = _suggestion(svc.build_payload(s, T), 'dries_fast')
    assert suggestion['action']['value'] == 2
    svc.update_plant(s, pid, {'interval_days': suggestion['action']['value']}, T)
    assert 'dries_fast' not in _kinds(svc.build_payload(s, T))


def test_applied_overwater_suggestion_does_not_fire_again():
    s = FakePlantStore()
    pid = _mk(s)
    _backdate(s, pid, date(2026, 10, 1))
    svc.build_payload(s, T)
    svc.add_event(s, pid, {'event_type': 'water', 'event_at': '2026-10-13T08:00'}, T)
    for day in ('2026-10-12', '2026-10-13', '2026-10-14'):
        svc.set_soil(s, pid, {'day': day, 'soil_status': 'wet'}, T)
    suggestion = _suggestion(svc.build_payload(s, T), 'overwater')
    assert suggestion['action']['value'] == 4
    svc.update_plant(s, pid, {'interval_days': suggestion['action']['value']}, T)
    assert 'overwater' not in _kinds(svc.build_payload(s, T))


def test_seasonal_not_resuggested_after_interval_change_in_same_season():
    s = FakePlantStore()
    july = date(2026, 7, 10)
    pid = svc.create_plant(s, {'name': 'פיקוס', 'plant_type': 'fern', 'interval_days': 4}, date(2026, 7, 1))
    assert 'seasonal' in _kinds(svc.build_payload(s, july))
    svc.update_plant(s, pid, {'interval_days': 5}, july)  # manual change, season never acked
    assert 'seasonal' not in _kinds(svc.build_payload(s, july))
    assert 'seasonal' not in _kinds(svc.build_payload(s, date(2026, 7, 11)))


# ── F3: auto plants are not "due" / "overdue" and never watered by water-all-due ──
def test_auto_plant_on_scheduled_day_is_watered_not_due():
    s = FakePlantStore()
    pid = svc.create_plant(s, {'name': 'מונסטרה', 'plant_type': 'monstera',
                               'irrigation_mode': 'auto', 'interval_days': 3}, date(2026, 10, 11))
    p = svc.build_payload(s, T)  # day 3 after creation is a scheduled auto day → recorded
    assert p['plants'][0]['status'] == 'auto' and p['plants'][0]['days_since_water'] == 0
    assert p['summary'] == {'due_today': 0, 'overdue': 0, 'auto_today': 1}
    assert 'overdue' not in _kinds(p)
    svc.update_plant(s, pid, {'irrigation_mode': 'manual'}, T)  # watered today by the schedule
    assert svc.build_payload(s, T)['summary'] == {'due_today': 0, 'overdue': 0, 'auto_today': 0}


def test_water_due_skips_auto_plants():
    s = FakePlantStore()
    manual = _mk(s, name='manual')
    auto = _mk(s, name='auto', irrigation_mode='auto')
    _backdate(s, manual, date(2026, 10, 1))
    _backdate(s, auto, date(2026, 10, 1))
    n = svc.water_due(s, {'event_at': '2026-10-14T09:00'}, T)
    assert n == 1 and [e['plant_id'] for e in s.events.values()] == [manual]


# ── Rooms ──────────────────────────────────────────────────────────────────
DEFAULT_ROOM_NAMES = ['סלון', 'מטבח', 'חדר שינה', 'חדר עבודה', 'מרפסת', 'אמבטיה']


def _room_id(store, name):
    return [r['id'] for r in store.list_rooms() if r['name'] == name][0]


def test_payload_lists_default_rooms_in_order():
    s = FakePlantStore()
    assert [r['name'] for r in svc.build_payload(s, T)['rooms']] == DEFAULT_ROOM_NAMES


def test_create_room_validates_name():
    s = FakePlantStore()
    rid = svc.create_room(s, {'name': '  חדר ילדים  '})
    assert s.get_room(rid)['name'] == 'חדר ילדים'
    for bad in ('', '   ', 'x' * 31, 'סלון', 'חדר ילדים'):
        with pytest.raises(svc.PlantError) as e:
            svc.create_room(s, {'name': bad})
        assert e.value.status == 400
    assert svc.build_payload(s, T)['rooms'][-1]['name'] == 'חדר ילדים'


def test_rename_room():
    s = FakePlantStore()
    rid = _room_id(s, 'מרפסת')
    svc.rename_room(s, rid, {'name': 'מרפסת שירות'})
    assert s.get_room(rid)['name'] == 'מרפסת שירות'
    svc.rename_room(s, rid, {'name': 'מרפסת שירות'})  # same name on itself is fine
    with pytest.raises(svc.PlantError):
        svc.rename_room(s, rid, {'name': 'סלון'})
    with pytest.raises(svc.PlantError) as e:
        svc.rename_room(s, 999, {'name': 'x'})
    assert e.value.status == 404


def test_plant_room_assignment_and_validation():
    s = FakePlantStore()
    kitchen = _room_id(s, 'מטבח')
    pid = _mk(s, room_id=kitchen)
    assert svc.build_payload(s, T)['plants'][0]['room_id'] == kitchen
    svc.update_plant(s, pid, {'room_id': None}, T)
    assert svc.build_payload(s, T)['plants'][0]['room_id'] is None
    svc.update_plant(s, pid, {'room_id': str(kitchen)}, T)
    assert s.get_plant(pid)['room_id'] == kitchen
    for bad in (999, 'abc'):
        with pytest.raises(svc.PlantError):
            svc.update_plant(s, pid, {'room_id': bad}, T)
    with pytest.raises(svc.PlantError):
        _mk(s, room_id=999)


def test_plant_without_room_field_keeps_room_on_update():
    s = FakePlantStore()
    kitchen = _room_id(s, 'מטבח')
    pid = _mk(s, room_id=kitchen)
    svc.update_plant(s, pid, {'interval_days': 5}, T)
    assert s.get_plant(pid)['room_id'] == kitchen


def test_deleted_room_unassigns_in_payload_and_restore_brings_back():
    s = FakePlantStore()
    balcony = _room_id(s, 'מרפסת')
    pid = _mk(s, room_id=balcony)
    svc.delete_room(s, balcony)
    p = svc.build_payload(s, T)
    assert balcony not in [r['id'] for r in p['rooms']]
    assert p['plants'][0]['room_id'] is None
    assert [r['id'] for r in svc.deleted_rooms(s)] == [balcony]
    with pytest.raises(svc.PlantError):
        _mk(s, room_id=balcony)  # cannot assign a deleted room
    svc.restore_room(s, balcony)
    assert svc.build_payload(s, T)['plants'][0]['room_id'] == balcony
    assert s.get_plant(pid)['room_id'] == balcony


def test_restore_room_with_taken_name_is_rejected():
    s = FakePlantStore()
    bath = _room_id(s, 'אמבטיה')
    svc.delete_room(s, bath)
    svc.create_room(s, {'name': 'אמבטיה'})
    with pytest.raises(svc.PlantError) as e:
        svc.restore_room(s, bath)
    assert e.value.status == 400
    with pytest.raises(svc.PlantError) as e:
        svc.delete_room(s, 999)
    assert e.value.status == 404


NEW_TYPES = ('zz', 'birdsnest', 'philodendron', 'snake', 'kalanchoe', 'geranium', 'petunia', 'adansonii', 'orchid', 'oregano', 'rosemary', 'basil',
             'chives', 'thyme', 'pentas', 'angelonia', 'spiky', 'strap', 'conifer', 'shrub')


@pytest.mark.parametrize('plant_type', NEW_TYPES)
def test_visual_plant_types_are_accepted(plant_type):
    s = FakePlantStore()
    pid = _mk(s, plant_type=plant_type)
    assert s.get_plant(pid)['plant_type'] == plant_type


# ── Irrigation configs ─────────────────────────────────────────────────────
def _cfg(store, **kw):
    body = {'name': 'טפטפת מרפסת', 'style': 'interval', 'interval_days': 2, 'time': '06:30'}
    body.update(kw)
    return svc.create_config(store, body, T)


def test_create_config_validates():
    s = FakePlantStore()
    _cfg(s)
    for bad in ({'name': ''}, {'name': 'טפטפת מרפסת'}, {'name': 'x', 'style': 'monthly'},
                {'name': 'x', 'interval_days': 0}, {'name': 'x', 'style': 'weekdays', 'weekdays': []},
                {'name': 'x', 'style': 'weekdays', 'weekdays': [7]}, {'name': 'x', 'time': '25:00'}):
        with pytest.raises(svc.PlantError):
            _cfg(s, **bad)


def test_config_assigns_many_plants_and_reassigns():
    s = FakePlantStore()
    a, b, c = _mk(s, name='a'), _mk(s, name='b'), _mk(s, name='c')
    cid = _cfg(s, plant_ids=[a, b])
    p = svc.build_payload(s, T)
    on = {x['id']: x for x in p['plants']}
    assert on[a]['irrigation_mode'] == 'auto' and on[a]['config_id'] == cid and on[c]['config_id'] is None
    assert p['configs'][0]['plant_count'] == 2 and p['configs'][0]['time'] == '06:30'
    svc.update_config(s, cid, {'plant_ids': [b, c]}, T)
    assert s.get_plant(a)['irrigation_mode'] == 'manual' and s.get_plant(a)['config_id'] is None
    assert s.get_plant(c)['config_id'] == cid and s.get_plant(c)['irrigation_mode'] == 'auto'


def test_config_drives_expected_days_and_watering_time():
    s = FakePlantStore()
    pid = _mk(s)
    _backdate(s, pid, date(2026, 10, 10))
    _cfg(s, style='weekdays', weekdays=[3], plant_ids=[pid])   # Wednesdays; 2026-10-14 is a Wednesday
    svc.build_payload(s, T)
    assert s.days[(pid, T)]['auto_expected'] is True
    assert s.days[(pid, date(2026, 10, 13))]['auto_expected'] is False
    assert [e['event_at'] for e in s.events.values()] == [datetime(2026, 10, 14, 6, 30)]


def test_config_edit_does_not_rewrite_history():
    s = FakePlantStore()
    pid = _mk(s)
    _backdate(s, pid, date(2026, 10, 1))
    cid = _cfg(s, interval_days=2, plant_ids=[pid])
    svc.build_payload(s, date(2026, 10, 6))
    before = {d: r['auto_expected'] for (_, d), r in s.days.items()}
    svc.update_config(s, cid, {'style': 'weekdays', 'weekdays': [0, 1, 2, 3, 4, 5, 6]}, date(2026, 10, 6))
    svc.build_payload(s, date(2026, 10, 8))
    assert {d: r['auto_expected'] for (_, d), r in s.days.items() if d <= date(2026, 10, 6)} == before
    assert s.days[(pid, date(2026, 10, 7))]['auto_expected'] is True


def test_plant_config_field():
    s = FakePlantStore()
    cid = _cfg(s)
    pid = _mk(s)
    svc.update_plant(s, pid, {'config_id': cid}, T)
    assert s.get_plant(pid)['irrigation_mode'] == 'auto' and s.get_plant(pid)['config_id'] == cid
    svc.update_plant(s, pid, {'irrigation_mode': 'manual'}, T)
    assert s.get_plant(pid)['config_id'] is None
    with pytest.raises(svc.PlantError):
        svc.update_plant(s, pid, {'config_id': 999}, T)


def test_delete_config_in_use_is_rejected():
    s = FakePlantStore()
    pid = _mk(s)
    cid = _cfg(s, plant_ids=[pid])
    with pytest.raises(svc.PlantError) as e:
        svc.delete_config(s, cid)
    assert e.value.status == 400 and '1' in str(e.value)
    svc.update_config(s, cid, {'plant_ids': []}, T)
    svc.delete_config(s, cid)
    assert svc.build_payload(s, T)['configs'] == []
    with pytest.raises(svc.PlantError) as e:
        svc.delete_config(s, 999)
    assert e.value.status == 404


def test_config_plant_suggestions_name_the_config():
    from datetime import timedelta
    s = FakePlantStore()
    pid = _mk(s)
    _cfg(s, plant_ids=[pid])
    svc.build_payload(s, T)
    for i in range(3):
        svc.set_soil(s, pid, {'day': (T - timedelta(days=i)).isoformat(), 'soil_status': 'wet'}, T)
    sug = [x for x in svc.build_payload(s, T)['suggestions'] if x['kind'] == 'overwater'][0]
    assert sug['action'] is None and 'טפטפת מרפסת' in sug['text']


# ── Dead plants → archive ──────────────────────────────────────────────────
def test_mark_dead_moves_plant_to_archive():
    s = FakePlantStore()
    a, b = _mk(s, name='a'), _mk(s, name='b')
    _backdate(s, a, date(2026, 9, 1))
    svc.build_payload(s, T)
    svc.add_event(s, a, {'event_type': 'water', 'event_at': '2026-10-10T08:00'}, T)
    svc.mark_dead(s, a, {'died_at': '2026-10-12', 'cause': 'overwater', 'note': ' שורשים רקובים '}, T)
    p = svc.build_payload(s, T)
    assert [x['id'] for x in p['plants']] == [b]
    assert all(x['plant_id'] != a for x in p['suggestions'])
    arch = svc.archive(s)
    assert len(arch) == 1 and arch[0]['id'] == a
    assert arch[0]['died_at'] == '2026-10-12' and arch[0]['cause'] == 'overwater' and arch[0]['note'] == 'שורשים רקובים'
    assert arch[0]['lifespan_days'] == 41 and arch[0]['waterings'] == 1 and arch[0]['last_water'] == '2026-10-10'


def test_mark_dead_validates():
    s = FakePlantStore()
    pid = _mk(s)
    for bad in ({'died_at': '2026-10-15'}, {'died_at': 'x'}, {'cause': 'boredom'}, {'note': 'x' * 201}):
        with pytest.raises(svc.PlantError):
            svc.mark_dead(s, pid, bad, T)
    with pytest.raises(svc.PlantError) as e:
        svc.mark_dead(s, 999, {}, T)
    assert e.value.status == 404


def test_mark_dead_defaults_to_today_unknown_cause():
    s = FakePlantStore()
    pid = _mk(s)
    svc.mark_dead(s, pid, {}, T)
    arch = svc.archive(s)[0]
    assert arch['died_at'] == T.isoformat() and arch['cause'] == 'unknown' and arch['note'] is None


def test_dead_plant_cannot_be_edited_and_can_be_revived():
    s = FakePlantStore()
    pid = _mk(s)
    svc.mark_dead(s, pid, {}, T)
    with pytest.raises(svc.PlantError) as e:
        svc.add_event(s, pid, {'event_type': 'water'}, T)
    assert e.value.status == 404
    with pytest.raises(svc.PlantError):
        svc.mark_dead(s, pid, {}, T)
    svc.revive(s, pid)
    assert [x['id'] for x in svc.build_payload(s, T)['plants']] == [pid] and svc.archive(s) == []
    with pytest.raises(svc.PlantError):
        svc.revive(s, pid)          # not dead anymore


def test_dead_plant_leaves_its_config():
    s = FakePlantStore()
    pid = _mk(s)
    cid = _cfg(s, plant_ids=[pid])
    svc.mark_dead(s, pid, {}, T)
    assert svc.build_payload(s, T)['configs'][0]['plant_count'] == 0
    svc.delete_config(s, cid)       # no longer "in use"


# ── Config start date + re-align ───────────────────────────────────────────
def test_new_interval_config_defaults_start_date_to_today():
    s = FakePlantStore()
    cid = _cfg(s)
    assert s.get_config(cid)['start_date'] == T
    assert svc.build_payload(s, T)['configs'][0]['start_date'] == T.isoformat()
    wk = _cfg(s, name='w', style='weekdays', weekdays=[1], start_date='2026-10-01')
    assert s.get_config(wk)['start_date'] is None               # weekday plans don't use one
    with pytest.raises(svc.PlantError):
        _cfg(s, name='bad', start_date='not-a-date')


def test_realign_marks_rhythm_and_never_touches_the_users_records():
    s = FakePlantStore()
    pid = _mk(s)
    _backdate(s, pid, date(2026, 10, 1))
    svc.build_payload(s, T)                       # 14 days materialized while the plant was manual
    # the user's records: a manual watering on 10/11 and a by-hand confirmed auto watering on 10/5
    svc.add_event(s, pid, {'event_type': 'water', 'event_at': '2026-10-11T08:00'}, T)
    s.add_event(pid, 'water', datetime(2026, 10, 5, 7), 'auto_confirmed', None)
    s.days[(pid, date(2026, 10, 5))].update(auto_confirmed=True, watered=True)
    # a schedule-recorded watering on the old rhythm's 10/7
    s.add_event(pid, 'water', datetime(2026, 10, 7, 7), svc.AUTO_SOURCE, None)
    s.days[(pid, date(2026, 10, 7))].update(auto_expected=True, watered=True, auto_confirmed=True)
    # the drip timer has been running every 3 days since 9/29 → 10/2, 10/5, 10/8, 10/11, 10/14
    cid = _cfg(s, interval_days=3, start_date='2026-09-29', plant_ids=[pid])
    n = svc.realign_config(s, cid, T)
    assert n == 4                                 # 10/2, 10/8, 10/14 marked + 10/7 removed
    assert not s.days[(pid, date(2026, 10, 7))]['watered']
    assert s.days[(pid, date(2026, 10, 5))]['auto_confirmed'] and s.days[(pid, date(2026, 10, 11))]['watered']
    svc.build_payload(s, T)                       # the next load records the newly scheduled days
    water = sorted((e['event_at'].day, e['source']) for e in s.events.values())
    assert water == [(2, 'auto'), (5, 'auto_confirmed'), (8, 'auto'), (11, 'manual'), (14, 'auto')]


def test_realign_unknown_config_is_404():
    s = FakePlantStore()
    with pytest.raises(svc.PlantError) as e:
        svc.realign_config(s, 999, T)
    assert e.value.status == 404


# ── Plant photos ───────────────────────────────────────────────────────────
import base64 as _b64

JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 64          # JPEG magic + filler
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64


def _data_url(mime, raw):
    return f'data:{mime};base64,' + _b64.b64encode(raw).decode()


def test_set_photo_and_payload_version():
    s = FakePlantStore()
    pid = _mk(s)
    assert svc.build_payload(s, T)['plants'][0]['photo'] is None
    svc.set_photo(s, pid, {'data': _data_url('image/jpeg', JPEG)})
    v1 = svc.build_payload(s, T)['plants'][0]['photo']
    assert v1
    assert svc.get_photo(s, pid) == ('image/jpeg', JPEG)
    svc.set_photo(s, pid, {'data': _data_url('image/png', PNG)})       # replace
    assert svc.get_photo(s, pid) == ('image/png', PNG)


def test_photo_validation():
    s = FakePlantStore()
    pid = _mk(s)
    for bad in ({}, {'data': 'not a data url'}, {'data': _data_url('image/gif', b'GIF89a' + b'0' * 10)},
                {'data': 'data:image/jpeg;base64,@@@'}, {'data': _data_url('image/jpeg', PNG)},
                {'data': _data_url('image/jpeg', b'\xff\xd8\xff' + b'0' * (svc.MAX_PHOTO_BYTES + 1))}):
        with pytest.raises(svc.PlantError) as e:
            svc.set_photo(s, pid, bad)
        assert e.value.status == 400
    with pytest.raises(svc.PlantError) as e:
        svc.set_photo(s, 999, {'data': _data_url('image/jpeg', JPEG)})
    assert e.value.status == 404


def test_remove_photo_and_missing_photo():
    s = FakePlantStore()
    pid = _mk(s)
    with pytest.raises(svc.PlantError) as e:
        svc.get_photo(s, pid)
    assert e.value.status == 404
    svc.set_photo(s, pid, {'data': _data_url('image/jpeg', JPEG)})
    svc.remove_photo(s, pid)
    assert svc.build_payload(s, T)['plants'][0]['photo'] is None


def test_archived_plant_keeps_photo():
    s = FakePlantStore()
    pid = _mk(s)
    svc.set_photo(s, pid, {'data': _data_url('image/jpeg', JPEG)})
    svc.mark_dead(s, pid, {}, T)
    assert svc.archive(s)[0]['photo']
    assert svc.get_photo(s, pid)[0] == 'image/jpeg'
