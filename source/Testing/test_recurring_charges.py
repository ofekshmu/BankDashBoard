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


def test_build_group_rejects_stale_bill():
    # Last occurrence was March 2026; today is December 2026 — 8 months
    # since the last complete month with an occurrence, well past the
    # 6-month cutoff. No longer a *current* recurring bill.
    members = [
        {'table': 'CardTransactions', 'id': 1, 'date': date(2026, 1, 5), 'name': 'OLDGYM', 'amount': 150.0, 'category': 'בריאות וכושר'},
        {'table': 'CardTransactions', 'id': 2, 'date': date(2026, 2, 5), 'name': 'OLDGYM', 'amount': 150.0, 'category': 'בריאות וכושר'},
        {'table': 'CardTransactions', 'id': 3, 'date': date(2026, 3, 5), 'name': 'OLDGYM', 'amount': 150.0, 'category': 'בריאות וכושר'},
    ]
    cluster = {'norm_key': 'oldgym', 'members': members}
    group = build_group_from_cluster(cluster, today=date(2026, 12, 15))
    assert group is None, "a bill not seen in more than 6 months should no longer count as recurring"
    print("PASS: build_group_from_cluster rejects stale bill")


def test_build_group_keeps_bill_within_six_months():
    # Last occurrence was March 2026; today is September 2026 — exactly 5
    # months since the last complete month with an occurrence (August),
    # still within the 6-month cutoff.
    members = [
        {'table': 'CardTransactions', 'id': 1, 'date': date(2026, 1, 5), 'name': 'RECENTGYM', 'amount': 150.0, 'category': 'בריאות וכושר'},
        {'table': 'CardTransactions', 'id': 2, 'date': date(2026, 2, 5), 'name': 'RECENTGYM', 'amount': 150.0, 'category': 'בריאות וכושר'},
        {'table': 'CardTransactions', 'id': 3, 'date': date(2026, 3, 5), 'name': 'RECENTGYM', 'amount': 150.0, 'category': 'בריאות וכושר'},
    ]
    cluster = {'norm_key': 'recentgym', 'members': members}
    group = build_group_from_cluster(cluster, today=date(2026, 9, 15))
    assert group is not None, "a bill last seen 5 months ago should still count as recurring"
    print("PASS: build_group_from_cluster keeps bill within six months")


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


def test_build_group_drops_occurrence_beyond_amount_ceiling():
    # One occurrence is wildly larger (>50% above the median of the rest) —
    # it should be dropped from the group entirely rather than merely flagged.
    members = [
        {'table': 'BankTransactions', 'id': 1, 'date': date(2026, 1, 5), 'name': 'NURSERY', 'amount': 180.0, 'category': 'רהיטים ובית'},
        {'table': 'BankTransactions', 'id': 2, 'date': date(2026, 2, 5), 'name': 'NURSERY', 'amount': 190.0, 'category': 'רהיטים ובית'},
        {'table': 'BankTransactions', 'id': 3, 'date': date(2026, 3, 5), 'name': 'NURSERY', 'amount': 170.0, 'category': 'רהיטים ובית'},
        {'table': 'BankTransactions', 'id': 4, 'date': date(2026, 4, 5), 'name': 'NURSERY', 'amount': 600.0, 'category': 'רהיטים ובית'},
    ]
    cluster = {'norm_key': 'nursery', 'members': members}
    group = build_group_from_cluster(cluster, today=date(2026, 5, 15))
    assert group is not None
    months_present = [o['month'] for o in group['occurrences']]
    assert '2026-04' not in months_present, "the 600.0 outlier should have been dropped, not just flagged"
    assert group['occurrence_count'] == 3
    print("PASS: build_group_from_cluster drops occurrence beyond amount ceiling")


def test_build_group_rejects_too_many_changed():
    # 3 out of 5 occurrences deviate from the median by more than
    # AMOUNT_CHANGE_THRESHOLD (15%) but each individually stays under the 50%
    # hard ceiling — too unstable to be a fixed bill, not just "one price rise".
    members = [
        {'table': 'BankTransactions', 'id': 1, 'date': date(2026, 1, 5), 'name': 'MARKET', 'amount': 100.0, 'category': 'מצרכים'},
        {'table': 'BankTransactions', 'id': 2, 'date': date(2026, 2, 5), 'name': 'MARKET', 'amount': 140.0, 'category': 'מצרכים'},
        {'table': 'BankTransactions', 'id': 3, 'date': date(2026, 3, 5), 'name': 'MARKET', 'amount': 60.0, 'category': 'מצרכים'},
        {'table': 'BankTransactions', 'id': 4, 'date': date(2026, 4, 5), 'name': 'MARKET', 'amount': 130.0, 'category': 'מצרכים'},
        {'table': 'BankTransactions', 'id': 5, 'date': date(2026, 5, 5), 'name': 'MARKET', 'amount': 100.0, 'category': 'מצרכים'},
    ]
    cluster = {'norm_key': 'market', 'members': members}
    group = build_group_from_cluster(cluster, today=date(2026, 6, 15))
    assert group is None, "too many changed-amount months should disqualify the group"
    print("PASS: build_group_from_cluster rejects too many changed months")


def test_build_group_rejects_too_fragmented():
    # Mirrors the real "משתלת על הדרך" pattern: several short runs separated
    # by gaps, plus one occurrence far above the rest (dropped by the amount
    # ceiling), leaving 4 separate runs — too sporadic to be a fixed bill.
    members = [
        {'table': 'BankTransactions', 'id': 1, 'date': date(2025, 8, 21), 'name': 'NURSERY', 'amount': 328.0, 'category': 'רהיטים ובית'},
        {'table': 'BankTransactions', 'id': 2, 'date': date(2025, 10, 29), 'name': 'NURSERY', 'amount': 170.0, 'category': 'רהיטים ובית'},
        {'table': 'BankTransactions', 'id': 3, 'date': date(2025, 11, 16), 'name': 'NURSERY', 'amount': 138.0, 'category': 'רהיטים ובית'},
        {'table': 'BankTransactions', 'id': 4, 'date': date(2025, 12, 14), 'name': 'NURSERY', 'amount': 211.0, 'category': 'רהיטים ובית'},
        {'table': 'BankTransactions', 'id': 5, 'date': date(2026, 2, 24), 'name': 'NURSERY', 'amount': 98.0,  'category': 'רהיטים ובית'},
        {'table': 'BankTransactions', 'id': 6, 'date': date(2026, 4, 28), 'name': 'NURSERY', 'amount': 168.0, 'category': 'רהיטים ובית'},
        {'table': 'BankTransactions', 'id': 7, 'date': date(2026, 5, 29), 'name': 'NURSERY', 'amount': 306.0, 'category': 'רהיטים ובית'},
        {'table': 'BankTransactions', 'id': 8, 'date': date(2026, 6, 14), 'name': 'NURSERY', 'amount': 190.0, 'category': 'רהיטים ובית'},
    ]
    cluster = {'norm_key': 'nursery2', 'members': members}
    group = build_group_from_cluster(cluster, today=date(2026, 7, 24))
    assert group is None, "too many separate appear/gap/reappear runs should disqualify the group"
    print("PASS: build_group_from_cluster rejects too fragmented pattern")


def test_build_group_keeps_single_clean_price_rise():
    # A real fixed bill with exactly one price rise partway through — must
    # NOT be disqualified by the amount-stability rules.
    members = []
    tx_id = 1
    for month in (6, 7, 8):
        members.append({'table': 'CardTransactions', 'id': tx_id, 'date': date(2025, month, 22), 'name': 'SPOTIFYIL', 'amount': 36.0, 'category': 'תחביבים ופנאי'})
        tx_id += 1
    for month in (9, 10, 11, 12):
        members.append({'table': 'CardTransactions', 'id': tx_id, 'date': date(2025, month, 22), 'name': 'SPOTIFYIL', 'amount': 44.0, 'category': 'תחביבים ופנאי'})
        tx_id += 1
    for month in (1, 2, 3, 4, 6):
        members.append({'table': 'CardTransactions', 'id': tx_id, 'date': date(2026, month, 22), 'name': 'SPOTIFYIL', 'amount': 44.0, 'category': 'תחביבים ופנאי'})
        tx_id += 1
    cluster = {'norm_key': 'spotifyil', 'members': members}
    group = build_group_from_cluster(cluster, today=date(2026, 7, 24))
    assert group is not None, "a single clean price rise must not disqualify a real recurring bill"
    assert group['occurrence_count'] == 12
    print("PASS: build_group_from_cluster keeps a single clean price rise")


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


def test_get_recurring_groups_excludes_installment_payments():
    db = DataBase()
    db.ensure_recurring_tables()

    # Use a real existing CardID (CardTransactions.CardID has a FK to Card).
    card_id_row = db.cursor.execute('SELECT CardID FROM Card LIMIT 1').fetchone()
    assert card_id_row is not None, "test requires at least one row in Card"
    card_id = card_id_row[0]

    test_name = 'RC_TEST_INSTALLMENT_PURCHASE'
    ids = []
    try:
        # 3 months of a classic installment pattern: "תשלום N מתוך 6", charge
        # value (total) > transaction value (per-installment), charge date a
        # month after executed date — matches is_payment_transaction() in
        # calculations.py exactly.
        for i, (y, m) in enumerate([(2099, 1), (2099, 2), (2099, 3)], start=1):
            executed = date(y, m, 10)
            charged = date(y, m + 1, 3) if m < 12 else date(y + 1, 1, 3)
            row = db.cursor.execute("""
                INSERT INTO CardTransactions
                    (CardID, Name, Executed_Date, Charge_Date, Charge_Value,
                     Transaction_Value, Source_file, Category, Extra_Info)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING ID
            """, (card_id, test_name, executed, charged, 600.0, 100.0,
                  'RC_TEST', 'מוצרי חשמל', f'תשלום {i} מתוך 6')).fetchone()
            ids.append(row[0])
        db.connection.commit()

        groups = get_recurring_groups(db, today=date(2099, 5, 15))
        match = next((g for g in groups if g['name'] == test_name), None)
        assert match is None, "installment-payment transactions must not be detected as a recurring bill"
        print("PASS: get_recurring_groups excludes installment payments")
    finally:
        if ids:
            db.cursor.execute("DELETE FROM CardTransactions WHERE ID = ANY(%s)", (ids,))
            db.connection.commit()


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
    test_build_group_rejects_stale_bill()
    test_build_group_keeps_bill_within_six_months()
    test_build_group_flags_amount_changed()
    test_build_group_drops_occurrence_beyond_amount_ceiling()
    test_build_group_rejects_too_many_changed()
    test_build_group_rejects_too_fragmented()
    test_build_group_keeps_single_clean_price_rise()
    test_build_timeline_marks_paid_missing_and_before_start()
    test_get_recurring_groups_end_to_end()
    test_get_recurring_groups_excludes_installment_payments()
    print("\nAll tests passed")
