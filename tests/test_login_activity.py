import pytest
import os
from dotenv import load_dotenv
from source.database import DataBase, initialize_login_activity_table

load_dotenv()

@pytest.fixture
def db():
    database = DataBase()
    initialize_login_activity_table()
    return database

def test_log_login(db):
    """Test logging a login event"""
    session_id = 'test_session_123'
    device_info = 'Mozilla/5.0 (Windows NT 10.0)'
    ip_address = '192.168.1.100'

    result = db.log_login(session_id, device_info, ip_address)
    assert result is True

def test_log_logout(db):
    """Test logging a logout event"""
    session_id = 'test_session_456'
    device_info = 'Mozilla/5.0'
    ip_address = '10.0.0.1'

    # First log in
    db.log_login(session_id, device_info, ip_address)

    # Then log out
    result = db.log_logout(session_id)
    assert result is True

def test_get_login_activity(db):
    """Test retrieving login activity"""
    session_id = 'test_session_789'
    device_info = 'Chrome/Linux'
    ip_address = '192.168.1.50'

    # Log a login
    db.log_login(session_id, device_info, ip_address)

    # Retrieve activities
    activities = db.get_login_activity()
    assert len(activities) > 0

    # Verify the last activity
    last_activity = activities[0]
    assert session_id in last_activity['session_id'] or last_activity['session_id'] == session_id
