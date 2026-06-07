# Deployment Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the banking app to a cloud-deployed web app (Vercel + Neon PostgreSQL) with login authentication, activity logging, mobile-responsive design, and environment-variable-based credential management.

**Architecture:** Flask app with session-based authentication, PostgreSQL database on Neon, login_activity table for tracking, Vercel serverless deployment with environment variables for secrets.

**Tech Stack:** Python Flask, PostgreSQL (Neon), Flask-Session, psycopg2, python-dotenv, Vercel, responsive CSS.

---

## File Structure

**New Files:**
- `source/auth.py` — Authentication logic
- `source/routes/auth_routes.py` — Login/logout routes
- `source/routes/activity_routes.py` — Activity log page
- `source/html/login.html` — Login page template
- `source/html/activity_log.html` — Activity log page template
- `migration_script.py` — SQLite → PostgreSQL data migration
- `vercel.json` — Vercel deployment config
- `.env.example` — Example environment variables
- `tests/test_auth.py` — Authentication tests
- `tests/test_login_activity.py` — Login activity logging tests

**Modified Files:**
- `source/database.py` — Add PostgreSQL connection + login_activity table
- `source/AppManager.py` — Add auth middleware
- `requirements.txt` — Add dependencies (psycopg2, Flask-Session, python-dotenv)
- `source/html/output.html` — Add responsive mobile CSS
- Any other HTML files — Add responsive mobile CSS

---

## Task 1: Set Up Environment Variables and Dependencies

**Files:**
- Create: `.env.example`
- Modify: `requirements.txt`

- [ ] **Step 1: Create .env.example file**

Create `C:\Users\ofeks\OneDrive\Ofek\BankProject\.env.example`:

```
# Authentication
ADMIN_PASSWORD=your_secure_password_here

# Database (PostgreSQL on Neon)
DATABASE_URL=postgresql://user:password@host/dbname

# Flask Session
FLASK_SECRET_KEY=your_random_secret_key_here

# Environment
FLASK_ENV=production
```

- [ ] **Step 2: Update requirements.txt with new dependencies**

Read current `requirements.txt` and add:

```
psycopg2-binary==2.9.9
Flask-Session==0.5.0
python-dotenv==1.0.0
```

- [ ] **Step 3: Test environment variable loading**

Run:
```bash
cd C:\Users\ofeks\OneDrive\Ofek\BankProject
pip install -r requirements.txt
python -c "import psycopg2; import flask_session; import dotenv; print('All dependencies installed')"
```

Expected: "All dependencies installed"

- [ ] **Step 4: Commit**

```bash
git add .env.example requirements.txt
git commit -m "chore: add environment variables and dependencies for deployment"
```

---

## Task 2: Update Database Connection for PostgreSQL

**Files:**
- Modify: `source/database.py`

- [ ] **Step 1: Add PostgreSQL connection at the top of database.py**

Replace the SQLite import with PostgreSQL connection code. At the top of `source/database.py`, after imports, add:

```python
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import DictCursor

load_dotenv()

# PostgreSQL connection
def get_db_connection():
    """Get PostgreSQL connection from environment variable"""
    try:
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        return conn
    except Exception as e:
        utils.log(f"Database connection failed: {e}", 'error')
        return None
```

- [ ] **Step 2: Add login_activity table initialization**

In `source/database.py`, add this function after `get_db_connection()`:

```python
def initialize_login_activity_table():
    """Create login_activity table if it doesn't exist"""
    conn = get_db_connection()
    if conn is None:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS login_activity (
                id SERIAL PRIMARY KEY,
                login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                logout_time TIMESTAMP,
                session_id VARCHAR(255),
                device_info VARCHAR(500),
                ip_address VARCHAR(45)
            );
            CREATE INDEX IF NOT EXISTS idx_login_time ON login_activity(login_time DESC);
        """)
        conn.commit()
        cursor.close()
        conn.close()
        utils.log("login_activity table initialized", 'system')
        return True
    except Exception as e:
        utils.log(f"Failed to initialize login_activity table: {e}", 'error')
        return False
```

- [ ] **Step 3: Update existing database class to use PostgreSQL**

In the `DataBase` class constructor, add PostgreSQL initialization:

```python
def __init__(self):
    self.conn = get_db_connection()
    if self.conn is None:
        utils.log("Failed to connect to PostgreSQL", 'error')
    initialize_login_activity_table()
```

- [ ] **Step 4: Add login_activity query methods to DataBase class**

Add to `DataBase` class:

```python
def log_login(self, session_id, device_info, ip_address):
    """Log a user login event"""
    try:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO login_activity (session_id, device_info, ip_address)
            VALUES (%s, %s, %s)
        """, (session_id, device_info, ip_address))
        self.conn.commit()
        cursor.close()
        return True
    except Exception as e:
        utils.log(f"Failed to log login: {e}", 'error')
        return False

def log_logout(self, session_id):
    """Log a user logout event"""
    try:
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE login_activity
            SET logout_time = CURRENT_TIMESTAMP
            WHERE session_id = %s AND logout_time IS NULL
        """, (session_id,))
        self.conn.commit()
        cursor.close()
        return True
    except Exception as e:
        utils.log(f"Failed to log logout: {e}", 'error')
        return False

def get_login_activity(self):
    """Get all login activity (for activity log page)"""
    try:
        cursor = self.conn.cursor(cursor_factory=DictCursor)
        cursor.execute("""
            SELECT id, login_time, logout_time, device_info, ip_address
            FROM login_activity
            ORDER BY login_time DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        return rows
    except Exception as e:
        utils.log(f"Failed to get login activity: {e}", 'error')
        return []
```

- [ ] **Step 5: Commit**

```bash
git add source/database.py
git commit -m "feat: update database for PostgreSQL and add login_activity table"
```

---

## Task 3: Create Authentication Module

**Files:**
- Create: `source/auth.py`

- [ ] **Step 1: Write auth.py with password validation**

Create `source/auth.py`:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add source/auth.py
git commit -m "feat: create authentication module"
```

---

## Task 4: Create Login Route and Template

**Files:**
- Create: `source/routes/auth_routes.py`
- Create: `source/html/login.html`

- [ ] **Step 1: Create auth_routes.py**

Create `source/routes/auth_routes.py`:

```python
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
        
        if auth_manager.validate_password(password):
            # Password is correct
            session_id = auth_manager.generate_session_id()
            device_info = auth_manager.get_device_info(request)
            ip_address = auth_manager.get_ip_address(request)
            
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
            utils.log(f"Failed login attempt from {request.remote_addr}", 'warning')
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
```

- [ ] **Step 2: Create login.html template**

Create `source/html/login.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bank App Login</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }
        
        .login-container {
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
            width: 100%;
            max-width: 400px;
            padding: 40px;
        }
        
        h1 {
            text-align: center;
            color: #333;
            margin-bottom: 30px;
            font-size: 24px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 500;
            font-size: 14px;
        }
        
        input[type="password"] {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        
        input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        
        button:active {
            transform: translateY(0);
        }
        
        .error-message {
            background-color: #fee;
            color: #c33;
            padding: 12px;
            border-radius: 5px;
            margin-bottom: 20px;
            font-size: 14px;
            border-left: 4px solid #c33;
        }
        
        @media (max-width: 480px) {
            .login-container {
                padding: 30px 20px;
            }
            
            h1 {
                font-size: 20px;
            }
            
            input[type="password"],
            button {
                font-size: 16px;
                padding: 14px;
            }
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>Bank App</h1>
        
        {% if error %}
        <div class="error-message">{{ error }}</div>
        {% endif %}
        
        <form method="POST">
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required autofocus>
            </div>
            
            <button type="submit">Login</button>
        </form>
    </div>
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add source/routes/auth_routes.py source/html/login.html
git commit -m "feat: add login route and template"
```

---

## Task 5: Create Activity Log Page

**Files:**
- Create: `source/routes/activity_routes.py`
- Create: `source/html/activity_log.html`

- [ ] **Step 1: Create activity_routes.py**

Create `source/routes/activity_routes.py`:

```python
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
        formatted_activities.append({
            'id': activity['id'],
            'login_time': activity['login_time'].strftime('%Y-%m-%d %H:%M:%S') if activity['login_time'] else 'N/A',
            'logout_time': activity['logout_time'].strftime('%Y-%m-%d %H:%M:%S') if activity['logout_time'] else 'Still logged in',
            'device_info': activity['device_info'],
            'ip_address': activity['ip_address']
        })
    
    return render_template('activity_log.html', activities=formatted_activities)
```

- [ ] **Step 2: Create activity_log.html template**

Create `source/html/activity_log.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Activity Log</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background-color: #f5f5f5;
            padding: 20px;
        }
        
        .container {
            max-width: 1000px;
            margin: 0 auto;
        }
        
        h1 {
            color: #333;
            margin-bottom: 30px;
            font-size: 28px;
        }
        
        .logout-btn {
            background-color: #c33;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            margin-bottom: 20px;
            float: right;
        }
        
        .logout-btn:hover {
            background-color: #a22;
        }
        
        .back-btn {
            background-color: #667eea;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            margin-bottom: 20px;
            text-decoration: none;
            display: inline-block;
        }
        
        .back-btn:hover {
            background-color: #5568d3;
        }
        
        .clearfix::after {
            content: "";
            display: table;
            clear: both;
        }
        
        table {
            width: 100%;
            background: white;
            border-collapse: collapse;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            border-radius: 5px;
            overflow: hidden;
        }
        
        th {
            background-color: #667eea;
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
            font-size: 14px;
        }
        
        td {
            padding: 12px 15px;
            border-bottom: 1px solid #eee;
        }
        
        tr:hover {
            background-color: #f9f9f9;
        }
        
        tr:last-child td {
            border-bottom: none;
        }
        
        .status-active {
            color: #22a;
            font-weight: 600;
        }
        
        .status-inactive {
            color: #666;
        }
        
        .no-activities {
            text-align: center;
            padding: 40px;
            color: #999;
            font-size: 16px;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 0;
            }
            
            h1 {
                font-size: 20px;
                margin-bottom: 20px;
            }
            
            table {
                font-size: 12px;
            }
            
            th, td {
                padding: 10px;
            }
            
            .logout-btn,
            .back-btn {
                display: block;
                width: 100%;
                margin-bottom: 10px;
                float: none;
            }
            
            .clearfix {
                margin-bottom: 20px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="clearfix">
            <a href="/" class="back-btn">Back to App</a>
            <form method="POST" action="/logout" style="display: inline; float: right;">
                <button type="submit" class="logout-btn">Logout</button>
            </form>
        </div>
        
        <h1>Login Activity Log</h1>
        
        {% if activities %}
        <table>
            <thead>
                <tr>
                    <th>Login Time</th>
                    <th>Logout Time</th>
                    <th>Device Info</th>
                    <th>IP Address</th>
                </tr>
            </thead>
            <tbody>
                {% for activity in activities %}
                <tr>
                    <td>{{ activity.login_time }}</td>
                    <td>
                        {% if 'Still logged in' in activity.logout_time %}
                        <span class="status-active">{{ activity.logout_time }}</span>
                        {% else %}
                        <span class="status-inactive">{{ activity.logout_time }}</span>
                        {% endif %}
                    </td>
                    <td>{{ activity.device_info }}</td>
                    <td>{{ activity.ip_address }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="no-activities">No login activity recorded yet.</div>
        {% endif %}
    </div>
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add source/routes/activity_routes.py source/html/activity_log.html
git commit -m "feat: add activity log page and routes"
```

---

## Task 6: Integrate Authentication into AppManager

**Files:**
- Modify: `source/AppManager.py`

- [ ] **Step 1: Update AppManager to require login**

In `source/AppManager.py`, find where the Flask app is created and wrap routes with the `@require_login` decorator. At the top of the file, add:

```python
from routes.auth_routes import auth_bp, require_login
from routes.activity_routes import activity_bp
```

Then register blueprints in the Flask app initialization (find where `app = Flask(...)` is):

```python
# Register authentication blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(activity_bp)

# Configure session
from flask_session import Session
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)
```

- [ ] **Step 2: Wrap main route with @require_login**

Find the main route handler (likely `@app.route('/')` or similar) and add the decorator:

```python
@app.route('/')
@require_login
def index():
    # existing code
```

- [ ] **Step 3: Commit**

```bash
git add source/AppManager.py
git commit -m "feat: integrate authentication middleware into AppManager"
```

---

## Task 7: Update CSS for Mobile Responsiveness

**Files:**
- Modify: `source/html/output.html`
- Modify: Any other HTML files in `source/html/`

- [ ] **Step 1: Add responsive viewport meta tag and CSS to output.html**

At the top of `source/html/output.html`, in the `<head>` section, ensure this exists:

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0">
```

Then add this CSS media query at the end of the `<style>` section:

```css
/* Mobile Responsive Design */
@media (max-width: 768px) {
    body {
        padding: 10px;
        font-size: 14px;
    }
    
    .container, .main-content {
        padding: 10px;
        margin: 0;
    }
    
    table {
        font-size: 12px;
        display: block;
        overflow-x: auto;
    }
    
    th, td {
        padding: 8px;
    }
    
    button, input, select {
        padding: 12px;
        font-size: 16px;
        min-height: 44px;
    }
    
    .header, .sidebar, .navigation {
        display: block;
        width: 100%;
    }
    
    h1, h2, h3 {
        font-size: 18px;
        margin-bottom: 15px;
    }
}

@media (max-width: 480px) {
    body {
        padding: 5px;
        font-size: 12px;
    }
    
    table {
        font-size: 10px;
    }
    
    th, td {
        padding: 5px;
    }
    
    button, input, select {
        width: 100%;
        padding: 12px;
        font-size: 16px;
        margin-bottom: 10px;
    }
    
    h1, h2 {
        font-size: 16px;
    }
}
```

- [ ] **Step 2: Test mobile layout**

Open output.html in a browser and use Chrome DevTools to test at 375px width (iPhone viewport).

Expected: All content visible, readable, buttons clickable.

- [ ] **Step 3: Commit**

```bash
git add source/html/output.html
git commit -m "feat: add mobile responsive CSS"
```

---

## Task 8: Create Migration Script (SQLite to PostgreSQL)

**Files:**
- Create: `migration_script.py`

- [ ] **Step 1: Create migration_script.py**

Create `migration_script.py` at project root:

```python
#!/usr/bin/env python
"""
Migration script: SQLite to PostgreSQL
Copies CardTransactions and BankTransactions data from local SQLite to Neon PostgreSQL
"""

import sqlite3
import os
import sys
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_batch

load_dotenv()

DB_SQLITE = 'source/database.db'  # Update path if different
DB_POSTGRES_URL = os.getenv('DATABASE_URL')

if not DB_POSTGRES_URL:
    print("ERROR: DATABASE_URL not set in environment")
    sys.exit(1)

if not os.path.exists(DB_SQLITE):
    print(f"ERROR: SQLite database not found at {DB_SQLITE}")
    sys.exit(1)

def migrate_table(sqlite_conn, pg_conn, table_name):
    """Migrate a single table from SQLite to PostgreSQL"""
    print(f"\nMigrating {table_name}...")
    
    # Get data from SQLite
    sqlite_cursor = sqlite_conn.cursor()
    sqlite_cursor.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cursor.fetchall()
    column_names = [desc[0] for desc in sqlite_cursor.description]
    
    if not rows:
        print(f"  No data in {table_name}")
        return
    
    # Create table in PostgreSQL if it doesn't exist
    pg_cursor = pg_conn.cursor()
    
    # This is a simplified approach - you may need to adjust column types
    # For production, consider using schema detection
    
    try:
        # Insert data into PostgreSQL
        placeholders = ','.join(['%s'] * len(column_names))
        insert_sql = f"INSERT INTO {table_name} ({','.join(column_names)}) VALUES ({placeholders})"
        
        execute_batch(pg_cursor, insert_sql, rows, page_size=100)
        pg_conn.commit()
        
        print(f"  ✓ Migrated {len(rows)} rows from {table_name}")
    except Exception as e:
        pg_conn.rollback()
        print(f"  ✗ Error migrating {table_name}: {e}")
        return False
    finally:
        pg_cursor.close()
    
    return True

def main():
    print("Starting migration from SQLite to PostgreSQL...")
    
    try:
        # Connect to SQLite
        sqlite_conn = sqlite3.connect(DB_SQLITE)
        sqlite_cursor = sqlite_conn.cursor()
        
        # Get list of tables
        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in sqlite_cursor.fetchall()]
        
        print(f"Found tables: {', '.join(tables)}")
        
        # Connect to PostgreSQL
        pg_conn = psycopg2.connect(DB_POSTGRES_URL)
        
        # Migrate each table
        for table in tables:
            if table.startswith('sqlite_'):  # Skip SQLite internal tables
                continue
            migrate_table(sqlite_conn, pg_conn, table)
        
        pg_conn.close()
        sqlite_conn.close()
        
        print("\n✓ Migration completed successfully")
        
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Create .gitignore entry for migration**

Add to `.gitignore`:

```
migration_script.py.log
*.db
```

- [ ] **Step 3: Commit**

```bash
git add migration_script.py
git commit -m "feat: create SQLite to PostgreSQL migration script"
```

---

## Task 9: Create Vercel Configuration

**Files:**
- Create: `vercel.json`

- [ ] **Step 1: Create vercel.json**

Create `vercel.json` at project root:

```json
{
  "buildCommand": "pip install -r requirements.txt",
  "outputDirectory": ".",
  "env": {
    "ADMIN_PASSWORD": "@admin_password",
    "DATABASE_URL": "@database_url",
    "FLASK_SECRET_KEY": "@flask_secret_key"
  },
  "functions": {
    "source/AppManager.py": {
      "memory": 1024,
      "timeout": 60
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add vercel.json
git commit -m "feat: add Vercel deployment configuration"
```

---

## Task 10: Create Tests for Authentication

**Files:**
- Create: `tests/test_auth.py`

- [ ] **Step 1: Create test_auth.py**

Create `tests/test_auth.py`:

```python
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
    """Test IP address extraction"""
    with flask_app.test_request_context(
        headers={'X-Forwarded-For': '192.168.1.100, 10.0.0.1'}
    ):
        ip = auth_manager.get_ip_address(request)
        assert ip == '192.168.1.100'

def test_get_ip_address_fallback(auth_manager, flask_app):
    """Test IP address extraction with fallback"""
    with flask_app.test_request_context():
        ip = auth_manager.get_ip_address(request)
        assert ip is not None
        assert len(ip) > 0
```

- [ ] **Step 2: Run tests**

```bash
cd C:\Users\ofeks\OneDrive\Ofek\BankProject
pytest tests/test_auth.py -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_auth.py
git commit -m "test: add authentication unit tests"
```

---

## Task 11: Create Tests for Login Activity Logging

**Files:**
- Create: `tests/test_login_activity.py`

- [ ] **Step 1: Create test_login_activity.py**

Create `tests/test_login_activity.py`:

```python
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
```

- [ ] **Step 2: Run tests**

```bash
cd C:\Users\ofeks\OneDrive\Ofek\BankProject
pytest tests/test_login_activity.py -v
```

Expected: All tests pass (or skip if DB not available).

- [ ] **Step 3: Commit**

```bash
git add tests/test_login_activity.py
git commit -m "test: add login activity logging tests"
```

---

## Task 12: Local Testing Before Deployment

**Files:**
- No files to modify (testing only)

- [ ] **Step 1: Create .env file locally**

Copy `.env.example` to `.env` and fill in test values:

```
ADMIN_PASSWORD=test_password_123
DATABASE_URL=postgresql://localhost/bankapp_test
FLASK_SECRET_KEY=test_secret_key_12345
FLASK_ENV=development
```

- [ ] **Step 2: Run the app locally**

```bash
cd C:\Users\ofeks\OneDrive\Ofek\BankProject
python AppManager.py
```

Expected: App starts without errors.

- [ ] **Step 3: Test login flow**

Open browser to `http://localhost:5000/login`
- Try wrong password → should see error
- Try correct password → should redirect to app
- Click on activity log → should show login records
- Click logout → should return to login page

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add .env
git commit -m "test: add local environment configuration"
```

---

## Task 13: Deploy to Vercel

**Files:**
- No files to modify (deployment only)

- [ ] **Step 1: Push code to GitHub**

```bash
git push origin deploy-app
```

- [ ] **Step 2: Set up Vercel project**

Go to vercel.com, create new project, connect GitHub repo.

- [ ] **Step 3: Add environment variables in Vercel dashboard**

In Vercel project settings → Environment Variables, add:
- `ADMIN_PASSWORD` = [your secure password]
- `DATABASE_URL` = [Neon PostgreSQL connection string]
- `FLASK_SECRET_KEY` = [random secret key]

- [ ] **Step 4: Deploy**

Vercel will automatically build and deploy on push.

- [ ] **Step 5: Test production**

Visit your Vercel app URL:
- Login with correct password
- Verify app works
- Check activity log
- Test from mobile browser (responsive design)

- [ ] **Step 6: Commit**

```bash
git commit --allow-empty -m "deploy: release to Vercel production"
git push origin deploy-app
```

---

## Summary of Changes

✅ Environment-based credential management (no hardcoded passwords)  
✅ PostgreSQL database on Neon (from SQLite)  
✅ Login authentication (single admin user)  
✅ Login/logout activity logging with device info and IP address  
✅ Activity log page (new route + template)  
✅ Mobile-responsive CSS updates  
✅ Test coverage for auth and logging  
✅ Vercel deployment configuration  
✅ Data migration script (SQLite → PostgreSQL)

---
