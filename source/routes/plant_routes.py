"""Plant tracker (מעקב עציצים) page + JSON API.

Every mutating endpoint returns the full page payload so the client can
refresh its once-a-day cache in one round trip.
"""
import logging
import os
from datetime import date, datetime, timezone

from flask import Blueprint, Response, jsonify, request, send_file

import plant_service as svc

logger = logging.getLogger(__name__)

plants_bp = Blueprint('plants', __name__)

PLANT_HTML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'html', 'PlantTracker.html')


def get_store():
    """A ready PlantStore. Tests monkeypatch this with an in-memory fake."""
    from database import DataBase
    from plant_store import PlantStore
    store = PlantStore(DataBase())
    store.ensure()
    return store


def _body():
    return request.get_json(silent=True) or {}


def _server_today():
    """The server's UTC date. Module-level so tests can pin it."""
    return datetime.now(timezone.utc).date()


def _today():
    """The client's local date (query string or JSON body), else the server's UTC date.

    A skewed or crafted client date would materialize rows into the future, so it must be
    within one day of the server date (the widest real timezone difference).
    """
    raw = request.args.get('today') or _body().get('today')
    server = _server_today()
    if not raw:
        return server
    try:
        day = date.fromisoformat(raw)
    except (TypeError, ValueError):
        raise svc.PlantError('תאריך המכשיר שגוי')
    if abs((day - server).days) > 1:
        raise svc.PlantError('תאריך המכשיר שגוי')
    return day


def _respond(action=None):
    try:
        store = get_store()
        today = _today()
        svc.materialize(store, today)  # before the action so a new day's gap is filled first
        extra = action(store, today) if action else None
        payload = svc.build_payload(store, today)
        if extra:
            payload.update(extra)
        return jsonify(payload)
    except svc.PlantError as e:
        return jsonify({'ok': False, 'error': str(e)}), e.status
    except Exception as e:
        logger.exception('plant tracker request failed: %s %s', request.method, request.path)
        return jsonify({'ok': False, 'error': str(e)}), 500


@plants_bp.route('/plants')
def plants_page():
    if os.path.exists(PLANT_HTML):
        return send_file(PLANT_HTML)
    return 'Plant tracker page not found', 404


@plants_bp.route('/api/plants', methods=['GET', 'POST'])
def api_plants():
    if request.method == 'GET':
        return _respond()
    return _respond(lambda s, t: {'created_id': svc.create_plant(s, _body(), t)})


@plants_bp.route('/api/plants/<int:pid>', methods=['PUT', 'DELETE'])
def api_plant(pid):
    if request.method == 'DELETE':
        return _respond(lambda s, t: svc.delete_plant(s, pid))
    return _respond(lambda s, t: svc.update_plant(s, pid, _body(), t))


@plants_bp.route('/api/plants/<int:pid>/restore', methods=['POST'])
def api_plant_restore(pid):
    return _respond(lambda s, t: svc.restore_plant(s, pid))


@plants_bp.route('/api/plants/deleted')
def api_plants_deleted():
    try:
        return jsonify({'ok': True, 'plants': svc.deleted_plants(get_store())})
    except Exception as e:
        logger.exception('plant tracker request failed: %s %s', request.method, request.path)
        return jsonify({'ok': False, 'error': str(e)}), 500


@plants_bp.route('/api/plants/<int:pid>/events', methods=['POST'])
def api_plant_events(pid):
    return _respond(lambda s, t: {'created_id': svc.add_event(s, pid, _body(), t)})


@plants_bp.route('/api/plants/events/<int:eid>', methods=['DELETE'])
def api_plant_event_delete(eid):
    return _respond(lambda s, t: svc.delete_event(s, eid))


@plants_bp.route('/api/plants/<int:pid>/soil', methods=['PUT'])
def api_plant_soil(pid):
    return _respond(lambda s, t: svc.set_soil(s, pid, _body(), t))


@plants_bp.route('/api/plants/<int:pid>/dismiss-season', methods=['POST'])
def api_plant_dismiss_season(pid):
    return _respond(lambda s, t: svc.dismiss_season(s, pid, t))


@plants_bp.route('/api/plants/rooms', methods=['GET', 'POST'])
def api_plant_rooms():
    if request.method == 'POST':
        return _respond(lambda s, t: {'created_id': svc.create_room(s, _body())})
    try:
        return jsonify(dict(ok=True, **svc.rooms_overview(get_store())))
    except Exception as e:
        logger.exception('plant tracker request failed: %s %s', request.method, request.path)
        return jsonify({'ok': False, 'error': str(e)}), 500


@plants_bp.route('/api/plants/rooms/<int:rid>', methods=['PUT', 'DELETE'])
def api_plant_room(rid):
    if request.method == 'DELETE':
        return _respond(lambda s, t: svc.delete_room(s, rid))
    return _respond(lambda s, t: svc.rename_room(s, rid, _body()))


@plants_bp.route('/api/plants/rooms/<int:rid>/restore', methods=['POST'])
def api_plant_room_restore(rid):
    return _respond(lambda s, t: svc.restore_room(s, rid))


@plants_bp.route('/api/plants/<int:pid>/photo', methods=['GET', 'PUT', 'DELETE'])
def api_plant_photo(pid):
    if request.method == 'PUT':
        return _respond(lambda s, t: svc.set_photo(s, pid, _body()))
    if request.method == 'DELETE':
        return _respond(lambda s, t: svc.remove_photo(s, pid))
    try:
        mime, data = svc.get_photo(get_store(), pid)
    except svc.PlantError as e:
        return jsonify({'ok': False, 'error': str(e)}), e.status
    except Exception as e:
        logger.exception('plant tracker request failed: %s %s', request.method, request.path)
        return jsonify({'ok': False, 'error': str(e)}), 500
    # The page requests ?v=<photo version>, so a cached copy is valid until the photo changes.
    return Response(data, mimetype=mime, headers={'Cache-Control': 'private, max-age=31536000, immutable'})


@plants_bp.route('/api/plants/<int:pid>/dead', methods=['POST'])
def api_plant_dead(pid):
    return _respond(lambda s, t: svc.mark_dead(s, pid, _body(), t))


@plants_bp.route('/api/plants/<int:pid>/revive', methods=['POST'])
def api_plant_revive(pid):
    return _respond(lambda s, t: svc.revive(s, pid))


@plants_bp.route('/api/plants/archive')
def api_plants_archive():
    try:
        return jsonify({'ok': True, 'plants': svc.archive(get_store())})
    except Exception as e:
        logger.exception('plant tracker request failed: %s %s', request.method, request.path)
        return jsonify({'ok': False, 'error': str(e)}), 500


@plants_bp.route('/api/plants/configs', methods=['GET', 'POST'])
def api_plant_configs():
    if request.method == 'POST':
        return _respond(lambda s, t: {'created_id': svc.create_config(s, _body(), t)})
    try:
        return jsonify(dict(ok=True, **svc.configs_overview(get_store())))
    except Exception as e:
        logger.exception('plant tracker request failed: %s %s', request.method, request.path)
        return jsonify({'ok': False, 'error': str(e)}), 500


@plants_bp.route('/api/plants/configs/<int:cid>/realign', methods=['POST'])
def api_plant_config_realign(cid):
    return _respond(lambda s, t: {'realigned': svc.realign_config(s, cid, t)})


@plants_bp.route('/api/plants/configs/<int:cid>', methods=['PUT', 'DELETE'])
def api_plant_config(cid):
    if request.method == 'DELETE':
        return _respond(lambda s, t: svc.delete_config(s, cid))
    return _respond(lambda s, t: svc.update_config(s, cid, _body(), t))


@plants_bp.route('/api/plants/water-due', methods=['POST'])
def api_plants_water_due():
    return _respond(lambda s, t: {'watered_count': svc.water_due(s, _body(), t)})
