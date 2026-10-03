"""PostgreSQL persistence for the plant tracker (Plants / PlantRooms / PlantEvents / PlantDays).

The only module with plant SQL. `autocommit=False` lets tests run inside a
transaction they roll back.
"""

# Seeded into an empty PlantRooms table, in this display order.
DEFAULT_ROOMS = ('סלון', 'מטבח', 'חדר שינה', 'חדר עבודה', 'מרפסת', 'אמבטיה')

_PLANT_COLS = ('ID, Name, Plant_Type, Color, Irrigation_Mode, Interval_Days, '
               'Auto_Time, Season_Ack, Created_At, Deleted_At, Interval_Changed_At, Room_ID, Config_ID')
_PLANT_UPDATABLE = {
    'name': 'Name', 'plant_type': 'Plant_Type', 'color': 'Color',
    'irrigation_mode': 'Irrigation_Mode', 'interval_days': 'Interval_Days',
    'auto_time': 'Auto_Time', 'season_ack': 'Season_Ack', 'interval_changed_at': 'Interval_Changed_At',
    'room_id': 'Room_ID', 'config_id': 'Config_ID',
}
_DAY_UPDATABLE = {'soil_status': 'Soil_Status', 'watered': 'Watered', 'auto_confirmed': 'Auto_Confirmed'}
_EVENT_COLS = 'ID, Plant_ID, Event_Type, Event_At, Source, Note'
_ROOM_COLS = 'ID, Name, Sort_Order, Deleted_At'
_CONFIG_COLS = 'ID, Name, Style, Interval_Days, Weekdays, Water_Time, Deleted_At'
_CONFIG_UPDATABLE = {'name': 'Name', 'style': 'Style', 'interval_days': 'Interval_Days',
                     'weekdays': 'Weekdays', 'time': 'Water_Time'}


def _plant(r):
    return {'id': r[0], 'name': r[1], 'plant_type': r[2], 'color': r[3],
            'irrigation_mode': r[4], 'interval_days': r[5], 'auto_time': r[6],
            'season_ack': r[7], 'created_at': r[8], 'deleted_at': r[9],
            'interval_changed_at': r[10], 'room_id': r[11], 'config_id': r[12]}


def _room(r):
    return {'id': r[0], 'name': r[1], 'sort_order': r[2], 'deleted_at': r[3]}


def _config(r):
    return {'id': r[0], 'name': r[1], 'style': r[2], 'interval_days': r[3],
            'weekdays': [int(x) for x in r[4].split(',')] if r[4] else [],
            'time': r[5], 'deleted_at': r[6]}


def _weekdays_sql(f):
    """Weekdays are stored as text, e.g. '0,3' (Sun=0)."""
    if 'weekdays' in f:
        f = dict(f, weekdays=','.join(str(d) for d in f['weekdays'] or []) or None)
    return f


def _event(r):
    return {'id': r[0], 'plant_id': r[1], 'event_type': r[2], 'event_at': r[3],
            'source': r[4], 'note': r[5]}


class PlantStore:
    _ready = False

    def __init__(self, db, autocommit=True):
        self.db = db
        self.autocommit = autocommit

    def _q(self, sql, params=()):
        return self.db.cursor.execute(sql, params)

    def _commit(self):
        if self.autocommit:
            self.db.connection.commit()

    def ensure(self):
        """Create the plant tables if missing (idempotent, once per process)."""
        if PlantStore._ready:
            return
        self._q("""
            CREATE TABLE IF NOT EXISTS Plants (
                ID              SERIAL    PRIMARY KEY,
                Name            TEXT      NOT NULL,
                Plant_Type      TEXT      NOT NULL,
                Color           TEXT      NOT NULL,
                Irrigation_Mode TEXT      NOT NULL DEFAULT 'manual',
                Interval_Days   INTEGER   NOT NULL DEFAULT 3,
                Auto_Time       TEXT,
                Season_Ack      TEXT,
                Created_At      DATE      NOT NULL DEFAULT CURRENT_DATE,
                Deleted_At      TIMESTAMP
            )
        """)
        self._q("""
            CREATE TABLE IF NOT EXISTS PlantRooms (
                ID         SERIAL    PRIMARY KEY,
                Name       TEXT      NOT NULL,
                Sort_Order INTEGER   NOT NULL DEFAULT 0,
                Deleted_At TIMESTAMP
            )
        """)
        if self._q('SELECT COUNT(*) FROM PlantRooms').fetchone()[0] == 0:
            for i, name in enumerate(DEFAULT_ROOMS):
                self._q('INSERT INTO PlantRooms (Name, Sort_Order) VALUES (%s, %s)', (name, i))
        # Plants already exist in production, so newer columns are added in place.
        self._q("ALTER TABLE Plants ADD COLUMN IF NOT EXISTS Interval_Changed_At DATE")
        self._q("ALTER TABLE Plants ADD COLUMN IF NOT EXISTS Room_ID INTEGER REFERENCES PlantRooms(ID)")
        self._q("""
            CREATE TABLE IF NOT EXISTS IrrigationConfigs (
                ID            SERIAL    PRIMARY KEY,
                Name          TEXT      NOT NULL,
                Style         TEXT      NOT NULL,
                Interval_Days INTEGER,
                Weekdays      TEXT,
                Water_Time    TEXT      NOT NULL,
                Deleted_At    TIMESTAMP
            )
        """)
        self._q("ALTER TABLE Plants ADD COLUMN IF NOT EXISTS Config_ID INTEGER REFERENCES IrrigationConfigs(ID)")
        self._q("""
            CREATE TABLE IF NOT EXISTS PlantEvents (
                ID          SERIAL    PRIMARY KEY,
                Plant_ID    INTEGER   NOT NULL REFERENCES Plants(ID) ON DELETE CASCADE,
                Event_Type  TEXT      NOT NULL,
                Event_At    TIMESTAMP NOT NULL,
                Source      TEXT      NOT NULL DEFAULT 'manual',
                Note        TEXT
            )
        """)
        self._q("CREATE INDEX IF NOT EXISTS idx_plantevents_plant_at ON PlantEvents (Plant_ID, Event_At)")
        self._q("""
            CREATE TABLE IF NOT EXISTS PlantDays (
                Plant_ID       INTEGER NOT NULL REFERENCES Plants(ID) ON DELETE CASCADE,
                Day            DATE    NOT NULL,
                Soil_Status    TEXT,
                Watered        BOOLEAN NOT NULL DEFAULT FALSE,
                Auto_Expected  BOOLEAN NOT NULL DEFAULT FALSE,
                Auto_Confirmed BOOLEAN NOT NULL DEFAULT FALSE,
                PRIMARY KEY (Plant_ID, Day)
            )
        """)
        self._commit()
        if self.autocommit:
            PlantStore._ready = True

    # ── Plants ──────────────────────────────────────────────────────────────
    def list_plants(self, deleted=False):
        cond = 'IS NOT NULL' if deleted else 'IS NULL'
        rows = self._q(f'SELECT {_PLANT_COLS} FROM Plants WHERE Deleted_At {cond} ORDER BY ID').fetchall()
        return [_plant(r) for r in rows]

    def get_plant(self, pid):
        r = self._q(f'SELECT {_PLANT_COLS} FROM Plants WHERE ID=%s', (pid,)).fetchone()
        return _plant(r) if r else None

    def count_plants(self):
        return self._q('SELECT COUNT(*) FROM Plants').fetchone()[0]

    def add_plant(self, f):
        r = self._q(
            'INSERT INTO Plants (Name, Plant_Type, Color, Irrigation_Mode, Interval_Days, Auto_Time, '
            'Created_At, Room_ID, Config_ID) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING ID',
            (f['name'], f['plant_type'], f['color'], f['irrigation_mode'],
             f['interval_days'], f.get('auto_time'), f['created_at'], f.get('room_id'), f.get('config_id'))
        ).fetchone()
        self._commit()
        return r[0]

    def update_plant(self, pid, f):
        cols = [(col, f[key]) for key, col in _PLANT_UPDATABLE.items() if key in f]
        if not cols:
            return
        sets = ', '.join(f'{col}=%s' for col, _ in cols)
        self._q(f'UPDATE Plants SET {sets} WHERE ID=%s', tuple(v for _, v in cols) + (pid,))
        self._commit()

    def soft_delete_plant(self, pid):
        self._q('UPDATE Plants SET Deleted_At=CURRENT_TIMESTAMP WHERE ID=%s', (pid,))
        self._commit()

    def restore_plant(self, pid):
        self._q('UPDATE Plants SET Deleted_At=NULL WHERE ID=%s', (pid,))
        self._commit()

    # ── Rooms ───────────────────────────────────────────────────────────────
    def list_rooms(self, deleted=False):
        cond = 'IS NOT NULL' if deleted else 'IS NULL'
        rows = self._q(f'SELECT {_ROOM_COLS} FROM PlantRooms WHERE Deleted_At {cond} '
                       'ORDER BY Sort_Order, ID').fetchall()
        return [_room(r) for r in rows]

    def get_room(self, rid):
        r = self._q(f'SELECT {_ROOM_COLS} FROM PlantRooms WHERE ID=%s', (rid,)).fetchone()
        return _room(r) if r else None

    def add_room(self, name):
        r = self._q('INSERT INTO PlantRooms (Name, Sort_Order) '
                    'SELECT %s, COALESCE(MAX(Sort_Order), -1) + 1 FROM PlantRooms RETURNING ID',
                    (name,)).fetchone()
        self._commit()
        return r[0]

    def rename_room(self, rid, name):
        self._q('UPDATE PlantRooms SET Name=%s WHERE ID=%s', (name, rid))
        self._commit()

    def soft_delete_room(self, rid):
        self._q('UPDATE PlantRooms SET Deleted_At=CURRENT_TIMESTAMP WHERE ID=%s', (rid,))
        self._commit()

    def restore_room(self, rid):
        self._q('UPDATE PlantRooms SET Deleted_At=NULL WHERE ID=%s', (rid,))
        self._commit()

    # ── Irrigation configs ──────────────────────────────────────────────────
    def list_configs(self, deleted=False):
        cond = 'IS NOT NULL' if deleted else 'IS NULL'
        rows = self._q(f'SELECT {_CONFIG_COLS} FROM IrrigationConfigs WHERE Deleted_At {cond} ORDER BY ID').fetchall()
        return [_config(r) for r in rows]

    def get_config(self, cid):
        r = self._q(f'SELECT {_CONFIG_COLS} FROM IrrigationConfigs WHERE ID=%s', (cid,)).fetchone()
        return _config(r) if r else None

    def add_config(self, f):
        f = _weekdays_sql(f)
        r = self._q('INSERT INTO IrrigationConfigs (Name, Style, Interval_Days, Weekdays, Water_Time) '
                    'VALUES (%s, %s, %s, %s, %s) RETURNING ID',
                    (f['name'], f['style'], f.get('interval_days'), f.get('weekdays'), f['time'])).fetchone()
        self._commit()
        return r[0]

    def update_config(self, cid, f):
        f = _weekdays_sql(f)
        cols = [(col, f[key]) for key, col in _CONFIG_UPDATABLE.items() if key in f]
        if not cols:
            return
        sets = ', '.join(f'{col}=%s' for col, _ in cols)
        self._q(f'UPDATE IrrigationConfigs SET {sets} WHERE ID=%s', tuple(v for _, v in cols) + (cid,))
        self._commit()

    def soft_delete_config(self, cid):
        self._q('UPDATE IrrigationConfigs SET Deleted_At=CURRENT_TIMESTAMP WHERE ID=%s', (cid,))
        self._commit()

    # ── Days ────────────────────────────────────────────────────────────────
    def last_materialized_days(self, ids):
        if not ids:
            return {}
        rows = self._q('SELECT Plant_ID, MAX(Day) FROM PlantDays WHERE Plant_ID = ANY(%s) GROUP BY Plant_ID',
                       (list(ids),)).fetchall()
        return {r[0]: r[1] for r in rows}

    def insert_days(self, rows):
        if not rows:
            return
        placeholders = ', '.join(['(%s, %s, %s, %s, %s, %s)'] * len(rows))
        params = []
        for r in rows:
            params += [r['plant_id'], r['day'], r['soil_status'], r['watered'],
                       r['auto_expected'], r['auto_confirmed']]
        self._q('INSERT INTO PlantDays (Plant_ID, Day, Soil_Status, Watered, Auto_Expected, Auto_Confirmed) '
                f'VALUES {placeholders} ON CONFLICT (Plant_ID, Day) DO NOTHING', tuple(params))
        self._commit()

    def get_days(self, ids, start, end):
        if not ids:
            return {}
        rows = self._q(
            'SELECT Plant_ID, Day, Soil_Status, Watered, Auto_Expected, Auto_Confirmed FROM PlantDays '
            'WHERE Plant_ID = ANY(%s) AND Day BETWEEN %s AND %s ORDER BY Plant_ID, Day',
            (list(ids), start, end)
        ).fetchall()
        out = {}
        for r in rows:
            out.setdefault(r[0], []).append({'day': r[1], 'soil_status': r[2], 'watered': r[3],
                                             'auto_expected': r[4], 'auto_confirmed': r[5]})
        return out

    def upsert_day(self, pid, day, **fields):
        cols = [(col, fields[key]) for key, col in _DAY_UPDATABLE.items() if key in fields]
        if not cols:
            return
        names = ', '.join(col for col, _ in cols)
        marks = ', '.join(['%s'] * len(cols))
        updates = ', '.join(f'{col}=EXCLUDED.{col}' for col, _ in cols)
        self._q(f'INSERT INTO PlantDays (Plant_ID, Day, {names}) VALUES (%s, %s, {marks}) '
                f'ON CONFLICT (Plant_ID, Day) DO UPDATE SET {updates}',
                (pid, day) + tuple(v for _, v in cols))
        self._commit()

    # ── Events ──────────────────────────────────────────────────────────────
    def add_event(self, pid, event_type, event_at, source, note):
        r = self._q('INSERT INTO PlantEvents (Plant_ID, Event_Type, Event_At, Source, Note) '
                    'VALUES (%s, %s, %s, %s, %s) RETURNING ID',
                    (pid, event_type, event_at, source, note)).fetchone()
        self._commit()
        return r[0]

    def get_event(self, eid):
        r = self._q(f'SELECT {_EVENT_COLS} FROM PlantEvents WHERE ID=%s', (eid,)).fetchone()
        return _event(r) if r else None

    def delete_event(self, eid):
        self._q('DELETE FROM PlantEvents WHERE ID=%s', (eid,))
        self._commit()

    def get_events(self, ids, start, end):
        if not ids:
            return {}
        rows = self._q(f'SELECT {_EVENT_COLS} FROM PlantEvents '
                       'WHERE Plant_ID = ANY(%s) AND Event_At::date BETWEEN %s AND %s ORDER BY Event_At, ID',
                       (list(ids), start, end)).fetchall()
        out = {}
        for r in rows:
            out.setdefault(r[1], []).append(_event(r))
        return out

    def water_dates(self, pid):
        rows = self._q("SELECT DISTINCT Event_At::date FROM PlantEvents "
                       "WHERE Plant_ID=%s AND Event_Type='water' ORDER BY 1", (pid,)).fetchall()
        return [r[0] for r in rows]

    def last_event_dates(self, ids, today):
        if not ids:
            return {}
        rows = self._q('SELECT Plant_ID, Event_Type, MAX(Event_At)::date FROM PlantEvents '
                       'WHERE Plant_ID = ANY(%s) AND Event_At::date <= %s GROUP BY Plant_ID, Event_Type',
                       (list(ids), today)).fetchall()
        out = {}
        for pid, etype, d in rows:
            out.setdefault(pid, {})[etype] = d
        return out
