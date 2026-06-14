from flask import Blueprint, render_template, request, session, redirect, url_for
from src_utils.utils import utils
from auth import AuthManager
from database import DataBase

auth_bp = Blueprint('auth', __name__)
auth_manager = AuthManager()
db = DataBase()

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and authentication handler"""
    if request.method == 'POST':
        password = request.form.get('password', '')

        session_id = auth_manager.generate_session_id()
        device_info = auth_manager.get_device_info(request)
        ip_address = auth_manager.get_ip_address(request)

        if auth_manager.validate_password(password):
            # Password is correct
            # Log the login
            db.log_login(session_id, device_info, ip_address)

            # Create session
            session['user'] = 'admin'
            session['session_id'] = session_id
            session.permanent = True

            utils.log(f"Admin login successful from {ip_address}", 'system')
            return redirect(url_for('index'))  # Redirect to main app
        else:
            # Password is incorrect
            utils.log(f"Failed login attempt from {ip_address}", 'warning')
            return render_template('login.html', error='Invalid password')

    # GET request - show login page
    if 'user' in session:
        return redirect(url_for('index'))  # Already logged in

    return render_template('login.html')

@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Logout handler"""
    session_id = session.get('session_id')

    if session_id:
        db.log_logout(session_id)
        utils.log(f"Admin logout", 'system')

    session.clear()
    return redirect(url_for('auth.login'))

def require_login(f):
    """Decorator to require login for routes"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)

    return decorated_function
