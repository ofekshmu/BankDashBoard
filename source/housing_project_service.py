"""New-build housing projects (Mona): loading, validating edits and feeding the accounts page.

Pure orchestration over a `db` (DataBase or a test fake) — the money model is in
src_utils/housing_projects.py and the routes are in routes/housing_project_routes.py.
"""
import logging
import math
from datetime import date

import src_utils.housing_projects as hp

logger = logging.getLogger(__name__)

MAX_PRICE = 1e10
MAX_CATEGORY_LEN = 80


class ProjectError(Exception):
    """A request the user can fix; the message is shown to them (Hebrew)."""


class UnknownProject(ProjectError):
    pass


def account_name(settings):
    """The asset's name on the accounts page ('נכס מונה'); 'נכס' puts it in the real-estate group."""
    return f"נכס {settings['name']}"


# ── loading ────────────────────────────────────────────────────────────────
def _timeline_category(db, settings):
    """The project's timeline category key: the saved one while it exists, else the category labelled
    like the project ('MONA' / 'מונה'), which is then remembered. None when there is none."""
    cat = settings.get('timeline_category')
    if cat and db.timeline_category_exists(cat):
        return cat
    labels = {settings['name'].strip().lower(), settings['key'].lower()}
    for c in db.get_timeline_categories():
        if c['label'].strip().lower() in labels:
            db.update_housing_project(settings['key'], timeline_category=c['key'])
            return c['key']
    return None


def _with_kinds(db, key, txs):
    """The project's payments with their automatic kind and the kind the user chose (if it fits)."""
    chosen = db.get_housing_tx_kinds(key)
    out = []
    for t in txs:
        is_out = bool(t['out'] and t['out'] > 0)
        auto = hp.classify_kind(t['name'], t['description'], t['out'], t['income'])
        out.append({**t, 'auto_kind': auto, 'kind': hp.apply_override(auto, chosen.get(t['key']), is_out)})
    return out


def _load(db, key):
    db.ensure_housing_project_tables()
    settings = db.get_housing_project(key)
    if not settings:
        raise UnknownProject('הפרויקט לא נמצא')
    settings['timeline_category'] = _timeline_category(db, settings)
    return settings


def _events(db, settings):
    if not settings['timeline_category']:
        return []
    return db.get_timeline_events(category=settings['timeline_category'])


def _build(db, settings, today):
    txs = _with_kinds(db, settings['key'], db.get_project_transactions(settings['tx_category']))
    return txs, hp.build_project(settings, txs, _events(db, settings), today)


def project_payload(db, key, today):
    """Everything the housing page's project tab shows (see housing_projects.build_project)."""
    settings = _load(db, key)
    _, payload = _build(db, settings, today)
    payload['account_name'] = account_name(settings)
    return payload


# ── editing ────────────────────────────────────────────────────────────────
def _number(value, label, lo, hi, *, low_open=False):
    if isinstance(value, bool) or value is None or value == '':
        raise ProjectError(f'{label} לא תקין')
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ProjectError(f'{label} לא תקין')
    if math.isnan(n) or math.isinf(n) or n > hi or n < lo or (low_open and n == lo):
        raise ProjectError(f'{label} חייב להיות בין {lo:g} ל-{hi:g}' if not low_open else f'{label} לא תקין')
    return n


def _date_or_none(value, label):
    if value in (None, ''):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ProjectError(f'{label} לא תקין')


def update_project(db, key, body, today):
    """Validate and save the given settings (price, down_pct, growth_pct, contract_date, delivery_date,
    tx_category); returns the new payload. Nothing is saved when any field is invalid."""
    current = _load(db, key)
    fields = {}
    if 'price' in body:
        raw = body['price']
        fields['price'] = None if raw in (None, '') else _number(raw, 'מחיר הדירה', 0, MAX_PRICE, low_open=True)
    if 'down_pct' in body:
        fields['down_pct'] = _number(body['down_pct'], 'אחוז מקדמה', 0, 100)
    if 'mortgage_pct' in body:
        fields['mortgage_pct'] = _number(body['mortgage_pct'], 'אחוז המשכנתא', 0, 100)
    if 'growth_pct' in body:
        fields['growth_pct'] = _number(body['growth_pct'], 'שיעור עליית הערך', 0, hp.MAX_GROWTH_PCT)
    for name, label in (('contract_date', 'תאריך החתימה'), ('delivery_date', 'תאריך המסירה')):
        if name in body:
            fields[name] = _date_or_none(body[name], label)
    if 'tx_category' in body:
        cat = body['tx_category'].strip() if isinstance(body['tx_category'], str) else ''
        if not cat or len(cat) > MAX_CATEGORY_LEN:
            raise ProjectError('שם הקטגוריה לא תקין')
        fields['tx_category'] = db.canonical_category(cat)
    if not fields:
        raise ProjectError('אין מה לשנות')
    contract = fields.get('contract_date', current['contract_date'])
    delivery = fields.get('delivery_date', current['delivery_date'])
    if contract and delivery and delivery < contract:
        raise ProjectError('תאריך המסירה לפני תאריך החתימה')
    down = fields.get('down_pct', current['down_pct'])
    mortgage = fields.get('mortgage_pct', current['mortgage_pct'])
    if down > 100 - mortgage:
        raise ProjectError(f'המקדמה ({down:g}%) גדולה מההון העצמי הנדרש ({100 - mortgage:g}% — מה שנשאר אחרי המשכנתא)')
    db.update_housing_project(key, **fields)
    return project_payload(db, key, today)


def set_tx_kind(db, key, tx_key, kind, today):
    """Remember that one payment goes into the apartment price / is an extra cost (outgoing) or is
    income / a refund (incoming); kind None goes back to the automatic one. Returns the new payload."""
    settings = _load(db, key)
    txs = {t['key']: t for t in db.get_project_transactions(settings['tx_category'])}
    t = txs.get(tx_key)
    if t is None:
        raise ProjectError('התנועה לא שייכת לפרויקט')
    if kind is not None:
        allowed = hp.OUT_KINDS if t['out'] and t['out'] > 0 else hp.IN_KINDS
        if kind not in allowed:
            raise ProjectError('סוג לא מתאים לתנועה')
    db.set_housing_tx_kind(key, tx_key, kind)
    return project_payload(db, key, today)


# ── the monthly analysis: payments that went into an apartment's value ─────
SHABAZI = 'shabazi'                       # the existing apartment: no project row, only per-payment kinds
INVESTMENT_KINDS = (hp.KIND_PRICE, hp.KIND_REFUND)


def shabazi_category():
    from src_utils.mortgage import MORTGAGE_CATEGORY
    return MORTGAGE_CATEGORY


def investment_keys(db):
    """Keys ('Table:ID' / 'split:ID') of every payment that went into an apartment's value — a Mona payment of
    kind price (or a refund of such money) and any שבזי payment the user marked so. The monthly analysis shows
    them as investments instead of expenses (src_utils/property_investments.py)."""
    db.ensure_housing_project_tables()
    keys = set()
    settings = db.get_housing_project('mona')
    if settings:
        for t in _with_kinds(db, settings['key'], db.get_project_transactions(settings['tx_category'])):
            if t['kind'] in INVESTMENT_KINDS:
                keys.add(t['key'])
    marked = {k for k, kind in db.get_housing_tx_kinds(SHABAZI).items() if kind in INVESTMENT_KINDS}
    if marked:       # a payment re-tagged elsewhere since it was marked is no longer the apartment's
        current = db.get_all_category_transactions(shabazi_category())
        marked &= set(current['Key']) if 'Key' in current.columns else set()
    keys.update(marked)
    return keys


def apartment_categories(db):
    """{category name: apartment key} for the categories whose payments can go into an apartment's value:
    the Mona project's tag and שבזי's. The tagger offers the expense-type choice for exactly these."""
    db.ensure_housing_project_tables()
    out = {shabazi_category(): SHABAZI}
    settings = db.get_housing_project('mona')
    if settings:
        out[settings['tx_category']] = 'mona'
    return out


def apply_tag_kind(db, table, tx_id, category, kind, explicit=True):
    """Right after a transaction was tagged with `category`: remember whether it went into the apartment's value
    (`kind` 'price') or is an extra expense (anything else = the default). A choice left over from an earlier
    apartment tag is dropped when the transaction is tagged elsewhere. Money coming in cannot go into the value,
    so only outgoing payments keep 'price'. With `explicit` False (the request said nothing about the type — e.g. a
    description edit) the payment's own apartment choice is left as it is."""
    key = f'{table}:{tx_id}'
    project = apartment_categories(db).get(category)
    for pkey in ('mona', SHABAZI):
        if pkey != project and key in db.get_housing_tx_kinds(pkey):
            db.set_housing_tx_kind(pkey, key, None)
    if not project or not explicit:
        return
    wanted = hp.KIND_PRICE if kind == hp.KIND_PRICE and db.is_outgoing(table, tx_id) else None
    if (db.get_housing_tx_kinds(project).get(key) or None) != wanted:
        db.set_housing_tx_kind(project, key, wanted)


def shabazi_default_kind(out):
    """A שבזי payment is an expense (or income) until the user says it went into the apartment's value."""
    return hp.KIND_COST if out and out > 0 else hp.KIND_INCOME


def attach_kinds(df, chosen):
    """`df` (housing transactions with Key / Out) with a Kind column: the user's choice when it fits the payment's
    direction, else the default."""
    if df is None or df.empty or 'Key' not in df.columns:
        return df
    df = df.copy()
    df['Kind'] = [hp.apply_override(shabazi_default_kind(out), chosen.get(key), bool(out and out > 0))
                  for key, out in zip(df['Key'], df['Out'])]
    return df


def set_shabazi_tx_kind(db, tx_key, kind):
    """Remember that a שבזי payment went into the apartment's value / is an expense (outgoing) or income / a refund
    (incoming); None goes back to the default. Returns {key: kind} of all the user's choices."""
    if not isinstance(tx_key, str):
        raise ProjectError('התנועה לא שייכת לנכס')
    db.ensure_housing_project_tables()
    rows = db.get_all_category_transactions(shabazi_category())
    match = rows[rows['Key'] == tx_key] if 'Key' in rows.columns else rows.iloc[0:0]
    if match.empty:
        raise ProjectError('התנועה לא שייכת לנכס')
    if kind is not None:
        allowed = hp.OUT_KINDS if float(match.iloc[0]['Out'] or 0) > 0 else hp.IN_KINDS
        if kind not in allowed:
            raise ProjectError('סוג לא מתאים לתנועה')
    db.set_housing_tx_kind(SHABAZI, tx_key, kind)
    return db.get_housing_tx_kinds(SHABAZI)


# ── the asset on the accounts page ─────────────────────────────────────────
def account_assets(db, today):
    """{account name: [[iso date, equity], ...]} for every project that has money in its price."""
    db.ensure_housing_project_tables()
    out = {}
    for settings in db.list_housing_projects():
        settings['timeline_category'] = _timeline_category(db, settings)
        txs = _with_kinds(db, settings['key'], db.get_project_transactions(settings['tx_category']))
        series = hp.equity_history(settings, txs, _events(db, settings), today)
        if series:
            out[account_name(settings)] = [[d.isoformat(), round(v, 2)] for d, v in series]
    return out


def overlay_accounts(payload, db, today):
    """The accounts payload with the projects' assets added (and the Total shifted by them).
    Never raises: when the projects can't be read the accounts page is served without them."""
    try:
        return hp.apply_overlay(payload, account_assets(db, today))
    except Exception:
        logger.exception('housing projects could not be added to the accounts payload')
        return payload
