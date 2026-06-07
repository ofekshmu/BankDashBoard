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


def test_full_balance_flow():
    from SpotifyTracker import compute_all_balances
    db = DataBase()

    # Setup: 3 members (1 exempt, 2 paying), 2 months of charges
    db.cursor.execute("DELETE FROM SpotifyMemberPayments WHERE Member_ID IN (SELECT ID FROM SpotifyMembers WHERE Name LIKE 'E2E_%')")
    db.cursor.execute("DELETE FROM SpotifyMembers WHERE Name LIKE 'E2E_%'")
    db.cursor.execute("DELETE FROM SpotifyMonthlyCharge WHERE Month IN ('2099-03','2099-04')")
    db.commit_changes()

    owner_id = db.add_spotify_member('E2E_Owner', is_exempt=1)
    alice_id = db.add_spotify_member('E2E_Alice', is_exempt=0)
    bob_id   = db.add_spotify_member('E2E_Bob',   is_exempt=0)

    # 2 months, 3 members → share = 120/3 = 40 per person
    db.add_spotify_charge('2099-03', total_amount=120.0, member_count=3, confirmed=1)
    db.add_spotify_charge('2099-04', total_amount=120.0, member_count=3, confirmed=1)

    # Alice pays for both months (80 total — even)
    db.add_spotify_payment(alice_id, 80.0, '2099-03-10')

    # Bob pays only once (40 — owes 1 month)
    db.add_spotify_payment(bob_id, 40.0, '2099-03-15')

    balances = compute_all_balances(db)
    bal_by_name = {b['name']: b for b in balances}

    assert 'E2E_Owner' not in bal_by_name, "Exempt member must not appear in balances"
    assert bal_by_name['E2E_Alice']['status'] == 'even',  f"Alice should be even, got {bal_by_name['E2E_Alice']}"
    assert bal_by_name['E2E_Bob']['status']   == 'owes',  f"Bob should owe, got {bal_by_name['E2E_Bob']}"
    assert bal_by_name['E2E_Bob']['months_status'] == -1, f"Bob should owe 1 month, got {bal_by_name['E2E_Bob']['months_status']}"

    # Cleanup
    db.cursor.execute("DELETE FROM SpotifyMemberPayments WHERE Member_ID IN (?,?)", (alice_id, bob_id))
    db.cursor.execute("DELETE FROM SpotifyMembers WHERE ID IN (?,?,?)", (owner_id, alice_id, bob_id))
    db.cursor.execute("DELETE FROM SpotifyMonthlyCharge WHERE Month IN ('2099-03','2099-04')")
    db.commit_changes()
    print("PASS: full balance flow e2e")


if __name__ == '__main__':
    test_spotify_tables_exist()
    print("PASS: all Spotify tables exist")
    test_member_crud()
    test_charge_crud()
    test_payment_crud()
    test_compute_balance_owes()
    test_compute_balance_ahead()
    test_compute_balance_even()
    test_full_balance_flow()
    print("\nAll tests passed")
