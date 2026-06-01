"""Integration tests for Spotify Tracker feature."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import DataBase

def test_spotify_tables_exist():
    db = DataBase()
    tables = {r[0] for r in db.cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert 'SpotifyMembers' in tables, "SpotifyMembers table missing"
    assert 'SpotifyMonthlyCharge' in tables, "SpotifyMonthlyCharge table missing"
    assert 'SpotifyMemberPayments' in tables, "SpotifyMemberPayments table missing"


def test_member_crud():
    db = DataBase()
    # Clean up from previous runs
    db.cursor.execute("DELETE FROM SpotifyMembers WHERE Name = 'TestMember'")
    db.commit_changes()

    mid = db.add_spotify_member('TestMember', is_exempt=0)
    assert isinstance(mid, int) and mid > 0

    members = db.get_spotify_members()
    names = [m['name'] for m in members]
    assert 'TestMember' in names

    db.update_spotify_member(mid, name='TestMemberRenamed', is_exempt=0, is_active=1)
    members = db.get_spotify_members()
    assert any(m['name'] == 'TestMemberRenamed' for m in members)

    db.delete_spotify_member(mid)
    members = db.get_spotify_members()
    assert not any(m['name'] == 'TestMemberRenamed' for m in members)
    print("PASS: member CRUD")


def test_charge_crud():
    db = DataBase()
    db.cursor.execute("DELETE FROM SpotifyMonthlyCharge WHERE Month = '2099-01'")
    db.commit_changes()

    cid = db.add_spotify_charge(month='2099-01', total_amount=149.90, member_count=5, tx_id=None, confirmed=1)
    assert isinstance(cid, int)

    charges = db.get_spotify_charges()
    assert any(c['month'] == '2099-01' for c in charges)

    db.update_spotify_charge(cid, total_amount=159.90, member_count=5, confirmed=1)
    charges = db.get_spotify_charges()
    updated = next(c for c in charges if c['month'] == '2099-01')
    assert updated['total_amount'] == 159.90

    db.cursor.execute("DELETE FROM SpotifyMonthlyCharge WHERE ID = ?", (cid,))
    db.commit_changes()
    print("PASS: charge CRUD")


def test_payment_crud():
    db = DataBase()
    mid = db.add_spotify_member('PayTestMember', is_exempt=0)

    pid = db.add_spotify_payment(member_id=mid, amount=29.98, payment_date='2099-01-15', tx_id=None)
    assert isinstance(pid, int)

    payments = db.get_spotify_payments(member_id=mid)
    assert len(payments) == 1
    assert payments[0]['amount'] == 29.98

    db.delete_spotify_payment(pid)
    payments = db.get_spotify_payments(member_id=mid)
    assert len(payments) == 0

    db.delete_spotify_member(mid)
    print("PASS: payment CRUD")


def test_compute_balance_owes():
    from SpotifyTracker import compute_balance
    charges = [
        {'month': '2025-04', 'total_amount': 120.0, 'member_count': 4, 'confirmed': 1},
        {'month': '2025-05', 'total_amount': 120.0, 'member_count': 4, 'confirmed': 1},
        {'month': '2025-06', 'total_amount': 120.0, 'member_count': 4, 'confirmed': 1},
    ]
    payments = [{'amount': 30.0}]  # paid only one month
    result = compute_balance(payments, charges)
    assert result['status'] == 'owes'
    assert result['balance'] == round(30.0 - 90.0, 2)  # -60.0
    assert result['months_status'] == -2  # ceil(60/30) = 2
    print("PASS: compute_balance owes")


def test_compute_balance_ahead():
    from SpotifyTracker import compute_balance
    charges = [
        {'month': '2025-06', 'total_amount': 120.0, 'member_count': 4, 'confirmed': 1},
    ]
    payments = [{'amount': 90.0}]  # paid 3x the monthly share
    result = compute_balance(payments, charges)
    assert result['status'] == 'ahead'
    assert result['balance'] == 60.0  # 90 - 30 = 60
    assert result['months_status'] == 2  # floor(60/30) = 2
    print("PASS: compute_balance ahead")


def test_compute_balance_even():
    from SpotifyTracker import compute_balance
    charges = [
        {'month': '2025-06', 'total_amount': 120.0, 'member_count': 4, 'confirmed': 1},
    ]
    payments = [{'amount': 30.0}]
    result = compute_balance(payments, charges)
    assert result['status'] == 'even'
    assert result['months_status'] == 0
    print("PASS: compute_balance even")


if __name__ == '__main__':
    test_spotify_tables_exist()
    print("PASS: all Spotify tables exist")
    test_member_crud()
    test_charge_crud()
    test_payment_crud()
    test_compute_balance_owes()
    test_compute_balance_ahead()
    test_compute_balance_even()
    print("\nAll tests passed")
