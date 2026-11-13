# Plant Tracker (מעקב עציצים) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new sidebar page `/plants` that tracks house plants on a 14-day daily timeline (watering, irrigation mode, soil status), logs care events, and shows rule-based suggestions.

**Architecture:** Pure date/rule logic (`src_utils/plant_logic.py`, `src_utils/plant_suggestions.py`) is DB-free and unit-tested. `plant_store.py` is the only file with SQL; `plant_service.py` validates input and orchestrates store + logic into one JSON payload; `routes/plant_routes.py` is a thin Flask blueprint. One `PlantDays` row per plant per day is materialized on the first request of each day (Option B). The page caches the payload in `localStorage` per local date.

**Tech Stack:** Python 3.10 (global interpreter), Flask blueprint, PostgreSQL via psycopg2 (`DataBase` singleton), vanilla JS + inline SVG, pytest.

**Spec:** `docs/superpowers/specs/2026-10-03-plant-tracker-design.md`

## Global Constraints

- Run Python/pytest with the **global** `python` (3.10.4), never `venv/Scripts/python.exe` (missing psycopg2/dotenv).
- `today` is always the **client's local date**, sent as `?today=YYYY-MM-DD` (GET) or `"today"` in the JSON body; server falls back to `date.today()`. Never derive "today" from server UTC when the client sent one.
- Plant types: `cactus, monstera, fern, succulent, herb, flower, tree, sprout`. Modes: `manual, auto`. Soil: `dry, humid, wet` (or null). Event types: `water, fertilize, repot, prune, pest`. Timeline: 14 days.
- All API responses: `{ok: true, ...}` or `{ok: false, error}` with HTTP 400 (validation), 404 (unknown/deleted plant or event), 500 (unexpected).
- Never register a route path/endpoint that already exists in `WebApp.py` (`grep -n "/plants\|api_plants" source/WebApp.py` must be empty before Task 5 — verified empty on 2026-10-03).
- Palette: navy `#1e2a4a`, teal `#1e9d8b`, bg `#f4f6f9`, white `#fff`. Plant colour palette: `#1e9d8b #2f6fb0 #7a5bc4 #c2577a #d9822b #4f8a3c #b0503a #3b8f9e`.
- Do not hardcode local Windows paths. All UI copy in Hebrew, RTL.
- Feature completion bumps `VERSION` to **1.17.0**. Each commit in this plan is local; push only at the end (Task 7) and only if the user asks.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Small deviations from the spec, decided here: `ensure()` lives on `PlantStore` (not `DataBase`) to keep `database.py` from growing; `Plants.Created_At` is a `DATE` (the client's local creation date) rather than a timestamp; schedule changes apply from the **next** materialized day (today's row already exists once the page loaded).

---

### Task 1: Pure plant date logic

**Files:**
- Create: `source/src_utils/plant_logic.py`
- Test: `tests/test_plant_logic.py`

**Interfaces:**
- Produces:
  - constants `PLANT_TYPES`, `IRRIGATION_MODES`, `SOIL_STATUSES`, `EVENT_TYPES` (tuples of str), `TIMELINE_DAYS = 14`
  - `is_auto_expected(day: date, anchor: date, interval_days: int) -> bool`
  - `materialize_rows(plant: dict, last_day: date|None, today: date, water_dates: set[date]) -> list[dict]` — row dict keys: `plant_id, day, soil_status, watered, auto_expected, auto_confirmed`
  - `plant_status(plant: dict, last_water: date|None, today: date) -> tuple[int, str]` — status in `ok|due|overdue`
  - `season_key(day: date) -> str|None`
  - `timeline_window(today: date) -> list[date]` (oldest → newest, 14 items)
  - `build_summary(plants: list[dict], days_by_plant: dict[int, list[dict]], today: date) -> dict` — keys `due_today, overdue, auto_pending_confirm`
- Plant dict shape used everywhere: `id, name, plant_type, color, irrigation_mode, interval_days, auto_time, season_ack, created_at (date), deleted_at`

- [ ] **Step 1: Write the failing tests**

`tests/test_plant_logic.py`:
```python
from datetime import date

from src_utils.plant_logic import (
    materialize_rows, plant_status, season_key, timeline_window, build_summary,
)


def _plant(**kw):
    p = {'id': 1, 'name': 'פיקוס', 'irrigation_mode': 'manual', 'interval_days': 3,
         'auto_time': None, 'created_at': date(2026, 10, 1), 'season_ack': None}
    p.update(kw)
    return p


def test_materialize_from_creation_when_no_rows():
    rows = materialize_rows(_plant(), None, date(2026, 10, 3), set())
    assert [r['day'] for r in rows] == [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)]
    assert all(r['soil_status'] is None and not r['watered'] and not r['auto_confirmed'] for r in rows)
    assert all(r['plant_id'] == 1 for r in rows)


def test_materialize_fills_only_gap_after_last_day():
    rows = materialize_rows(_plant(), date(2026, 10, 2), date(2026, 10, 4), set())
    assert [r['day'] for r in rows] == [date(2026, 10, 3), date(2026, 10, 4)]


def test_materialize_nothing_when_up_to_date():
    assert materialize_rows(_plant(), date(2026, 10, 3), date(2026, 10, 3), set()) == []


def test_materialize_marks_watered_days():
    rows = materialize_rows(_plant(), None, date(2026, 10, 3), {date(2026, 10, 2)})
    assert [r['watered'] for r in rows] == [False, True, False]


def test_auto_expected_every_interval_from_creation():
    p = _plant(irrigation_mode='auto', interval_days=2, auto_time='07:00')
    rows = materialize_rows(p, None, date(2026, 10, 6), set())
    assert [r['day'].day for r in rows if r['auto_expected']] == [3, 5]


def test_auto_expected_reanchors_on_last_water():
    p = _plant(irrigation_mode='auto', interval_days=3, auto_time='07:00')
    rows = materialize_rows(p, None, date(2026, 10, 8), {date(2026, 10, 2)})
    # anchor is the creation day until the 2nd is watered, then the 2nd → 5th and 8th
    assert [r['day'].day for r in rows if r['auto_expected']] == [5, 8]


def test_manual_plants_never_auto_expected():
    rows = materialize_rows(_plant(interval_days=1), None, date(2026, 10, 5), set())
    assert not any(r['auto_expected'] for r in rows)


def test_plant_status():
    p = _plant(interval_days=3)
    assert plant_status(p, date(2026, 10, 10), date(2026, 10, 12)) == (2, 'ok')
    assert plant_status(p, date(2026, 10, 10), date(2026, 10, 13)) == (3, 'due')
    assert plant_status(p, date(2026, 10, 10), date(2026, 10, 15)) == (5, 'overdue')
    assert plant_status(p, None, date(2026, 10, 4)) == (3, 'due')  # never watered → counts from creation


def test_season_key():
    assert season_key(date(2026, 7, 1)) == '2026-summer'
    assert season_key(date(2026, 12, 5)) == '2027-winter'
    assert season_key(date(2027, 2, 28)) == '2027-winter'
    assert season_key(date(2026, 10, 3)) is None


def test_timeline_window_is_14_days_ending_today():
    w = timeline_window(date(2026, 10, 14))
    assert len(w) == 14 and w[0] == date(2026, 10, 1) and w[-1] == date(2026, 10, 14)


def test_build_summary_counts():
    plants = [{'id': 1, 'status': 'due'}, {'id': 2, 'status': 'overdue'}, {'id': 3, 'status': 'ok'}]
    days = {3: [
        {'day': date(2026, 10, 2), 'auto_expected': True, 'auto_confirmed': False, 'watered': False},
        {'day': date(2026, 10, 3), 'auto_expected': True, 'auto_confirmed': True, 'watered': True},
    ]}
    assert build_summary(plants, days, date(2026, 10, 3)) == {
        'due_today': 1, 'overdue': 1, 'auto_pending_confirm': 1}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_plant_logic.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'src_utils.plant_logic'`

- [ ] **Step 3: Implement**

`source/src_utils/plant_logic.py`:
```python
"""Pure date logic for the plant tracker (מעקב עציצים) — no DB, no Flask."""
from datetime import timedelta

PLANT_TYPES = ('cactus', 'monstera', 'fern', 'succulent', 'herb', 'flower', 'tree', 'sprout')
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
    pending = sum(
        1 for rows in days_by_plant.values() for r in rows
        if r['day'] <= today and r['auto_expected'] and not r['auto_confirmed'] and not r['watered']
    )
    return {
        'due_today': sum(1 for p in plants if p['status'] == 'due'),
        'overdue': sum(1 for p in plants if p['status'] == 'overdue'),
        'auto_pending_confirm': pending,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_plant_logic.py -q`
Expected: `11 passed`

- [ ] **Step 5: Commit**

```bash
git add source/src_utils/plant_logic.py tests/test_plant_logic.py
git commit -m "feat(plants): pure daily-timeline logic" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Rule-based suggestions

**Files:**
- Create: `source/src_utils/plant_suggestions.py`
- Test: `tests/test_plant_suggestions.py`

**Interfaces:**
- Consumes: `plant_status`, `season_key` from Task 1.
- Produces: `build_suggestions(plant: dict, rows: list[dict], last_events: dict[str, date], today: date) -> list[dict]`
  - `rows`: that plant's PlantDays dicts (keys `day, soil_status, watered, auto_expected, auto_confirmed`) inside the window
  - `last_events`: `{event_type: date}` — latest event of each type on/before today (all history, not just the window)
  - each suggestion: `{plant_id, kind, level, text, action}`; `kind` ∈ `overdue, dries_fast, overwater, auto_unconfirmed, seasonal, fertilize, no_soil`; `level` ∈ `alert, warn, info`; `action` is `None` or one of `{type:'water_now'}`, `{type:'set_interval', value:int[, season_key:str]}`, `{type:'confirm_auto', day:'YYYY-MM-DD'}`, `{type:'fertilize_now'}`, `{type:'set_soil'}`

- [ ] **Step 1: Write the failing tests**

`tests/test_plant_suggestions.py`:
```python
from datetime import date, timedelta

from src_utils.plant_suggestions import build_suggestions

T = date(2026, 10, 14)  # October: no season key, outside fertilize season (Mar–Sep)


def _plant(**kw):
    p = {'id': 1, 'name': 'פיקוס', 'irrigation_mode': 'manual', 'interval_days': 3,
         'auto_time': None, 'created_at': date(2026, 9, 1), 'season_ack': None}
    p.update(kw)
    return p


def _rows(spec, today=T):
    """spec: {days_ago: {field: value}} → 14 rows ending at `today`."""
    out = []
    for i in range(14):
        r = {'day': today - timedelta(days=i), 'soil_status': None, 'watered': False,
             'auto_expected': False, 'auto_confirmed': False}
        r.update(spec.get(i, {}))
        out.append(r)
    return out


def _one_row(day):
    return [{'day': day, 'soil_status': 'humid', 'watered': False,
             'auto_expected': False, 'auto_confirmed': False}]


def _kinds(s):
    return [x['kind'] for x in s]


def _get(s, kind):
    return [x for x in s if x['kind'] == kind][0]


WATERED_YESTERDAY = {'water': T - timedelta(days=1)}
SOIL_TODAY = {0: {'soil_status': 'humid'}}


def test_quiet_plant_has_no_suggestions():
    assert build_suggestions(_plant(), _rows(SOIL_TODAY), WATERED_YESTERDAY, T) == []


def test_overdue():
    s = build_suggestions(_plant(), _rows(SOIL_TODAY), {'water': T - timedelta(days=5)}, T)
    o = _get(s, 'overdue')
    assert o['level'] == 'alert' and '2' in o['text'] and o['action'] == {'type': 'water_now'}
    assert o['plant_id'] == 1


def test_dries_fast_suggests_shorter_interval():
    rows = _rows({0: {'soil_status': 'dry'}, 1: {'watered': True},
                  5: {'soil_status': 'dry', 'watered': True}})
    s = build_suggestions(_plant(), rows, WATERED_YESTERDAY, T)
    assert _get(s, 'dries_fast')['action'] == {'type': 'set_interval', 'value': 2}


def test_dries_fast_needs_two_occurrences():
    rows = _rows({0: {'soil_status': 'dry'}, 1: {'watered': True}})
    assert 'dries_fast' not in _kinds(build_suggestions(_plant(), rows, WATERED_YESTERDAY, T))


def test_dries_fast_not_below_one_day():
    rows = _rows({0: {'soil_status': 'dry'}, 1: {'watered': True},
                  5: {'soil_status': 'dry', 'watered': True}})
    s = build_suggestions(_plant(interval_days=1), rows, {'water': T}, T)
    assert 'dries_fast' not in _kinds(s)


def test_overwatering():
    rows = _rows({i: {'soil_status': 'wet'} for i in range(3)})
    s = build_suggestions(_plant(), rows, WATERED_YESTERDAY, T)
    w = _get(s, 'overwater')
    assert w['level'] == 'warn' and w['action'] == {'type': 'set_interval', 'value': 4}


def test_auto_unconfirmed_points_at_latest_missed_day():
    p = _plant(irrigation_mode='auto', auto_time='07:00')
    rows = _rows({0: {'soil_status': 'humid'}, 2: {'auto_expected': True},
                  5: {'auto_expected': True}, 8: {'auto_expected': True,
                                                  'auto_confirmed': True, 'watered': True}})
    a = _get(build_suggestions(p, rows, WATERED_YESTERDAY, T), 'auto_unconfirmed')
    assert '2' in a['text']
    assert a['action'] == {'type': 'confirm_auto', 'day': (T - timedelta(days=2)).isoformat()}


def test_auto_expected_today_is_not_flagged_yet():
    p = _plant(irrigation_mode='auto', auto_time='07:00')
    rows = _rows({0: {'soil_status': 'humid', 'auto_expected': True}})
    assert 'auto_unconfirmed' not in _kinds(build_suggestions(p, rows, WATERED_YESTERDAY, T))


def test_seasonal_summer_and_ack():
    t = date(2026, 7, 10)
    le = {'water': t - timedelta(days=1), 'fertilize': t - timedelta(days=3)}
    s = build_suggestions(_plant(interval_days=4), _one_row(t), le, t)
    assert _get(s, 'seasonal')['action'] == {'type': 'set_interval', 'value': 3,
                                             'season_key': '2026-summer'}
    s2 = build_suggestions(_plant(interval_days=4, season_ack='2026-summer'), _one_row(t), le, t)
    assert 'seasonal' not in _kinds(s2)


def test_seasonal_winter_longer():
    t = date(2027, 1, 10)
    s = build_suggestions(_plant(interval_days=4), _one_row(t), {'water': t - timedelta(days=1)}, t)
    assert _get(s, 'seasonal')['action']['value'] == 5


def test_seasonal_skipped_when_no_change():
    t = date(2027, 1, 10)
    s = build_suggestions(_plant(interval_days=1), _one_row(t), {'water': t}, t)
    assert 'seasonal' not in _kinds(s)


def test_fertilize_reminder_in_growing_season():
    t = date(2026, 4, 10)
    p = _plant(created_at=date(2026, 1, 1))
    s = build_suggestions(p, _one_row(t), {'water': t - timedelta(days=1)}, t)
    assert _get(s, 'fertilize')['action'] == {'type': 'fertilize_now'}
    s2 = build_suggestions(p, _one_row(t), {'water': t - timedelta(days=1),
                                            'fertilize': t - timedelta(days=10)}, t)
    assert 'fertilize' not in _kinds(s2)


def test_fertilize_skipped_for_new_plants():
    t = date(2026, 4, 10)
    s = build_suggestions(_plant(created_at=t - timedelta(days=5)), _one_row(t),
                          {'water': t - timedelta(days=1)}, t)
    assert 'fertilize' not in _kinds(s)


def test_no_soil_data():
    s = build_suggestions(_plant(), _rows({}), WATERED_YESTERDAY, T)
    assert _get(s, 'no_soil') == {'plant_id': 1, 'kind': 'no_soil', 'level': 'info',
                                  'text': 'פיקוס: לא עודכן מצב אדמה בשבוע האחרון',
                                  'action': {'type': 'set_soil'}}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_plant_suggestions.py -q`
Expected: collection error `No module named 'src_utils.plant_suggestions'`

- [ ] **Step 3: Implement**

`source/src_utils/plant_suggestions.py`:
```python
"""Rule-based care suggestions for the plant tracker — pure functions."""
from datetime import timedelta

from src_utils.plant_logic import plant_status, season_key

_DAY = timedelta(days=1)


def _sugg(plant, kind, level, text, action=None):
    return {'plant_id': plant['id'], 'kind': kind, 'level': level, 'text': text, 'action': action}


def _round_half_up(x):
    return int(x + 0.5)


def build_suggestions(plant, rows, last_events, today):
    out = []
    name = plant['name']
    interval = plant['interval_days']
    by_day = {r['day']: r for r in rows}

    # 1. Overdue
    since, status = plant_status(plant, last_events.get('water'), today)
    if status == 'overdue':
        out.append(_sugg(plant, 'overdue', 'alert',
                         f'{name}: באיחור השקיה של {since - interval} ימים', {'type': 'water_now'}))

    # 2. Soil dry on the watering day or the day after — twice in the window
    fast = [d for d, r in by_day.items() if r['soil_status'] == 'dry' and (
        r['watered'] or by_day.get(d - _DAY, {}).get('watered'))]
    if len(fast) >= 2 and interval > 1:
        out.append(_sugg(plant, 'dries_fast', 'warn',
                         f'{name}: האדמה מתייבשת מהר — מומלץ לקצר את המרווח ל-{interval - 1} ימים',
                         {'type': 'set_interval', 'value': interval - 1}))

    # 3. Wet three days in a row (today and the two before)
    if all(by_day.get(today - i * _DAY, {}).get('soil_status') == 'wet' for i in range(3)):
        out.append(_sugg(plant, 'overwater', 'warn',
                         f'{name}: האדמה רטובה 3 ימים ברצף — סכנת השקיית יתר, מומלץ להאריך את המרווח',
                         {'type': 'set_interval', 'value': interval + 1}))

    # 4. Past scheduled auto waterings that were never confirmed
    missed = sorted(d for d, r in by_day.items()
                    if d < today and r['auto_expected'] and not r['auto_confirmed'] and not r['watered'])
    if plant['irrigation_mode'] == 'auto' and missed:
        out.append(_sugg(plant, 'auto_unconfirmed', 'warn',
                         f'{name}: {len(missed)} השקיות אוטומטיות לא אושרו — בדוק את מערכת ההשקיה',
                         {'type': 'confirm_auto', 'day': missed[-1].isoformat()}))

    # 5. Seasonal interval adjustment — once per season (season_ack)
    key = season_key(today)
    if key and plant.get('season_ack') != key:
        if key.endswith('summer'):
            new = max(1, _round_half_up(interval * 0.75))
            text = f'{name}: קיץ — מומלץ להשקות כל {new} ימים במקום {interval}'
        else:
            new = _round_half_up(interval * 1.25)
            text = f'{name}: חורף — אפשר להאריך את המרווח ל-{new} ימים'
        if new != interval:
            out.append(_sugg(plant, 'seasonal', 'info', text,
                             {'type': 'set_interval', 'value': new, 'season_key': key}))

    # 6. Fertilize reminder in growing season (Mar–Sep), plants older than 30 days
    last_fert = last_events.get('fertilize')
    if (3 <= today.month <= 9 and (today - plant['created_at']).days >= 30
            and (last_fert is None or (today - last_fert).days > 30)):
        out.append(_sugg(plant, 'fertilize', 'info',
                         f'{name}: לא דושן ביותר מ-30 יום — עונת גדילה, מומלץ לדשן',
                         {'type': 'fertilize_now'}))

    # 7. No soil status in the last 7 days
    if not any(by_day.get(today - i * _DAY, {}).get('soil_status') for i in range(7)):
        out.append(_sugg(plant, 'no_soil', 'info',
                         f'{name}: לא עודכן מצב אדמה בשבוע האחרון', {'type': 'set_soil'}))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_plant_suggestions.py -q`
Expected: `14 passed`

- [ ] **Step 5: Commit**

```bash
git add source/src_utils/plant_suggestions.py tests/test_plant_suggestions.py
git commit -m "feat(plants): rule-based care suggestions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: PostgreSQL store + in-memory fake

**Files:**
- Create: `source/plant_store.py`
- Create: `tests/plant_fakes.py`
- Test: `tests/test_plant_store_db.py` (opt-in, runs only with `PLANT_DB_TESTS=1`)

**Interfaces:**
- Consumes: `DataBase()` from `source/database.py` (`db.cursor.execute(sql, params)` returns a chainable cursor with `.fetchone()/.fetchall()`; `db.connection.commit()/rollback()`).
- Produces — `PlantStore(db, autocommit=True)` and `FakePlantStore()` with identical methods:
  - `ensure() -> None`
  - `list_plants(deleted: bool = False) -> list[plant dict]` (active only, or deleted only; ordered by id)
  - `get_plant(pid) -> plant dict | None` (includes deleted)
  - `count_plants() -> int` (including deleted)
  - `add_plant(f: dict) -> int` — `f` keys: `name, plant_type, color, irrigation_mode, interval_days, auto_time (optional), created_at (date)`
  - `update_plant(pid, f: dict) -> None` — any subset of `name, plant_type, color, irrigation_mode, interval_days, auto_time, season_ack`
  - `soft_delete_plant(pid)`, `restore_plant(pid)`
  - `last_materialized_days(ids) -> {pid: date}`
  - `insert_days(rows: list[row dict]) -> None` — existing (plant_id, day) rows are left untouched
  - `get_days(ids, start: date, end: date) -> {pid: [ {day, soil_status, watered, auto_expected, auto_confirmed} ... ordered by day ]}`
  - `upsert_day(pid, day, **fields)` — fields subset of `soil_status, watered, auto_confirmed`
  - `add_event(pid, event_type, event_at: datetime, source, note) -> int`
  - `get_event(eid) -> {id, plant_id, event_type, event_at: datetime, source, note} | None`
  - `delete_event(eid)`
  - `get_events(ids, start: date, end: date) -> {pid: [event dicts ordered by event_at]}`
  - `water_dates(pid) -> sorted list[date]`
  - `last_event_dates(ids, today: date) -> {pid: {event_type: date}}`

- [ ] **Step 1: Write the opt-in DB test**

`tests/test_plant_store_db.py`:
```python
"""Round-trip PlantStore against the real DATABASE_URL inside a rolled-back transaction.

Opt-in: set PLANT_DB_TESTS=1. Nothing is committed.
"""
import os
from datetime import date, datetime

import pytest

pytestmark = pytest.mark.skipif(os.getenv('PLANT_DB_TESTS') != '1',
                                reason='set PLANT_DB_TESTS=1 to run against DATABASE_URL')


@pytest.fixture
def store():
    from dotenv import load_dotenv
    load_dotenv()
    from database import DataBase
    from plant_store import PlantStore
    db = DataBase()
    s = PlantStore(db, autocommit=False)
    s.ensure()
    yield s
    db.connection.rollback()


def test_roundtrip(store):
    pid = store.add_plant({'name': '__plant_test__', 'plant_type': 'fern', 'color': '#1e9d8b',
                           'irrigation_mode': 'auto', 'interval_days': 2, 'auto_time': '07:00',
                           'created_at': date(2026, 10, 1)})
    p = store.get_plant(pid)
    assert p['plant_type'] == 'fern' and p['created_at'] == date(2026, 10, 1) and p['deleted_at'] is None

    blank = {'plant_id': pid, 'day': date(2026, 10, 1), 'soil_status': None, 'watered': False,
             'auto_expected': False, 'auto_confirmed': False}
    store.insert_days([blank])
    store.insert_days([dict(blank, soil_status='wet', watered=True)])  # conflict → ignored
    assert store.last_materialized_days([pid]) == {pid: date(2026, 10, 1)}

    store.upsert_day(pid, date(2026, 10, 1), soil_status='dry')
    store.upsert_day(pid, date(2026, 10, 2), watered=True)
    days = store.get_days([pid], date(2026, 10, 1), date(2026, 10, 2))[pid]
    assert [(r['soil_status'], r['watered']) for r in days] == [('dry', False), (None, True)]

    eid = store.add_event(pid, 'water', datetime(2026, 10, 2, 8, 30), 'manual', None)
    assert store.water_dates(pid) == [date(2026, 10, 2)]
    assert store.last_event_dates([pid], date(2026, 10, 3)) == {pid: {'water': date(2026, 10, 2)}}
    assert store.get_events([pid], date(2026, 10, 1), date(2026, 10, 3))[pid][0]['id'] == eid
    assert store.get_event(eid)['event_at'] == datetime(2026, 10, 2, 8, 30)

    store.update_plant(pid, {'interval_days': 4, 'season_ack': '2026-summer'})
    assert store.get_plant(pid)['interval_days'] == 4

    store.soft_delete_plant(pid)
    assert pid not in [x['id'] for x in store.list_plants()]
    assert pid in [x['id'] for x in store.list_plants(deleted=True)]
    store.restore_plant(pid)
    assert pid in [x['id'] for x in store.list_plants()]

    store.delete_event(eid)
    assert store.water_dates(pid) == [] and store.get_event(eid) is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `PLANT_DB_TESTS=1 python -m pytest tests/test_plant_store_db.py -q` (PowerShell: `$env:PLANT_DB_TESTS='1'; python -m pytest tests/test_plant_store_db.py -q`)
Expected: FAIL — `ModuleNotFoundError: No module named 'plant_store'`

- [ ] **Step 3: Implement `source/plant_store.py`**

```python
"""PostgreSQL persistence for the plant tracker (Plants / PlantEvents / PlantDays).

The only module with plant SQL. `autocommit=False` lets tests run inside a
transaction they roll back.
"""

_PLANT_COLS = ('ID, Name, Plant_Type, Color, Irrigation_Mode, Interval_Days, '
               'Auto_Time, Season_Ack, Created_At, Deleted_At')
_PLANT_UPDATABLE = {
    'name': 'Name', 'plant_type': 'Plant_Type', 'color': 'Color',
    'irrigation_mode': 'Irrigation_Mode', 'interval_days': 'Interval_Days',
    'auto_time': 'Auto_Time', 'season_ack': 'Season_Ack',
}
_DAY_UPDATABLE = {'soil_status': 'Soil_Status', 'watered': 'Watered', 'auto_confirmed': 'Auto_Confirmed'}
_EVENT_COLS = 'ID, Plant_ID, Event_Type, Event_At, Source, Note'


def _plant(r):
    return {'id': r[0], 'name': r[1], 'plant_type': r[2], 'color': r[3],
            'irrigation_mode': r[4], 'interval_days': r[5], 'auto_time': r[6],
            'season_ack': r[7], 'created_at': r[8], 'deleted_at': r[9]}


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
            'INSERT INTO Plants (Name, Plant_Type, Color, Irrigation_Mode, Interval_Days, Auto_Time, Created_At) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING ID',
            (f['name'], f['plant_type'], f['color'], f['irrigation_mode'],
             f['interval_days'], f.get('auto_time'), f['created_at'])
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
                       'WHERE Plant_ID = ANY(%s) AND Event_At::date BETWEEN %s AND %s ORDER BY Event_At',
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
```

- [ ] **Step 4: Implement `tests/plant_fakes.py`**

```python
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
```

- [ ] **Step 5: Run the DB test**

Run (PowerShell): `$env:PLANT_DB_TESTS='1'; python -m pytest tests/test_plant_store_db.py -q; Remove-Item Env:PLANT_DB_TESTS`
Expected: `1 passed`. (The transaction is rolled back — no rows or tables are left behind if the tables did not exist before.)
Also run without the env var: `python -m pytest tests/test_plant_store_db.py -q` → `1 skipped`.

- [ ] **Step 6: Commit**

```bash
git add source/plant_store.py tests/plant_fakes.py tests/test_plant_store_db.py
git commit -m "feat(plants): Postgres store for plants, events and daily rows" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Service layer (validation, materialization, payload)

**Files:**
- Create: `source/plant_service.py`
- Test: `tests/test_plant_service.py`

**Interfaces:**
- Consumes: Task 1 logic, Task 2 `build_suggestions`, Task 3 store interface (tests use `FakePlantStore`).
- Produces (all take a store; `today: date`):
  - `class PlantError(Exception)` with `.status` (400 default, 404 for not found)
  - `PALETTE: list[str]`
  - `materialize(store, today) -> None`
  - `build_payload(store, today) -> dict` — keys `ok, today, window, plants, days, events, suggestions, summary`; `days`/`events` are keyed by **string** plant id; plant JSON adds `last_water, days_since_water, status`; day JSON `{day, soil_status, watered, auto_expected, auto_confirmed}`; event JSON `{id, event_type, event_at:'YYYY-MM-DDTHH:MM', source, note}`
  - `create_plant(store, body, today) -> int`, `update_plant(store, pid, body, today)`, `delete_plant(store, pid)`, `restore_plant(store, pid)`, `deleted_plants(store) -> list[dict]`
  - `add_event(store, pid, body, today) -> int`, `delete_event(store, eid)`
  - `set_soil(store, pid, body, today)`, `confirm_auto(store, pid, body, today)`, `dismiss_season(store, pid, today)`
  - `water_due(store, body, today) -> int` (number of plants watered)

- [ ] **Step 1: Write the failing tests**

`tests/test_plant_service.py`:
```python
from datetime import date, datetime

import pytest

import plant_service as svc
from tests.plant_fakes import FakePlantStore

T = date(2026, 10, 14)


def _mk(store, **kw):
    body = {'name': 'פיקוס', 'plant_type': 'fern', 'irrigation_mode': 'manual', 'interval_days': 3}
    body.update(kw)
    return svc.create_plant(store, body, T)


def _backdate(store, pid, d):
    store.plants[pid]['created_at'] = d


def test_create_validates():
    s = FakePlantStore()
    for bad in ({'name': '', 'plant_type': 'fern'},
                {'name': 'x', 'plant_type': 'palm'},
                {'name': 'x' * 41, 'plant_type': 'fern'}):
        with pytest.raises(svc.PlantError):
            svc.create_plant(s, bad, T)
    with pytest.raises(svc.PlantError):
        _mk(s, interval_days=0)
    with pytest.raises(svc.PlantError):
        _mk(s, irrigation_mode='auto', auto_time='25:00')
    with pytest.raises(svc.PlantError):
        _mk(s, color='teal')
    assert s.plants == {}


def test_create_defaults_color_and_auto_time():
    s = FakePlantStore()
    pid = _mk(s, irrigation_mode='auto')
    p = s.get_plant(pid)
    assert p['color'] == svc.PALETTE[0] and p['auto_time'] == '07:00' and p['created_at'] == T
    assert s.get_plant(_mk(s))['color'] == svc.PALETTE[1]


def test_payload_materializes_once_and_is_idempotent():
    s = FakePlantStore()
    pid = _mk(s)
    _backdate(s, pid, date(2026, 10, 1))
    p1 = svc.build_payload(s, T)
    p2 = svc.build_payload(s, T)
    assert len(s.days) == 14 and p1 == p2
    assert p1['today'] == '2026-10-14' and len(p1['window']) == 14
    assert [d['day'] for d in p1['days'][str(pid)]][-1] == '2026-10-14'
    assert p1['plants'][0]['status'] == 'overdue' and p1['plants'][0]['last_water'] is None


def test_payload_fills_gap_days_after_absence():
    s = FakePlantStore()
    pid = _mk(s)
    _backdate(s, pid, date(2026, 10, 1))
    svc.build_payload(s, date(2026, 10, 3))
    svc.build_payload(s, T)
    assert sorted(d for (_, d) in s.days) == [date(2026, 10, i) for i in range(1, 15)]


def test_interval_change_does_not_rewrite_history():
    s = FakePlantStore()
    pid = _mk(s, irrigation_mode='auto', interval_days=2)
    _backdate(s, pid, date(2026, 10, 1))
    svc.build_payload(s, date(2026, 10, 6))
    before = {d: r['auto_expected'] for (_, d), r in s.days.items()}
    svc.update_plant(s, pid, {'interval_days': 5}, date(2026, 10, 6))
    svc.build_payload(s, date(2026, 10, 8))
    after = {d: r['auto_expected'] for (_, d), r in s.days.items() if d <= date(2026, 10, 6)}
    assert before == after


def test_water_event_marks_day_and_delete_unmarks():
    s = FakePlantStore()
    pid = _mk(s)
    svc.build_payload(s, T)
    eid = svc.add_event(s, pid, {'event_type': 'water', 'event_at': '2026-10-14T08:15'}, T)
    assert s.days[(pid, T)]['watered'] is True
    assert s.events[eid]['event_at'] == datetime(2026, 10, 14, 8, 15) and s.events[eid]['source'] == 'manual'
    svc.delete_event(s, eid)
    assert s.days[(pid, T)]['watered'] is False


def test_event_validation():
    s = FakePlantStore()
    pid = _mk(s)
    with pytest.raises(svc.PlantError):
        svc.add_event(s, pid, {'event_type': 'water', 'event_at': '2026-10-15T08:00'}, T)
    with pytest.raises(svc.PlantError):
        svc.add_event(s, pid, {'event_type': 'sing', 'event_at': '2026-10-14T08:00'}, T)
    with pytest.raises(svc.PlantError) as e:
        svc.add_event(s, 999, {'event_type': 'water'}, T)
    assert e.value.status == 404
    with pytest.raises(svc.PlantError) as e:
        svc.delete_event(s, 999)
    assert e.value.status == 404


def test_event_defaults_to_now():
    s = FakePlantStore()
    pid = _mk(s)
    eid = svc.add_event(s, pid, {'event_type': 'fertilize', 'note': ' דשן נוזלי '}, date.today())
    assert s.events[eid]['event_at'].date() == date.today() and s.events[eid]['note'] == 'דשן נוזלי'


def test_set_soil():
    s = FakePlantStore()
    pid = _mk(s)
    svc.build_payload(s, T)
    svc.set_soil(s, pid, {'day': '2026-10-14', 'soil_status': 'wet'}, T)
    assert s.days[(pid, T)]['soil_status'] == 'wet'
    svc.set_soil(s, pid, {'day': '2026-10-14', 'soil_status': None}, T)
    assert s.days[(pid, T)]['soil_status'] is None
    with pytest.raises(svc.PlantError):
        svc.set_soil(s, pid, {'day': '2026-10-14', 'soil_status': 'muddy'}, T)
    with pytest.raises(svc.PlantError):
        svc.set_soil(s, pid, {'day': '2026-10-15', 'soil_status': 'dry'}, T)


def test_confirm_auto_creates_event_at_auto_time():
    s = FakePlantStore()
    pid = _mk(s, irrigation_mode='auto', auto_time='06:30')
    svc.build_payload(s, T)
    svc.confirm_auto(s, pid, {'day': '2026-10-14'}, T)
    e = list(s.events.values())[0]
    assert e['event_at'] == datetime(2026, 10, 14, 6, 30) and e['source'] == 'auto_confirmed'
    assert s.days[(pid, T)]['auto_confirmed'] and s.days[(pid, T)]['watered']
    svc.delete_event(s, e['id'])
    assert not s.days[(pid, T)]['auto_confirmed'] and not s.days[(pid, T)]['watered']


def test_confirm_auto_rejected_for_manual():
    s = FakePlantStore()
    pid = _mk(s)
    with pytest.raises(svc.PlantError):
        svc.confirm_auto(s, pid, {'day': '2026-10-14'}, T)


def test_water_due_only_waters_due_plants():
    s = FakePlantStore()
    a = _mk(s, name='a')
    _mk(s, name='b')
    _backdate(s, a, date(2026, 10, 1))
    n = svc.water_due(s, {'event_at': '2026-10-14T09:00'}, T)
    assert n == 1 and [e['plant_id'] for e in s.events.values()] == [a]


def test_soft_delete_and_restore():
    s = FakePlantStore()
    pid = _mk(s)
    svc.delete_plant(s, pid)
    assert svc.build_payload(s, T)['plants'] == []
    assert [p['id'] for p in svc.deleted_plants(s)] == [pid]
    with pytest.raises(svc.PlantError):
        svc.update_plant(s, pid, {'name': 'x'}, T)
    svc.restore_plant(s, pid)
    assert [p['id'] for p in svc.build_payload(s, T)['plants']] == [pid]


def test_update_switching_to_auto_gets_default_time():
    s = FakePlantStore()
    pid = _mk(s)
    svc.update_plant(s, pid, {'irrigation_mode': 'auto'}, T)
    assert s.plants[pid]['auto_time'] == '07:00'


def test_dismiss_season():
    s = FakePlantStore()
    pid = _mk(s)
    svc.dismiss_season(s, pid, date(2026, 7, 1))
    assert s.plants[pid]['season_ack'] == '2026-summer'
    with pytest.raises(svc.PlantError):
        svc.dismiss_season(s, pid, date(2026, 10, 1))


def test_payload_suggestions_sorted_alert_first():
    s = FakePlantStore()
    pid = _mk(s)
    _backdate(s, pid, date(2026, 10, 1))
    levels = [x['level'] for x in svc.build_payload(s, T)['suggestions']]
    assert levels[0] == 'alert' and levels == sorted(levels, key=['alert', 'warn', 'info'].index)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_plant_service.py -q`
Expected: collection error `No module named 'plant_service'`

- [ ] **Step 3: Implement `source/plant_service.py`**

```python
"""Plant tracker service: validates input and orchestrates PlantStore + pure logic.

Every public mutator raises PlantError (status 400/404) on bad input; the routes
turn that into {ok: False, error}. `today` is always the client's local date.
"""
import re
from datetime import date, datetime, time

from src_utils.plant_logic import (
    PLANT_TYPES, IRRIGATION_MODES, SOIL_STATUSES, EVENT_TYPES,
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
    return d


def _parse_event_at(raw, today):
    if not raw:
        return datetime.now().replace(second=0, microsecond=0)
    try:
        dt = datetime.fromisoformat(str(raw))
    except ValueError:
        raise PlantError('זמן לא תקין')
    if dt.date() > today:
        raise PlantError('לא ניתן לרשום אירוע עתידי')
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_plant_logic.py tests/test_plant_suggestions.py tests/test_plant_service.py -q`
Expected: all pass (`41 passed` — 11 + 14 + 16)

- [ ] **Step 5: Commit**

```bash
git add source/plant_service.py tests/test_plant_service.py
git commit -m "feat(plants): service layer — validation, daily materialization, payload" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Flask blueprint + registration

**Files:**
- Create: `source/routes/plant_routes.py`
- Modify: `source/WebApp.py` (register blueprint right after the `SPOTIFY_HTML = ...` line, ~line 5915)
- Test: `tests/test_plant_routes.py`

**Interfaces:**
- Consumes: everything in `plant_service` (Task 4).
- Produces: `plants_bp` (Blueprint name `plants`) and module-level `get_store()` (monkeypatched in tests). Routes:

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/plants` | — | HTML page (Task 6) |
| GET | `/api/plants?today=` | — | payload |
| POST | `/api/plants` | plant fields | payload + `created_id` |
| PUT / DELETE | `/api/plants/<id>` | plant fields / — | payload |
| POST | `/api/plants/<id>/restore` | — | payload |
| GET | `/api/plants/deleted` | — | `{ok, plants}` |
| POST | `/api/plants/<id>/events` | `{event_type, event_at?, note?}` | payload + `created_id` |
| DELETE | `/api/plants/events/<eid>` | — | payload |
| PUT | `/api/plants/<id>/soil` | `{day, soil_status}` | payload |
| POST | `/api/plants/<id>/confirm-auto` | `{day}` | payload |
| POST | `/api/plants/<id>/dismiss-season` | — | payload |
| POST | `/api/plants/water-due` | `{event_at?}` | payload + `watered_count` |

All mutating bodies also carry `today`.

- [ ] **Step 1: Write the failing tests**

`tests/test_plant_routes.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_plant_routes.py -q`
Expected: collection error `cannot import name 'plant_routes' from 'routes'`

- [ ] **Step 3: Implement `source/routes/plant_routes.py`**

```python
"""Plant tracker (מעקב עציצים) page + JSON API.

Every mutating endpoint returns the full page payload so the client can
refresh its once-a-day cache in one round trip.
"""
import os
from datetime import date

from flask import Blueprint, jsonify, request, send_file

import plant_service as svc

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


def _today():
    """The client's local date (query string or JSON body), else the server's."""
    raw = request.args.get('today') or _body().get('today')
    try:
        return date.fromisoformat(raw) if raw else date.today()
    except (TypeError, ValueError):
        return date.today()


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


@plants_bp.route('/api/plants/<int:pid>/confirm-auto', methods=['POST'])
def api_plant_confirm_auto(pid):
    return _respond(lambda s, t: svc.confirm_auto(s, pid, _body(), t))


@plants_bp.route('/api/plants/<int:pid>/dismiss-season', methods=['POST'])
def api_plant_dismiss_season(pid):
    return _respond(lambda s, t: svc.dismiss_season(s, pid, t))


@plants_bp.route('/api/plants/water-due', methods=['POST'])
def api_plants_water_due():
    return _respond(lambda s, t: {'watered_count': svc.water_due(s, _body(), t)})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_plant_routes.py -q`
Expected: `8 passed`

- [ ] **Step 5: Register the blueprint in `WebApp.py`**

First confirm no conflict: `grep -n "'/plants\|/api/plants\|api_plants" source/WebApp.py` → no output.

Insert immediately before the `SPOTIFY_HTML = os.path.join(_HERE, 'html', 'SpotifyTracker.html')` line:
```python
# ── Plant tracker (מעקב עציצים) — routes live in routes/plant_routes.py ──────
from routes.plant_routes import plants_bp
app.register_blueprint(plants_bp)

```

- [ ] **Step 6: Verify the app imports and the route is mapped**

Run: `python -c "import sys; sys.path.insert(0,'source'); from WebApp import app; print(sorted(r.rule for r in app.url_map.iter_rules() if 'plants' in r.rule))"`
Expected: a list containing `/plants`, `/api/plants`, `/api/plants/<int:pid>`, … and no `AssertionError`.

- [ ] **Step 7: Commit**

```bash
git add source/routes/plant_routes.py source/WebApp.py tests/test_plant_routes.py
git commit -m "feat(plants): /plants page route and JSON API blueprint" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The page — `PlantTracker.html`

**Files:**
- Create: `source/html/PlantTracker.html`
- Modify: `tests/test_plant_routes.py` (add one page test)

**Interfaces:**
- Consumes: the API from Task 5 and its payload shape from Task 4.
- Produces: the `/plants` page. Shared chrome (CSS variables, sidebar, buttons, modal, nav JS, debug panel) is copied verbatim from `SpotifyTracker.html` by a one-off script, so it stays identical to other pages.

- [ ] **Step 1: Write the failing page test** — append to `tests/test_plant_routes.py`:

```python
def test_page_is_served(client):
    r = client.get('/plants')
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'מעקב עציצים' in html
    assert 'class="nav-item active" href="/plants"' in html
    assert '@SHELL' not in html and '@SIDEBAR@' not in html and '@DEBUG@' not in html
```

Run: `python -m pytest tests/test_plant_routes.py::test_page_is_served -q` → FAIL (404, file missing).

- [ ] **Step 2: Write the page template** `source/html/PlantTracker.html` with placeholder markers:

```html
<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>מעקב עציצים</title>
<style>
/*@SHELL_CSS@*/

/* ── Plant tracker ─────────────────────────────────────────── */
.pt-main { width: 100%; max-width: 1100px; margin: 0 auto; padding: 18px 16px 40px; display: flex; flex-direction: column; gap: 16px; }
.pt-card { background: var(--white); border-radius: var(--radius); box-shadow: var(--shadow-sm); padding: 16px 18px; }
.pt-summary { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.pt-stat { display: flex; align-items: baseline; gap: 6px; padding: 8px 14px; border-radius: 10px; background: var(--bg); font-size: .85em; color: var(--text-sub); }
.pt-stat b { font-size: 1.35em; color: var(--navy); }
.pt-stat.due b { color: var(--teal); }
.pt-stat.overdue b { color: var(--red); }
.pt-stat.pending b { color: var(--amber); }
.pt-legend { display: flex; flex-wrap: wrap; gap: 12px; font-size: .74em; color: var(--text-muted); margin-top: 10px; }
.pt-legend span { display: inline-flex; align-items: center; gap: 4px; }
.pt-swatch { width: 12px; height: 6px; border-radius: 3px; display: inline-block; }
.pt-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.pt-sugg-head { display: flex; align-items: center; gap: 8px; cursor: pointer; font-weight: 700; font-size: .9em; user-select: none; }
.pt-sugg-count { background: var(--teal-light); color: var(--teal); border-radius: 20px; padding: 1px 9px; font-size: .8em; }
.pt-sugg-list { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
.pt-sugg-list.hidden { display: none; }
.pt-sugg { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; padding: 9px 12px; border-radius: 10px; border-right: 4px solid var(--teal); background: var(--teal-light); font-size: .84em; }
.pt-sugg.warn { border-color: var(--amber); background: #fff8e6; }
.pt-sugg.alert { border-color: var(--red); background: #fdeeee; }
.pt-sugg-text { flex: 1; min-width: 180px; }
.pt-sugg-btns { display: flex; gap: 6px; flex-shrink: 0; }
.pt-empty { text-align: center; color: var(--text-muted); padding: 40px 10px; font-size: .9em; }
.pt-rows { display: flex; flex-direction: column; gap: 12px; }
.pt-row { display: flex; align-items: center; gap: 14px; }
.pt-plant { display: flex; align-items: center; gap: 10px; width: 230px; flex-shrink: 0; cursor: pointer; border: none; background: none; font-family: inherit; text-align: right; padding: 0; color: inherit; }
.pt-plant svg { flex-shrink: 0; }
.pt-plant-name { font-weight: 700; font-size: .92em; }
.pt-plant-meta { font-size: .72em; color: var(--text-muted); margin-top: 3px; }
.pt-badge { display: inline-block; padding: 1px 7px; border-radius: 10px; font-weight: 600; background: var(--bg); color: var(--text-sub); }
.pt-badge.auto { background: #e8f0fb; color: #2f6fb0; }
.pt-status { font-weight: 700; }
.pt-status.due { color: var(--teal); }
.pt-status.overdue { color: var(--red); }
.pt-cells { display: flex; gap: 4px; overflow-x: auto; flex: 1; min-width: 0; padding-bottom: 4px; }
.pt-cell { flex: 0 0 auto; width: 44px; height: 66px; border-radius: 9px; border: 1.5px solid var(--border); background: var(--white); display: flex; flex-direction: column; align-items: center; justify-content: space-between; padding: 4px 0 0; cursor: pointer; font-family: inherit; overflow: hidden; color: var(--navy); }
.pt-cell:hover { border-color: var(--teal); }
.pt-cell.today { border-color: var(--teal); box-shadow: 0 0 0 2px var(--teal-glow); }
.pt-cell.blank { cursor: default; opacity: .35; background: var(--bg); }
.pt-cell-date { font-size: .62em; color: var(--text-muted); line-height: 1.1; text-align: center; }
.pt-marks { display: flex; gap: 2px; height: 5px; }
.pt-mark { width: 5px; height: 5px; border-radius: 50%; }
.pt-soil { width: 100%; height: 6px; background: #e3e6ec; }
.pt-soil.dry { background: #d8b47a; }
.pt-soil.humid { background: #8fd3c7; }
.pt-soil.wet { background: #2f6fb0; }
.pt-drop { width: 16px; height: 18px; }
.pt-drop.watered path { fill: #2f8fd8; stroke: #2f8fd8; }
.pt-drop.expected path { fill: none; stroke: #2f8fd8; stroke-dasharray: 2 2; }
.pt-drop.none path { fill: none; stroke: #d5d9e2; }
.pt-seg { display: flex; gap: 6px; flex-wrap: wrap; }
.pt-seg button { flex: 1; min-width: 64px; padding: 8px 6px; border-radius: 8px; border: 1.5px solid var(--border); background: var(--white); cursor: pointer; font-family: inherit; font-size: .82em; color: var(--navy); }
.pt-seg button.on { border-color: var(--teal); background: var(--teal-light); color: var(--teal); font-weight: 700; }
.pt-types { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.pt-types button { border: 2px solid transparent; border-radius: 12px; background: var(--bg); padding: 6px 2px 4px; cursor: pointer; font-family: inherit; font-size: .7em; color: var(--text-sub); display: flex; flex-direction: column; align-items: center; gap: 3px; }
.pt-types button.on { border-color: var(--teal); background: var(--teal-light); }
.pt-colors { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.pt-colors button { width: 26px; height: 26px; border-radius: 50%; border: 3px solid transparent; cursor: pointer; }
.pt-colors button.on { border-color: var(--navy); }
.pt-colors input[type="color"] { width: 30px; height: 30px; border: none; background: none; cursor: pointer; padding: 0; }
.pt-inline { display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap; }
.pt-inline .field-input { flex: 1; min-width: 120px; }
.pt-evlist { display: flex; flex-direction: column; gap: 6px; }
.pt-ev { display: flex; align-items: center; gap: 8px; font-size: .82em; padding: 6px 10px; border-radius: 8px; background: var(--bg); }
.pt-ev span { flex: 1; }
.pt-ev button { background: none; border: none; cursor: pointer; color: var(--text-muted); font-size: 1em; }
.pt-ev button:hover { color: var(--red); }
.pt-toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%) translateY(20px); background: var(--navy); color: #fff; padding: 10px 18px; border-radius: 10px; font-size: .85em; opacity: 0; pointer-events: none; transition: opacity .2s, transform .2s; z-index: 2000; max-width: calc(100vw - 32px); }
.pt-toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
.pt-toast.err { background: var(--red); }
.pt-restore-row { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: .88em; }
.pt-restore-row span { flex: 1; }
@media (max-width: 720px) {
  .pt-main { padding: 14px 16px 40px; }
  .pt-row { flex-direction: column; align-items: stretch; gap: 6px; }
  .pt-plant { width: auto; }
  .pt-types { grid-template-columns: repeat(4, 1fr); }
}
</style>
<link rel="stylesheet" href="/design-system.css">
</head>
<body>

<!--@SIDEBAR@-->

<div class="page-wrap">
  <div class="page-header">
    <button class="ham-btn" id="ham-btn" onclick="toggleNav()" aria-label="תפריט">
      <svg width="18" height="14" viewBox="0 0 18 14" fill="none">
        <rect width="18" height="2" rx="1" fill="currentColor"/>
        <rect y="6" width="18" height="2" rx="1" fill="currentColor"/>
        <rect y="12" width="18" height="2" rx="1" fill="currentColor"/>
      </svg>
    </button>
    <span class="page-title">מעקב עציצים</span>
    <span class="spacer"></span>
    <button class="btn btn-ghost btn-sm" onclick="refresh()" title="רענון מהשרת">↻</button>
    <button class="btn btn-ghost btn-sm" onclick="openDeleted()">נמחקו</button>
    <button class="btn btn-primary btn-sm" onclick="openPlantModal(null)">+ עציץ חדש</button>
  </div>

  <main class="pt-main">
    <section class="pt-card">
      <div class="pt-summary" id="pt-summary"></div>
      <div class="pt-legend">
        <span><svg class="pt-drop watered" viewBox="0 0 16 18"><path d="M8 1.5C8 1.5 2.5 8 2.5 11.5a5.5 5.5 0 0 0 11 0C13.5 8 8 1.5 8 1.5z" stroke-width="1.6"/></svg>הושקה</span>
        <span><svg class="pt-drop expected" viewBox="0 0 16 18"><path d="M8 1.5C8 1.5 2.5 8 2.5 11.5a5.5 5.5 0 0 0 11 0C13.5 8 8 1.5 8 1.5z" stroke-width="1.6"/></svg>אוטומטי — ממתין לאישור</span>
        <span><i class="pt-swatch" style="background:#d8b47a"></i>יבשה</span>
        <span><i class="pt-swatch" style="background:#8fd3c7"></i>לחה</span>
        <span><i class="pt-swatch" style="background:#2f6fb0"></i>רטובה</span>
        <span><i class="pt-dot" style="background:#d9822b"></i>דישון</span>
        <span><i class="pt-dot" style="background:#7a5bc4"></i>העברת עציץ</span>
        <span><i class="pt-dot" style="background:#4f8a3c"></i>גיזום</span>
        <span><i class="pt-dot" style="background:#c2577a"></i>מזיקים</span>
      </div>
    </section>

    <section class="pt-card" id="pt-sugg-card" style="display:none">
      <div class="pt-sugg-head" onclick="toggleSugg()">
        <span>💡 המלצות</span><span class="pt-sugg-count" id="pt-sugg-count">0</span>
        <span class="spacer"></span><span id="pt-sugg-chev">▾</span>
      </div>
      <div class="pt-sugg-list" id="pt-sugg-list"></div>
    </section>

    <section class="pt-card">
      <div class="pt-rows" id="pt-rows"><div class="pt-empty">טוען…</div></div>
    </section>
  </main>
</div>

<div class="modal-backdrop" id="day-modal" onclick="if(event.target===this)closeModal('day-modal')">
  <div class="modal"><button class="modal-close-btn" onclick="closeModal('day-modal')" aria-label="סגור">✕</button><div id="day-body"></div></div>
</div>
<div class="modal-backdrop" id="plant-modal" onclick="if(event.target===this)closeModal('plant-modal')">
  <div class="modal"><button class="modal-close-btn" onclick="closeModal('plant-modal')" aria-label="סגור">✕</button><div id="plant-body"></div></div>
</div>
<div class="modal-backdrop" id="deleted-modal" onclick="if(event.target===this)closeModal('deleted-modal')">
  <div class="modal"><button class="modal-close-btn" onclick="closeModal('deleted-modal')" aria-label="סגור">✕</button>
    <div class="modal-title">עציצים שנמחקו</div><div id="deleted-body"></div></div>
</div>
<div class="pt-toast" id="pt-toast"></div>

<script>
'use strict';
/*@SHELL_JS@*/

// ── Constants ──────────────────────────────────────────────────
var PLANT_TYPES = [['monstera','מונסטרה'],['fern','שרך'],['cactus','קקטוס'],['succulent','סוקולנט'],
                   ['herb','תבלין'],['flower','פרח'],['tree','עץ'],['sprout','נבט']];
var PALETTE = ['#1e9d8b','#2f6fb0','#7a5bc4','#c2577a','#d9822b','#4f8a3c','#b0503a','#3b8f9e'];
var SOIL_LABELS = {dry: 'יבשה', humid: 'לחה', wet: 'רטובה'};
var EVENT_LABELS = {water: 'השקיה', fertilize: 'דישון', repot: 'העברת עציץ', prune: 'גיזום', pest: 'טיפול במזיקים'};
var EVENT_COLORS = {fertilize: '#d9822b', repot: '#7a5bc4', prune: '#4f8a3c', pest: '#c2577a'};
var ACTION_LABELS = {water_now: 'השקה עכשיו', fertilize_now: 'סמן דישון', confirm_auto: 'אשר השקה', set_soil: 'עדכן אדמה'};
var WEEKDAYS = ['א','ב','ג','ד','ה','ו','ש'];
var DROP = '<path d="M8 1.5C8 1.5 2.5 8 2.5 11.5a5.5 5.5 0 0 0 11 0C13.5 8 8 1.5 8 1.5z" stroke-width="1.6"/>';
var GLYPHS = {
  cactus:    '<path d="M21 34V14a3 3 0 0 1 6 0v20"/><path d="M21 26h-4a2 2 0 0 1-2-2v-5"/><path d="M27 22h4a2 2 0 0 0 2-2v-4"/><path d="M15 34h18l-2 6H17z"/>',
  monstera:  '<path d="M24 38C12 34 9 22 14 12c6 2 14 0 18-4 4 10 2 24-8 30z"/><path d="M24 38c-2-10-2-18 2-26"/><path d="M15 21l5 2M16 29l5-1M30 17l-5 3M29 26l-5 1"/>',
  fern:      '<path d="M14 40C20 30 24 20 32 9"/><path d="M18 34l-5-2M19 31l5 1M21 27l-5-3M22 24l5 0M24 20l-4-4M26 17l5-1M28 13l-2-4"/>',
  succulent: '<path d="M24 35c-3-4-3-10 0-15 3 5 3 11 0 15z"/><path d="M22 34c-4-2-7-6-7-11 4 1 7 4 8 8"/><path d="M26 34c4-2 7-6 7-11-4 1-7 4-8 8"/><path d="M14 35h20l-2 5H16z"/>',
  herb:      '<path d="M24 40V14"/><path d="M24 31c-4-1-7-4-8-8 4 0 7 3 8 8z"/><path d="M24 24c4-1 7-4 8-8-4 0-7 3-8 8z"/><path d="M24 17c-2-3-2-6 0-9 2 3 2 6 0 9z"/>',
  flower:    '<path d="M24 40V24"/><path d="M24 34c-4 0-7-3-8-6 4 0 7 2 8 6z"/><circle cx="24" cy="11.5" r="3.5"/><circle cx="30.5" cy="18" r="3.5"/><circle cx="17.5" cy="18" r="3.5"/><circle cx="24" cy="24.5" r="3.5"/><circle cx="24" cy="18" r="2" fill="#fff"/>',
  tree:      '<path d="M24 8c-7 0-12 5-12 11 0 5 4 9 9 9h6c5 0 9-4 9-9 0-6-5-11-12-11z"/><path d="M24 28v12M24 34l-4-3M24 32l4-3"/>',
  sprout:    '<path d="M24 40V24"/><path d="M24 26c0-6-4-10-11-10 0 6 4 10 11 10z"/><path d="M24 22c0-6 4-10 11-10 0 6-4 10-11 10z"/><path d="M14 40h20"/>'
};

// ── Helpers ────────────────────────────────────────────────────
function pad(n){ return (n < 10 ? '0' : '') + n; }
function localDate(d){ return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
function localDateTime(d){ return localDate(d) + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes()); }
function parseDay(s){ var p = s.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
function esc(s){
  return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
    return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
  });
}
function fmtDay(s){ var d = parseDay(s); return 'יום ' + WEEKDAYS[d.getDay()] + "' " + d.getDate() + '/' + (d.getMonth() + 1); }
function toast(msg, isErr){
  var t = document.getElementById('pt-toast');
  t.textContent = msg;
  t.className = 'pt-toast show' + (isErr ? ' err' : '');
  clearTimeout(toast._t);
  toast._t = setTimeout(function(){ t.className = 'pt-toast'; }, 2600);
}
function closeAllModals(){ document.querySelectorAll('.modal-backdrop').forEach(function(m){ m.classList.remove('open'); }); }
function closeModal(id){ document.getElementById(id).classList.remove('open'); }
function openModal(id){ document.getElementById(id).classList.add('open'); }
function isOpen(id){ return document.getElementById(id).classList.contains('open'); }

function plantIcon(type, color, name, size){
  var initial = esc(String(name || '?').trim().charAt(0) || '?');
  return '<svg viewBox="0 0 48 48" width="' + size + '" height="' + size + '" aria-hidden="true">' +
    '<rect x="1" y="1" width="46" height="46" rx="13" fill="' + esc(color) + '"/>' +
    '<g fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' + (GLYPHS[type] || GLYPHS.sprout) + '</g>' +
    '<circle cx="40" cy="40" r="7" fill="#fff"/>' +
    '<text x="40" y="43.5" text-anchor="middle" font-size="10" font-weight="700" font-family="Segoe UI, Arial" fill="' + esc(color) + '">' + initial + '</text></svg>';
}

// ── Data + once-a-day cache ────────────────────────────────────
var CACHE_KEY = 'plants_cache';
var TODAY = localDate(new Date());
var state = null;

function readCache(){
  try {
    var c = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null');
    return c && c.date === TODAY ? c.payload : null;
  } catch (_) { return null; }
}
function writeCache(p){ try { localStorage.setItem(CACHE_KEY, JSON.stringify({date: TODAY, payload: p})); } catch (_) {} }

// Resolves to the response on success, null on failure (after showing a toast).
function api(method, url, body){
  var opts = {method: method, headers: {'Content-Type': 'application/json'}};
  if (method === 'GET') url += (url.indexOf('?') < 0 ? '?' : '&') + 'today=' + TODAY;
  else opts.body = JSON.stringify(Object.assign({today: TODAY}, body || {}));
  return fetch(url, opts)
    .then(function(r){ return r.json(); })
    .then(function(d){
      if (!d.ok) throw new Error(d.error || 'שגיאה');
      if (d.plants && d.summary) { state = d; writeCache(d); render(); }
      return d;
    })
    .catch(function(e){ toast(e.message || 'שגיאת רשת', true); return null; });
}
function refresh(){
  return api('GET', '/api/plants').then(function(d){
    if (!d && !state) document.getElementById('pt-rows').innerHTML = '<div class="pt-empty">שגיאה בטעינת הנתונים</div>';
    return d;
  });
}
function init(){
  var cached = readCache();
  if (cached) { state = cached; render(); } else { refresh(); }
}
// A tab left open past midnight refreshes when it becomes visible again.
document.addEventListener('visibilitychange', function(){
  if (document.visibilityState !== 'visible') return;
  var now = localDate(new Date());
  if (now !== TODAY) { TODAY = now; refresh(); }
});

// ── Lookups ────────────────────────────────────────────────────
function plantById(id){ for (var i = 0; i < state.plants.length; i++) if (state.plants[i].id === id) return state.plants[i]; return null; }
function dayRow(pid, day){ var rows = state.days[String(pid)] || []; for (var i = 0; i < rows.length; i++) if (rows[i].day === day) return rows[i]; return null; }
function dayEvents(pid, day){ return (state.events[String(pid)] || []).filter(function(e){ return e.event_at.slice(0, 10) === day; }); }

// ── Render ─────────────────────────────────────────────────────
function render(){
  renderSummary();
  renderSuggestions();
  renderRows();
  if (dayCtx && isOpen('day-modal')) renderDay();
}

function renderSummary(){
  var s = state.summary, due = s.due_today + s.overdue;
  document.getElementById('pt-summary').innerHTML =
    '<div class="pt-stat due"><b>' + s.due_today + '</b> להשקות היום</div>' +
    '<div class="pt-stat overdue"><b>' + s.overdue + '</b> באיחור</div>' +
    '<div class="pt-stat pending"><b>' + s.auto_pending_confirm + '</b> אוטומטי ממתין לאישור</div>' +
    '<span class="spacer"></span>' +
    '<button class="btn btn-primary btn-sm" onclick="waterAllDue()"' + (due ? '' : ' disabled') + '>💧 השקה לכל הממתינים (' + due + ')</button>';
}
function waterAllDue(){
  var n = state.summary.due_today + state.summary.overdue;
  if (!n || !confirm('לסמן השקה עכשיו ל-' + n + ' עציצים?')) return;
  api('POST', '/api/plants/water-due', {event_at: localDateTime(new Date())})
    .then(function(d){ if (d) toast('סומנה השקה ל-' + d.watered_count + ' עציצים'); });
}

var suggOpen = true;
try { suggOpen = localStorage.getItem('plants_sugg_open') !== '0'; } catch (_) {}
function toggleSugg(){
  suggOpen = !suggOpen;
  try { localStorage.setItem('plants_sugg_open', suggOpen ? '1' : '0'); } catch (_) {}
  renderSuggestions();
}
function renderSuggestions(){
  var list = state.suggestions;
  document.getElementById('pt-sugg-card').style.display = list.length ? '' : 'none';
  document.getElementById('pt-sugg-count').textContent = list.length;
  document.getElementById('pt-sugg-chev').textContent = suggOpen ? '▾' : '◂';
  var el = document.getElementById('pt-sugg-list');
  el.className = 'pt-sugg-list' + (suggOpen ? '' : ' hidden');
  el.innerHTML = list.map(function(s, i){
    var a = s.action, btns = '';
    if (a) {
      var label = a.type === 'set_interval' ? 'החל (' + a.value + ' ימים)' : ACTION_LABELS[a.type];
      btns += '<button class="btn btn-primary btn-xs" onclick="applySuggestion(' + i + ')">' + label + '</button>';
    }
    if (s.kind === 'seasonal') btns += '<button class="btn btn-ghost btn-xs" onclick="dismissSeason(' + s.plant_id + ')">התעלם</button>';
    return '<div class="pt-sugg ' + s.level + '"><span class="pt-sugg-text">' + esc(s.text) + '</span><span class="pt-sugg-btns">' + btns + '</span></div>';
  }).join('');
}
function applySuggestion(i){
  var s = state.suggestions[i], a = s.action, pid = s.plant_id, now = localDateTime(new Date());
  if (a.type === 'set_interval') {
    var body = {interval_days: a.value};
    if (a.season_key) body.season_ack = a.season_key;
    api('PUT', '/api/plants/' + pid, body).then(function(d){ if (d) toast('המרווח עודכן'); });
  } else if (a.type === 'water_now') {
    api('POST', '/api/plants/' + pid + '/events', {event_type: 'water', event_at: now}).then(function(d){ if (d) toast('סומנה השקה'); });
  } else if (a.type === 'fertilize_now') {
    api('POST', '/api/plants/' + pid + '/events', {event_type: 'fertilize', event_at: now}).then(function(d){ if (d) toast('סומן דישון'); });
  } else if (a.type === 'confirm_auto') {
    api('POST', '/api/plants/' + pid + '/confirm-auto', {day: a.day}).then(function(d){ if (d) toast('ההשקה אושרה'); });
  } else if (a.type === 'set_soil') {
    openDay(pid, TODAY);
  }
}
function dismissSeason(pid){ api('POST', '/api/plants/' + pid + '/dismiss-season', {}); }

function renderRows(){
  var el = document.getElementById('pt-rows');
  if (!state.plants.length) {
    el.innerHTML = '<div class="pt-empty">עדיין אין עציצים — לחצו "+ עציץ חדש" כדי להתחיל 🌱</div>';
    return;
  }
  var days = state.window.slice().reverse();  // today first = RTL leading edge
  el.innerHTML = state.plants.map(function(p){
    var mode = p.irrigation_mode === 'auto'
      ? '<span class="pt-badge auto">אוטומטי · כל ' + p.interval_days + ' ימים · ' + esc(p.auto_time || '') + '</span>'
      : '<span class="pt-badge">ידני · כל ' + p.interval_days + ' ימים</span>';
    var st = p.status === 'overdue' ? ' <span class="pt-status overdue">באיחור</span>'
           : p.status === 'due' ? ' <span class="pt-status due">להשקות היום</span>' : '';
    var last = !p.last_water ? 'טרם הושקה' : p.days_since_water === 0 ? 'הושקה היום' : 'הושקה לפני ' + p.days_since_water + ' ימים';
    return '<div class="pt-row">' +
      '<button class="pt-plant" onclick="openPlantModal(' + p.id + ')" title="עריכת עציץ">' + plantIcon(p.plant_type, p.color, p.name, 44) +
        '<div><div class="pt-plant-name">' + esc(p.name) + '</div><div class="pt-plant-meta">' + mode + '</div>' +
        '<div class="pt-plant-meta">' + last + st + '</div></div></button>' +
      '<div class="pt-cells">' + days.map(function(day){ return cellHtml(p, day); }).join('') + '</div></div>';
  }).join('');
}
function cellHtml(p, day){
  var d = parseDay(day), label = WEEKDAYS[d.getDay()] + ' ' + d.getDate();
  var r = dayRow(p.id, day);
  if (!r) return '<div class="pt-cell blank"><span class="pt-cell-date">' + label + '</span></div>';
  var drop = r.watered ? 'watered' : (r.auto_expected && !r.auto_confirmed ? 'expected' : 'none');
  var marks = dayEvents(p.id, day).filter(function(e){ return e.event_type !== 'water'; })
    .map(function(e){ return '<span class="pt-mark" style="background:' + EVENT_COLORS[e.event_type] + '"></span>'; }).join('');
  var tip = fmtDay(day) + (r.soil_status ? ' · אדמה ' + SOIL_LABELS[r.soil_status] : '') +
            (r.watered ? ' · הושקה' : drop === 'expected' ? ' · השקה אוטומטית ממתינה לאישור' : '');
  return '<button class="pt-cell' + (day === state.today ? ' today' : '') + '" title="' + esc(tip) + '" onclick="openDay(' + p.id + ',\'' + day + '\')">' +
    '<span class="pt-cell-date">' + label + '</span>' +
    '<svg class="pt-drop ' + drop + '" viewBox="0 0 16 18">' + DROP + '</svg>' +
    '<span class="pt-marks">' + marks + '</span>' +
    '<span class="pt-soil ' + (r.soil_status || '') + '"></span></button>';
}

// ── Day editor ─────────────────────────────────────────────────
var dayCtx = null;
function openDay(pid, day){ dayCtx = {pid: pid, day: day}; renderDay(); openModal('day-modal'); }
function renderDay(){
  var p = plantById(dayCtx.pid);
  if (!p) { closeModal('day-modal'); dayCtx = null; return; }
  var day = dayCtx.day, r = dayRow(p.id, day) || {}, evs = dayEvents(p.id, day);
  var now = localDateTime(new Date());
  var defAt = day === TODAY ? now : day + 'T12:00';
  var soil = ['dry', 'humid', 'wet'].map(function(k){
    return '<button class="' + (r.soil_status === k ? 'on' : '') + '" onclick="setSoil(\'' + k + '\')">' + SOIL_LABELS[k] + '</button>';
  }).join('') + '<button class="' + (!r.soil_status ? 'on' : '') + '" onclick="setSoil(null)">לא ידוע</button>';
  var confirmBtn = (p.irrigation_mode === 'auto' && r.auto_expected && !r.auto_confirmed && !r.watered)
    ? '<div class="field-row"><button class="btn btn-primary" style="width:100%;justify-content:center" onclick="confirmAuto()">✔ אשר השקה אוטומטית (' + esc(p.auto_time) + ')</button></div>'
    : '';
  var types = Object.keys(EVENT_LABELS).filter(function(k){ return k !== 'water'; })
    .map(function(k){ return '<option value="' + k + '">' + EVENT_LABELS[k] + '</option>'; }).join('');
  var list = evs.length ? evs.map(function(e){
    return '<div class="pt-ev"><span>' + EVENT_LABELS[e.event_type] + ' · ' + e.event_at.slice(11, 16) +
      (e.source === 'auto_confirmed' ? ' (אוטומטי)' : '') + (e.note ? ' — ' + esc(e.note) : '') + '</span>' +
      '<button onclick="deleteEvent(' + e.id + ')" title="מחיקה" aria-label="מחיקה">✕</button></div>';
  }).join('') : '<div class="pt-plant-meta">אין אירועים ביום זה</div>';
  document.getElementById('day-body').innerHTML =
    '<div class="modal-title" style="display:flex;align-items:center;gap:10px">' + plantIcon(p.plant_type, p.color, p.name, 34) +
      '<span>' + esc(p.name) + ' · ' + fmtDay(day) + '</span></div>' +
    confirmBtn +
    '<div class="field-row"><span class="field-label">מצב אדמה</span><div class="pt-seg">' + soil + '</div></div>' +
    '<div class="field-row"><label class="field-label" for="day-at">מועד (ברירת מחדל: עכשיו)</label><div class="pt-inline">' +
      '<input type="datetime-local" class="field-input" id="day-at" value="' + defAt + '" max="' + now + '">' +
      '<button class="btn btn-primary" onclick="addWater()">💧 סמן השקה</button></div></div>' +
    '<div class="field-row"><span class="field-label">אירוע נוסף באותו מועד</span><div class="pt-inline">' +
      '<select class="field-input" id="day-ev-type">' + types + '</select>' +
      '<input class="field-input" id="day-ev-note" placeholder="הערה (לא חובה)" maxlength="200">' +
      '<button class="btn btn-ghost" onclick="addOtherEvent()">הוסף</button></div></div>' +
    '<div class="field-row"><span class="field-label">אירועים ביום זה</span><div class="pt-evlist">' + list + '</div></div>';
}
function eventAt(){ return document.getElementById('day-at').value; }
function setSoil(k){ api('PUT', '/api/plants/' + dayCtx.pid + '/soil', {day: dayCtx.day, soil_status: k}); }
function addWater(){
  api('POST', '/api/plants/' + dayCtx.pid + '/events', {event_type: 'water', event_at: eventAt()})
    .then(function(d){ if (d) toast('סומנה השקה'); });
}
function addOtherEvent(){
  api('POST', '/api/plants/' + dayCtx.pid + '/events', {
    event_type: document.getElementById('day-ev-type').value,
    event_at: eventAt(),
    note: document.getElementById('day-ev-note').value
  }).then(function(d){ if (d) toast('האירוע נוסף'); });
}
function confirmAuto(){
  api('POST', '/api/plants/' + dayCtx.pid + '/confirm-auto', {day: dayCtx.day})
    .then(function(d){ if (d) toast('ההשקה אושרה'); });
}
function deleteEvent(id){ if (confirm('למחוק את האירוע?')) api('DELETE', '/api/plants/events/' + id, {}); }

// ── Plant add / edit ───────────────────────────────────────────
var editCtx = null;
function openPlantModal(pid){
  var p = pid ? plantById(pid) : null;
  editCtx = p
    ? {id: p.id, name: p.name, plant_type: p.plant_type, color: p.color, irrigation_mode: p.irrigation_mode,
       interval_days: p.interval_days, auto_time: p.auto_time || '07:00'}
    : {id: null, name: '', plant_type: 'monstera', color: PALETTE[(state ? state.plants.length : 0) % PALETTE.length],
       irrigation_mode: 'manual', interval_days: 3, auto_time: '07:00'};
  renderPlantModal();
  openModal('plant-modal');
  setTimeout(function(){ var n = document.getElementById('pm-name'); if (n) n.focus(); }, 50);
}
function pmSet(k, v){ editCtx[k] = v; renderPlantModal(); }
function renderPlantModal(){
  var e = editCtx;
  var types = PLANT_TYPES.map(function(t){
    return '<button class="' + (e.plant_type === t[0] ? 'on' : '') + '" onclick="pmSet(\'plant_type\',\'' + t[0] + '\')">' +
      plantIcon(t[0], e.color, e.name || t[1], 40) + t[1] + '</button>';
  }).join('');
  var colors = PALETTE.map(function(c){
    return '<button class="' + (e.color === c ? 'on' : '') + '" style="background:' + c + '" onclick="pmSet(\'color\',\'' + c + '\')" aria-label="' + c + '"></button>';
  }).join('') + '<input type="color" value="' + esc(e.color) + '" onchange="pmSet(\'color\', this.value)" title="צבע מותאם">';
  var modes = '<button class="' + (e.irrigation_mode === 'manual' ? 'on' : '') + '" onclick="pmSet(\'irrigation_mode\',\'manual\')">ידנית</button>' +
              '<button class="' + (e.irrigation_mode === 'auto' ? 'on' : '') + '" onclick="pmSet(\'irrigation_mode\',\'auto\')">אוטומטית</button>';
  document.getElementById('plant-body').innerHTML =
    '<div class="modal-title" style="display:flex;align-items:center;gap:10px">' + plantIcon(e.plant_type, e.color, e.name, 40) +
      '<span>' + (e.id ? 'עריכת עציץ' : 'עציץ חדש') + '</span></div>' +
    '<div class="field-row"><label class="field-label" for="pm-name">שם</label>' +
      '<input class="field-input" id="pm-name" maxlength="40" value="' + esc(e.name) + '" oninput="editCtx.name=this.value"></div>' +
    '<div class="field-row"><span class="field-label">סוג (קובע את הסמל)</span><div class="pt-types">' + types + '</div></div>' +
    '<div class="field-row"><span class="field-label">צבע</span><div class="pt-colors">' + colors + '</div></div>' +
    '<div class="field-row"><span class="field-label">השקיה</span><div class="pt-seg">' + modes + '</div></div>' +
    '<div class="field-row pt-inline">' +
      '<div style="flex:1"><label class="field-label" for="pm-interval">כל כמה ימים</label>' +
        '<input class="field-input" type="number" min="1" max="60" id="pm-interval" value="' + e.interval_days + '" oninput="editCtx.interval_days=this.value"></div>' +
      (e.irrigation_mode === 'auto'
        ? '<div style="flex:1"><label class="field-label" for="pm-time">שעת השקה אוטומטית</label>' +
          '<input class="field-input" type="time" id="pm-time" value="' + esc(e.auto_time) + '" oninput="editCtx.auto_time=this.value"></div>'
        : '') +
    '</div>' +
    '<div class="modal-footer">' +
      (e.id ? '<button class="btn btn-danger" style="margin-left:auto" onclick="deletePlant()">מחיקה</button>' : '') +
      '<button class="btn btn-ghost" onclick="closeModal(\'plant-modal\')">ביטול</button>' +
      '<button class="btn btn-primary" onclick="savePlant()">שמירה</button></div>';
}
function savePlant(){
  var e = editCtx;
  var body = {name: String(e.name).trim(), plant_type: e.plant_type, color: e.color,
              irrigation_mode: e.irrigation_mode, interval_days: parseInt(e.interval_days, 10)};
  if (e.irrigation_mode === 'auto') body.auto_time = e.auto_time;
  if (!body.name) { toast('יש להזין שם', true); return; }
  var req = e.id ? api('PUT', '/api/plants/' + e.id, body) : api('POST', '/api/plants', body);
  req.then(function(d){ if (d) { closeModal('plant-modal'); toast(e.id ? 'העציץ עודכן' : 'העציץ נוסף'); } });
}
function deletePlant(){
  var e = editCtx;
  if (!confirm('למחוק את "' + e.name + '"? אפשר לשחזר מתוך "נמחקו".')) return;
  api('DELETE', '/api/plants/' + e.id, {}).then(function(d){ if (d) { closeModal('plant-modal'); toast('העציץ נמחק'); } });
}

// ── Deleted / restore ──────────────────────────────────────────
function openDeleted(){
  var body = document.getElementById('deleted-body');
  body.innerHTML = '<div class="pt-plant-meta">טוען…</div>';
  openModal('deleted-modal');
  fetch('/api/plants/deleted').then(function(r){ return r.json(); }).then(function(d){
    if (!d.ok) throw new Error(d.error);
    body.innerHTML = d.plants.length ? d.plants.map(function(p){
      return '<div class="pt-restore-row">' + plantIcon(p.plant_type, p.color, p.name, 30) + '<span>' + esc(p.name) + '</span>' +
        '<button class="btn btn-ghost btn-sm" onclick="restorePlant(' + p.id + ')">שחזור</button></div>';
    }).join('') : '<div class="pt-plant-meta">אין עציצים שנמחקו</div>';
  }).catch(function(e){ toast(e.message || 'שגיאה', true); });
}
function restorePlant(id){
  api('POST', '/api/plants/' + id + '/restore', {}).then(function(d){ if (d) { toast('העציץ שוחזר'); openDeleted(); } });
}

init();
</script>

<!--@DEBUG@-->
</body>
</html>
```

- [ ] **Step 3: Fill in the shared chrome from `SpotifyTracker.html`** (one-off script, run from repo root; not committed)

```bash
python - <<'EOF'
import pathlib
src = pathlib.Path('source/html/SpotifyTracker.html').read_text(encoding='utf-8-sig').splitlines()

def block(start, end):
    i = next(n for n, line in enumerate(src) if start in line)
    j = next(n for n in range(i, len(src)) if end in src[n])
    return '\n'.join(src[i:j + 1])

css = '\n'.join([
    block(':root {', '.btn-danger:hover'),               # variables, body, nav, sidebar, header, buttons
    block('/* ── Modals', '.modal-wide'),                  # modal backdrop + box
    block('.modal-title {', 'input[type="date"].field-input'),  # modal title/close/footer + fields
    block('.debug-fab{', '.debug-line.warn'),             # debug panel
])
sidebar = block('<!-- Nav overlay -->', '</nav>')
sidebar = sidebar.replace('<a class="nav-item active" href="/spotify">', '<a class="nav-item" href="/spotify">')
sidebar = sidebar.replace(
    '<a class="nav-item" href="/spotify">Spotify Tracker</a>',
    '<a class="nav-item" href="/spotify">Spotify Tracker</a>\n    <a class="nav-item active" href="/plants">מעקב עציצים</a>')
js = block("fetch('/api/version')", "document.addEventListener('keydown'")  # version badge, restart, nav
debug = block('<button class="debug-fab"', '</script>')

p = pathlib.Path('source/html/PlantTracker.html')
html = p.read_text(encoding='utf-8')
for marker, value in (('/*@SHELL_CSS@*/', css), ('<!--@SIDEBAR@-->', sidebar),
                      ('/*@SHELL_JS@*/', js), ('<!--@DEBUG@-->', debug)):
    assert html.count(marker) == 1, marker
    html = html.replace(marker, value)
p.write_text(html, encoding='utf-8')
print('ok', len(html))
EOF
```
Expected: `ok <size>`. Then check: `grep -c "app-version-badge-2\|function restartServer\|function toggleNav\|_startDebugStream\|nav-item active\" href=\"/plants\"" source/html/PlantTracker.html` → `5` or more, and `grep -n "@SHELL\|@SIDEBAR@\|@DEBUG@" source/html/PlantTracker.html` → no output.

- [ ] **Step 4: Run the page test**

Run: `python -m pytest tests/test_plant_routes.py -q`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add source/html/PlantTracker.html tests/test_plant_routes.py
git commit -m "feat(plants): plant tracker page with SVG plant badges and daily cache" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Sidebar link everywhere, version, run & verify

**Files:**
- Modify (add one nav line after the Spotify link): `source/WebApp.py` (2 places), `source/src_utils/utils.py`, `source/html/Base_template.html`, `Bills.html`, `CardAnalysis.html`, `Category_output.html`, `Files.html`, `Organizer_Table.html`, `RecurringCharges.html`, `Search.html`, `SpotifyTracker.html`, `Tagger.html`
- Skip: `source/html/output.html` (stale prettified artifact, multi-line links) and `Outputs/**` (generated; picks up the link on regeneration)
- Modify: `VERSION` → `1.17.0`

- [ ] **Step 1: Insert the nav link** (keeps each file's indentation and line endings)

```bash
python - <<'EOF'
import pathlib, re
files = ['source/WebApp.py', 'source/src_utils/utils.py'] + [
    f'source/html/{n}.html' for n in ('Base_template', 'Bills', 'CardAnalysis', 'Category_output', 'Files',
                                      'Organizer_Table', 'RecurringCharges', 'Search', 'SpotifyTracker', 'Tagger')]
pat = re.compile(r'^([ \t]*)(<a class="nav-item(?: active)?" href="/spotify">Spotify Tracker</a>)(\r?\n)', re.M)
for f in files:
    p = pathlib.Path(f)
    raw = p.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    text = raw.decode('utf-8-sig')
    if 'href="/plants"' in text:
        print('skip (already has link)', f); continue
    new, n = pat.subn(lambda m: f'{m[1]}{m[2]}{m[3]}{m[1]}<a class="nav-item" href="/plants">מעקב עציצים</a>{m[3]}', text)
    assert n >= 1, f
    p.write_bytes((b'\xef\xbb\xbf' if bom else b'') + new.encode('utf-8'))
    print(n, f)
EOF
```
Expected: `2 source/WebApp.py`, `1` for each other file. Verify: `grep -rn 'href="/plants"' source --include=*.py --include=*.html | grep -v pycache | wc -l` → `14` (13 inserted + the active link in PlantTracker.html).

- [ ] **Step 2: Bump version** — set `VERSION` to `1.17.0`.

- [ ] **Step 3: Full test run**

Run: `python -m pytest tests/test_plant_logic.py tests/test_plant_suggestions.py tests/test_plant_service.py tests/test_plant_routes.py -q`
Expected: `50 passed`. Then the DB round-trip: `$env:PLANT_DB_TESTS='1'; python -m pytest tests/test_plant_store_db.py -q; Remove-Item Env:PLANT_DB_TESTS` → `1 passed`.

- [ ] **Step 4: Restart the dev server and confirm the version**

Clear `__pycache__` under `source/`, stop the old server, start `BankDash` via `preview_start` (launch.json, port 5050), then `GET http://localhost:5050/api/version` → `{"version": "1.17.0"}`.

- [ ] **Step 5: Verify in the browser pane** (logged in via the landing page)

1. Open `/plants` → empty state text, summary shows 0/0/0, no console errors.
2. Add a manual plant (fern, interval 2) and an auto plant (monstera, every 3 days at 07:00) → both rows appear with distinct icons, today's cell highlighted.
3. Click today's cell on the manual plant → set soil "יבשה", "סמן השקה" with the default time → drop filled, soil strip sand, "הושקה היום".
4. Add a "דישון" event → orange marker dot on the cell.
5. Reload the page → `read_network_requests` shows **no** `/api/plants` request (served from the daily cache).
6. Delete the auto plant → gone; "נמחקו" lists it; restore → back.
7. `resize_window` mobile (375px) → rows stack, cells scroll inside the row, no page-level horizontal scroll.
8. Clean up the test plants afterwards (delete them) so the real list starts empty — or leave them if the user wants to keep them.
9. Screenshot as proof.

- [ ] **Step 6: Commit**

```bash
git add VERSION source/WebApp.py source/src_utils/utils.py source/html/Base_template.html source/html/Bills.html source/html/CardAnalysis.html source/html/Category_output.html source/html/Files.html source/html/Organizer_Table.html source/html/RecurringCharges.html source/html/Search.html source/html/SpotifyTracker.html source/html/Tagger.html
git commit -m "feat(plants): add מעקב עציצים to every sidebar; v1.17.0" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
Do not push unless the user asks.
