import pytest
import os
from dotenv import load_dotenv
from source.auth import AuthManager
from flask import Flask, request

load_dotenv()

@pytest.fixture
def auth_manager():
    return AuthManager()

@pytest.fixture
def flask_app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app

def test_validate_password_correct(auth_manager):
    """Test password validation with correct password"""
    # Assuming ADMIN_PASSWORD is set in .env
    result = auth_manager.validate_password(os.getenv('ADMIN_PASSWORD'))
    assert result is True

def test_validate_password_incorrect(auth_manager):
    """Test password validation with incorrect password"""
    result = auth_manager.validate_password('wrong_password')
    assert result is False

def test_generate_session_id(auth_manager):
    """Test session ID generation"""
    session_id_1 = auth_manager.generate_session_id()
    session_id_2 = auth_manager.generate_session_id()

    assert len(session_id_1) > 0
    assert len(session_id_2) > 0
    assert session_id_1 != session_id_2

def test_get_device_info(auth_manager, flask_app):
    """Test device info extraction"""
    with flask_app.test_request_context(
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0)'}
    ):
        device_info = auth_manager.get_device_info(request)
        assert 'Mozilla' in device_info

def test_get_ip_address(auth_manager, flask_app):
    """Test IP address extraction from remote_addr (not X-Forwarded-For)"""
    with flask_app.test_request_context(
        environ_base={'REMOTE_ADDR': '192.168.1.100'},
        headers={'X-Forwarded-For': '10.0.0.1'}
    ):
        ip = auth_manager.get_ip_address(request)
        assert ip == '192.168.1.100'

def test_get_ip_address_fallback(auth_manager, flask_app):
    """Test IP address extraction with fallback"""
    with flask_app.test_request_context(environ_base={'REMOTE_ADDR': '127.0.0.1'}):
        ip = auth_manager.get_ip_address(request)
        assert ip is not None
        assert len(ip) > 0
        assert ip == '127.0.0.1'
