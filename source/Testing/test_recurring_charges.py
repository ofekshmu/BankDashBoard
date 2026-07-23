"""Tests for Recurring Charges feature."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date

from database import DataBase
from RecurringCharges import (
    normalize_name, cluster_transactions,
    month_key, find_longest_run, build_group_from_cluster,
    build_timeline, get_recurring_groups,
)


def test_recurring_tables_exist():
    db = DataBase()
    db.ensure_recurring_tables()
    for tbl in ('recurringdismissed', 'recurringmerges', 'recurringexcludedtransactions'):
        row = db.cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name=%s)",
            (tbl,)
        ).fetchone()
        assert row[0] is True, f"{tbl} table missing"
    print("PASS: recurring tables exist")


def test_dismiss_restore_roundtrip():
    db = DataBase()
    db.ensure_recurring_tables()
    key = 'RC_TEST_dismiss_key'
    db.cursor.execute("DELETE FROM RecurringDismissed WHERE Group_Key=%s", (key,))
    db.connection.commit()

    assert key not in db.get_recurring_dismissed()
    db.dismiss_recurring_group(key)
    assert key in db.get_recurring_dismissed()
    db.restore_recurring_group(key)
    assert key not in db.get_recurring_dismissed()
    print("PASS: dismiss/restore round-trip")


def test_merge_roundtrip():
    db = DataBase()
    db.ensure_recurring_tables()
    sec, prim = 'RC_TEST_secondary', 'RC_TEST_primary'
    db.cursor.execute("DELETE FROM RecurringMerges WHERE Secondary_Key=%s", (sec,))
    db.connection.commit()

    db.add_recurring_merge(sec, prim)
    merges = db.get_recurring_merges()
    assert merges.get(sec) == prim

    db.cursor.execute("DELETE FROM RecurringMerges WHERE Secondary_Key=%s", (sec,))
    db.connection.commit()
    print("PASS: merge round-trip")


def test_exclude_tx_roundtrip():
    db = DataBase()
    db.ensure_recurring_tables()
    db.cursor.execute(
        "DELETE FROM RecurringExcludedTransactions WHERE Table_Name=%s AND TX_ID=%s",
        ('BankTransactions', -999999)
    )
    db.connection.commit()

    assert ('BankTransactions', -999999) not in db.get_recurring_excluded_tx()
    db.exclude_recurring_tx('BankTransactions', -999999)
    assert ('BankTransactions', -999999) in db.get_recurring_excluded_tx()

    db.cursor.execute(
        "DELETE FROM RecurringExcludedTransactions WHERE Table_Name=%s AND TX_ID=%s",
        ('BankTransactions', -999999)
    )
    db.connection.commit()
    print("PASS: exclude-tx round-trip")


def test_normalize_name():
    assert normalize_name('NETFLIX.COM 123456') == 'netflix com'
    assert normalize_name('  Health  Insurance  99') == 'health insurance'
    assert normalize_name('') == ''
    assert normalize_name(None) == ''
    print("PASS: normalize_name")


def test_cluster_transactions_groups_similar_names():
    txs = [
        {'table': 'CardTransactions', 'id': 1, 'date': date(2026, 1, 5), 'name': 'NETFLIX.COM', 'amount': 39.9, 'category': 'מנויים'},
        {'table': 'CardTransactions', 'id': 2, 'date': date(2026, 2, 5), 'name': 'NETFLIX.COM', 'amount': 39.9, 'category': 'מנויים'},
        {'table': 'CardTransactions', 'id': 3, 'date': date(2026, 3, 6), 'name': 'NETFLIX COM 998211', 'amount': 44.9, 'category': 'מנויים'},
        {'table': 'BankTransactions', 'id': 4, 'date': date(2026, 1, 10), 'name': 'ELECTRIC COMPANY', 'amount': 210.0, 'category': 'חשבונות'},
    ]
    clusters = cluster_transactions(txs)
    assert len(clusters) == 2, f"expected 2 clusters, got {len(clusters)}"
    netflix_cluster = next(c for c in clusters if len(c['members']) == 3)
    assert {m['id'] for m in netflix_cluster['members']} == {1, 2, 3}
    print("PASS: cluster_transactions groups similar names")


def test_cluster_transactions_keeps_unrelated_separate():
    txs = [
        {'table': 'BankTransactions', 'id': 1, 'date': date(2026, 1, 1), 'name': 'SUPERMARKET A', 'amount': 300.0, 'category': 'מצרכים'},
        {'table': 'BankTransactions', 'id': 2, 'date': date(2026, 1, 2), 'name': 'GYM MEMBERSHIP', 'amount': 150.0, 'category': 'בריאות וכושר'},
    ]
    clusters = cluster_transactions(txs)
    assert len(clusters) == 2
    print("PASS: cluster_transactions keeps unrelated separate")


def test_month_key():
    assert month_key(date(2026, 3, 5)) == '2026-03'
    assert month_key(date(2026, 11, 30)) == '2026-11'
    print("PASS: month_key")


def test_find_longest_run():
    assert find_longest_run(['2026-01', '2026-02', '2026-03']) == ['2026-01', '2026-02', '2026-03']
    assert find_longest_run(['2026-01', '2026-03', '2026-04', '2026-05']) == ['2026-03', '2026-04', '2026-05']
    assert find_longest_run([]) == []
    assert find_longest_run(['2026-06']) == ['2026-06']
    print("PASS: find_longest_run")


def test_build_group_from_cluster_qualifies_and_stats():
    members = [
        {'table': 'CardTransactions', 'id': 1, 'date': date(2026, 1, 5), 'name': 'NETFLIX', 'amount': 39.9, 'category': 'מנויים'},
        {'table': 'CardTransactions', 'id': 2, 'date': date(2026, 2, 5), 'name': 'NETFLIX', 'amount': 39.9, 'category': 'מנויים'},
        {'table': 'CardTransactions', 'id': 3, 'date': date(2026, 3, 5), 'name': 'NETFLIX', 'amount': 39.9, 'category': 'מנויים'},
    ]
    cluster = {'norm_key': 'netflix', 'members': members}
    group = build_group_from_cluster(cluster, today=date(2026, 4, 15))
    assert group is not None
    assert group['occurrence_count'] == 3
    assert group['average_amount'] == 39.9
    assert group['total_spent'] == round(39.9 * 3, 2)
    assert group['min_amount'] == 39.9
    assert group['max_amount'] == 39.9
    assert group['first_payment_date'] == date(2026, 1, 5)
    assert group['last_payment_date'] == date(2026, 3, 5)
    assert group['possibly_stopped'] is False  # last complete month (March) has an occurrence
    print("PASS: build_group_from_cluster qualifies + stats")


def test_build_group_from_cluster_rejects_short_history():
    members = [
        {'table': 'CardTransactions', 'id': 1, 'date': date(2026, 1, 5), 'name': 'ONEOFF', 'amount': 39.9, 'category': 'מנויים'},
        {'table': 'CardTransactions', 'id': 2, 'date': date(2026, 2, 5), 'name': 'ONEOFF', 'amount': 39.9, 'category': 'מנויים'},
    ]
    cluster = {'norm_key': 'oneoff', 'members': members}
    group = build_group_from_cluster(cluster, today=date(2026, 4, 15))
    assert group is None
    print("PASS: build_group_from_cluster rejects <3 occurrences")


def test_build_group_flags_possibly_stopped():
    members = [
        {'table': 'CardTransactions', 'id': 1, 'date': date(2026, 1, 5), 'name': 'GYM', 'amount': 150.0, 'category': 'בריאות וכושר'},
        {'table': 'CardTransactions', 'id': 2, 'date': date(2026, 2, 5), 'name': 'GYM', 'amount': 150.0, 'category': 'בריאות וכושר'},
        {'table': 'CardTransactions', 'id': 3, 'date': date(2026, 3, 5), 'name': 'GYM', 'amount': 150.0, 'category': 'בריאות וכושר'},
    ]
    # today is May 15 — April (last complete month) has no occurrence
    cluster = {'norm_key': 'gym', 'members': members}
    group = build_group_from_cluster(cluster, today=date(2026, 5, 15))
    assert group['possibly_stopped'] is True
    print("PASS: build_group_from_cluster flags possibly_stopped")


def test_build_group_flags_amount_changed():
    members = [
        {'table': 'CardTransactions', 'id': 1, 'date': date(2026, 1, 5), 'name': 'INTERNET', 'amount': 100.0, 'category': 'חשבון אינטרנט'},
        {'table': 'CardTransactions', 'id': 2, 'date': date(2026, 2, 5), 'name': 'INTERNET', 'amount': 100.0, 'category': 'חשבון אינטרנט'},
        {'table': 'CardTransactions', 'id': 3, 'date': date(2026, 3, 5), 'name': 'INTERNET', 'amount': 140.0, 'category': 'חשבון אינטרנט'},
    ]
    cluster = {'norm_key': 'internet', 'members': members}
    group = build_group_from_cluster(cluster, today=date(2026, 4, 1))
    changed_months = [o['month'] for o in group['occurrences'] if o['status'] == 'changed']
    assert changed_months == ['2026-03']
    print("PASS: build_group_from_cluster flags amount_changed")


def test_build_timeline_marks_paid_missing_and_before_start():
    occurrences = [
        {'month': '2026-02', 'status': 'paid'},
        {'month': '2026-03', 'status': 'changed'},
    ]
    first_payment_date = date(2026, 2, 10)
    timeline = build_timeline(occurrences, first_payment_date, today=date(2026, 4, 1))
    assert len(timeline) == 12
    by_month = {t['month']: t for t in timeline}
    assert by_month['2026-02']['status'] == 'paid'
    assert by_month['2026-03']['status'] == 'changed'
    assert by_month['2026-01']['status'] == 'before_start'
    assert by_month['2025-05']['status'] == 'before_start'
    print("PASS: build_timeline")


def test_get_recurring_groups_end_to_end():
    db = DataBase()
    db.ensure_recurring_tables()

    # Insert 3 months of a fake recurring charge into BankTransactions (no FK
    # constraints, unlike CardTransactions.CardID -> Card), future-dated +
    # prefixed to avoid colliding with real data.
    test_name = 'RC_TEST_STREAMING_SVC'
    ids = []
    for (y, m) in [(2099, 1), (2099, 2), (2099, 3)]:
        row = db.cursor.execute("""
            INSERT INTO BankTransactions
                (Date, Name, Out, Income, Source_file, Category)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING ID
        """, (date(y, m, 5), test_name, 39.9, 0, 'RC_TEST', 'מנויים')).fetchone()
        ids.append(row[0])
    db.connection.commit()

    groups = get_recurring_groups(db, today=date(2099, 4, 15))
    match = next((g for g in groups if g['name'] == test_name), None)
    assert match is not None, "expected the test streaming charge to be detected as recurring"
    assert match['occurrence_count'] == 3
    assert len(match['timeline']) == 12

    # Cleanup
    db.cursor.execute(
        "DELETE FROM BankTransactions WHERE ID = ANY(%s)", (ids,)
    )
    db.connection.commit()
    print("PASS: get_recurring_groups end-to-end")


if __name__ == '__main__':
    test_recurring_tables_exist()
    test_dismiss_restore_roundtrip()
    test_merge_roundtrip()
    test_exclude_tx_roundtrip()
    test_normalize_name()
    test_cluster_transactions_groups_similar_names()
    test_cluster_transactions_keeps_unrelated_separate()
    test_month_key()
    test_find_longest_run()
    test_build_group_from_cluster_qualifies_and_stats()
    test_build_group_from_cluster_rejects_short_history()
    test_build_group_flags_possibly_stopped()
    test_build_group_flags_amount_changed()
    test_build_timeline_marks_paid_missing_and_before_start()
    test_get_recurring_groups_end_to_end()
    print("\nAll tests passed")
