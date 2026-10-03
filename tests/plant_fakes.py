"""In-memory stand-in for plant_store.PlantStore — same methods and return shapes."""
from datetime import datetime

_DAY_KEYS = ('day', 'soil_status', 'watered', 'auto_expected', 'auto_confirmed')


class FakePlantStore:
    def __init__(self):
        self.plants, self.days, self.events = {}, {}, {}
        self._next_plant = 1
        self._next_event = 1

    def ensure(self):
        pass

    def list_plants(self, deleted=False):
        return [dict(p) for p in sorted(self.plants.values(), key=lambda p: p['id'])
                if bool(p['deleted_at']) == deleted]

    def get_plant(self, pid):
        p = self.plants.get(pid)
        return dict(p) if p else None

    def count_plants(self):
        return len(self.plants)

    def add_plant(self, f):
        pid = self._next_plant
        self._next_plant += 1
        self.plants[pid] = {'id': pid, 'name': f['name'], 'plant_type': f['plant_type'],
                            'color': f['color'], 'irrigation_mode': f['irrigation_mode'],
                            'interval_days': f['interval_days'], 'auto_time': f.get('auto_time'),
                            'season_ack': None, 'created_at': f['created_at'], 'deleted_at': None}
        return pid

    def update_plant(self, pid, f):
        for k in ('name', 'plant_type', 'color', 'irrigation_mode', 'interval_days', 'auto_time', 'season_ack'):
            if k in f:
                self.plants[pid][k] = f[k]

    def soft_delete_plant(self, pid):
        self.plants[pid]['deleted_at'] = datetime.now()

    def restore_plant(self, pid):
        self.plants[pid]['deleted_at'] = None

    def last_materialized_days(self, ids):
        out = {}
        for pid, d in self.days:
            if pid in ids and (pid not in out or d > out[pid]):
                out[pid] = d
        return out

    def insert_days(self, rows):
        for r in rows:
            self.days.setdefault((r['plant_id'], r['day']), {k: r[k] for k in _DAY_KEYS})

    def get_days(self, ids, start, end):
        out = {}
        for pid, d in sorted(self.days):
            if pid in ids and start <= d <= end:
                out.setdefault(pid, []).append(dict(self.days[(pid, d)]))
        return out

    def upsert_day(self, pid, day, **fields):
        row = self.days.setdefault((pid, day), {'day': day, 'soil_status': None, 'watered': False,
                                                'auto_expected': False, 'auto_confirmed': False})
        row.update(fields)

    def add_event(self, pid, event_type, event_at, source, note):
        eid = self._next_event
        self._next_event += 1
        self.events[eid] = {'id': eid, 'plant_id': pid, 'event_type': event_type,
                            'event_at': event_at, 'source': source, 'note': note}
        return eid

    def get_event(self, eid):
        e = self.events.get(eid)
        return dict(e) if e else None

    def delete_event(self, eid):
        self.events.pop(eid, None)

    def get_events(self, ids, start, end):
        out = {}
        for e in sorted(self.events.values(), key=lambda e: e['event_at']):
            if e['plant_id'] in ids and start <= e['event_at'].date() <= end:
                out.setdefault(e['plant_id'], []).append(dict(e))
        return out

    def water_dates(self, pid):
        return sorted({e['event_at'].date() for e in self.events.values()
                       if e['plant_id'] == pid and e['event_type'] == 'water'})

    def last_event_dates(self, ids, today):
        out = {}
        for e in self.events.values():
            d = e['event_at'].date()
            if e['plant_id'] in ids and d <= today:
                per = out.setdefault(e['plant_id'], {})
                if e['event_type'] not in per or d > per[e['event_type']]:
                    per[e['event_type']] = d
        return out
