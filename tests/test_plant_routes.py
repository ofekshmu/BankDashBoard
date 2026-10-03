import pytest
from flask import Flask

from routes import plant_routes
from tests.plant_fakes import FakePlantStore

TODAY = '2026-10-14'


@pytest.fixture
def client(monkeypatch):
    store = FakePlantStore()
    monkeypatch.setattr(plant_routes, 'get_store', lambda: store)
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


def test_dismiss_season_outside_season_is_400(client):
    _create(client)
    r = client.post('/api/plants/1/dismiss-season', json={'today': TODAY})
    assert r.status_code == 400
    r = client.post('/api/plants/1/dismiss-season', json={'today': '2026-07-01'})
    assert r.status_code == 200 and r.get_json()['plants'][0]['season_ack'] == '2026-summer'


def test_page_is_served(client):
    r = client.get('/plants')
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'מעקב עציצים' in html
    assert 'class="nav-item active" href="/plants"' in html
    assert '@SHELL' not in html and '@SIDEBAR@' not in html and '@DEBUG@' not in html
