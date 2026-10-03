import json
from datetime import date, datetime

import landing_loaders as ll

TODAY = date(2026, 10, 4)


class FakeCursor:
    def __init__(self, rows_by_table):
        self.rows_by_table, self.sql = rows_by_table, []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        self._rows = next((rows for key, rows in self.rows_by_table.items() if key in sql), [])
        return self

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeDB:
    def __init__(self, rows_by_table=None, **attrs):
        self.cursor = FakeCursor(rows_by_table or {})
        self.ensured = []
        for k, v in attrs.items():
            setattr(self, k, v)

    def __getattr__(self, name):
        if name.startswith('ensure_'):
            return lambda: self.ensured.append(name)
        raise AttributeError(name)


def use(monkeypatch, db):
    monkeypatch.setattr(ll, '_db', lambda: db)
    return db


def test_timeline_reads_newest_created_event(monkeypatch):
    db = use(monkeypatch, FakeDB({'TimelineEvents': [('חתונה', date(2026, 11, 2), datetime(2026, 10, 1))]}))
    b = ll.load_timeline(TODAY)
    assert b['kpi'] == 'חתונה' and 'ensure_timeline_tables' in db.ensured
    sql = db.cursor.sql[-1]
    assert 'Deleted_At IS NULL' in sql and 'ORDER BY e.Created_At DESC' in sql
    use(monkeypatch, FakeDB({}))
    assert ll.load_timeline(TODAY)['dot'] == 'grey'


def test_bills_excludes_fillers(monkeypatch):
    db = use(monkeypatch, FakeDB({'BillEntries': [(1, 'חשמל', '2026-01', '2026-02', 600)]}))
    b = ll.load_bills(TODAY)
    assert b['kpi'] == '300₪' and 'COALESCE(e.Is_Filler, 0) = 0' in db.cursor.sql[-1]


def test_files_newest(monkeypatch):
    use(monkeypatch, FakeDB({'FROM File': [('a.xlsx', 'Leumi Bank', date(2026, 10, 1), datetime(2026, 10, 3))]}))
    assert ll.load_files(TODAY)['details'] == ['a.xlsx', 'Leumi Bank']


def test_tagger(monkeypatch):
    use(monkeypatch, FakeDB(get_recently_tagged=lambda limit: [
        {'name': 'שופרסל', 'charge_value': 10, 'category': 'סופר', 'exec_date': '2026-10-02'}][:limit]))
    assert ll.load_tagger(TODAY)['caption'] == 'שופרסל'
    use(monkeypatch, FakeDB(get_recently_tagged=lambda limit: []))
    assert ll.load_tagger(TODAY)['dot'] == 'grey'


def test_recurring_reads_cached_groups(monkeypatch):
    data = {'groups': [{'name': 'ביטוח', 'current_amount': 300, 'next_expected': '2026-10-06'}]}
    use(monkeypatch, FakeDB(get_recurring_cache=lambda: {'data_json': json.dumps(data)}))
    assert ll.load_recurring(TODAY)['kpi'] == '300₪'
    use(monkeypatch, FakeDB(get_recurring_cache=lambda: None))
    assert ll.load_recurring(TODAY)['dot'] == 'grey'


def test_cards_spotify_plants_use_existing_functions(monkeypatch):
    db = use(monkeypatch, FakeDB())
    monkeypatch.setattr(ll, '_card_data', lambda d: {'cards': [{'card_id': '1', 'network': 'Visa', 'current_charge': 5}]})
    monkeypatch.setattr(ll, '_spotify_balances', lambda d: [{'name': 'דנה', 'balance': -30}])
    monkeypatch.setattr(ll, '_plants_summary', lambda today: {'due_today': 1, 'overdue': 0, 'auto_pending_confirm': 0})
    assert ll.load_cards(TODAY)['kpi'] == '1' and 'ensure_card_limits_table' in db.ensured
    assert ll.load_spotify(TODAY)['kpi'] == '30₪' and 'ensure_spotify_tables' in db.ensured
    assert ll.load_plants(TODAY)['kpi'] == '1'


def test_register_default_loaders(monkeypatch):
    from routes import landing_routes as lr
    monkeypatch.setattr(lr, 'LOADERS', {})
    ll.register_default_loaders()
    assert set(lr.LOADERS) == {'cards', 'timeline', 'bills', 'spotify', 'plants', 'recurring', 'tagger', 'files'}


def test_load_month_keys_sorted_keys_from_bank_transactions(monkeypatch):
    db = use(monkeypatch, FakeDB({'BankTransactions': [('2026-08',), ('2026-09',)]}))
    assert ll.load_month_keys() == [{'key': '2026_08'}, {'key': '2026_09'}]
    assert 'BankTransactions' in db.cursor.sql[0]


def test_load_month_keys_skips_malformed_rows(monkeypatch):
    use(monkeypatch, FakeDB({'BankTransactions': [('2026-08',), ('bad',), ('20260-9',), ('2026/09',), ('abcd-ef',), ('2026-09',)]}))
    assert ll.load_month_keys() == [{'key': '2026_08'}, {'key': '2026_09'}]


def test_load_month_keys_propagates_errors(monkeypatch):
    class Boom:
        class cursor:
            @staticmethod
            def execute(sql, params=None):
                raise RuntimeError('db down')
    use(monkeypatch, Boom())
    try:
        ll.load_month_keys()
        assert False, 'should raise'
    except RuntimeError:
        pass
