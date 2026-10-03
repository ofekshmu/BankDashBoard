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
