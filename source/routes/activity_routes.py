from flask import Blueprint, render_template, session
from auth import AuthManager
from database import DataBase
from routes.auth_routes import require_login

activity_bp = Blueprint('activity', __name__)
db = DataBase()

@activity_bp.route('/activity')
@require_login
def activity_log():
    """Display login/logout activity log"""
    activities = db.get_login_activity()

    # Format data for display
    formatted_activities = []
    for activity in activities:
        is_still_logged_in = activity['logout_time'] is None
        formatted_activities.append({
            'id': activity['id'],
            'login_time': activity['login_time'].strftime('%Y-%m-%d %H:%M:%S') if activity['login_time'] else 'N/A',
            'logout_time': activity['logout_time'].strftime('%Y-%m-%d %H:%M:%S') if activity['logout_time'] else 'Still logged in',
            'is_still_logged_in': is_still_logged_in,
            'device_info': activity['device_info'],
            'ip_address': activity['ip_address']
        })

    return render_template('activity_log.html', activities=formatted_activities)
