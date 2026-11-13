# General (Non-Mortgage) Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing mortgage-only Timeline feature into a general-purpose life-events timeline, reachable from its own new sidebar nav item, while the housing panel's existing "ציר זמן" sub-tab keeps working exactly as before (now implicitly filtered to mortgage events).

**Architecture:** One new `Category` column on the existing `TimelineEvents` table (`'mortgage'` | `'general'`, default `'mortgage'` for backward compatibility with existing rows). The existing timeline rendering engine in `Base_template.html` (`_renderTimeline`, `_tlDrawAxis`, the modal functions, etc.) is generalized to target a configurable container element and scope, then reused — unmodified in behavior for the housing case — by a new top-level panel with a 3-way category filter toggle. No new database table, no duplicated widget code.

**Tech Stack:** Same as the existing feature — Flask/psycopg2 backend, vanilla ES5 JS inside the existing IIFE, inline CSS, no build step.

**Note on verification:** No automated test suite exists in this repo. Verification is manual: run the app, log in with the local `.env` `ADMIN_PASSWORD` (don't echo it), and check behavior in a browser.

---

### Task 1: Database layer — add the `Category` column

**Files:**
- Modify: `source/database.py`

- [ ] **Step 1: Add the column to `ensure_timeline_tables()`**

Find:
```python
    def ensure_timeline_tables(self) -> None:
        """Create TimelineEvents and TimelineEventTransactions if absent."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS TimelineEvents (
                ID          SERIAL    PRIMARY KEY,
                Name        TEXT      NOT NULL,
                Event_Date  DATE      NOT NULL,
                Description TEXT,
                Color       TEXT      NOT NULL DEFAULT '#1e9d8b',
                Created_At  TIMESTAMP DEFAULT now()
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS TimelineEventTransactions (
                ID                SERIAL  PRIMARY KEY,
                Event_ID          INTEGER NOT NULL REFERENCES TimelineEvents(ID) ON DELETE CASCADE,
                Transaction_Table TEXT    NOT NULL,
                Transaction_ID    INTEGER NOT NULL,
                Note              TEXT
            )
        """)
        self.connection.commit()
```
Replace with (adds the new column via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, following this file's own established pattern for adding a column to a table that already exists in production — e.g. `BillTypes.BillGroup` was added the same way; the `DEFAULT 'mortgage'` means every existing row, all of which were created by the mortgage timeline before this feature existed, is correctly backfilled to `'mortgage'` with no manual migration needed):
```python
    def ensure_timeline_tables(self) -> None:
        """Create TimelineEvents and TimelineEventTransactions if absent."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS TimelineEvents (
                ID          SERIAL    PRIMARY KEY,
                Name        TEXT      NOT NULL,
                Event_Date  DATE      NOT NULL,
                Description TEXT,
                Color       TEXT      NOT NULL DEFAULT '#1e9d8b',
                Created_At  TIMESTAMP DEFAULT now()
            )
        """)
        self.cursor.execute(
            "ALTER TABLE TimelineEvents ADD COLUMN IF NOT EXISTS Category TEXT NOT NULL DEFAULT 'mortgage'"
        )
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS TimelineEventTransactions (
                ID                SERIAL  PRIMARY KEY,
                Event_ID          INTEGER NOT NULL REFERENCES TimelineEvents(ID) ON DELETE CASCADE,
                Transaction_Table TEXT    NOT NULL,
                Transaction_ID    INTEGER NOT NULL,
                Note              TEXT
            )
        """)
        self.connection.commit()
```

- [ ] **Step 2: Update `get_timeline_events()` to accept an optional category filter**

Find:
```python
    def get_timeline_events(self) -> list:
        c = self.connection.cursor()
        c.execute("""
            SELECT ID, Name, Event_Date, Description, Color
            FROM TimelineEvents
            ORDER BY Event_Date ASC, ID ASC
        """)
        events = {}
        order = []
        for r in c.fetchall():
            events[r[0]] = {
                'id': r[0],
                'name': r[1],
                'event_date': str(r[2])[:10] if r[2] else None,
                'description': r[3] or '',
                'color': r[4] or '#1e9d8b',
                'transactions': [],
            }
            order.append(r[0])
```
Replace with (adds an optional `category` parameter; when given, filters via a parameterized `WHERE`; when `None`, behaves exactly as before — returns all events regardless of category — which is what the new general panel's default "show all" view needs, and note the returned dict now also includes `category` so the frontend can tell events apart when needed):
```python
    def get_timeline_events(self, category: str = None) -> list:
        c = self.connection.cursor()
        if category:
            c.execute("""
                SELECT ID, Name, Event_Date, Description, Color, Category
                FROM TimelineEvents
                WHERE Category = %s
                ORDER BY Event_Date ASC, ID ASC
            """, (category,))
        else:
            c.execute("""
                SELECT ID, Name, Event_Date, Description, Color, Category
                FROM TimelineEvents
                ORDER BY Event_Date ASC, ID ASC
            """)
        events = {}
        order = []
        for r in c.fetchall():
            events[r[0]] = {
                'id': r[0],
                'name': r[1],
                'event_date': str(r[2])[:10] if r[2] else None,
                'description': r[3] or '',
                'color': r[4] or '#1e9d8b',
                'category': r[5],
                'transactions': [],
            }
            order.append(r[0])
```
(The rest of `get_timeline_events()` — the transaction-join query and the loop that attaches `transactions` to each event — is unchanged; leave it exactly as-is below this point.)

- [ ] **Step 3: Update `add_timeline_event()` to accept a category**

Find:
```python
    def add_timeline_event(self, name: str, event_date: str, description: str = '', color: str = '#1e9d8b') -> int:
        row = self.cursor.execute("""
            INSERT INTO TimelineEvents (Name, Event_Date, Description, Color)
            VALUES (%s, %s, %s, %s) RETURNING ID
        """, (name, event_date, description or None, color)).fetchone()
        return row[0]
```
Replace with:
```python
    def add_timeline_event(self, name: str, event_date: str, description: str = '', color: str = '#1e9d8b', category: str = 'general') -> int:
        row = self.cursor.execute("""
            INSERT INTO TimelineEvents (Name, Event_Date, Description, Color, Category)
            VALUES (%s, %s, %s, %s, %s) RETURNING ID
        """, (name, event_date, description or None, color, category)).fetchone()
        return row[0]
```
(`update_timeline_event()` and `delete_timeline_event()` are NOT changed — per the design spec, an event's category is immutable after creation via the API, so the update method has no reason to touch it.)

- [ ] **Step 4: Verify manually**

```bash
cd source
python -c "
from database import DataBase
db = DataBase()
db.ensure_timeline_tables()
mid = db.add_timeline_event('Mortgage test', '2026-08-01', category='mortgage')
gid = db.add_timeline_event('General test', '2026-08-02', category='general')
db.commit_changes()
print('all:', [e['category'] for e in db.get_timeline_events()])
print('mortgage only:', [e['name'] for e in db.get_timeline_events(category='mortgage')])
print('general only:', [e['name'] for e in db.get_timeline_events(category='general')])
db.delete_timeline_event(mid)
db.delete_timeline_event(gid)
db.commit_changes()
"
```
Expected: `all:` prints a list including `'mortgage'` and `'general'` among its entries (plus whatever category your existing real rows have — should all read `'mortgage'` since they predate this feature); `mortgage only:` includes `'Mortgage test'` but not `'General test'`; `general only:` includes `'General test'` but not `'Mortgage test'`.

- [ ] **Step 5: Commit**

```bash
git add source/database.py
git commit -m "$(cat <<'EOF'
feat(timeline): add Category column to support general (non-mortgage) events

Existing rows default to 'mortgage' via the column's DEFAULT, since
the mortgage timeline is the only thing that has ever written to this
table. get_timeline_events() gains an optional category filter;
add_timeline_event() gains a category parameter (defaulting to
'general', the more conservative default for direct/API use).
EOF
)"
```
Bump `/VERSION` (check current value first, increment by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```

---

### Task 2: Backend API — category filter on GET, category field on POST

**Files:**
- Modify: `source/WebApp.py`

- [ ] **Step 1: Add the category filter to the GET handler**

Find:
```python
@app.route('/api/timeline/events', methods=['GET', 'POST'])
def api_timeline_events():
    from database import DataBase
    try:
        db = DataBase()
        db.ensure_timeline_tables()
        if request.method == 'GET':
            return jsonify({'ok': True, 'events': db.get_timeline_events()})
        body  = request.get_json(force=True) or {}
        name  = (body.get('name') or '').strip()
        date  = (body.get('event_date') or '').strip()
        color = (body.get('color') or '#1e9d8b').strip()
        desc  = (body.get('description') or '').strip()
        if not name:
            return jsonify({'ok': False, 'error': 'Name required'})
        if not date:
            return jsonify({'ok': False, 'error': 'Date required'})
        eid = db.add_timeline_event(name, date, desc, color)
        db.commit_changes()
        return jsonify({'ok': True, 'id': eid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
```
Replace with:
```python
@app.route('/api/timeline/events', methods=['GET', 'POST'])
def api_timeline_events():
    from database import DataBase
    try:
        db = DataBase()
        db.ensure_timeline_tables()
        if request.method == 'GET':
            category = (request.args.get('category') or '').strip()
            if category not in ('mortgage', 'general'):
                category = None
            return jsonify({'ok': True, 'events': db.get_timeline_events(category=category)})
        body     = request.get_json(force=True) or {}
        name     = (body.get('name') or '').strip()
        date     = (body.get('event_date') or '').strip()
        color    = (body.get('color') or '#1e9d8b').strip()
        desc     = (body.get('description') or '').strip()
        category = (body.get('category') or '').strip()
        if category not in ('mortgage', 'general'):
            category = 'general'
        if not name:
            return jsonify({'ok': False, 'error': 'Name required'})
        if not date:
            return jsonify({'ok': False, 'error': 'Date required'})
        eid = db.add_timeline_event(name, date, desc, color, category)
        db.commit_changes()
        return jsonify({'ok': True, 'id': eid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
```
(The `PUT` handler in `api_timeline_event()` — the sibling function for `/api/timeline/events/<int:event_id>` — is NOT changed. It doesn't read a `category` field from the request body at all, so there is no way to change an event's category via the API, matching the design spec's "category is immutable after creation" rule.)

- [ ] **Step 2: Verify manually**

Start the app (`cd source && python WebApp.py`), then from another terminal:
```bash
curl -s -X POST http://localhost:5050/api/timeline/events \
  -H "Content-Type: application/json" \
  -d '{"name":"Mortgage curl test","event_date":"2026-08-01","category":"mortgage"}'
curl -s -X POST http://localhost:5050/api/timeline/events \
  -H "Content-Type: application/json" \
  -d '{"name":"General curl test","event_date":"2026-08-02","category":"general"}'
curl -s -X POST http://localhost:5050/api/timeline/events \
  -H "Content-Type: application/json" \
  -d '{"name":"No category curl test","event_date":"2026-08-03"}'
```
Expected: all three return `{"ok": true, "id": <int>}`. Then:
```bash
curl -s "http://localhost:5050/api/timeline/events?category=mortgage"
curl -s "http://localhost:5050/api/timeline/events?category=general"
curl -s "http://localhost:5050/api/timeline/events"
```
Expected: the `?category=mortgage` response includes only "Mortgage curl test"; the `?category=general` response includes "General curl test" AND "No category curl test" (since the omitted-category POST defaulted to `'general'`); the no-filter response includes all three. Delete all three test events afterward via `curl -X DELETE http://localhost:5050/api/timeline/events/<id>` for each id returned above.

- [ ] **Step 3: Commit**

```bash
git add source/WebApp.py
git commit -m "$(cat <<'EOF'
feat(timeline): support category filtering and tagging over the API

GET /api/timeline/events accepts an optional ?category=mortgage|general
filter (any other/missing value returns all events, unfiltered).
POST accepts an optional category field, defaulting to 'general' for
any caller that doesn't specify one explicitly.
EOF
)"
```
Bump `/VERSION` (check current value first, increment by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```

---

### Task 3: Frontend — generalize the shared timeline engine (no behavior change for housing)

**Files:**
- Modify: `source/html/Base_template.html`

This task makes the existing timeline rendering code target a configurable container and scope instead of the hardcoded `'housing-timeline'` id and an implicit "no filter" fetch — but wires it up so the HOUSING sub-tab's behavior is completely unchanged (it explicitly sets scope to `'mortgage'`, matching what it already implicitly was). Task 4 then adds the actual new panel that uses the `'general'` scope.

- [ ] **Step 1: Add the new scope/container state variables**

Find:
```javascript
  var _tlPxPerDay = 6;
  var _tlMinimizeMode = (localStorage.getItem('tl_minimize_mode') !== '0');
```
Replace with:
```javascript
  var _tlPxPerDay = 6;
  var _tlMinimizeMode = (localStorage.getItem('tl_minimize_mode') !== '0');
  var _tlContainerId = 'housing-timeline';
  var _tlActiveScope = 'mortgage'; // 'mortgage' | 'general' — which UI surface is driving the shared engine
  var _tlCategoryFilter = 'all';   // only meaningful when _tlActiveScope === 'general': 'all' | 'mortgage' | 'general'
```

- [ ] **Step 2: Make `_loadTimelineTab()` fetch with the right filter and target the right container**

Find:
```javascript
  async function _loadTimelineTab() {
    var tl = document.getElementById('housing-timeline');
    if (!tl) return;
    tl.innerHTML = '<div class="tl-empty">טוען…</div>';
    try {
      var r = await fetch('/api/timeline/events');
      var d = await r.json();
      _timelineEvents = d.events || [];
    } catch (e) {
      _timelineEvents = [];
    }
    _renderTimeline(_timelineEvents);
  }
```
Replace with:
```javascript
  function _tlEventsUrl() {
    if (_tlActiveScope === 'mortgage') return '/api/timeline/events?category=mortgage';
    if (_tlCategoryFilter && _tlCategoryFilter !== 'all') return '/api/timeline/events?category=' + _tlCategoryFilter;
    return '/api/timeline/events';
  }

  async function _loadTimelineTab() {
    var tl = document.getElementById(_tlContainerId);
    if (!tl) return;
    tl.innerHTML = '<div class="tl-empty">טוען…</div>';
    try {
      var r = await fetch(_tlEventsUrl());
      var d = await r.json();
      _timelineEvents = d.events || [];
    } catch (e) {
      _timelineEvents = [];
    }
    _renderTimeline(_timelineEvents);
  }
```

- [ ] **Step 3: Make `_renderTimeline()` target the configurable container**

Find, in `_renderTimeline`:
```javascript
  function _renderTimeline(events) {
    var tl = document.getElementById('housing-timeline');
    if (!tl) return;
```
Replace with:
```javascript
  function _renderTimeline(events) {
    var tl = document.getElementById(_tlContainerId);
    if (!tl) return;
```
(The rest of `_renderTimeline` — the toolbar/axis-wrap markup and the calls to `_tlDrawAxis`/`_tlWireScrollArrows` — is unchanged.)

- [ ] **Step 4: Make the housing sub-tab explicitly set scope before loading**

Find, in `_switchHousingTab`:
```javascript
    if (tab === 'timeline') {
      ov.style.display = 'none';
      tl.style.display = '';
      if (bOv) bOv.classList.remove('active');
      if (bTl) bTl.classList.add('active');
      if (!_timelineEvents) {
        _loadTimelineTab();
      } else {
        _renderTimeline(_timelineEvents);
      }
```
Replace with:
```javascript
    if (tab === 'timeline') {
      ov.style.display = 'none';
      tl.style.display = '';
      if (bOv) bOv.classList.remove('active');
      if (bTl) bTl.classList.add('active');
      _tlContainerId = 'housing-timeline';
      _tlActiveScope = 'mortgage';
      if (!_timelineEvents) {
        _loadTimelineTab();
      } else {
        _renderTimeline(_timelineEvents);
      }
```

- [ ] **Step 5: Tag new events with the right category on save**

Find, in `_tlSubmitEvent`:
```javascript
    var body = { name: name, event_date: date, description: desc, color: _tlSelectedColor };
```
Replace with:
```javascript
    var body = {
      name: name, event_date: date, description: desc, color: _tlSelectedColor,
      category: _tlActiveScope === 'mortgage' ? 'mortgage' : 'general',
    };
```
(This field is harmlessly ignored by the server's `PUT` handler when `_tlModalMode === 'edit'`, since editing never changes an event's category — see Task 2. It's only actually used by the server on `POST`, i.e. when adding a brand-new event.)

- [ ] **Step 6: Verify manually — confirm the housing sub-tab is completely unaffected**

Start the app, log in, open the housing panel's "ציר זמן" sub-tab. Confirm:
1. It loads and displays exactly as before (no visible change) — existing mortgage events still show up.
2. Creating a new event from here still works, and the created event has `category: 'mortgage'` (verify via `curl http://localhost:5050/api/timeline/events?category=mortgage` after creating it).
3. Editing, deleting, and transaction-linking on an existing mortgage event all still work exactly as before.
4. No console errors.
5. Clean up any test events created.

- [ ] **Step 7: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
refactor(timeline): generalize the shared engine by container id + scope

Introduces _tlContainerId/_tlActiveScope/_tlCategoryFilter so the same
_renderTimeline/_tlDrawAxis/_tlSubmitEvent code can drive more than one
timeline surface. The housing sub-tab explicitly sets scope to
'mortgage', preserving its exact existing behavior -- this is purely
a generalization, no user-visible change yet. A later task adds the
new general-timeline panel that actually uses the 'general' scope.
EOF
)"
```
Bump `/VERSION` (check current value first, increment by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```

---

### Task 4: Frontend — new sidebar nav item, `/timeline` route, and the general-timeline panel

**Files:**
- Modify: `source/WebApp.py`
- Modify: `source/html/Base_template.html`

- [ ] **Step 1: Add the `/timeline` redirect route**

Find, in `source/WebApp.py`:
```python
@app.route('/housing')
def housing_page():
    """Redirect to the latest monthly page with ?panel=housing."""
    latest_key = _get_latest_yyyy_mm()
    if latest_key:
        return redirect(f'/general/{latest_key}?panel=housing')
    return redirect('/')
```
Add this new route immediately after it:
```python
@app.route('/timeline')
def general_timeline_page():
    """Redirect to the latest monthly page with ?panel=timeline."""
    latest_key = _get_latest_yyyy_mm()
    if latest_key:
        return redirect(f'/general/{latest_key}?panel=timeline')
    return redirect('/')
```

- [ ] **Step 2: Add the sidebar nav link**

Find, in `source/html/Base_template.html`:
```html
    <a class="nav-item" href="/housing">דיור</a>
```
Add this new line immediately after it:
```html
    <a class="nav-item" href="/timeline">ציר זמן</a>
```

- [ ] **Step 3: Add the empty panel shell**

Find:
```html
  <div id="panel-housing" class="panel"></div>
```
Add this new line immediately after it:
```html
  <div id="panel-timeline" class="panel"></div>
```

- [ ] **Step 4: Register the panel's title and top-clearance CSS**

Find:
```javascript
var _PANEL_TITLES = { overview: 'ניתוח חודשי', accounts: 'חשבונות', housing: 'ניהול נכס' };
```
Replace with:
```javascript
var _PANEL_TITLES = { overview: 'ניתוח חודשי', accounts: 'חשבונות', housing: 'ניהול נכס', timeline: 'ציר זמן' };
```
Find:
```css
#housing-overview, #housing-timeline { margin-top:64px; }
```
Replace with:
```css
#housing-overview, #housing-timeline, #panel-timeline { margin-top:64px; }
```
Find, inside the existing `@media (max-width:700px) { ... }` block:
```css
  #housing-overview, #housing-timeline { margin-top:60px; }
```
Replace with:
```css
  #housing-overview, #housing-timeline, #panel-timeline { margin-top:60px; }
```
(This reuses the exact same clearance values already established for the housing panel's content, so `#panel-timeline`'s content clears the fixed hamburger button the same way.)

- [ ] **Step 5: Add the filter-toggle CSS**

Add this new rule block right after the `.hs-subtabs` rule (the one with `position:fixed; top:18px; right:70px; ...`):
```css
.tl-filter-row { display:flex; gap:8px; margin-bottom:14px; }
```

- [ ] **Step 6: Add the panel-loading and filter-switching functions**

Add these new functions right after `_tlEventsUrl()` (added in Task 3):
```javascript
  function _tlFilterBtnHtml(value, label) {
    return '<button class="hs-subtab-btn' + (_tlCategoryFilter === value ? ' active' : '') + '" onclick="_tlSetCategoryFilter(\'' + value + '\')">' + label + '</button>';
  }

  function _loadGeneralTimelinePanel() {
    _tlContainerId = 'panel-timeline-content';
    _tlActiveScope = 'general';
    var panel = document.getElementById('panel-timeline');
    if (!panel) return;
    if (!document.getElementById('panel-timeline-content')) {
      panel.innerHTML =
        '<div class="tl-filter-row" id="tl-filter-row">' +
          _tlFilterBtnHtml('all', 'הכל') +
          _tlFilterBtnHtml('mortgage', 'משכנתא') +
          _tlFilterBtnHtml('general', 'כללי') +
        '</div>' +
        '<div id="panel-timeline-content"></div>';
    }
    _timelineEvents = null;
    _loadTimelineTab();
  }

  function _tlSetCategoryFilter(filter) {
    _tlCategoryFilter = filter;
    var row = document.getElementById('tl-filter-row');
    if (row) {
      row.innerHTML =
        _tlFilterBtnHtml('all', 'הכל') +
        _tlFilterBtnHtml('mortgage', 'משכנתא') +
        _tlFilterBtnHtml('general', 'כללי');
    }
    _timelineEvents = null;
    _loadTimelineTab();
  }
```

- [ ] **Step 7: Wire the panel into `showPanel()` and the auto-open-from-URL logic**

Find, in `showPanel(name, btn)`:
```javascript
  var nonMonthly = ['housing', 'accounts'];
  if (nonMonthly.indexOf(name) !== -1) { url.searchParams.set('panel', name); }
  else { url.searchParams.delete('panel'); }
  window.history.replaceState({}, '', url.toString());
  if (name === 'housing' && typeof _loadHousingPanel === 'function') _loadHousingPanel(false);
```
Replace with:
```javascript
  var nonMonthly = ['housing', 'accounts', 'timeline'];
  if (nonMonthly.indexOf(name) !== -1) { url.searchParams.set('panel', name); }
  else { url.searchParams.delete('panel'); }
  window.history.replaceState({}, '', url.toString());
  if (name === 'housing' && typeof _loadHousingPanel === 'function') _loadHousingPanel(false);
  if (name === 'timeline' && typeof _loadGeneralTimelinePanel === 'function') _loadGeneralTimelinePanel();
```
Find, in the auto-open-from-URL IIFE:
```javascript
    if (panel === 'housing') {
      document.addEventListener('DOMContentLoaded', function() {
```
Add this new block immediately BEFORE that `if (panel === 'housing') {` line:
```javascript
    if (panel === 'timeline') {
      setTimeout(function() {
        if (typeof _loadGeneralTimelinePanel === 'function') _loadGeneralTimelinePanel();
      }, 0);
    }
```
(This mirrors the existing `if (panel === 'accounts') { setTimeout(...) }` block just above it in the same function — deferred via `setTimeout(0)` for the same reason documented in the surrounding code: `_loadGeneralTimelinePanel` is defined later in the same script block, so it must wait until the whole script has finished executing before being called.)

- [ ] **Step 8: Expose the new onclick-referenced function on `window`**

The housing/timeline script runs inside an IIFE (`(function() { ... })()`), so `var`/`function` declarations inside it are NOT globally accessible — inline `onclick="..."` attributes in HTML strings run in global scope. `_tlSetCategoryFilter` is referenced via `onclick` in the filter-row buttons built in Step 6, so it MUST be exposed. (`_loadGeneralTimelinePanel` is only ever called directly from JS — Step 7's `showPanel`/auto-open code — never from an inline HTML attribute, so it does NOT need exposure.)

Find the existing "expose IIFE-internal functions" block (search for `window._tlCalGoToday`) and add one line near it:
```javascript
  window._tlSetCategoryFilter = _tlSetCategoryFilter;
```
If you skip this, clicking any of the "הכל"/"משכנתא"/"כללי" filter buttons will throw `ReferenceError: _tlSetCategoryFilter is not defined` in the console and silently do nothing.

- [ ] **Step 9: Also mark the new nav link active when landing directly via the URL**

Find, in the same auto-open-from-URL IIFE:
```javascript
    var navBtn = document.getElementById('nav-' + panel);
    if (!navBtn) {
      // For panels backed by external links (e.g. housing → /housing)
      navBtn = document.querySelector('.nav-item[href="/' + panel + '"]');
    }
    if (navBtn) navBtn.classList.add('active');
```
This code is generic (it already looks up `.nav-item[href="/timeline"]` automatically once `panel === 'timeline'`, since it's driven by the `panel` variable, not a hardcoded name) — **no change needed here**, just confirm during Step 9's manual verification that it actually does mark the "ציר זמן" nav link active when landing on `/timeline` directly.

- [ ] **Step 10: Verify manually**

Start the app, log in. Then:
1. Click "ציר זמן" in the sidebar (the NEW top-level one, not inside the housing panel). Confirm it navigates to `/timeline`, which redirects to `/general/<month>?panel=timeline`, and the new panel shows a filter row ("הכל"/"משכנתא"/"כללי", "הכל" active by default) above the same timeline widget used by the housing panel (zoom buttons, minimize toggle, add-event button, vertical axis).
2. Confirm the new nav link is marked active (highlighted) when landing here.
3. Create a test event from this new page. Confirm via `curl http://localhost:5050/api/timeline/events?category=general` that it was tagged `'general'`.
4. Switch the filter to "משכנתא" — confirm only mortgage-tagged events show (your earlier housing test events, if any still exist, plus none of the "general" one you just created). Switch to "כללי" — confirm only the general event shows. Switch back to "הכל" — confirm both show together.
5. Go to the housing panel's "ציר זמן" sub-tab and confirm it STILL shows only mortgage events, with no filter UI, exactly as before this whole feature — i.e. confirm the general event you created does NOT appear there.
6. Reload the page directly at a URL like `/general/<month>?panel=timeline` (paste it straight into the address bar) and confirm the panel loads correctly and the nav link shows active, exercising the auto-open-from-URL path independently of clicking the sidebar link.
7. Test the full event lifecycle from the new page: view an event (click its marker), edit it, delete it, link a transaction with a note — all should work identically to how they already work on the housing timeline, since it's the same shared modal/engine.
8. No console errors anywhere in this walkthrough.
9. Clean up all test events created.

- [ ] **Step 11: Commit**

```bash
git add source/WebApp.py source/html/Base_template.html
git commit -m "$(cat <<'EOF'
feat(timeline): add a general (non-mortgage) events page

New sidebar nav item "ציר זמן" → /timeline → panel-timeline, reusing
the same timeline widget/modal engine as the housing panel's sub-tab
via the container-id/scope generalization from the previous commit.
Adds a 3-way category filter (all/mortgage/general) specific to this
new panel; the housing sub-tab remains unfiltered-UI, mortgage-only.
EOF
)"
```
Bump `/VERSION` (check current value first, increment by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```

---

### Task 5: End-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Full manual walkthrough**

Start the app fresh, log in. Walk through, in one session:
1. Housing panel's mortgage timeline: unaffected, mortgage-only, no filter UI — create, view, edit, delete, link a transaction.
2. New top-level timeline page: create a general event, confirm it's tagged `'general'` and does NOT show up on the housing timeline.
3. Filter toggle on the new page correctly narrows to each category and back to all.
4. An event created on one page and then viewed/edited from the SAME page where it's visible under the current filter works correctly (e.g., a mortgage event, viewed on the general page while "הכל" or "משכנתא" is selected, opens/edits/deletes correctly using the same shared modal).
5. Grep for duplicate route registration, per this project's standing pitfall (documented in CLAUDE.md):
```bash
grep -n "'/timeline'" source/WebApp.py source/routes/*.py
```
Expected: exactly one match, in `source/WebApp.py`, confirming no duplicate route conflict (and that the app started without a Flask `AssertionError`, confirmed implicitly by everything above having worked).
6. No console errors throughout.
7. Clean up all test data.

- [ ] **Step 2: Final commit**

If Step 1 surfaced any fixes, commit them individually (each with its own version bump). If nothing needed fixing, no commit is required for this task.
