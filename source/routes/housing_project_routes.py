"""JSON API of the housing projects (new-build apartments such as Mona) — shown as a tab on /housing.

GET  /api/housing/projects/<key>            the whole project (settings, money, statistics, payments, events)
POST /api/housing/projects/<key>            change settings: price, down_pct, growth_pct, contract_date,
                                            delivery_date, tx_category
POST /api/housing/projects/<key>/tx-kind    {key, kind}: mark one payment as price/cost (outgoing) or
                                            income/refund (incoming); kind null = automatic

Every endpoint answers {ok, project} so the page can replace its copy in one round trip.
"""
import logging
from datetime import date

from flask import Blueprint, jsonify, request

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


@housing_projects_bp.route('/api/housing/projects/<key>/tx-kind', methods=['POST'])
def project_tx_kind(key):
    body = _body()
    tx_key, kind = body.get('key'), body.get('kind')
    if not isinstance(tx_key, str) or not (kind is None or isinstance(kind, str)):
        return jsonify({'ok': False, 'error': 'בקשה לא תקינה'}), 400
    return _respond(lambda db, today: svc.set_tx_kind(db, key, tx_key, kind, today))
