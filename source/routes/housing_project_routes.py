"""JSON API of the housing projects (new-build apartments such as Mona) — shown as a tab on /housing.

GET  /api/housing/projects/<key>            the whole project (settings, money, statistics, payments, events)
POST /api/housing/projects/<key>            change settings: price, down_pct, growth_pct, contract_date,
                                            delivery_date, tx_category
GET  /api/housing/shabazi/tx-kinds          {key: kind} of the user's choices for שבזי payments
POST /api/housing/shabazi/tx-kind           {key, kind}: the same for a שבזי payment (default: an expense)
POST /api/housing/projects/<key>/tx-kind    {key, kind}: mark one payment as price/cost (outgoing) or
                                            income/refund (incoming); kind null = automatic

GET  /api/housing/info/<apartment>          the "מידע חיוני" rows of 'shabazi' / 'mona': {ok, items:[{label, value}]}
PUT  /api/housing/info/<apartment>          {items: [...]} replaces them; answers the saved rows

The project endpoints answer {ok, project} so the page can replace its copy in one round trip.
"""
import logging
from datetime import date

from flask import Blueprint, jsonify, request

import housing_info_service as info_svc
import housing_project_service as svc

logger = logging.getLogger(__name__)

housing_projects_bp = Blueprint('housing_projects', __name__)


def get_db():
    """The database. Tests monkeypatch this with an in-memory fake."""
    from database import DataBase
    return DataBase()


def _today():
    """The server's date. Module-level so tests can pin it."""
    return date.today()


def _body():
    return request.get_json(silent=True) or {}


def _respond(action):
    try:
        return jsonify({'ok': True, 'project': action(get_db(), _today())})
    except svc.UnknownProject as e:
        return jsonify({'ok': False, 'error': str(e)}), 404
    except svc.ProjectError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception:
        logger.exception('housing project request failed')
        return jsonify({'ok': False, 'error': 'שגיאת שרת'}), 500


@housing_projects_bp.route('/api/housing/projects/<key>', methods=['GET'])
def project_get(key):
    return _respond(lambda db, today: svc.project_payload(db, key, today))


@housing_projects_bp.route('/api/housing/projects/<key>', methods=['POST'])
def project_update(key):
    body = _body()
    return _respond(lambda db, today: svc.update_project(db, key, body, today))


@housing_projects_bp.route('/api/housing/shabazi/tx-kinds', methods=['GET'])
def shabazi_tx_kinds():
    """{key: kind} of the user's choices for שבזי payments. The page asks for it fresh because the housing data
    it shows is cached for a while."""
    try:
        db = get_db()
        db.ensure_housing_project_tables()
        return jsonify({'ok': True, 'kinds': db.get_housing_tx_kinds(svc.SHABAZI)})
    except Exception:
        logger.exception('shabazi tx kinds failed')
        return jsonify({'ok': False, 'error': 'שגיאת שרת'}), 500


@housing_projects_bp.route('/api/housing/shabazi/tx-kind', methods=['POST'])
def shabazi_tx_kind():
    """{key, kind}: say that one שבזי payment went into the apartment's value (price) / is an expense (cost);
    kind null = back to the default."""
    body = _body()
    kind = body.get('kind')
    if not (kind is None or isinstance(kind, str)):
        return jsonify({'ok': False, 'error': 'בקשה לא תקינה'}), 400
    try:
        return jsonify({'ok': True, 'kinds': svc.set_shabazi_tx_kind(get_db(), body.get('key'), kind)})
    except svc.ProjectError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception:
        logger.exception('shabazi tx kind failed')
        return jsonify({'ok': False, 'error': 'שגיאת שרת'}), 500


@housing_projects_bp.route('/api/housing/projects/<key>/tx-kind', methods=['POST'])
def project_tx_kind(key):
    body = _body()
    tx_key, kind = body.get('key'), body.get('kind')
    if not isinstance(tx_key, str) or not (kind is None or isinstance(kind, str)):
        return jsonify({'ok': False, 'error': 'בקשה לא תקינה'}), 400
    return _respond(lambda db, today: svc.set_tx_kind(db, key, tx_key, kind, today))


def _info_respond(action):
    try:
        return jsonify({'ok': True, 'items': action(get_db())})
    except info_svc.UnknownApartment as e:
        return jsonify({'ok': False, 'error': str(e)}), 404
    except info_svc.InfoError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception:
        logger.exception('housing info request failed')
        return jsonify({'ok': False, 'error': 'שגיאת שרת'}), 500


@housing_projects_bp.route('/api/housing/info/<prop>', methods=['GET'])
def info_get(prop):
    return _info_respond(lambda db: info_svc.load_info(db, prop))


@housing_projects_bp.route('/api/housing/info/<prop>', methods=['PUT'])
def info_put(prop):
    items = _body().get('items')
    return _info_respond(lambda db: info_svc.save_info(db, prop, items))
