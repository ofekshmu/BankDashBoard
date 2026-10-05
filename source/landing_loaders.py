"""DB loaders for the landing dashboard blocks that need only the database.

Each loader reuses the feature's own data function (same numbers as its page)
and hands the raw data to the matching landing_service builder. Monthly,
accounts and housing need WebApp internals and are registered from WebApp.py.
"""
import json

import landing_service as ls


def _db():
    from database import DataBase
    return DataBase()


# Thin wrappers around feature modules, so tests can stub them.
def _card_data(db):
    from CardAnalysis import get_card_analysis_data
    return get_card_analysis_data(db)


def _spotify_balances(db):
    from SpotifyTracker import compute_all_balances
    return compute_all_balances(db)


def _plants_summary(today):
    import plant_service
    from routes.plant_routes import get_store
    return plant_service.build_payload(get_store(), today)['summary']


def load_cards(today):
    db = _db()
    db.ensure_card_limits_table()
    data = _card_data(db)
    return ls.build_cards(data.get('cards'), data.get('month'))


def load_timeline(today):
    db = _db()
    db.ensure_timeline_tables()
    rows = db.cursor.execute(
        'SELECT e.Name, e.Event_Date, e.Created_At FROM TimelineEvents e '
        'LEFT JOIN TimelineCategories tc ON tc.Key = e.Category '
        'WHERE e.Deleted_At IS NULL AND tc.Deleted_At IS NULL '
        'ORDER BY e.Created_At DESC NULLS LAST, e.ID DESC LIMIT 1').fetchall()
    if not rows:
        return ls.build_timeline(None)
    name, event_date, created_at = rows[0]
    return ls.build_timeline({'name': name, 'event_date': event_date, 'created_at': created_at})


def load_bills(today):
    """Same entries and types the bills page loads (/api/bills/entries, /api/bills/types)."""
    db = _db()
    return ls.build_bills(db.get_bill_types(), db.get_bill_entries())


def load_spotify(today):
    db = _db()
    db.ensure_spotify_tables()
    return ls.build_spotify(_spotify_balances(db))


def load_plants(today):
    return ls.build_plants(_plants_summary(today))


def load_recurring(today):
    db = _db()
    db.ensure_recurring_tables()
    cache = db.get_recurring_cache()
    groups = json.loads(cache['data_json']).get('groups') if cache and cache.get('data_json') else []
    return ls.build_recurring(groups, today)


def load_tagger(today):
    """Untagged count and newest untagged transactions, from the Tagger page's own queries.
    get_untagged_recent takes the newest IDs per table, then sorts by date — a few hundred
    rows is plenty for the newest dates to be among them."""
    db = _db()
    return ls.build_tagger(db.get_untagged_recent(limit=200), db.count_untagged_total())


def load_files(today):
    rows = _db().cursor.execute(
        'SELECT File_Name, Format, Date, Last_update FROM File '
        'ORDER BY Last_update DESC NULLS LAST, Date DESC LIMIT 1').fetchall()
    if not rows:
        return ls.build_files(None)
    name, fmt, d, last_update = rows[0]
    return ls.build_files({'file_name': name, 'format': fmt, 'date': d, 'last_update': last_update})


def _file_rows(db):
    """[(charge-month date, card number)] from the File table (the organizer's source)."""
    df = db.get_file_table()
    return [] if df is None or df.empty else list(zip(df['Date'], df['Card_Number']))


def _card_statuses(month_start):
    """{card: verified?} for one spending month — the organizer table's per-cell check."""
    from src_utils.utils import utils
    v = utils.card_charge_validation(utils.get_card_charge_df(month_start), month_start,
                                     tolerance=20, interactive=False)
    return {} if v.empty else {str(c): bool(s) for c, s in zip(v['CardID'], v['Status'])}


def load_card_validation_misses(today, months=3):
    """[(spending month 'YYYY_MM', card)] whose charge matched no bank debit, over the last
    `months` spending months, newest first — the organizer table's red cells. Only cards with
    a file for that month count (a file is dated by its charge month, one month later)."""
    from datetime import datetime
    rows = _file_rows(_db())
    misses = []
    for back in range(1, months + 1):
        n = today.year * 12 + today.month - 1 - back
        spend = datetime(n // 12, n % 12 + 1, 1)
        charge = (spend.year + spend.month // 12, spend.month % 12 + 1)
        cards = {str(card) for d, card in rows
                 if ls.as_date(d) and (ls.as_date(d).year, ls.as_date(d).month) == charge}
        if not cards:
            continue
        statuses = _card_statuses(spend)
        misses += [(spend.strftime('%Y_%m'), c) for c in sorted(cards) if statuses.get(c) is False]
    return misses


def load_month_keys():
    """Months that have bank data, ascending: [{'key': 'YYYY_MM'}, ...].

    Deliberately does not catch exceptions: a DB failure must surface as the
    route's isolated (uncached) 500 instead of a silent stale fallback."""
    rows = _db().cursor.execute(
        'SELECT DISTINCT LEFT(CAST(Date AS TEXT), 7) FROM BankTransactions '
        'WHERE Date IS NOT NULL ORDER BY 1').fetchall()
    keys = []
    for row in rows:
        ym = str(row[0])
        if len(ym) == 7 and ym[4] == '-' and ym[:4].isdigit() and ym[5:].isdigit():
            keys.append({'key': f'{ym[:4]}_{ym[5:]}'})
    return keys


def register_default_loaders():
    from routes.landing_routes import register_loader
    for name, fn in (('cards', load_cards), ('timeline', load_timeline), ('bills', load_bills),
                     ('spotify', load_spotify), ('plants', load_plants), ('recurring', load_recurring),
                     ('tagger', load_tagger), ('files', load_files)):
        register_loader(name, fn)
