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
DEATH_CAUSES = ('overwater', 'underwater', 'pests', 'temperature', 'unknown')


def _require_plant(store, pid):
    """A living plant (deleted and dead plants count as not found)."""
    p = store.get_plant(pid)
    if not p or p['deleted_at'] or p.get('died_at'):
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


def _room_field(store, body, f):
    """Validate an optional `room_id` from the body into `f` (None = no room)."""
    if 'room_id' not in body:
        return
    raw = body['room_id']
    if raw in (None, ''):
        f['room_id'] = None
        return
    try:
        rid = int(raw)
    except (TypeError, ValueError):
        raise PlantError('חדר לא קיים')
    room = store.get_room(rid)
    if not room or room['deleted_at']:
        raise PlantError('חדר לא קיים')
    f['room_id'] = rid


# ── Plants ─────────────────────────────────────────────────────────────────
def _config_field(store, body, f):
    """Validate an optional `config_id`: a config makes the plant automatic; manual clears it."""
    if 'config_id' in body:
        raw = body['config_id']
        if raw in (None, ''):
            f['config_id'] = None
        else:
            _require_config(store, raw, status=400)
            f['config_id'] = int(raw)
            f['irrigation_mode'] = 'auto'
    if f.get('irrigation_mode') == 'manual':
        f['config_id'] = None


def create_plant(store, body, today):
    f = _validate_fields(body, partial=False)
    _room_field(store, body, f)
    _config_field(store, body, f)
    f.pop('season_ack', None)
    f.setdefault('color', PALETTE[store.count_plants() % len(PALETTE)])
    if f['irrigation_mode'] == 'auto':
        f.setdefault('auto_time', DEFAULT_AUTO_TIME)
    f['created_at'] = today
    return store.add_plant(f)


def update_plant(store, pid, body, today):
    p = _require_plant(store, pid)
    f = _validate_fields(body, partial=True)
    _room_field(store, body, f)
    _config_field(store, body, f)
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


# ── Dead plants → archive ──────────────────────────────────────────────────
def mark_dead(store, pid, body, today):
    _require_plant(store, pid)
    raw = body.get('died_at')
    try:
        died = date.fromisoformat(str(raw)) if raw else today
    except ValueError:
        raise PlantError('תאריך לא תקין')
    if died > today:
        raise PlantError('לא ניתן לסמן תאריך עתידי')
    cause = body.get('cause') or 'unknown'
    if cause not in DEATH_CAUSES:
        raise PlantError('סיבה לא מוכרת')
    note = str(body.get('note') or '').strip() or None
    if note and len(note) > 200:
        raise PlantError('הערה ארוכה מדי')
    store.update_plant(pid, {'died_at': died, 'death_cause': cause, 'death_note': note})


def revive(store, pid):
    p = store.get_plant(pid)
    if not p or p['deleted_at']:
        raise PlantError('עציץ לא נמצא', 404)
    if not p.get('died_at'):
        raise PlantError('העציץ אינו בארכיון')
    store.update_plant(pid, {'died_at': None, 'death_cause': None, 'death_note': None})


def archive(store):
    """Dead plants, newest death first, with lifespan and watering history."""
    active_rooms = _active_room_ids(store)
    out = []
    for p in store.list_dead_plants():
        water = store.water_dates(p['id'])
        item = _plant_json(p, max(water) if water else None, active_rooms=active_rooms)
        item.update({'died_at': p['died_at'].isoformat(), 'cause': p['death_cause'], 'note': p['death_note'],
                     'lifespan_days': (p['died_at'] - p['created_at']).days, 'waterings': len(water)})
        out.append(item)
    return out


def deleted_plants(store):
    active = _active_room_ids(store)
    return [_plant_json(p, active_rooms=active) for p in store.list_plants(deleted=True)]


# ── Rooms ──────────────────────────────────────────────────────────────────
def _require_room(store, rid, active=True):
    room = store.get_room(rid)
    if not room or (active and room['deleted_at']):
        raise PlantError('חדר לא נמצא', 404)
    return room


def _room_name(store, body, exclude_id=None):
    name = str(body.get('name') or '').strip()
    if not name or len(name) > 30:
        raise PlantError('שם חדר חייב להכיל 1-30 תווים')
    if any(r['name'] == name and r['id'] != exclude_id for r in store.list_rooms()):
        raise PlantError('קיים כבר חדר בשם זה')
    return name


def _active_room_ids(store):
    return {r['id'] for r in store.list_rooms()}


def create_room(store, body):
    return store.add_room(_room_name(store, body))


def rename_room(store, rid, body):
    _require_room(store, rid)
    store.rename_room(rid, _room_name(store, body, exclude_id=rid))


def delete_room(store, rid):
    """Soft delete: its plants show as unassigned until the room is restored."""
    _require_room(store, rid)
    store.soft_delete_room(rid)


def restore_room(store, rid):
    room = _require_room(store, rid, active=False)
    if any(r['name'] == room['name'] for r in store.list_rooms()):
        raise PlantError('קיים כבר חדר בשם זה')
    store.restore_room(rid)


def deleted_rooms(store):
    return [_room_json(r) for r in store.list_rooms(deleted=True)]


def rooms_overview(store):
    """Active and soft-deleted rooms, for the room manager."""
    return {'rooms': [_room_json(r) for r in store.list_rooms()], 'deleted': deleted_rooms(store)}


def _room_json(r):
    return {'id': r['id'], 'name': r['name']}


# ── Irrigation configs (shared schedules for automatic plants) ─────────────
CONFIG_STYLES = ('interval', 'weekdays')


def _require_config(store, cid, status=404):
    try:
        cfg = store.get_config(int(cid))
    except (TypeError, ValueError):
        cfg = None
    if not cfg or cfg['deleted_at']:
        raise PlantError('תוכנית השקיה לא נמצאה', status)
    return cfg


def _config_fields(store, body, current=None):
    """Validated config fields, normalised so an interval config has no weekdays and vice versa."""
    f = {}
    if 'name' in body or current is None:
        name = str(body.get('name') or '').strip()
        if not name or len(name) > 30:
            raise PlantError('שם תוכנית חייב להכיל 1-30 תווים')
        if any(c['name'] == name and c['id'] != (current or {}).get('id') for c in store.list_configs()):
            raise PlantError('קיימת כבר תוכנית בשם זה')
        f['name'] = name
    if 'style' in body or current is None:
        style = body.get('style') or 'interval'
        if style not in CONFIG_STYLES:
            raise PlantError('סוג תוכנית לא מוכר')
        f['style'] = style
    if 'interval_days' in body:
        try:
            f['interval_days'] = int(body['interval_days'])
        except (TypeError, ValueError):
            raise PlantError('מרווח השקיה לא תקין')
    if 'weekdays' in body:
        days = body['weekdays'] or []
        if not isinstance(days, list) or not all(isinstance(d, int) and 0 <= d <= 6 for d in days):
            raise PlantError('ימי השקיה לא תקינים')
        f['weekdays'] = sorted(set(days))
    if 'time' in body or current is None:
        t = body.get('time') or DEFAULT_AUTO_TIME
        if not _HHMM.match(str(t)):
            raise PlantError('שעת השקיה לא תקינה')
        f['time'] = t

    merged = dict(current or {}, **f)
    if merged['style'] == 'interval':
        if not isinstance(merged.get('interval_days'), int) or not 1 <= merged['interval_days'] <= 60:
            raise PlantError('מרווח השקיה חייב להיות 1-60 ימים')
        f['interval_days'], f['weekdays'] = merged['interval_days'], []
    else:
        if not merged.get('weekdays'):
            raise PlantError('יש לבחור לפחות יום אחד')
        f['interval_days'], f['weekdays'] = None, merged['weekdays']
    return f


def _plants_on(store, cid):
    return [p for p in store.list_plants() if p['irrigation_mode'] == 'auto' and p.get('config_id') == cid]


def _assign_plants(store, cid, plant_ids):
    """Exactly these plants use the config: they become automatic, others on it go back to manual."""
    if not isinstance(plant_ids, list):
        raise PlantError('רשימת עציצים לא תקינה')
    wanted = set()
    for pid in plant_ids:
        try:
            wanted.add(_require_plant(store, int(pid))['id'])
        except (TypeError, ValueError):
            raise PlantError('רשימת עציצים לא תקינה')
    for p in _plants_on(store, cid):
        if p['id'] not in wanted:
            store.update_plant(p['id'], {'irrigation_mode': 'manual', 'config_id': None})
    for pid in wanted:
        store.update_plant(pid, {'irrigation_mode': 'auto', 'config_id': cid})


def create_config(store, body, today):
    cid = store.add_config(_config_fields(store, body))
    if 'plant_ids' in body:
        _assign_plants(store, cid, body['plant_ids'])
    return cid


def update_config(store, cid, body, today):
    """Changes apply to every plant on the config from the next materialized day on."""
    current = _require_config(store, cid)
    store.update_config(current['id'], _config_fields(store, body, current))
    if 'plant_ids' in body:
        _assign_plants(store, current['id'], body['plant_ids'])


def delete_config(store, cid):
    cfg = _require_config(store, cid)
    in_use = len(_plants_on(store, cfg['id']))
    if in_use:
        raise PlantError(f'התוכנית בשימוש ב-{in_use} עציצים — העבירו אותם לתוכנית אחרת או להשקיה ידנית')
    store.soft_delete_config(cfg['id'])


def _config_json(c, plants):
    return {'id': c['id'], 'name': c['name'], 'style': c['style'], 'interval_days': c['interval_days'],
            'weekdays': c['weekdays'] or [], 'time': c['time'],
            'plant_count': sum(1 for p in plants if p['irrigation_mode'] == 'auto' and p.get('config_id') == c['id'])}


def configs_overview(store):
    plants = store.list_plants()
    return {'configs': [_config_json(c, plants) for c in store.list_configs()]}


def _plant_config(p, configs_by_id):
    """The active config an automatic plant follows, else None (it then uses its own interval)."""
    if p['irrigation_mode'] != 'auto':
        return None
    return configs_by_id.get(p.get('config_id'))


def _schedule(cfg):
    if not cfg:
        return None
    return {'style': cfg['style'], 'interval_days': cfg['interval_days'],
            'weekdays': cfg['weekdays'] or [], 'time': cfg['time']}


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
    cfg = _plant_config(p, {c['id']: c for c in store.list_configs()})
    hh, mm = ((cfg or {}).get('time') or p['auto_time'] or DEFAULT_AUTO_TIME).split(':')
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
    configs = {c['id']: c for c in store.list_configs()}
    rows = []
    for p in plants:
        last = lasts.get(p['id'])
        if last is not None and last >= today:
            continue
        rows.extend(materialize_rows(p, last, today, set(store.water_dates(p['id'])),
                                     _schedule(_plant_config(p, configs))))
    store.insert_days(rows)


def _plant_json(p, last_water=None, since=None, status=None, active_rooms=(), cfg=None):
    room_id = p.get('room_id')
    return {'id': p['id'], 'name': p['name'], 'plant_type': p['plant_type'], 'color': p['color'],
            'irrigation_mode': p['irrigation_mode'], 'interval_days': p['interval_days'],
            'auto_time': p['auto_time'], 'season_ack': p['season_ack'],
            'created_at': p['created_at'].isoformat(),
            'last_water': last_water.isoformat() if last_water else None,
            'days_since_water': since, 'status': status,
            # a plant in a deleted room shows as unassigned until the room is restored
            'room_id': room_id if room_id in active_rooms else None,
            'config_id': cfg['id'] if cfg else None}


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
    rooms = store.list_rooms()
    active_rooms = {r['id'] for r in rooms}
    configs = store.list_configs()
    configs_by_id = {c['id']: c for c in configs}
    out, suggestions = [], []
    for p in plants:
        le = lasts.get(p['id'], {})
        since, status = plant_status(p, le.get('water'), today)
        if p['irrigation_mode'] == 'auto':
            status = 'auto'  # no due/overdue for plants watered by their own system
        cfg = _plant_config(p, configs_by_id)
        out.append(_plant_json(p, le.get('water'), since, status, active_rooms, cfg))
        sugg_plant = dict(p, config_name=cfg['name']) if cfg else p
        suggestions.extend(build_suggestions(sugg_plant, days.get(p['id'], []), le, today))
    suggestions.sort(key=lambda s: _LEVEL_ORDER[s['level']])
    return {
        'ok': True,
        'today': today.isoformat(),
        'window': [d.isoformat() for d in window],
        'plants': out,
        'rooms': [_room_json(r) for r in rooms],
        'configs': [_config_json(c, plants) for c in configs],
        'days': {str(pid): [_day_json(r) for r in rows] for pid, rows in days.items()},
        'events': {str(pid): [_event_json(e) for e in evs] for pid, evs in events.items()},
        'suggestions': suggestions,
        'summary': build_summary(out, days, today),
    }
