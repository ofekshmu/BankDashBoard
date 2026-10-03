"""Plant tracker service: validates input and orchestrates PlantStore + pure logic.

Every public mutator raises PlantError (status 400/404) on bad input; the routes
turn that into {ok: False, error}. `today` is always the client's local date.
"""
import re
from datetime import date, datetime, time, timedelta

from src_utils.plant_logic import (
    PLANT_TYPES, IRRIGATION_MODES, SOIL_STATUSES, EVENT_TYPES, TIMELINE_DAYS,
    materialize_rows, plant_status, season_key, timeline_window, build_summary,
)
from src_utils.plant_suggestions import build_suggestions

PALETTE = ['#1e9d8b', '#2f6fb0', '#7a5bc4', '#c2577a', '#d9822b', '#4f8a3c', '#b0503a', '#3b8f9e']
DEFAULT_AUTO_TIME = '07:00'
_LEVEL_ORDER = {'alert': 0, 'warn': 1, 'info': 2}
_HHMM = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
_HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


class PlantError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ── Parsing / validation ───────────────────────────────────────────────────
def _require_plant(store, pid):
    p = store.get_plant(pid)
    if not p or p['deleted_at']:
        raise PlantError('עציץ לא נמצא', 404)
    return p


def _parse_day(raw, today):
    try:
        d = date.fromisoformat(str(raw))
    except (TypeError, ValueError):
        raise PlantError('תאריך לא תקין')
    if d > today:
        raise PlantError('לא ניתן לעדכן יום עתידי')
    window_start = today - timedelta(days=TIMELINE_DAYS - 1)
    if d < window_start:
        raise PlantError('ניתן לעדכן רק את 14 הימים האחרונים')
    return d


def _parse_event_at(raw, today):
    if not raw:
        return datetime.combine(today, datetime.now().time()).replace(second=0, microsecond=0)
    try:
        dt = datetime.fromisoformat(str(raw))
    except ValueError:
        raise PlantError('זמן לא תקין')
    if dt.date() > today:
        raise PlantError('לא ניתן לרשום אירוע עתידי')
    window_start = today - timedelta(days=TIMELINE_DAYS - 1)
    if dt.date() < window_start:
        raise PlantError('ניתן לעדכן רק את 14 הימים האחרונים')
    return dt.replace(second=0, microsecond=0, tzinfo=None)


def _validate_fields(body, partial):
    f = {}
    if 'name' in body or not partial:
        name = str(body.get('name') or '').strip()
        if not name or len(name) > 40:
            raise PlantError('שם עציץ חייב להכיל 1-40 תווים')
        f['name'] = name
    if 'plant_type' in body or not partial:
        if body.get('plant_type') not in PLANT_TYPES:
            raise PlantError('סוג עציץ לא מוכר')
        f['plant_type'] = body['plant_type']
    if body.get('color') is not None:
        if not _HEX.match(str(body['color'])):
            raise PlantError('צבע לא תקין')
        f['color'] = body['color']
    if 'irrigation_mode' in body or not partial:
        mode = body.get('irrigation_mode') or 'manual'
        if mode not in IRRIGATION_MODES:
            raise PlantError('מצב השקיה לא מוכר')
        f['irrigation_mode'] = mode
    if 'interval_days' in body or not partial:
        try:
            n = int(body.get('interval_days', 3))
        except (TypeError, ValueError):
            raise PlantError('מרווח השקיה לא תקין')
        if not 1 <= n <= 60:
            raise PlantError('מרווח השקיה חייב להיות 1-60 ימים')
        f['interval_days'] = n
    if body.get('auto_time'):
        if not _HHMM.match(str(body['auto_time'])):
            raise PlantError('שעת השקיה לא תקינה')
        f['auto_time'] = body['auto_time']
    if 'season_ack' in body:
        f['season_ack'] = body['season_ack'] or None
    return f


# ── Plants ─────────────────────────────────────────────────────────────────
def create_plant(store, body, today):
    f = _validate_fields(body, partial=False)
    f.pop('season_ack', None)
    f.setdefault('color', PALETTE[store.count_plants() % len(PALETTE)])
    if f['irrigation_mode'] == 'auto':
        f.setdefault('auto_time', DEFAULT_AUTO_TIME)
    f['created_at'] = today
    return store.add_plant(f)


def update_plant(store, pid, body, today):
    p = _require_plant(store, pid)
    f = _validate_fields(body, partial=True)
    if f.get('irrigation_mode') == 'auto' and not (f.get('auto_time') or p['auto_time']):
        f['auto_time'] = DEFAULT_AUTO_TIME
    if 'interval_days' in f and f['interval_days'] != p['interval_days']:
        f['interval_changed_at'] = today  # suggestions only look at history after this day
    store.update_plant(pid, f)


def delete_plant(store, pid):
    _require_plant(store, pid)
    store.soft_delete_plant(pid)


def restore_plant(store, pid):
    if not store.get_plant(pid):
        raise PlantError('עציץ לא נמצא', 404)
    store.restore_plant(pid)


def deleted_plants(store):
    return [_plant_json(p) for p in store.list_plants(deleted=True)]


# ── Days / events ──────────────────────────────────────────────────────────
def _refresh_watered(store, pid, day):
    store.upsert_day(pid, day, watered=day in set(store.water_dates(pid)))


def add_event(store, pid, body, today):
    _require_plant(store, pid)
    etype = body.get('event_type')
    if etype not in EVENT_TYPES:
        raise PlantError('סוג אירוע לא מוכר')
    at = _parse_event_at(body.get('event_at'), today)
    note = str(body.get('note') or '').strip() or None
    if note and len(note) > 200:
        raise PlantError('הערה ארוכה מדי')
    eid = store.add_event(pid, etype, at, 'manual', note)
    if etype == 'water':
        _refresh_watered(store, pid, at.date())
    return eid


def delete_event(store, eid):
    e = store.get_event(eid)
    if not e:
        raise PlantError('אירוע לא נמצא', 404)
    store.delete_event(eid)
    day = e['event_at'].date()
    if e['event_type'] == 'water':
        _refresh_watered(store, e['plant_id'], day)
    if e['source'] == 'auto_confirmed':
        store.upsert_day(e['plant_id'], day, auto_confirmed=False)


def set_soil(store, pid, body, today):
    _require_plant(store, pid)
    day = _parse_day(body.get('day'), today)
    soil = body.get('soil_status') or None
    if soil is not None and soil not in SOIL_STATUSES:
        raise PlantError('מצב אדמה לא מוכר')
    store.upsert_day(pid, day, soil_status=soil)


def confirm_auto(store, pid, body, today):
    p = _require_plant(store, pid)
    if p['irrigation_mode'] != 'auto':
        raise PlantError('העציץ אינו בהשקיה אוטומטית')
    day = _parse_day(body.get('day'), today)
    hh, mm = (p['auto_time'] or DEFAULT_AUTO_TIME).split(':')
    store.add_event(pid, 'water', datetime.combine(day, time(int(hh), int(mm))), 'auto_confirmed', None)
    store.upsert_day(pid, day, watered=True, auto_confirmed=True)


def dismiss_season(store, pid, today):
    _require_plant(store, pid)
    key = season_key(today)
    if not key:
        raise PlantError('אין המלצה עונתית כרגע')
    store.update_plant(pid, {'season_ack': key})


def water_due(store, body, today):
    at = _parse_event_at(body.get('event_at'), today)
    plants = store.list_plants()
    lasts = store.last_event_dates([p['id'] for p in plants], today)
    count = 0
    for p in plants:
        if p['irrigation_mode'] == 'auto':
            continue  # watered by its own system; confirmed via confirm_auto
        _, status = plant_status(p, lasts.get(p['id'], {}).get('water'), today)
        if status in ('due', 'overdue'):
            store.add_event(p['id'], 'water', at, 'manual', None)
            _refresh_watered(store, p['id'], at.date())
            count += 1
    return count


# ── Daily materialization + payload ────────────────────────────────────────
def materialize(store, today):
    """Insert the missing PlantDays rows (through today) for every active plant."""
    plants = store.list_plants()
    lasts = store.last_materialized_days([p['id'] for p in plants])
    rows = []
    for p in plants:
        last = lasts.get(p['id'])
        if last is not None and last >= today:
            continue
        rows.extend(materialize_rows(p, last, today, set(store.water_dates(p['id']))))
    store.insert_days(rows)


def _plant_json(p, last_water=None, since=None, status=None):
    return {'id': p['id'], 'name': p['name'], 'plant_type': p['plant_type'], 'color': p['color'],
            'irrigation_mode': p['irrigation_mode'], 'interval_days': p['interval_days'],
            'auto_time': p['auto_time'], 'season_ack': p['season_ack'],
            'created_at': p['created_at'].isoformat(),
            'last_water': last_water.isoformat() if last_water else None,
            'days_since_water': since, 'status': status}


def _day_json(r):
    return {'day': r['day'].isoformat(), 'soil_status': r['soil_status'], 'watered': bool(r['watered']),
            'auto_expected': bool(r['auto_expected']), 'auto_confirmed': bool(r['auto_confirmed'])}


def _event_json(e):
    return {'id': e['id'], 'event_type': e['event_type'], 'event_at': e['event_at'].strftime('%Y-%m-%dT%H:%M'),
            'source': e['source'], 'note': e['note']}


def build_payload(store, today):
    materialize(store, today)
    plants = store.list_plants()
    ids = [p['id'] for p in plants]
    window = timeline_window(today)
    days = store.get_days(ids, window[0], today)
    events = store.get_events(ids, window[0], today)
    lasts = store.last_event_dates(ids, today)
    out, suggestions = [], []
    for p in plants:
        le = lasts.get(p['id'], {})
        since, status = plant_status(p, le.get('water'), today)
        if p['irrigation_mode'] == 'auto':
            status = 'auto'  # no due/overdue for plants watered by their own system
        out.append(_plant_json(p, le.get('water'), since, status))
        suggestions.extend(build_suggestions(p, days.get(p['id'], []), le, today))
    suggestions.sort(key=lambda s: _LEVEL_ORDER[s['level']])
    return {
        'ok': True,
        'today': today.isoformat(),
        'window': [d.isoformat() for d in window],
        'plants': out,
        'days': {str(pid): [_day_json(r) for r in rows] for pid, rows in days.items()},
        'events': {str(pid): [_event_json(e) for e in evs] for pid, evs in events.items()},
        'suggestions': suggestions,
        'summary': build_summary(out, days, today),
    }
