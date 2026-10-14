"""The "מידע חיוני" box of each apartment: a short, ordered list of name → detail rows
(contractors, meter numbers, phone numbers, address, ...) that the user keeps up to date.

Pure validation over a `db` (DataBase or a test fake); the page is in Base_template.html and the
endpoints are in routes/housing_project_routes.py.
"""
APARTMENTS = ('shabazi', 'mona')
MAX_ITEMS = 60
MAX_LABEL = 60
MAX_VALUE = 500


class InfoError(Exception):
    """A request the user can fix; the message is shown to them (Hebrew)."""


class UnknownApartment(InfoError):
    pass


def _check_apartment(prop):
    if prop not in APARTMENTS:
        raise UnknownApartment('הנכס לא נמצא')


def load_info(db, prop):
    """The apartment's rows, in the user's order: [{'label', 'value'}]."""
    _check_apartment(prop)
    db.ensure_housing_info_table()
    return db.get_housing_info(prop)


def _clean(items):
    if not isinstance(items, list):
        raise InfoError('רשימה לא תקינה')
    if len(items) > MAX_ITEMS:
        raise InfoError(f'אפשר לשמור עד {MAX_ITEMS} שורות')
    out = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('label'), str) or not isinstance(item.get('value'), str):
            raise InfoError('שורה לא תקינה')
        label, value = item['label'].strip(), item['value'].strip()
        if not label and not value:
            continue                      # an untouched new row
        if not label:
            raise InfoError('לכל שורה צריך שם')
        if len(label) > MAX_LABEL:
            raise InfoError(f'השם ארוך מדי (עד {MAX_LABEL} תווים)')
        if len(value) > MAX_VALUE:
            raise InfoError(f'הפירוט ארוך מדי (עד {MAX_VALUE} תווים)')
        out.append({'label': label, 'value': value})
    return out


def save_info(db, prop, items):
    """Replace the apartment's rows with `items` (blank rows dropped); returns what was saved.
    Nothing is saved when any row is invalid."""
    _check_apartment(prop)
    cleaned = _clean(items)
    db.ensure_housing_info_table()
    db.replace_housing_info(prop, cleaned)
    return cleaned
