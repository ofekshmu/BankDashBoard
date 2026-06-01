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

if __name__ == '__main__':
    test_spotify_tables_exist()
    print("PASS: all Spotify tables exist")
