"""Rule-based care suggestions for the plant tracker — pure functions."""
from datetime import timedelta

from src_utils.plant_logic import plant_status, season_key, soil_checked_status

_DAY = timedelta(days=1)
_MIN_INTERVAL, _MAX_INTERVAL = 1, 60


def _sugg(plant, kind, level, text, action=None):
    return {'plant_id': plant['id'], 'kind': kind, 'level': level, 'text': text, 'action': action}


def _round_half_up(x):
    return int(x + 0.5)


def _clamp_interval(n):
    return max(_MIN_INTERVAL, min(_MAX_INTERVAL, n))


def build_suggestions(plant, rows, last_events, today):
    out = []
    name = plant['name']
    interval = plant['interval_days']
    by_day = {r['day']: r for r in rows}
    # Day history from before the last interval change says nothing about the new interval.
    since_change = plant.get('interval_changed_at')
    # A plant on a shared irrigation config: changing the interval would change every plant on it,
    # so interval tips point at the config instead of offering a one-click change.
    config = plant.get('config_name')
    check_config = f' — בדוק את תוכנית "{config}"' if config else ''

    def _after_change(d):
        return since_change is None or d > since_change

    # 1. Overdue — manual plants only (an auto plant is watered by its system), and not when the
    #    soil was checked today and found moist/wet (the user decided it needs no water today)
    since, status = plant_status(plant, last_events.get('water'), today)
    status = soil_checked_status(status, by_day.get(today))
    if plant['irrigation_mode'] == 'manual' and status == 'overdue':
        out.append(_sugg(plant, 'overdue', 'alert',
                         f'{name}: באיחור השקיה של {since - interval} ימים', {'type': 'water_now'}))

    # 2. Soil found dry the day after a watering — twice in the window. Dry on the very day it was
    #    watered is the normal "check soil, then water" routine and does not count.
    fast = [d for d, r in by_day.items() if r['soil_status'] == 'dry' and _after_change(d)
            and _after_change(d - _DAY) and by_day.get(d - _DAY, {}).get('watered')]
    new = _clamp_interval(interval - 1)
    if len(fast) >= 2 and config:
        out.append(_sugg(plant, 'dries_fast', 'warn', f'{name}: האדמה מתייבשת מהר{check_config}'))
    elif len(fast) >= 2 and new != interval:
        out.append(_sugg(plant, 'dries_fast', 'warn',
                         f'{name}: האדמה מתייבשת מהר — מומלץ לקצר את המרווח ל-{new} ימים',
                         {'type': 'set_interval', 'value': new}))

    # 3. Wet three days in a row (today and the two before)
    wet_days = [today - i * _DAY for i in range(3)]
    new = _clamp_interval(interval + 1)
    wet_streak = all(_after_change(d) and by_day.get(d, {}).get('soil_status') == 'wet' for d in wet_days)
    if wet_streak and config:
        out.append(_sugg(plant, 'overwater', 'warn', f'{name}: האדמה רטובה 3 ימים ברצף{check_config}'))
    elif wet_streak and new != interval:
        out.append(_sugg(plant, 'overwater', 'warn',
                         f'{name}: האדמה רטובה 3 ימים ברצף — סכנת השקיית יתר, מומלץ להאריך את המרווח',
                         {'type': 'set_interval', 'value': new}))

    # 4. Seasonal interval adjustment — once per season (season_ack), and not after the
    #    interval was already tuned this season
    key = season_key(today)
    tuned_this_season = since_change is not None and season_key(since_change) == key
    if key and not config and plant.get('season_ack') != key and not tuned_this_season:
        if key.endswith('summer'):
            new = _clamp_interval(_round_half_up(interval * 0.75))
            text = f'{name}: קיץ — מומלץ להשקות כל {new} ימים במקום {interval}'
        else:
            new = _clamp_interval(_round_half_up(interval * 1.25))
            text = f'{name}: חורף — אפשר להאריך את המרווח ל-{new} ימים'
        if new != interval:
            out.append(_sugg(plant, 'seasonal', 'info', text,
                             {'type': 'set_interval', 'value': new, 'season_key': key}))

    # 5. Fertilize reminder in growing season (Mar–Sep), plants older than 30 days
    last_fert = last_events.get('fertilize')
    if (3 <= today.month <= 9 and (today - plant['created_at']).days >= 30
            and (last_fert is None or (today - last_fert).days > 30)):
        out.append(_sugg(plant, 'fertilize', 'info',
                         f'{name}: לא דושן ביותר מ-30 יום — עונת גדילה, מומלץ לדשן',
                         {'type': 'fertilize_now'}))

    # 6. No soil status in the last 7 days
    if not any(by_day.get(today - i * _DAY, {}).get('soil_status') for i in range(7)):
        out.append(_sugg(plant, 'no_soil', 'info',
                         f'{name}: לא עודכן מצב אדמה בשבוע האחרון', {'type': 'set_soil'}))
    return out
