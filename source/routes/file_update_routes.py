"""Updating a stored credit-card file with a newer copy (the logic is in file_update_service.py).

POST /api/files/analyze       {filename, existing?}              read-only report: status, counts, layout, rows
POST /api/files/apply-update  {filename, mode, existing?}        mode 'update' | 'replace'

WebApp.py calls init() with its folders and its insert lock (so an update never runs next to an insert)
and the function that finishes an insertion (withdrawal matching + auto-tagging of the new rows).
"""
import logging

from flask import Blueprint, jsonify, request

import file_update_service as svc

logger = logging.getLogger(__name__)

file_update_bp = Blueprint('file_update', __name__)

_cfg = {'folders': None, 'lock': None, 'finish': None}


def init(folders, lock, finish):
    """folders: file_update_service.Folders; lock: threading.Lock; finish(): runs after a change."""
    _cfg.update(folders=folders, lock=lock, finish=finish)


def get_db():
    """The database. Tests monkeypatch this with an in-memory fake."""
    from database import DataBase
    return DataBase()


def get_reader():
    """Reads a file with Excel. Tests monkeypatch this."""
    return svc.read_new_file


def get_header_reader():
    """Reads a table's header cells with Excel. Tests monkeypatch this."""
    return svc.read_header_cells


def _body():
    return request.get_json(silent=True) or {}


def _names(body):
    name = body.get('filename')
    existing = body.get('existing')
    if not isinstance(name, str) or not name.strip() or '/' in name or '\\' in name:
        return None, None
    return name.strip(), existing.strip() if isinstance(existing, str) and existing.strip() else None


def _format_of(name):
    """The format of the file `name` in the input folder.

    Parser keeps the answers of its last folder scan, but it skips a file whose name is contained in another
    file's ("x.xlsx" next to "x (1).xlsx"), so a missing answer is not "unrecognised": the one file is
    identified on its own."""
    import builtins
    from Parser import Parser
    real_input = builtins.input
    builtins.input = lambda *a, **k: '1'          # Parser asks questions on the terminal; the web has no terminal
    try:
        parser = Parser.getInstance()
        fmt = parser.name_to_type.get(name)
        if not fmt:
            fmt, _ = parser._Parser__identify(name)
        return fmt
    finally:
        builtins.input = real_input


def _run(work):
    lock = _cfg['lock']
    if lock is not None and not lock.acquire(blocking=False):
        return jsonify({'ok': False, 'error': 'כבר מתבצע עיבוד, נסה שוב בעוד רגע'}), 409
    try:
        return jsonify({'ok': True, **work()})
    except svc.NothingToCompare as e:
        return jsonify({'ok': False, 'error': str(e), 'nothing_to_compare': True}), 404
    except svc.UpdateError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception('file update request failed')
        return jsonify({'ok': False, 'error': f'שגיאה: {str(e)[:200] or type(e).__name__}'}), 500
    finally:
        if lock is not None:
            lock.release()


@file_update_bp.route('/api/files/analyze', methods=['POST'])
def analyze():
    name, existing = _names(_body())
    if not name:
        return jsonify({'ok': False, 'error': 'שם קובץ חסר'}), 400

    def work():
        fmt = _format_of(name)
        if not fmt:
            raise svc.UpdateError('הקובץ לא מזוהה')
        return {'report': svc.analyze(get_db(), get_reader(), name, fmt, _cfg['folders'], existing, get_header_reader())}
    return _run(work)


@file_update_bp.route('/api/files/apply-update', methods=['POST'])
def apply_update():
    body = _body()
    name, existing = _names(body)
    mode = body.get('mode')
    if not name or mode not in ('update', 'replace'):
        return jsonify({'ok': False, 'error': 'בקשה לא תקינה'}), 400

    def work():
        fmt = _format_of(name)
        if not fmt:
            raise svc.UpdateError('הקובץ לא מזוהה')
        result = svc.apply(get_db(), get_reader(), name, fmt, _cfg['folders'], mode, existing)
        finish = _cfg['finish']
        if finish:
            try:
                finish()
            except Exception:
                logger.exception('post-update processing failed')
                result['warnings'] = result.get('warnings', []) + ['העדכון נשמר, אך תיוג אוטומטי של הפעולות החדשות נכשל']
        return result
    return _run(work)
