"""Pure date logic for the plant tracker (מעקב עציצים) — no DB, no Flask."""
from datetime import timedelta

PLANT_TYPES = ('cactus', 'monstera', 'fern', 'succulent', 'herb', 'flower', 'tree', 'sprout',
               # drawn from specific plants' look
               'kalanchoe', 'geranium', 'petunia', 'adansonii', 'orchid', 'oregano', 'rosemary', 'basil',
               'chives', 'thyme', 'pentas', 'angelonia',
               # by shape, for plants whose species isn't known
               'spiky', 'strap', 'conifer', 'shrub')
IRRIGATION_MODES = ('manual', 'auto')
SOIL_STATUSES = ('dry', 'humid', 'wet')
EVENT_TYPES = ('water', 'fertilize', 'repot', 'prune', 'pest')
TIMELINE_DAYS = 14


def is_auto_expected(day, anchor, interval_days):
    """True when `day` falls on the auto schedule counted from `anchor` (anchor itself excluded)."""
    gap = (day - anchor).days
    return gap >= interval_days and gap % interval_days == 0


def _last_water_before(water_dates, day):
    prior = [d for d in water_dates if d < day]
    return max(prior) if prior else None


def materialize_rows(plant, last_day, today, water_dates):
    """PlantDays rows for every day after `last_day` (or from creation) through `today`.

    Soil status is never carried forward — a new day starts unknown.
    """
    d = last_day + timedelta(days=1) if last_day else plant['created_at']
    rows = []
    while d <= today:
        expected = False
        if plant['irrigation_mode'] == 'auto':
            anchor = _last_water_before(water_dates, d) or plant['created_at']
            expected = is_auto_expected(d, anchor, plant['interval_days'])
        rows.append({'plant_id': plant['id'], 'day': d, 'soil_status': None,
                     'watered': d in water_dates, 'auto_expected': expected,
                     'auto_confirmed': False})
        d += timedelta(days=1)
    return rows


def plant_status(plant, last_water, today):
    """(days since last watering — or since creation if never watered, status)."""
    since = (today - (last_water or plant['created_at'])).days
    if since > plant['interval_days']:
        return since, 'overdue'
    if since == plant['interval_days']:
        return since, 'due'
    return since, 'ok'


def season_key(day):
    """'YYYY-summer' for Jun–Sep, 'YYYY-winter' for Dec–Feb (Dec belongs to next year), else None."""
    if 6 <= day.month <= 9:
        return f'{day.year}-summer'
    if day.month == 12:
        return f'{day.year + 1}-winter'
    if day.month <= 2:
        return f'{day.year}-winter'
    return None


def timeline_window(today):
    return [today - timedelta(days=i) for i in range(TIMELINE_DAYS - 1, -1, -1)]


def build_summary(plants, days_by_plant, today):
    """Counts for the page header. `plants` entries carry `status` and `irrigation_mode`; auto plants have
    status 'auto' so they never count as due/overdue, and only auto plants contribute pending confirmations
    (rows left from before a switch to manual, or of plants not in the list, are ignored)."""
    auto_ids = {p['id'] for p in plants if p.get('irrigation_mode') == 'auto'}
    pending = sum(
        1 for pid, rows in days_by_plant.items() if pid in auto_ids for r in rows
        if r['day'] <= today and r['auto_expected'] and not r['auto_confirmed'] and not r['watered']
    )
    return {
        'due_today': sum(1 for p in plants if p['status'] == 'due'),
        'overdue': sum(1 for p in plants if p['status'] == 'overdue'),
        'auto_pending_confirm': pending,
    }
