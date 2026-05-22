import os
import hashlib
import secrets
from datetime import datetime
from dotenv import load_dotenv
from src_utils.utils import utils

load_dotenv()

class AuthManager:
    """Manage authentication for the application"""

    def __init__(self):
        self.admin_password = os.getenv('ADMIN_PASSWORD')
        if not self.admin_password:
            utils.log("ADMIN_PASSWORD not set in environment", 'error')

    def validate_password(self, provided_password):
        """Validate provided password against ADMIN_PASSWORD"""
        if not self.admin_password:
            utils.log("Admin password not configured", 'error')
            return False

        return provided_password == self.admin_password

    def generate_session_id(self):
        """Generate a secure session ID"""
        return secrets.token_urlsafe(32)

    def get_device_info(self, request):
        """Extract device info from Flask request"""
        user_agent = request.headers.get('User-Agent', 'Unknown')
        return user_agent[:500]  # Truncate to 500 chars

    def get_ip_address(self, request):
        """Get client IP address from Flask request"""
        # Check for proxy headers first
        if request.headers.get('X-Forwarded-For'):
            ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
        elif request.headers.get('X-Real-IP'):
            ip = request.headers.get('X-Real-IP')
        else:
            ip = request.remote_addr

        return ip[:45]  # Truncate to 45 chars (max IPv6 length)
