"""Updating a stored credit-card file with a newer copy: the report and the decision, against an
in-memory fake database, a fake Excel reader and temporary folders."""
import os
from datetime import date, datetime

import pytest

import file_update_service as svc

FMT = 'Isra-Card-2026'
NOW = datetime(2026, 10, 12, 20, 30, 5)


def rec(name, serial, value=50.0, executed=date(2026, 10, 1), card='4603'):
    return {'cardid': card, 'name': name, 'executed_date': datetime.combine(executed, datetime.min.time()),
            'charge_date': datetime(2026, 10, 10), 'charge_value': value, 'source_file': 'x.xlsx',
            'charge_currency': '₪', 'transaction_value': value, 'value_currency': '₪',
            'extra_info': f'Serial: {serial} | Info: (None)'}


R = {k: rec(k, i) for i, k in enumerate('abcde', start=1)}
META = [{'File_Name': 'n', 'Format': FMT, 'Card_Number': '4603', 'Initial_index': 13, 'Initial_col': 0,
         'Row_count': 25, 'Bad_rows': ''}]


class FakeDB:
    """Stores one file: its File row, TableMeta and rows (with ids / categories)."""

    def __init__(self, name='4603_10_2026.xlsx', stored=('a', 'b', 'c'), card='4603', month=date(2026, 10, 1),
                 tagged=(), described=(), linked=None):
        self.file = {'name': name, 'format': FMT, 'card': card, 'date': month, 'new_transactions': 3,
                     'transaction_count': len(stored), 'last_update': date(2026, 10, 4), 'updated_at': None}
        self.rows = []
        for n, k in enumerate(stored, start=100):
            r = dict(R[k], id=n, category='מצרכים' if k in tagged else 'NotCategorized',
                     description='הערה' if k in described else None)
            r['executed_date'] = r['executed_date'].date()
            r['charge_date'] = r['charge_date'].date()
            self.rows.append(r)
        self.links = linked or {}
        self.meta = [dict(META[0], File_Name=name, Row_count=len(stored))]
        self.plan = None

    def get_files_by_name(self, name):
        return [dict(self.file)] if self.file['name'] == name else []

    def get_files_by_identity(self, fmt, card, d):
        f = self.file
        return [dict(f)] if (f['format'], f['card'], f['date']) == (fmt, card, d.date() if isinstance(d, datetime) else d) else []

    def get_card_file_transactions(self, name, card):
        return [dict(r) for r in self.rows] if name == self.file['name'] and card == self.file['card'] else []

    def get_card_tx_links(self, ids):
        return {i: self.links[i] for i in ids if i in self.links}

    def get_table_Meta(self, name, fmt, card):
        return [dict(m) for m in self.meta]

    def apply_card_file_update(self, plan):
        self.plan = plan


def reader_for(*keys, name='4603_10_2026.xlsx', card='4603', month=datetime(2026, 10, 1)):
    def reader(file_name, fmt):
        return {'name': file_name, 'format': fmt, 'card': card, 'date': month,
                'records': [R[k] for k in keys], 'meta': [dict(META[0], File_Name=file_name, Row_count=len(keys))],
                'columns': 8, 'tables': 1}
    return reader


@pytest.fixture
def folders(tmp_path):
    f = svc.Folders(str(tmp_path / 'in'), str(tmp_path / 'ver'), str(tmp_path / 'trash'))
    os.makedirs(f.input)
    os.makedirs(os.path.join(f.verified, FMT))
    return f


def put(folder, name, content, fmt=None):
    path = os.path.join(folder, fmt, name) if fmt else os.path.join(folder, name)
    with open(path, 'wb') as fh:
        fh.write(content)
    return path


# ── the report ─────────────────────────────────────────────────────────────
def test_new_transactions_report(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    put(folders.verified, '4603_10_2026.xlsx', b'old', FMT)
    out = svc.analyze(FakeDB(tagged=('a', 'b')), reader_for('d', 'a', 'b', 'c', 'e'), '4603_10_2026.xlsx', FMT, folders)
    assert out['status'] == 'new_transactions' and out['status_label'] == 'קובץ עם פעולות חדשות'
    c = out['counts']
    assert (c['same'], c['added'], c['removed'], c['changed'], c['moved']) == (3, 2, 0, 0, 0)
    assert (c['existing_rows'], c['new_rows'], c['tagged_existing']) == (3, 5, 2)
    assert sorted(r['name'] for r in out['added']) == ['d', 'e']
    assert out['can_update'] and out['identity_ok'] and out['copy_state'] == 'different'
    assert out['existing']['archived_copy'] is True and out['warnings'] == []
    rows = next(s for s in out['structure'] if s['field'] == 'rows')
    assert (rows['old'], rows['new'], rows['changed']) == (3, 5, True)


def test_structure_compares_the_real_header_cells_of_both_files(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    put(folders.verified, '4603_10_2026.xlsx', b'old', FMT)
    seen = []
    base = ['תאריך רכישה', 'שם בית עסק', 'סכום עסקה']

    def header_reader(path, row, col):
        seen.append((os.path.basename(os.path.dirname(path)), row, col))
        return base + ['עמודה חדשה'] if path.startswith(folders.input) else base

    out = svc.analyze(FakeDB(), reader_for('a', 'b', 'c'), '4603_10_2026.xlsx', FMT, folders, header_reader=header_reader)
    s = {x['field']: x for x in out['structure']}
    assert (s['columns']['old'], s['columns']['new'], s['columns']['changed']) == (3, 4, True)
    assert s['headers']['changed'] and s['headers']['new'].endswith('עמודה חדשה')
    assert sorted(seen) == [(FMT, 12, 0), ('in', 12, 0)]          # both files' header row, from the saved table meta
    assert any('הבדלי מבנה' in w for w in out['warnings'])


def test_identical_headers_are_summarised_and_a_missing_archive_skips_the_old_side(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    reader = lambda path, row, col: ['א', 'ב', 'ג']
    out = svc.analyze(FakeDB(), reader_for('a', 'b', 'c'), '4603_10_2026.xlsx', FMT, folders, header_reader=reader)
    assert 'headers' not in {x['field'] for x in out['structure']}      # no archived copy -> nothing to compare
    put(folders.verified, '4603_10_2026.xlsx', b'old', FMT)
    out = svc.analyze(FakeDB(), reader_for('a', 'b', 'c'), '4603_10_2026.xlsx', FMT, folders, header_reader=reader)
    h = next(x for x in out['structure'] if x['field'] == 'headers')
    assert h['old'] == h['new'] == '3 כותרות זהות' and not h['changed']


def test_a_failing_header_reader_does_not_break_the_report(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    put(folders.verified, '4603_10_2026.xlsx', b'old', FMT)

    def boom(path, row, col):
        raise OSError('locked')
    out = svc.analyze(FakeDB(), reader_for('a', 'b', 'c'), '4603_10_2026.xlsx', FMT, folders, header_reader=boom)
    assert out['status'] == 'identical'


def test_identical_file_with_the_same_bytes_cannot_be_updated(folders):
    put(folders.input, '4603_10_2026.xlsx', b'same')
    put(folders.verified, '4603_10_2026.xlsx', b'same', FMT)
    out = svc.analyze(FakeDB(), reader_for('a', 'b', 'c'), '4603_10_2026.xlsx', FMT, folders)
    assert out['status'] == 'identical' and out['copy_state'] == 'same' and out['can_update'] is False
    with pytest.raises(svc.UpdateError, match='זהה'):
        svc.apply(FakeDB(), reader_for('a', 'b', 'c'), '4603_10_2026.xlsx', FMT, folders, 'update', now=NOW)


def test_identical_rows_in_a_different_file_can_be_swapped_in(folders):
    put(folders.input, '4603_10_2026.xlsx', b'resaved')
    put(folders.verified, '4603_10_2026.xlsx', b'old', FMT)
    out = svc.analyze(FakeDB(), reader_for('a', 'b', 'c'), '4603_10_2026.xlsx', FMT, folders)
    assert out['status'] == 'identical' and out['can_update'] is True


def test_rows_missing_from_the_new_file_get_their_own_status_and_an_investigation(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    put(folders.verified, '4603_10_2026.xlsx', b'old', FMT)
    db = FakeDB(tagged=('c',), described=('c',), linked={101: ['timeline']})
    out = svc.analyze(db, reader_for('a'), '4603_10_2026.xlsx', FMT, folders)
    assert out['status'] == 'missing_rows' and 'תחקור' in out['status_label']
    assert out['counts']['removed'] == 2 and out['counts']['removed_with_work'] == 2
    assert out['can_update'] is False and any('חריגה' in w for w in out['warnings'])
    inv = out['investigation']
    assert inv['shape'] == 'tail' and inv['missing_total'] == 2 and inv['missing_amount'] == 50 + 50
    assert [(m['position'], m['name'], m['work']) for m in inv['missing']] == [(2, 'b', True), (3, 'c', True)]
    b, c = inv['missing']
    assert b['id'] == 101 and b['links'] == ['timeline'] and b['serial'] == '2' and b['category'] == 'NotCategorized'
    assert c['category'] == 'מצרכים' and c['description'] == 'הערה'
    assert inv['work'] == {'tagged': 1, 'described': 1, 'linked': 1, 'link_kinds': {'timeline': 1}}
    stored, new = inv['files']['stored'], inv['files']['new']
    assert (stored['rows'], new['rows'], stored['total'], new['total']) == (3, 1, 150, 50)
    assert stored['file']['size'] == 3 and new['file']['size'] == 3 and stored['name'] == '4603_10_2026.xlsx'
    assert inv['missing_range'] == ('2026-10-01', '2026-10-01')
    text = ' '.join(inv['hints'])
    assert 'האחרונות' in text and 'סכום החסרות' in text and 'עבודה שתאבד' in text


def test_a_missing_row_lists_look_alikes_from_the_new_file(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    typo = dict(R['b'], charge_value=77.0, transaction_value=77.0, extra_info='Serial: 777 | Info: (None)')
    reader = reader_for('a', 'c')
    out = svc.analyze(FakeDB(), lambda n, f: dict(reader(n, f), records=[R['a'], typo, R['c']]),
                      '4603_10_2026.xlsx', FMT, folders)
    # b was stored with another serial and amount: unmatched on both sides, but same name + date
    assert out['status'] == 'missing_rows' and out['counts']['removed'] == 1 and out['counts']['added'] == 1
    sim = out['investigation']['missing'][0]['similar']
    assert sim == [{'new_position': 2, 'name': 'b', 'date': '2026-10-01', 'amount': 77.0,
                    'same': ['name', 'date'], 'differs': ['amount']}]
    assert any('דומה' in h for h in out['investigation']['hints'])


def test_a_row_with_a_link_counts_as_work(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    db = FakeDB(linked={101: ['timeline']})
    out = svc.analyze(db, reader_for('a'), '4603_10_2026.xlsx', FMT, folders)
    assert out['counts']['removed_with_work'] == 1


def test_no_investigation_when_nothing_is_missing(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    out = svc.analyze(FakeDB(), reader_for('a', 'b', 'c', 'd'), '4603_10_2026.xlsx', FMT, folders)
    assert out['investigation'] is None


def test_mixed_changes_are_other_and_corrected_amounts_are_changes(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    corrected = dict(R['b'], charge_value=99.0, transaction_value=99.0)
    reader = reader_for('a', 'c', 'd')
    out = svc.analyze(FakeDB(), lambda n, f: dict(reader(n, f), records=[R['a'], corrected, R['c'], R['d']]),
                      '4603_10_2026.xlsx', FMT, folders)
    assert out['status'] == 'other'
    assert out['counts']['changed'] == 1 and out['counts']['added'] == 1 and out['counts']['removed'] == 0
    assert out['changed'][0]['fields'] == ['charge_value', 'transaction_value']


def test_another_card_or_month_is_other_and_update_is_refused(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    reader = reader_for('a', 'b', 'c', card='6046')
    out = svc.analyze(FakeDB(), reader, '4603_10_2026.xlsx', FMT, folders)
    assert out['status'] == 'other' and out['identity_ok'] is False and out['can_update'] is False
    with pytest.raises(svc.UpdateError, match='אותו כרטיס'):
        svc.apply(FakeDB(), reader, '4603_10_2026.xlsx', FMT, folders, 'update', now=NOW)


def test_the_stored_file_is_found_by_card_and_month_when_the_name_differs(folders):
    put(folders.input, '4603_10_2026 (1).xlsx', b'new')
    out = svc.analyze(FakeDB(), reader_for('a', 'b', 'c', 'd'), '4603_10_2026 (1).xlsx', FMT, folders)
    assert out['existing']['name'] == '4603_10_2026.xlsx' and out['status'] == 'new_transactions'
    assert out['copy_state'] == 'different'


def test_nothing_to_compare_with(folders):
    put(folders.input, '4603_11_2026.xlsx', b'new')
    with pytest.raises(svc.NothingToCompare):
        svc.analyze(FakeDB(), reader_for('a', month=datetime(2026, 11, 1)), '4603_11_2026.xlsx', FMT, folders)


def test_identity_conflict_finds_another_name_for_the_same_month():
    db = FakeDB()
    assert svc.find_identity_conflict(db, reader_for('a'), '4603_10_2026 (1).xlsx', FMT)['name'] == '4603_10_2026.xlsx'
    assert svc.find_identity_conflict(db, reader_for('a'), '4603_10_2026.xlsx', FMT) is None
    assert svc.find_identity_conflict(db, reader_for('a', month=datetime(2026, 11, 1)), 'n.xlsx', FMT) is None


# ── the decision ───────────────────────────────────────────────────────────
def test_update_keeps_matched_rows_and_adds_the_new_ones(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    put(folders.verified, '4603_10_2026.xlsx', b'old', FMT)
    db = FakeDB(tagged=('a', 'b'))
    out = svc.apply(db, reader_for('d', 'a', 'b', 'c', 'e'), '4603_10_2026.xlsx', FMT, folders, 'update', now=NOW)
    p = db.plan
    assert p['kind'] == 'update' and p['old_name'] == p['new_name'] == '4603_10_2026.xlsx'
    assert sorted(k['id'] for k in p['keep']) == [100, 101, 102] and all(k['record'] is None for k in p['keep'])
    assert sorted(r['name'] for r in p['add']) == ['d', 'e'] and p['delete'] == []
    assert p['counts'] == {'added': 2, 'changed': 0, 'removed': 0, 'transactions': 5, 'new': 2}
    assert out['ok'] and out['counts']['added'] == 2 and out['warnings'] == []
    # the old copy is in the trash (timestamped), the new one in the archive, the input folder is empty
    assert os.listdir(os.path.join(folders.trash, FMT)) == ['20261012_203005_4603_10_2026.xlsx']
    assert open(os.path.join(folders.verified, FMT, '4603_10_2026.xlsx'), 'rb').read() == b'new'
    assert os.listdir(folders.input) == []


def test_update_is_refused_while_stored_rows_are_missing_but_replace_is_allowed(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    db = FakeDB(tagged=('c',))
    with pytest.raises(svc.UpdateError, match='תחקור'):
        svc.apply(db, reader_for('a'), '4603_10_2026.xlsx', FMT, folders, 'update', now=NOW)
    assert db.plan is None and os.listdir(folders.input) == ['4603_10_2026.xlsx']          # nothing touched
    svc.apply(db, reader_for('a'), '4603_10_2026.xlsx', FMT, folders, 'replace', now=NOW)
    assert db.plan['kind'] == 'replace' and sorted(db.plan['delete']) == [100, 101, 102]


def test_the_update_records_what_the_old_file_was(folders):
    put(folders.input, '4603_10_2026 (1).xlsx', b'new')
    put(folders.verified, '4603_10_2026.xlsx', b'old', FMT)
    db = FakeDB(tagged=('a', 'b'))
    svc.apply(db, reader_for('a', 'b', 'c', 'd', 'e'), '4603_10_2026 (1).xlsx', FMT, folders, 'update', now=NOW)
    assert db.plan['history'] == {'old_rows': 3, 'old_tagged': 2, 'old_saved_on': date(2026, 10, 4), 'new_rows': 5,
                                  'trash_name': '20261012_203005_4603_10_2026.xlsx'}
    assert db.plan['old_name'] == '4603_10_2026.xlsx'                        # the name that is about to disappear


def test_history_has_no_trash_name_when_there_was_no_archived_copy(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    db = FakeDB()
    svc.apply(db, reader_for('a', 'b', 'c', 'd'), '4603_10_2026.xlsx', FMT, folders, 'update', now=NOW)
    assert db.plan['history']['trash_name'] is None


def test_group_history_keys_by_statement_and_formats_for_json():
    rows = [
        {'at': datetime(2026, 10, 12, 20, 30, 5), 'format': FMT, 'card': '4603', 'month': date(2026, 10, 1),
         'kind': 'update', 'old_name': 'a.xlsx', 'new_name': 'b.xlsx', 'old_rows': 25, 'old_tagged': 25,
         'old_saved_on': date(2026, 10, 4), 'new_rows': 33, 'added': 8, 'changed': None, 'removed': 0,
         'trash_name': '20261012_a.xlsx'},
        {'at': datetime(2026, 10, 1, 9, 0), 'format': FMT, 'card': '6046', 'month': date(2026, 10, 1),
         'kind': 'replace', 'old_name': 'c.xlsx', 'new_name': 'c.xlsx', 'old_rows': 3, 'old_tagged': 0,
         'old_saved_on': None, 'new_rows': 4, 'added': 4, 'changed': 0, 'removed': 3, 'trash_name': None},
    ]
    out = svc.group_history(rows)
    assert set(out) == {f'{FMT}|4603|2026-10-01', f'{FMT}|6046|2026-10-01'}
    e = out[f'{FMT}|4603|2026-10-01'][0]
    assert e == {'at': '2026-10-12 20:30', 'kind': 'update', 'old_name': 'a.xlsx', 'new_name': 'b.xlsx',
                 'old_rows': 25, 'old_tagged': 25, 'old_saved_on': '2026-10-04', 'new_rows': 33, 'added': 8,
                 'changed': 0, 'removed': 0, 'trashed': True}
    assert out[f'{FMT}|6046|2026-10-01'][0]['old_saved_on'] == '' and out[f'{FMT}|6046|2026-10-01'][0]['trashed'] is False


def test_update_corrects_a_changed_row_in_place(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    corrected = dict(R['b'], charge_value=99.0, transaction_value=99.0)
    reader = reader_for('a', 'c')
    db = FakeDB()
    svc.apply(db, lambda n, f: dict(reader(n, f), records=[R['a'], corrected, R['c']]), '4603_10_2026.xlsx', FMT,
              folders, 'update', now=NOW)
    rec_b = next(k for k in db.plan['keep'] if k['id'] == 101)
    assert rec_b['record']['charge_value'] == 99.0 and db.plan['counts']['changed'] == 1


def test_update_under_a_new_name_renames_the_file_entry(folders):
    put(folders.input, '4603_10_2026 (1).xlsx', b'new')
    put(folders.verified, '4603_10_2026.xlsx', b'old', FMT)
    db = FakeDB()
    svc.apply(db, reader_for('a', 'b', 'c', 'd'), '4603_10_2026 (1).xlsx', FMT, folders, 'update', now=NOW)
    assert db.plan['old_name'] == '4603_10_2026.xlsx' and db.plan['new_name'] == '4603_10_2026 (1).xlsx'
    assert os.listdir(os.path.join(folders.verified, FMT)) == ['4603_10_2026 (1).xlsx']
    assert len(os.listdir(os.path.join(folders.trash, FMT))) == 1


def test_replace_swaps_everything_and_keeps_nothing(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    put(folders.verified, '4603_10_2026.xlsx', b'old', FMT)
    db = FakeDB(tagged=('a',))
    svc.apply(db, reader_for('a', 'd'), '4603_10_2026.xlsx', FMT, folders, 'replace', now=NOW)
    p = db.plan
    assert p['kind'] == 'replace' and p['keep'] == [] and sorted(p['delete']) == [100, 101, 102]
    assert len(p['add']) == 2 and p['counts']['transactions'] == 2


def test_replace_is_allowed_for_another_card_but_a_transaction_division_blocks_it(folders):
    put(folders.input, '4603_10_2026.xlsx', b'new')
    svc.apply(FakeDB(), reader_for('a', card='6046'), '4603_10_2026.xlsx', FMT, folders, 'replace', now=NOW)
    put(folders.input, '4603_10_2026.xlsx', b'new')
    with pytest.raises(svc.UpdateError, match='Devision'):
        svc.apply(FakeDB(linked={100: ['division']}), reader_for('a'), '4603_10_2026.xlsx', FMT, folders,
                  'replace', now=NOW)


def test_unknown_mode(folders):
    with pytest.raises(svc.UpdateError):
        svc.apply(FakeDB(), reader_for('a'), 'x.xlsx', FMT, folders, 'delete')


def test_check_input_copy(folders):
    put(folders.input, 'a.xlsx', b'1')
    assert svc.check_input_copy('a.xlsx', FMT, folders) == 'missing'
    put(folders.verified, 'a.xlsx', b'1', FMT)
    assert svc.check_input_copy('a.xlsx', FMT, folders) == 'same'
    put(folders.input, 'a.xlsx', b'2')
    assert svc.check_input_copy('a.xlsx', FMT, folders) == 'different'
