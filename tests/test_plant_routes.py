import logging
from datetime import date

import pytest
from flask import Flask

from routes import plant_routes
from tests.plant_fakes import FakePlantStore

TODAY = '2026-10-14'


@pytest.fixture
def client(monkeypatch):
    store = FakePlantStore()
    monkeypatch.setattr(plant_routes, 'get_store', lambda: store)
    monkeypatch.setattr(plant_routes, '_server_today', lambda: date(2026, 10, 14))
    app = Flask(__name__)
    app.register_blueprint(plant_routes.plants_bp)
    c = app.test_client()
    c.store = store
    return c


def _create(client, **kw):
    body = {'today': TODAY, 'name': 'מונסטרה', 'plant_type': 'monstera',
            'irrigation_mode': 'auto', 'interval_days': 2, 'auto_time': '07:00'}
    body.update(kw)
    return client.post('/api/plants', json=body).get_json()


def test_get_empty(client):
    r = client.get(f'/api/plants?today={TODAY}')
    d = r.get_json()
    assert r.status_code == 200 and d['ok'] and d['plants'] == []
    assert d['today'] == TODAY and len(d['window']) == 14 and d['summary']['overdue'] == 0


def test_create_returns_payload_and_id(client):
    d = _create(client)
    assert d['ok'] and d['created_id'] == 1
    assert d['plants'][0]['name'] == 'מונסטרה' and d['plants'][0]['created_at'] == TODAY
    assert d['days']['1'][0]['day'] == TODAY


def test_validation_error_is_400(client):
    r = client.post('/api/plants', json={'today': TODAY, 'name': '', 'plant_type': 'fern'})
    assert r.status_code == 400 and r.get_json()['ok'] is False


def test_unknown_plant_is_404(client):
    r = client.put('/api/plants/42', json={'today': TODAY, 'name': 'x'})
    assert r.status_code == 404 and r.get_json()['ok'] is False


def test_event_soil_confirm_flow(client):
    _create(client)
    d = client.post('/api/plants/1/events', json={'today': TODAY, 'event_type': 'fertilize',
                                                  'event_at': f'{TODAY}T10:00'}).get_json()
    assert d['created_id'] == 1 and d['events']['1'][0]['event_type'] == 'fertilize'
    d = client.put('/api/plants/1/soil', json={'today': TODAY, 'day': TODAY, 'soil_status': 'dry'}).get_json()
    assert d['days']['1'][-1]['soil_status'] == 'dry'
    d = client.post('/api/plants/1/confirm-auto', json={'today': TODAY, 'day': TODAY}).get_json()
    assert d['days']['1'][-1]['watered'] and d['days']['1'][-1]['auto_confirmed']
    d = client.delete('/api/plants/events/1', json={'today': TODAY}).get_json()
    assert [e['event_type'] for e in d['events']['1']] == ['water']


def test_delete_restore_and_deleted_list(client):
    _create(client)
    d = client.delete('/api/plants/1', json={'today': TODAY}).get_json()
    assert d['plants'] == []
    assert [p['id'] for p in client.get('/api/plants/deleted').get_json()['plants']] == [1]
    d = client.post('/api/plants/1/restore', json={'today': TODAY}).get_json()
    assert [p['id'] for p in d['plants']] == [1]


def test_water_due(client):
    _create(client, irrigation_mode='manual')
    client.store.plants[1]['created_at'] = client.store.plants[1]['created_at'].replace(day=1)
    d = client.post('/api/plants/water-due', json={'today': TODAY, 'event_at': f'{TODAY}T09:00'}).get_json()
    assert d['watered_count'] == 1 and d['plants'][0]['status'] == 'ok'


def test_dismiss_season_outside_season_is_400(client, monkeypatch):
    _create(client)
    r = client.post('/api/plants/1/dismiss-season', json={'today': TODAY})
    assert r.status_code == 400
    monkeypatch.setattr(plant_routes, '_server_today', lambda: date(2026, 7, 1))
    r = client.post('/api/plants/1/dismiss-season', json={'today': '2026-07-01'})
    assert r.status_code == 200 and r.get_json()['plants'][0]['season_ack'] == '2026-summer'


def test_page_is_served(client):
    r = client.get('/plants')
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'מעקב עציצים' in html
    assert 'class="nav-item active" href="/plants"' in html
    assert '@SHELL' not in html and '@SIDEBAR@' not in html and '@DEBUG@' not in html


# ── F4: the client's `today` is bounded to the server date ± 1 day ──────────
def test_far_future_today_is_400_and_materializes_nothing(client):
    r = client.get('/api/plants?today=2026-12-31')
    assert r.status_code == 400 and r.get_json()['ok'] is False
    r = client.post('/api/plants', json={'today': '2026-12-31', 'name': 'x', 'plant_type': 'fern'})
    assert r.status_code == 400
    assert client.store.days == {} and client.store.plants == {}


def test_far_past_today_is_400(client):
    assert client.get('/api/plants?today=2026-10-01').status_code == 400


@pytest.mark.parametrize('raw', ['garbage', '2026-13-45', '14/10/2026'])
def test_malformed_today_is_400(client, raw):
    r = client.get(f'/api/plants?today={raw}')
    assert r.status_code == 400 and r.get_json()['ok'] is False
    r = client.post('/api/plants', json={'today': raw, 'name': 'x', 'plant_type': 'fern'})
    assert r.status_code == 400


def test_today_within_one_day_of_server_is_accepted(client):
    r = client.get('/api/plants?today=2026-10-15')   # client ahead (e.g. UTC+14)
    assert r.status_code == 200 and r.get_json()['today'] == '2026-10-15'
    r = client.get('/api/plants?today=2026-10-13')   # client behind (e.g. UTC-12)
    assert r.status_code == 200 and r.get_json()['today'] == '2026-10-13'


def test_missing_today_uses_server_date(client):
    r = client.get('/api/plants')
    assert r.status_code == 200 and r.get_json()['today'] == TODAY


# ── F5: unexpected errors are logged with a traceback before the 500 ────────
def test_unexpected_error_is_logged_with_traceback(client, monkeypatch, caplog):
    def boom():
        raise RuntimeError('db down')
    monkeypatch.setattr(plant_routes, 'get_store', boom)
    with caplog.at_level(logging.ERROR):
        r = client.get(f'/api/plants?today={TODAY}')
    assert r.status_code == 500 and r.get_json()['ok'] is False
    assert any(rec.exc_info and rec.exc_info[0] is RuntimeError for rec in caplog.records)


def test_deleted_list_error_is_logged_with_traceback(client, monkeypatch, caplog):
    def boom():
        raise RuntimeError('db down')
    monkeypatch.setattr(plant_routes, 'get_store', boom)
    with caplog.at_level(logging.ERROR):
        r = client.get('/api/plants/deleted')
    assert r.status_code == 500 and r.get_json()['ok'] is False
    assert any(rec.exc_info and rec.exc_info[0] is RuntimeError for rec in caplog.records)


# ── Rooms ──────────────────────────────────────────────────────────────────
def test_rooms_crud_flow(client):
    d = client.get('/api/plants/rooms').get_json()
    assert d['ok'] and len(d['rooms']) == 6 and d['deleted'] == []
    d = client.post('/api/plants/rooms', json={'today': TODAY, 'name': 'חדר ילדים'}).get_json()
    rid = d['created_id']
    assert d['rooms'][-1] == {'id': rid, 'name': 'חדר ילדים'}
    d = client.put(f'/api/plants/rooms/{rid}', json={'today': TODAY, 'name': 'חדר משחקים'}).get_json()
    assert d['rooms'][-1]['name'] == 'חדר משחקים'
    _create(client, room_id=rid)
    d = client.delete(f'/api/plants/rooms/{rid}', json={'today': TODAY}).get_json()
    assert rid not in [r['id'] for r in d['rooms']] and d['plants'][0]['room_id'] is None
    assert [r['id'] for r in client.get('/api/plants/rooms').get_json()['deleted']] == [rid]
    d = client.post(f'/api/plants/rooms/{rid}/restore', json={'today': TODAY}).get_json()
    assert d['plants'][0]['room_id'] == rid


def test_room_errors(client):
    r = client.post('/api/plants/rooms', json={'today': TODAY, 'name': 'סלון'})
    assert r.status_code == 400 and r.get_json()['ok'] is False
    r = client.put('/api/plants/rooms/999', json={'today': TODAY, 'name': 'x'})
    assert r.status_code == 404
    r = client.post('/api/plants', json={'today': TODAY, 'name': 'x', 'plant_type': 'fern', 'room_id': 999})
    assert r.status_code == 400


def test_every_plant_type_has_an_icon_and_label_in_the_page(client):
    import re
    from src_utils.plant_logic import PLANT_TYPES
    html = client.get('/plants').get_data(as_text=True)
    glyphs = re.search(r'var GLYPHS = \{(.*?)\n\};', html, re.S).group(1)
    labels = re.search(r'var PLANT_TYPES = \[(.*?)\];', html, re.S).group(1)
    for t in PLANT_TYPES:
        assert re.search(r'\b' + t + r'\s*:', glyphs), f'no glyph for {t}'
        assert "['" + t + "'," in labels, f'no picker label for {t}'


# ── Irrigation configs ─────────────────────────────────────────────────────
def test_configs_crud_flow(client):
    _create(client, irrigation_mode='manual')
    d = client.post('/api/plants/configs', json={'today': TODAY, 'name': 'טפטפת', 'style': 'weekdays',
                                                 'weekdays': [0, 3], 'time': '07:00', 'plant_ids': [1]}).get_json()
    cid = d['created_id']
    assert d['configs'] == [{'id': cid, 'name': 'טפטפת', 'style': 'weekdays', 'interval_days': None,
                             'weekdays': [0, 3], 'time': '07:00', 'start_date': None, 'plant_count': 1}]
    assert d['plants'][0]['config_id'] == cid
    assert client.get('/api/plants/configs').get_json()['configs'][0]['id'] == cid
    d = client.put(f'/api/plants/configs/{cid}', json={'today': TODAY, 'time': '08:15'}).get_json()
    assert d['configs'][0]['time'] == '08:15'
    r = client.delete(f'/api/plants/configs/{cid}', json={'today': TODAY})
    assert r.status_code == 400
    client.put(f'/api/plants/configs/{cid}', json={'today': TODAY, 'plant_ids': []})
    d = client.delete(f'/api/plants/configs/{cid}', json={'today': TODAY}).get_json()
    assert d['configs'] == [] and d['plants'][0]['irrigation_mode'] == 'manual'
    assert client.put('/api/plants/configs/999', json={'today': TODAY, 'name': 'x'}).status_code == 404


# ── Archive ────────────────────────────────────────────────────────────────
def test_dead_archive_revive_flow(client):
    _create(client, irrigation_mode='manual')
    d = client.post('/api/plants/1/dead', json={'today': TODAY, 'died_at': TODAY, 'cause': 'pests', 'note': 'כנימות'}).get_json()
    assert d['ok'] and d['plants'] == []
    a = client.get('/api/plants/archive').get_json()
    assert a['ok'] and a['plants'][0]['id'] == 1 and a['plants'][0]['cause'] == 'pests'
    assert client.post('/api/plants/1/dead', json={'today': TODAY}).status_code == 404
    d = client.post('/api/plants/1/revive', json={'today': TODAY}).get_json()
    assert [p['id'] for p in d['plants']] == [1]
    assert client.post('/api/plants/1/revive', json={'today': TODAY}).status_code == 400


def test_config_start_date_and_realign_route(client):
    _create(client, irrigation_mode='manual')
    d = client.post('/api/plants/configs', json={'today': TODAY, 'name': 'טפטפת', 'style': 'interval',
                                                 'interval_days': 2, 'start_date': '2026-10-12', 'time': '07:00',
                                                 'plant_ids': [1]}).get_json()
    cid = d['created_id']
    assert d['configs'][0]['start_date'] == '2026-10-12'
    d = client.post(f'/api/plants/configs/{cid}/realign', json={'today': TODAY}).get_json()
    assert d['ok'] and 'realigned' in d
    assert client.post('/api/plants/configs/999/realign', json={'today': TODAY}).status_code == 404


# ── Plant photos ───────────────────────────────────────────────────────────
def test_photo_routes(client):
    import base64
    _create(client, irrigation_mode='manual')
    jpeg = b'\xff\xd8\xff\xe0' + b'\x01' * 40
    assert client.get('/api/plants/1/photo').status_code == 404
    d = client.put('/api/plants/1/photo', json={'today': TODAY,
                   'data': 'data:image/jpeg;base64,' + base64.b64encode(jpeg).decode()}).get_json()
    v = d['plants'][0]['photo']
    assert d['ok'] and v
    r = client.get(f'/api/plants/1/photo?v={v}')
    assert r.status_code == 200 and r.mimetype == 'image/jpeg' and r.data == jpeg
    assert 'max-age' in r.headers.get('Cache-Control', '')
    assert client.put('/api/plants/1/photo', json={'today': TODAY, 'data': 'x'}).status_code == 400
    d = client.delete('/api/plants/1/photo', json={'today': TODAY}).get_json()
    assert d['plants'][0]['photo'] is None


def test_every_plant_type_has_a_care_note(client):
    import json
    import re
    from src_utils.plant_logic import PLANT_TYPES
    html = client.get('/plants').get_data(as_text=True)
    care = json.loads(re.search(r'var CARE = (\{.*?\});\s*$', html, re.M).group(1))
    for t in PLANT_TYPES:
        assert t in care and all(care[t].get(k) for k in ('s', 'l', 'w', 'f', 'x')), f'no care note for {t}'
