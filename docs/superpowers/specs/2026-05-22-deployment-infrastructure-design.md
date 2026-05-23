# Deployment Infrastructure Design
**Date:** 2026-05-22  
**Status:** Approved for implementation

## Context
Migrate the banking app from local SQLite to a cloud-deployed web application accessible from anywhere with minimal service costs. Enable one admin user to access the app from multiple devices with login/logout activity tracking.

## Architecture

### Technology Stack
- **Hosting**: Vercel (free tier) — Flask Python app
- **Database**: Neon PostgreSQL (free tier, 0.5GB storage, 190 compute hours/month)
- **Code Repository**: GitHub
- **Authentication**: Session-based, single admin user with password stored as Vercel environment variable

### User Flow
1. User visits app URL (hosted on Vercel)
2. Login screen appears with password input
3. User enters password (validated against `ADMIN_PASSWORD` env var)
4. Session created via Flask-Session
5. User redirected to main app dashboard
6. User can access from any device with same password
7. Login/logout events recorded in database with device info

## Database Schema

### New Table: `login_activity`
```sql
CREATE TABLE login_activity (
    id SERIAL PRIMARY KEY,
    login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    logout_time TIMESTAMP,
    session_id VARCHAR(255),
    device_info VARCHAR(500),  -- browser/OS/device details
    ip_address VARCHAR(45)     -- IPv4 or IPv6
);
```

### Existing Tables (Unchanged)
- `CardTransactions` — existing card transaction data
- `BankTransactions` — existing bank transaction data

### Data Migration
- Export existing SQLite data
- Import into Neon PostgreSQL
- Verify row counts match post-migration

## Frontend Changes

### New Login Page
- Clean, minimal password input form
- Submit button triggers authentication
- Error message on invalid password
- Redirect to app dashboard on success

### New Activity Log Page
- Display login/logout history
- Columns: Login Time, Logout Time, Device Info, IP Address
- Table format, sortable by date
- Accessible only after login

### CSS Updates for Mobile Responsiveness
- Update existing HTML files to use responsive design
- Test on mobile devices (375px minimum width)
- Ensure all forms are mobile-friendly
- Touch-friendly button sizes (48px minimum)

## Environment Variables (Vercel)
```
ADMIN_PASSWORD=<secure-password>
DATABASE_URL=postgresql://user:password@neon-host/dbname
FLASK_SECRET_KEY=<random-secret-for-sessions>
```

## Security Measures
- ✅ Password never hardcoded in source (stored in Vercel env vars)
- ✅ HTTPS enforced by Vercel (default)
- ✅ Session cookies: httponly, secure flags enabled
- ✅ Database credentials in env vars only
- ✅ Personal data files (personal_config.json) remain local, not deployed
- ✅ No sensitive data in Git repository

## Deployment Process
1. Create Flask app wrapper for Vercel compatibility
2. Add login/logout routes and session management
3. Create login_activity table in Neon PostgreSQL
4. Migrate data from SQLite to PostgreSQL
5. Update CSS for mobile responsiveness
6. Deploy to Vercel
7. Set environment variables in Vercel dashboard
8. Create Activity Log page in frontend

## Testing
- ✅ Login with correct password → app loads
- ✅ Login with wrong password → error message displayed
- ✅ Logout → session cleared, login_activity.logout_time recorded
- ✅ Activity log shows all login/logout events with device info
- ✅ Mobile responsive design on 375px width
- ✅ Access from multiple devices with same password works
- ✅ Database migration: row count verification

## Success Criteria
- [ ] App accessible via public URL on Vercel
- [ ] Login screen appears before app loads
- [ ] One admin user can access from multiple devices
- [ ] Login/logout activity logged with device info
- [ ] Mobile-friendly responsive design
- [ ] No sensitive data exposed in deployment
- [ ] Data persists in Neon PostgreSQL
