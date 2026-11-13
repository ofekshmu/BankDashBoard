# Mortgage/Housing Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Timeline" sub-tab inside the housing/mortgage panel where the user can log dated events (optionally linked to one or more transactions with per-transaction notes) and browse them on a zoomable, pannable timeline.

**Architecture:** Two new Postgres tables (`TimelineEvents`, `TimelineEventTransactions`) behind five new Flask JSON routes, mirroring the existing Bills feature's data-access pattern in `database.py`/`WebApp.py`. The frontend is a custom vanilla-JS timeline widget added to `Base_template.html`, reusing the app's existing `/api/search/transactions` endpoint (with its `from`/`to` params) for the transaction-linking picker instead of building a new search endpoint.

**Tech Stack:** Flask, psycopg2 (raw SQL, no ORM), vanilla JS/CSS (no build step, matches existing `Base_template.html` housing panel code), Postgres (Neon).

**Note on verification:** This repository has no automated test suite (`pytest`, etc.) — Bills and other recent features were verified by running the Flask app locally and exercising the UI/API by hand. This plan follows that same convention: each task's verification step is a concrete manual check (a `python -c` snippet against the DB, a `curl` call, or a browser walkthrough), not a test run.

---

### Task 1: Database schema and CRUD methods

**Files:**
- Modify: `source/database.py` (add methods after `get_bill_suggestions_dismissed`, i.e. after the existing Bills section — search for `# ── Bills / Payment-tracking` to find the section boundary and insert a new `# ── Timeline events ─` section directly after the Bills section ends)

- [ ] **Step 1: Add `ensure_timeline_tables()`**

Insert this new section into `source/database.py` (place it right after the Bills section, i.e. after the last method of that section):

```python
    # ── Timeline events (housing panel) ─────────────────────────────────────

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
        c.execute("""
            SELECT
                l.ID, l.Event_ID, l.Transaction_Table, l.Transaction_ID, l.Note,
                CASE WHEN l.Transaction_Table='BankTransactions' THEN b.name
                     WHEN l.Transaction_Table='CardTransactions' THEN cc.name
                END AS tx_name,
                CASE WHEN l.Transaction_Table='BankTransactions' THEN CAST(b.date AS text)
                     WHEN l.Transaction_Table='CardTransactions' THEN CAST(cc.executed_date AS text)
                END AS tx_date,
                CASE WHEN l.Transaction_Table='BankTransactions' THEN (b.income - b.out)
                     WHEN l.Transaction_Table='CardTransactions' THEN cc.transaction_value
                END AS tx_amount
            FROM TimelineEventTransactions l
            LEFT JOIN BankTransactions b
                ON l.Transaction_Table='BankTransactions' AND l.Transaction_ID=b.id
            LEFT JOIN CardTransactions cc
                ON l.Transaction_Table='CardTransactions' AND l.Transaction_ID=cc.id
            ORDER BY l.ID ASC
        """)
        for r in c.fetchall():
            ev = events.get(r[1])
            if ev is None:
                continue
            ev['transactions'].append({
                'link_id': r[0],
                'transaction_table': r[2],
                'transaction_id': r[3],
                'note': r[4] or '',
                'tx_name': r[5],
                'tx_date': str(r[6])[:10] if r[6] else None,
                'tx_amount': float(r[7]) if r[7] is not None else None,
            })
        c.close()
        return [events[eid] for eid in order]

    def add_timeline_event(self, name: str, event_date: str, description: str = '', color: str = '#1e9d8b') -> int:
        row = self.cursor.execute("""
            INSERT INTO TimelineEvents (Name, Event_Date, Description, Color)
            VALUES (%s, %s, %s, %s) RETURNING ID
        """, (name, event_date, description or None, color)).fetchone()
        return row[0]

    def update_timeline_event(self, event_id: int, name: str, event_date: str, description: str = '', color: str = '#1e9d8b') -> None:
        self.cursor.execute("""
            UPDATE TimelineEvents SET Name=%s, Event_Date=%s, Description=%s, Color=%s
            WHERE ID=%s
        """, (name, event_date, description or None, color, event_id))

    def delete_timeline_event(self, event_id: int) -> None:
        self.cursor.execute("DELETE FROM TimelineEvents WHERE ID=%s", (event_id,))

    def add_timeline_link(self, event_id: int, transaction_table: str, transaction_id: int, note: str = '') -> int:
        row = self.cursor.execute("""
            INSERT INTO TimelineEventTransactions (Event_ID, Transaction_Table, Transaction_ID, Note)
            VALUES (%s, %s, %s, %s) RETURNING ID
        """, (event_id, transaction_table, transaction_id, note or None)).fetchone()
        return row[0]

    def update_timeline_link_note(self, link_id: int, note: str = '') -> None:
        self.cursor.execute(
            "UPDATE TimelineEventTransactions SET Note=%s WHERE ID=%s",
            (note or None, link_id)
        )

    def delete_timeline_link(self, link_id: int) -> None:
        self.cursor.execute("DELETE FROM TimelineEventTransactions WHERE ID=%s", (link_id,))
```

- [ ] **Step 2: Verify manually**

Run:
```bash
cd source
python -c "
from database import DataBase
db = DataBase()
db.ensure_timeline_tables()
eid = db.add_timeline_event('Test event', '2026-08-01', 'A description', '#3b82f6')
db.commit_changes()
print('created', eid)
events = db.get_timeline_events()
print(events)
lid = db.add_timeline_link(eid, 'BankTransactions', 1, 'test note')
db.commit_changes()
print(db.get_timeline_events())
db.delete_timeline_event(eid)
db.commit_changes()
print('after delete:', db.get_timeline_events())
"
```
Expected: prints the created event id, then the event (with empty `transactions`), then the event with one linked transaction entry containing `note: 'test note'`, then an empty list after delete (cascade removed the link too). If `BankTransactions` has no row with `id=1` in your local DB, the link's `tx_name`/`tx_date`/`tx_amount` will just be `None` — that's fine, it doesn't affect the pass/fail of this check.

- [ ] **Step 3: Commit**

```bash
git add source/database.py
git commit -m "$(cat <<'EOF'
feat(timeline): add TimelineEvents/TimelineEventTransactions tables and CRUD

Lays the data layer for the new mortgage-panel timeline feature,
following the same ensure_*_tables()/CRUD pattern used by Bills.
EOF
)"
```
Then bump `/VERSION` from `1.13.25` to `1.13.26` (edit the file directly, single line) and amend with a second commit:
```bash
git add VERSION
git commit -m "chore: bump version to 1.13.26"
```

---

### Task 2: Backend API routes

**Files:**
- Modify: `source/WebApp.py` (add routes after the Bills routes section — search for `@app.route('/api/bills/entries/<int:entry_id>'` and its handler, insert the new routes after that handler ends and before the next unrelated route)

- [ ] **Step 1: Add the timeline routes**

```python
# ── Timeline (housing panel) routes ─────────────────────────────────────────

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


@app.route('/api/timeline/events/<int:event_id>', methods=['PUT', 'DELETE'])
def api_timeline_event(event_id):
    from database import DataBase
    try:
        db = DataBase()
        db.ensure_timeline_tables()
        if request.method == 'PUT':
            body  = request.get_json(force=True) or {}
            name  = (body.get('name') or '').strip()
            date  = (body.get('event_date') or '').strip()
            color = (body.get('color') or '#1e9d8b').strip()
            desc  = (body.get('description') or '').strip()
            if not name:
                return jsonify({'ok': False, 'error': 'Name required'})
            if not date:
                return jsonify({'ok': False, 'error': 'Date required'})
            db.update_timeline_event(event_id, name, date, desc, color)
            db.commit_changes()
            return jsonify({'ok': True})
        db.delete_timeline_event(event_id)
        db.commit_changes()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/timeline/events/<int:event_id>/transactions', methods=['POST'])
def api_timeline_event_add_transaction(event_id):
    from database import DataBase
    try:
        db = DataBase()
        db.ensure_timeline_tables()
        body  = request.get_json(force=True) or {}
        table = (body.get('transaction_table') or '').strip()
        tx_id = body.get('transaction_id')
        note  = (body.get('note') or '').strip()
        if table not in ('BankTransactions', 'CardTransactions') or tx_id is None:
            return jsonify({'ok': False, 'error': 'Invalid transaction reference'})
        link_id = db.add_timeline_link(event_id, table, int(tx_id), note)
        db.commit_changes()
        return jsonify({'ok': True, 'link_id': link_id})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/timeline/events/<int:event_id>/transactions/<int:link_id>', methods=['PUT', 'DELETE'])
def api_timeline_event_transaction(event_id, link_id):
    from database import DataBase
    try:
        db = DataBase()
        if request.method == 'PUT':
            body = request.get_json(force=True) or {}
            db.update_timeline_link_note(link_id, (body.get('note') or '').strip())
            db.commit_changes()
            return jsonify({'ok': True})
        db.delete_timeline_link(link_id)
        db.commit_changes()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
```

- [ ] **Step 2: Verify manually**

Start the app (`python AppManager.py` per the project's standing run instruction, or `python WebApp.py` if that's how you normally run the dev server), then from another terminal:

```bash
curl -s -X POST http://localhost:5050/api/timeline/events \
  -H "Content-Type: application/json" \
  -d '{"name":"Curl test","event_date":"2026-08-01","description":"d","color":"#f59e0b"}'
```
Expected: `{"ok": true, "id": <some integer>}`.

```bash
curl -s http://localhost:5050/api/timeline/events
```
Expected: `{"ok": true, "events": [{"id": ..., "name": "Curl test", "event_date": "2026-08-01", "description": "d", "color": "#f59e0b", "transactions": []}]}`.

```bash
curl -s -X DELETE http://localhost:5050/api/timeline/events/<the id from above>
```
Expected: `{"ok": true}`, and a subsequent `GET /api/timeline/events` returns an empty `events` list.

- [ ] **Step 3: Commit**

```bash
git add source/WebApp.py
git commit -m "$(cat <<'EOF'
feat(timeline): add REST routes for timeline events and transaction links
EOF
)"
```
Bump `/VERSION` to `1.13.27` and commit:
```bash
git add VERSION
git commit -m "chore: bump version to 1.13.27"
```

---

### Task 3: Sub-tabs scaffold in the housing panel

**Files:**
- Modify: `source/html/Base_template.html`
  - CSS: insert a new rule block right after the existing housing CSS (after line ~899, i.e. right after the `#panel-housing .housing-2col-row .equity-bar-labels-4 { ... }` media-query block closes)
  - JS: modify the `_renderHousing` function (starts at line 7293) — change the final `panel.innerHTML = html;` assignment, and add tab-state variables + `_switchHousingTab()`

- [ ] **Step 1: Add sub-tab CSS**

Insert after the housing CSS block in the `<style>` section of `Base_template.html` (near the existing `#panel-housing` rules, e.g. right after the block ending with `#panel-housing .housing-2col-row .equity-bar-labels-4 { flex-direction: column; ... }` or wherever that mobile block closes — insert as a new top-level rule set, not nested):

```css
/* ── Housing panel sub-tabs ───────────────────────────────────── */
.hs-subtabs { display:flex; gap:8px; margin-bottom:14px; }
.hs-subtab-btn {
  padding:7px 16px; border-radius:20px; border:1.5px solid var(--border);
  background:var(--white); color:var(--text-sub); font-family:inherit;
  font-size:0.85em; font-weight:600; cursor:pointer; transition:all .12s;
}
.hs-subtab-btn:hover { border-color:var(--teal); color:var(--teal); }
.hs-subtab-btn.active { background:var(--teal); border-color:var(--teal); color:#fff; }
```

- [ ] **Step 2: Add tab-state variables**

In `Base_template.html`, right after the line `var _HS_CACHE_KEY = 'hs_v1';` (around line 7226), add:

```javascript
  var _housingActiveTab = 'overview';
  var _timelineEvents   = null;
```

- [ ] **Step 3: Wrap the overview HTML in a sub-tab container and add the switch function**

Find this line inside `_renderHousing` (around line 7514):

```javascript
    panel.innerHTML = html;
```

Replace it with:

```javascript
    panel.innerHTML =
      '<div class="hs-subtabs">' +
        '<button class="hs-subtab-btn active" id="hs-subtab-overview" onclick="_switchHousingTab(\'overview\')">סקירה כללית</button>' +
        '<button class="hs-subtab-btn" id="hs-subtab-timeline" onclick="_switchHousingTab(\'timeline\')">ציר זמן</button>' +
      '</div>' +
      '<div id="housing-overview">' + html + '</div>' +
      '<div id="housing-timeline" style="display:none"></div>';
```

Then find the closing of `_renderHousing` — the line that is just `  }` right after the Chart.js block (around line 7635, immediately before `// ── Main render orchestrator ───...` / `function _renderDynamicData`). Insert this line right before that closing `}`:

```javascript
    _switchHousingTab(_housingActiveTab, true);
```

So the end of the function reads (last few lines unchanged except the new line before the closing brace):

```javascript
        });
      }
    }

    _switchHousingTab(_housingActiveTab, true);
  }
```

Then, immediately after the closing `}` of `_renderHousing` (i.e. as a new top-level function right before `_renderDynamicData`), add:

```javascript
  // ── Housing panel sub-tabs ──────────────────────────────────────────────
  function _switchHousingTab(tab, skipFetch) {
    _housingActiveTab = tab;
    var ov  = document.getElementById('housing-overview');
    var tl  = document.getElementById('housing-timeline');
    var bOv = document.getElementById('hs-subtab-overview');
    var bTl = document.getElementById('hs-subtab-timeline');
    if (!ov || !tl) return;
    if (tab === 'timeline') {
      ov.style.display = 'none';
      tl.style.display = '';
      if (bOv) bOv.classList.remove('active');
      if (bTl) bTl.classList.add('active');
      if (!skipFetch || !_timelineEvents) {
        _loadTimelineTab();
      } else {
        _renderTimeline(_timelineEvents);
      }
    } else {
      tl.style.display = 'none';
      ov.style.display = '';
      if (bTl) bTl.classList.remove('active');
      if (bOv) bOv.classList.add('active');
    }
  }

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

  function _renderTimeline(events) {
    var tl = document.getElementById('housing-timeline');
    if (tl) tl.innerHTML = '<div class="tl-empty">ציר הזמן ייבנה במשימה הבאה</div>';
  }
```

(`_renderTimeline` is a temporary stub here — Task 4 replaces its body with the real widget. This keeps the app runnable and testable after this task.)

- [ ] **Step 4: Verify manually**

Start the app, open the site in a browser, navigate to the housing panel (sidebar → "דיור"). Confirm:
1. Two pill buttons ("סקירה כללית" / "ציר זמן") appear above the existing KPI cards.
2. The existing housing content (balance, equity bar, etc.) still renders exactly as before, now inside the "סקירה כללית" tab.
3. Clicking "ציר זמן" hides the overview and shows the placeholder text "ציר הזמן ייבנה במשימה הבאה".
4. Clicking back to "סקירה כללית" restores the overview content without a page reload.
5. No new console errors (`read_console_messages` if verifying via the Browser pane).

- [ ] **Step 5: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
feat(timeline): add sub-tab scaffold to the housing panel

Splits panel-housing into "Overview" (existing content) and a new
"Timeline" tab, toggled client-side without a new sidebar nav item.
EOF
)"
```
Bump `/VERSION` to `1.13.28` and commit:
```bash
git add VERSION
git commit -m "chore: bump version to 1.13.28"
```

---

### Task 4: Timeline axis widget (zoom, pan, ticks)

**Files:**
- Modify: `source/html/Base_template.html` (CSS additions near the sub-tab CSS from Task 3; replace the `_renderTimeline` stub body from Task 3; add `_tlDrawAxis`, `_tlZoom`, `_tlWireDrag`, `_tlDayMs` functions)

- [ ] **Step 1: Add timeline widget CSS**

Add directly after the `.hs-subtab-btn.active { ... }` rule from Task 3:

```css
/* ── Timeline widget ──────────────────────────────────────────── */
.tl-toolbar { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:10px; flex-wrap:wrap; }
.tl-toolbar-left { display:flex; align-items:center; gap:8px; }
.tl-zoom-btn {
  width:30px; height:30px; border-radius:8px; border:1.5px solid var(--border);
  background:var(--white); color:var(--navy); font-size:1.1em; font-weight:700;
  cursor:pointer; display:flex; align-items:center; justify-content:center;
}
.tl-zoom-btn:hover { border-color:var(--teal); color:var(--teal); }
.tl-add-btn {
  padding:7px 14px; border-radius:8px; border:none; background:var(--teal); color:#fff;
  font-family:inherit; font-size:0.85em; font-weight:700; cursor:pointer;
}
.tl-add-btn:hover { background:var(--teal-dark); }

.tl-axis-wrap {
  position:relative; overflow-x:auto; overflow-y:hidden; height:220px;
  border:1.5px solid var(--border); border-radius:10px; background:var(--white);
  cursor:grab;
}
.tl-axis-wrap.dragging { cursor:grabbing; user-select:none; }
.tl-axis-scroll { position:relative; height:100%; }
.tl-baseline { position:absolute; top:50%; right:0; left:0; height:2px; background:var(--border); }
.tl-tick { position:absolute; top:calc(50% - 4px); width:1px; height:8px; background:var(--text-muted); }
.tl-tick-label { position:absolute; top:calc(50% + 10px); font-size:0.72em; color:var(--text-muted); white-space:nowrap; transform:translateX(50%); }
.tl-empty { text-align:center; color:var(--text-muted); padding:60px 20px; }

@media (max-width:700px) {
  .tl-axis-wrap { height:170px; }
  .tl-tick-label { font-size:0.65em; }
}
```

- [ ] **Step 2: Replace the `_renderTimeline` stub and add the axis-drawing functions**

Replace the Task-3 stub:

```javascript
  function _renderTimeline(events) {
    var tl = document.getElementById('housing-timeline');
    if (tl) tl.innerHTML = '<div class="tl-empty">ציר הזמן ייבנה במשימה הבאה</div>';
  }
```

with:

```javascript
  var _tlPxPerDay = 6;

  function _tlDayMs() { return 24 * 60 * 60 * 1000; }

  function _renderTimeline(events) {
    var tl = document.getElementById('housing-timeline');
    if (!tl) return;
    tl.innerHTML =
      '<div class="tl-toolbar">' +
        '<div class="tl-toolbar-left">' +
          '<button class="tl-zoom-btn" onclick="_tlZoom(1.4)">+</button>' +
          '<button class="tl-zoom-btn" onclick="_tlZoom(0.714)">−</button>' +
        '</div>' +
        '<button class="tl-add-btn" onclick="alert(\'ייווסף במשימה 6\')">+ הוסף אירוע</button>' +
      '</div>' +
      '<div class="tl-axis-wrap" id="tl-axis-wrap">' +
        '<div class="tl-axis-scroll" id="tl-axis-scroll"></div>' +
      '</div>';
    _tlDrawAxis(events);
    _tlWireDrag();
  }

  function _tlZoom(factor) {
    _tlPxPerDay = Math.max(1.5, Math.min(80, _tlPxPerDay * factor));
    _tlDrawAxis(_timelineEvents || []);
  }

  function _tlDrawAxis(events) {
    var scroll = document.getElementById('tl-axis-scroll');
    if (!scroll) return;

    var today = new Date();
    var dates = (events || [])
      .map(function(e) { return new Date(e.event_date); })
      .filter(function(d) { return !isNaN(d); });
    dates.push(today);
    var minD = new Date(Math.min.apply(null, dates.map(function(d) { return d.getTime(); })));
    var maxD = new Date(Math.max.apply(null, dates.map(function(d) { return d.getTime(); })));
    minD = new Date(minD.getTime() - 30 * _tlDayMs());
    maxD = new Date(maxD.getTime() + 30 * _tlDayMs());

    var totalDays = Math.max(1, Math.round((maxD - minD) / _tlDayMs()));
    var widthPx = totalDays * _tlPxPerDay;
    scroll.style.width = widthPx + 'px';

    var html = '<div class="tl-baseline"></div>';
    var cursor = new Date(minD.getFullYear(), minD.getMonth(), 1);
    while (cursor <= maxD) {
      var offsetDays = (cursor - minD) / _tlDayMs();
      var rightPx = offsetDays * _tlPxPerDay;
      html += '<div class="tl-tick" style="right:' + rightPx + 'px"></div>';
      html += '<div class="tl-tick-label" style="right:' + rightPx + 'px">' +
        (cursor.getMonth() + 1) + '/' + cursor.getFullYear() + '</div>';
      cursor = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
    }
    scroll.innerHTML = html;
  }

  function _tlWireDrag() {
    var wrap = document.getElementById('tl-axis-wrap');
    if (!wrap) return;
    var isDown = false, startX = 0, startScroll = 0;
    wrap.addEventListener('mousedown', function(e) {
      isDown = true;
      wrap.classList.add('dragging');
      startX = e.pageX;
      startScroll = wrap.scrollLeft;
    });
    window.addEventListener('mouseup', function() {
      isDown = false;
      wrap.classList.remove('dragging');
    });
    window.addEventListener('mousemove', function(e) {
      if (!isDown) return;
      wrap.scrollLeft = startScroll - (e.pageX - startX);
    });
    wrap.addEventListener('wheel', function(e) {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        wrap.scrollLeft += e.deltaY;
        e.preventDefault();
      }
    }, { passive: false });
  }
```

- [ ] **Step 3: Verify manually**

Start the app, open the housing panel, click "ציר זמן". Confirm:
1. A bordered horizontal box appears with month/year tick labels (e.g. "8/2026") spaced along it.
2. Clicking `+` a few times visibly spaces the tick labels further apart (zoom in); clicking `−` compresses them (zoom out).
3. Dragging left/right inside the box with the mouse pans the tick labels; scrolling the mouse wheel over the box also pans it.
4. On a narrow viewport (resize to ~375px wide or use `resize_window` in the Browser pane), the box is shorter (170px) and tick labels are smaller.

- [ ] **Step 4: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
feat(timeline): add zoomable/pannable timeline axis widget
EOF
)"
```
Bump `/VERSION` to `1.13.29` and commit:
```bash
git add VERSION
git commit -m "chore: bump version to 1.13.29"
```

---

### Task 5: Event markers, speech bubbles, minimize/hover toggle, click-to-add

**Files:**
- Modify: `source/html/Base_template.html` (CSS additions; extend `_tlDrawAxis` to render markers and wire an empty-space click handler; add `_tlToggleMinimize`)

- [ ] **Step 1: Add marker/bubble CSS**

Add after the `@media (max-width:700px)` block from Task 4:

```css
.tl-toggle-wrap { display:flex; align-items:center; gap:7px; font-size:0.8em; color:var(--text-sub); }
.tl-switch { position:relative; width:36px; height:20px; border-radius:12px; background:var(--border); cursor:pointer; transition:background .15s; flex-shrink:0; }
.tl-switch.on { background:var(--teal); }
.tl-switch-knob { position:absolute; top:2px; right:2px; width:16px; height:16px; border-radius:50%; background:#fff; transition:right .15s; box-shadow:0 1px 2px rgba(0,0,0,.2); }
.tl-switch.on .tl-switch-knob { right:18px; }

.tl-marker { position:absolute; top:50%; transform:translate(50%, -50%); }
.tl-dot { width:10px; height:10px; border-radius:50%; border:2px solid #fff; box-shadow:0 0 0 1px rgba(0,0,0,.15); cursor:pointer; }
.tl-bubble {
  position:absolute; bottom:16px; right:50%; transform:translateX(50%);
  min-width:70px; max-width:180px; padding:6px 10px; border-radius:9px; color:#fff;
  font-size:0.76em; font-weight:600; cursor:pointer; box-shadow:var(--shadow-md);
  transition:opacity .12s, transform .12s;
  background:var(--bubble-color, var(--teal));
}
.tl-bubble::after {
  content:''; position:absolute; top:100%; right:50%; transform:translateX(50%);
  border:5px solid transparent; border-top-color:var(--bubble-color, var(--teal));
}
.tl-bubble-date { font-weight:400; opacity:.85; font-size:0.9em; }
.tl-axis-wrap.tl-minimize-mode .tl-marker:not(:hover) .tl-bubble { opacity:0; pointer-events:none; transform:translateX(50%) scale(.6); }
.tl-axis-wrap.tl-minimize-mode .tl-marker:not(:hover) .tl-dot { width:8px; height:8px; }
.tl-axis-wrap.tl-minimize-mode .tl-marker:hover .tl-dot { width:12px; height:12px; }

@media (max-width:700px) {
  .tl-bubble { font-size:0.7em; max-width:130px; }
}
```

- [ ] **Step 2: Add the minimize-toggle switch to the toolbar**

In `_renderTimeline` (Task 4), change:

```javascript
      '<div class="tl-toolbar">' +
        '<div class="tl-toolbar-left">' +
          '<button class="tl-zoom-btn" onclick="_tlZoom(1.4)">+</button>' +
          '<button class="tl-zoom-btn" onclick="_tlZoom(0.714)">−</button>' +
        '</div>' +
        '<button class="tl-add-btn" onclick="alert(\'ייווסף במשימה 6\')">+ הוסף אירוע</button>' +
      '</div>' +
      '<div class="tl-axis-wrap" id="tl-axis-wrap">' +
```

to:

```javascript
      '<div class="tl-toolbar">' +
        '<div class="tl-toolbar-left">' +
          '<button class="tl-zoom-btn" onclick="_tlZoom(1.4)">+</button>' +
          '<button class="tl-zoom-btn" onclick="_tlZoom(0.714)">−</button>' +
          '<div class="tl-toggle-wrap">' +
            '<span>הצג תמיד</span>' +
            '<div class="tl-switch' + (_tlMinimizeMode ? ' on' : '') + '" id="tl-minimize-switch" onclick="_tlToggleMinimize()"><div class="tl-switch-knob"></div></div>' +
            '<span>הקטן בריחוף</span>' +
          '</div>' +
        '</div>' +
        '<button class="tl-add-btn" onclick="alert(\'ייווסף במשימה 6\')">+ הוסף אירוע</button>' +
      '</div>' +
      '<div class="tl-axis-wrap' + (_tlMinimizeMode ? ' tl-minimize-mode' : '') + '" id="tl-axis-wrap">' +
```

Add the state variable next to `var _tlPxPerDay = 6;` (Task 4):

```javascript
  var _tlMinimizeMode = (localStorage.getItem('tl_minimize_mode') !== '0');
```

Add the toggle function next to `_tlZoom`:

```javascript
  function _tlToggleMinimize() {
    _tlMinimizeMode = !_tlMinimizeMode;
    localStorage.setItem('tl_minimize_mode', _tlMinimizeMode ? '1' : '0');
    var sw = document.getElementById('tl-minimize-switch');
    var wrap = document.getElementById('tl-axis-wrap');
    if (sw) sw.classList.toggle('on', _tlMinimizeMode);
    if (wrap) wrap.classList.toggle('tl-minimize-mode', _tlMinimizeMode);
  }
```

- [ ] **Step 3: Render markers and wire the empty-space click handler**

In `_tlDrawAxis` (Task 4), replace this line:

```javascript
    scroll.innerHTML = html;
```

with:

```javascript
    var columns = {};
    (events || []).forEach(function(ev) {
      var d = new Date(ev.event_date);
      if (isNaN(d)) return;
      var offsetDays = (d - minD) / _tlDayMs();
      var rightPx = Math.round(offsetDays * _tlPxPerDay);
      var col = Math.round(rightPx / 24);
      if (!columns[col]) columns[col] = [];
      columns[col].push({ ev: ev, rightPx: rightPx });
    });
    Object.keys(columns).forEach(function(col) {
      columns[col].forEach(function(item, stackIdx) {
        var ev = item.ev;
        var bubbleBottom = 16 + stackIdx * 46;
        html +=
          '<div class="tl-marker" style="right:' + item.rightPx + 'px" onclick="_tlOpenEditModal(' + ev.id + ')">' +
            '<div class="tl-dot" style="background:' + ev.color + '"></div>' +
            '<div class="tl-bubble" style="--bubble-color:' + ev.color + ';bottom:' + bubbleBottom + 'px">' +
              _esc(ev.name) + '<div class="tl-bubble-date">' + ev.event_date + '</div>' +
            '</div>' +
          '</div>';
      });
    });

    scroll.innerHTML = html || '<div class="tl-empty">אין אירועים עדיין — לחצו על "הוסף אירוע"</div>';

    scroll.onclick = function(e) {
      if (e.target.closest('.tl-marker')) return;
      var rect = scroll.getBoundingClientRect();
      var xFromRight = rect.right - e.clientX;
      var days = Math.round(xFromRight / _tlPxPerDay);
      var clickedDate = new Date(minD.getTime() + days * _tlDayMs());
      if (isNaN(clickedDate)) return;
      _tlOpenAddModal(clickedDate.toISOString().slice(0, 10));
    };
```

(`_tlOpenEditModal` and `_tlOpenAddModal` are added in Task 6 — until then, clicking a marker or empty space will throw a harmless "not defined" console error; this is expected and resolved by the next task.)

- [ ] **Step 4: Verify manually**

Start the app, add a test event directly via `curl` (as in Task 2's verification) with today's date, then reload the housing panel's Timeline tab. Confirm:
1. A colored dot appears on the baseline with a speech-bubble above it showing the event's name and date.
2. Toggling the "הצג תמיד / הקטן בריחוף" switch: in "הקטן בריחוף" (minimize) mode, the bubble disappears and the dot shrinks when the mouse is not over the marker, and the bubble reappears (dot grows) on hover. In "הצג תמיד" mode, the bubble is always visible.
3. Reloading the page preserves the toggle's last state (backed by `localStorage`).
4. Clicking on an empty part of the timeline (not a marker) currently throws a console error about `_tlOpenAddModal is not defined` — expected at this point, resolved in Task 6.
5. Delete the test event via `curl -X DELETE` afterward to leave the DB clean.

- [ ] **Step 5: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
feat(timeline): render event markers/speech bubbles with hover minimize toggle
EOF
)"
```
Bump `/VERSION` to `1.13.30` and commit:
```bash
git add VERSION
git commit -m "chore: bump version to 1.13.30"
```

---

### Task 6: Add/Edit event modal (name, date, description, color, delete)

**Files:**
- Modify: `source/html/Base_template.html` (CSS additions; add modal-building and CRUD-wiring JS functions)

- [ ] **Step 1: Add modal CSS**

Add after the Task 5 CSS:

```css
/* ── Timeline event modal ─────────────────────────────────────── */
.tl-overlay { position:fixed; inset:0; background:rgba(15,22,45,.45); z-index:700; display:flex; align-items:center; justify-content:center; }
.tl-overlay.hidden { display:none; }
.tl-modal {
  background:var(--white); border-radius:var(--radius); box-shadow:var(--shadow-md);
  width:min(480px, 94vw); max-height:90vh; overflow-y:auto; padding:20px 22px 18px;
  display:flex; flex-direction:column; gap:13px; position:relative;
}
.tl-modal-close { position:absolute; top:12px; left:14px; background:none; border:none; font-size:1.15em; cursor:pointer; color:var(--text-muted); }
.tl-modal-close:hover { color:var(--red); }
.tl-modal-title { font-size:1em; font-weight:700; padding-left:18px; }
.tl-field { display:flex; flex-direction:column; gap:4px; }
.tl-field label { font-size:0.78em; font-weight:600; color:var(--text-sub); }
.tl-field input, .tl-field textarea {
  padding:7px 10px; border:1.5px solid var(--border); border-radius:7px;
  font-size:0.87em; font-family:inherit; color:var(--navy); background:var(--white);
}
.tl-field input:focus, .tl-field textarea:focus { outline:none; border-color:var(--teal); }
.tl-field textarea { resize:vertical; min-height:56px; }
.tl-color-row { display:flex; gap:6px; flex-wrap:wrap; }
.tl-c-opt { width:22px; height:22px; border-radius:50%; border:2.5px solid transparent; cursor:pointer; transition:transform .1s; }
.tl-c-opt:hover { transform:scale(1.15); }
.tl-c-opt.sel { border-color:var(--navy); }
.tl-btn {
  padding:8px 16px; border-radius:8px; border:1.5px solid var(--border);
  background:var(--white); color:var(--text-sub); font-family:inherit;
  font-size:0.85em; font-weight:600; cursor:pointer;
}
.tl-btn:hover { border-color:var(--teal); color:var(--teal); }
.tl-btn-primary { background:var(--teal); border-color:var(--teal); color:#fff; }
.tl-btn-primary:hover { background:var(--teal-dark); color:#fff; }
.tl-btn-danger { color:var(--red); border-color:transparent; background:none; }
.tl-btn-danger:hover { text-decoration:underline; }
.tl-modal-actions { display:flex; gap:8px; justify-content:space-between; margin-top:2px; }
.tl-modal-actions-right { display:flex; gap:8px; }
.tl-status { font-size:0.8em; min-height:1em; }
.tl-status.err { color:var(--red); }
```

- [ ] **Step 2: Add modal state, build, open, color-select and close functions**

Add these as new top-level functions/variables, placed after `_tlWireDrag` (Task 4):

```javascript
  var TL_COLORS = ['#1e9d8b','#3b82f6','#f59e0b','#ef4444','#10b981',
                    '#8b5cf6','#f97316','#06b6d4','#e879f9','#84cc16'];
  var _tlModalMode     = 'add';
  var _tlEditingId     = null;
  var _tlSelectedColor = TL_COLORS[0];
  var _tlPendingLinks  = [];

  function _tlBuildModal() {
    if (document.getElementById('tl-overlay')) {
      _tlRenderColorRow();
      return;
    }
    var div = document.createElement('div');
    div.className = 'tl-overlay hidden';
    div.id = 'tl-overlay';
    div.innerHTML =
      '<div class="tl-modal">' +
        '<button class="tl-modal-close" onclick="_tlCloseModal()">✕</button>' +
        '<h2 class="tl-modal-title" id="tl-modal-title">הוסף אירוע</h2>' +
        '<div class="tl-field"><label>שם האירוע</label><input id="tl-name-inp" type="text" maxlength="80" placeholder="למשל: תשלום מקדמה"></div>' +
        '<div class="tl-field"><label>תאריך</label><input id="tl-date-inp" type="date"></div>' +
        '<div class="tl-field"><label>תיאור (אופציונלי)</label><textarea id="tl-desc-inp" placeholder="פרטים נוספים…"></textarea></div>' +
        '<div class="tl-field"><label>צבע</label><div class="tl-color-row" id="tl-color-row"></div></div>' +
        '<div class="tl-status" id="tl-status"></div>' +
        '<div class="tl-modal-actions">' +
          '<button class="tl-btn tl-btn-danger" onclick="_tlDeleteEvent()" id="tl-delete-btn" style="display:none">מחק אירוע</button>' +
          '<div class="tl-modal-actions-right">' +
            '<button class="tl-btn" onclick="_tlCloseModal()">ביטול</button>' +
            '<button class="tl-btn tl-btn-primary" onclick="_tlSubmitEvent()">שמור</button>' +
          '</div>' +
        '</div>' +
      '</div>';
    document.body.appendChild(div);
    _tlRenderColorRow();
  }

  function _tlRenderColorRow() {
    var row = document.getElementById('tl-color-row');
    if (!row) return;
    row.innerHTML = TL_COLORS.map(function(c) {
      return '<div class="tl-c-opt' + (c === _tlSelectedColor ? ' sel' : '') + '" style="background:' + c + '" data-color="' + c + '" onclick="_tlSelectColor(this)"></div>';
    }).join('');
  }

  function _tlSelectColor(el) {
    document.querySelectorAll('#tl-color-row .tl-c-opt').forEach(function(e) { e.classList.remove('sel'); });
    el.classList.add('sel');
    _tlSelectedColor = el.dataset.color;
  }

  function _tlCloseModal() {
    var ov = document.getElementById('tl-overlay');
    if (ov) ov.classList.add('hidden');
  }

  function _tlOpenAddModal(prefillDate) {
    _tlModalMode = 'add';
    _tlEditingId = null;
    _tlPendingLinks = [];
    _tlSelectedColor = TL_COLORS[0];
    _tlBuildModal();
    document.getElementById('tl-name-inp').value = '';
    document.getElementById('tl-date-inp').value = prefillDate || new Date().toISOString().slice(0, 10);
    document.getElementById('tl-desc-inp').value = '';
    document.getElementById('tl-modal-title').textContent = 'הוסף אירוע';
    document.getElementById('tl-delete-btn').style.display = 'none';
    document.getElementById('tl-status').textContent = '';
    document.getElementById('tl-overlay').classList.remove('hidden');
    setTimeout(function() {
      var inp = document.getElementById('tl-name-inp');
      if (inp) inp.focus();
    }, 60);
  }

  function _tlOpenEditModal(eventId) {
    var ev = (_timelineEvents || []).find(function(e) { return e.id === eventId; });
    if (!ev) return;
    _tlModalMode = 'edit';
    _tlEditingId = eventId;
    _tlSelectedColor = ev.color;
    _tlPendingLinks = (ev.transactions || []).map(function(t) {
      return {
        link_id: t.link_id, transaction_table: t.transaction_table, transaction_id: t.transaction_id,
        note: t.note, tx_name: t.tx_name, tx_date: t.tx_date, tx_amount: t.tx_amount,
      };
    });
    _tlBuildModal();
    document.getElementById('tl-name-inp').value = ev.name;
    document.getElementById('tl-date-inp').value = ev.event_date;
    document.getElementById('tl-desc-inp').value = ev.description || '';
    document.getElementById('tl-modal-title').textContent = 'ערוך אירוע';
    document.getElementById('tl-delete-btn').style.display = '';
    document.getElementById('tl-status').textContent = '';
    document.getElementById('tl-overlay').classList.remove('hidden');
  }

  async function _tlSubmitEvent() {
    var name = document.getElementById('tl-name-inp').value.trim();
    var date = document.getElementById('tl-date-inp').value;
    var desc = document.getElementById('tl-desc-inp').value.trim();
    var st = document.getElementById('tl-status');
    st.className = 'tl-status';
    if (!name) { st.className = 'tl-status err'; st.textContent = 'נא להזין שם אירוע'; return; }
    if (!date) { st.className = 'tl-status err'; st.textContent = 'נא לבחור תאריך'; return; }

    var body = { name: name, event_date: date, description: desc, color: _tlSelectedColor };
    var url = '/api/timeline/events';
    var method = 'POST';
    if (_tlModalMode === 'edit') { url += '/' + _tlEditingId; method = 'PUT'; }

    var resp = await fetch(url, { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    var r = await resp.json();
    if (!r.ok) { st.className = 'tl-status err'; st.textContent = r.error || 'שגיאה'; return; }

    _tlCloseModal();
    await _loadTimelineTab();
  }

  async function _tlDeleteEvent() {
    if (!_tlEditingId) return;
    if (!confirm('למחוק את האירוע? הפעולה לא הפיכה.')) return;
    await fetch('/api/timeline/events/' + _tlEditingId, { method: 'DELETE' });
    _tlCloseModal();
    await _loadTimelineTab();
  }
```

- [ ] **Step 3: Wire the "Add event" button**

In `_renderTimeline` (Task 5), replace:

```javascript
        '<button class="tl-add-btn" onclick="alert(\'ייווסף במשימה 6\')">+ הוסף אירוע</button>' +
```

with:

```javascript
        '<button class="tl-add-btn" onclick="_tlOpenAddModal(null)">+ הוסף אירוע</button>' +
```

- [ ] **Step 4: Verify manually**

Start the app, open the housing panel's Timeline tab. Confirm:
1. Clicking "+ הוסף אירוע" opens a modal with name/date/description fields and a row of 10 color swatches (first one pre-selected).
2. Clicking a different swatch selects it (visible ring around it) and deselects the previous one.
3. Submitting with an empty name shows the inline error "נא להזין שם אירוע" and does not close the modal.
4. Submitting with a name and date closes the modal and the new event appears as a marker on the timeline with the chosen color.
5. Clicking an existing marker (or clicking empty timeline space) opens the modal pre-filled with that event's data, title "ערוך אירוע", and a visible "מחק אירוע" button; editing the name/date/color and saving updates the marker; clicking "מחק אירוע" (after confirming the browser `confirm()` dialog) removes the marker.
6. Clicking empty space on the timeline opens the "add" modal with the date field pre-filled to the date under the click.

- [ ] **Step 5: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
feat(timeline): add/edit/delete event modal with color picker
EOF
)"
```
Bump `/VERSION` to `1.13.31` and commit:
```bash
git add VERSION
git commit -m "chore: bump version to 1.13.31"
```

---

### Task 7: Transaction linking (search, add, per-transaction note, remove)

**Files:**
- Modify: `source/html/Base_template.html` (CSS additions; add a transaction-search field + link list to the modal; add search/select/remove/note-edit functions; extend `_tlSubmitEvent` to sync links)

- [ ] **Step 1: Add transaction-linking CSS**

Add after the Task 6 CSS:

```css
.tl-link-list { display:flex; flex-direction:column; gap:6px; margin-top:6px; }
.tl-link-row-wrap { display:flex; flex-direction:column; gap:4px; }
.tl-link-row { display:flex; align-items:center; gap:8px; padding:6px 9px; background:var(--teal-light); border-radius:7px; font-size:0.8em; }
.tl-link-row-name { font-weight:600; flex:1; }
.tl-link-row-date { color:var(--text-muted); flex-shrink:0; }
.tl-link-remove { background:none; border:none; color:var(--text-muted); cursor:pointer; flex-shrink:0; font-size:1em; }
.tl-link-remove:hover { color:var(--red); }
.tl-link-row-note {
  width:100%; padding:5px 8px; border:1px solid var(--border); border-radius:6px;
  font-size:0.85em; font-family:inherit; box-sizing:border-box;
}
.tl-tx-search-results { max-height:180px; overflow-y:auto; border:1.5px solid var(--teal); border-radius:8px; margin-top:4px; }
.tl-tx-search-results.hidden { display:none; }
.tl-tx-search-row { padding:7px 10px; cursor:pointer; display:flex; gap:10px; font-size:0.82em; border-bottom:1px solid var(--border); }
.tl-tx-search-row:last-child { border-bottom:none; }
.tl-tx-search-row:hover { background:var(--teal-light); }
```

- [ ] **Step 2: Add the linking UI to the modal markup**

In `_tlBuildModal` (Task 6), insert this new field block right before the `<div class="tl-status" ...>` line:

```javascript
        '<div class="tl-field">' +
          '<label>קשר עסקאות (אופציונלי)</label>' +
          '<input id="tl-tx-search-inp" type="text" placeholder="חפש עסקה בסביבת התאריך…" oninput="_tlSearchTx(this.value)">' +
          '<div class="tl-tx-search-results hidden" id="tl-tx-search-results"></div>' +
          '<div class="tl-link-list" id="tl-link-list"></div>' +
        '</div>' +
```

- [ ] **Step 3: Render the pending-links list whenever the modal opens**

In `_tlOpenAddModal`, add this line right before `document.getElementById('tl-overlay').classList.remove('hidden');`:

```javascript
    _tlRenderLinkList();
```

In `_tlOpenEditModal`, add the same line right before its `document.getElementById('tl-overlay').classList.remove('hidden');`:

```javascript
    _tlRenderLinkList();
```

- [ ] **Step 4: Add the link-list render, search, select, remove, note-edit functions**

Add after `_tlDeleteEvent` (Task 6):

```javascript
  var _tlTxSearchTimer = null;
  var _tlLastSearchResults = [];

  function _tlRenderLinkList() {
    var list = document.getElementById('tl-link-list');
    if (!list) return;
    if (!_tlPendingLinks.length) { list.innerHTML = ''; return; }
    list.innerHTML = _tlPendingLinks.map(function(l, idx) {
      return '<div class="tl-link-row-wrap">' +
        '<div class="tl-link-row">' +
          '<span class="tl-link-row-name">' + _esc(l.tx_name || '') + '</span>' +
          '<span class="tl-link-row-date">' + (l.tx_date || '') + '</span>' +
          '<button class="tl-link-remove" onclick="_tlRemoveLink(' + idx + ')">✕</button>' +
        '</div>' +
        '<input class="tl-link-row-note" placeholder="הערה על העסקה הזו…" value="' + _esc(l.note || '') + '" oninput="_tlUpdateLinkNote(' + idx + ',this.value)">' +
      '</div>';
    }).join('');
  }

  function _tlUpdateLinkNote(idx, val) {
    if (_tlPendingLinks[idx]) _tlPendingLinks[idx].note = val;
  }

  function _tlRemoveLink(idx) {
    _tlPendingLinks.splice(idx, 1);
    _tlRenderLinkList();
  }

  function _tlSearchTx(val) {
    clearTimeout(_tlTxSearchTimer);
    var q = val.trim();
    var box = document.getElementById('tl-tx-search-results');
    if (!q) { box.classList.add('hidden'); return; }
    _tlTxSearchTimer = setTimeout(function() { _tlDoSearchTx(q); }, 250);
  }

  async function _tlDoSearchTx(q) {
    var dateInp = document.getElementById('tl-date-inp');
    var centerDate = dateInp && dateInp.value ? new Date(dateInp.value) : new Date();
    var from = new Date(centerDate.getTime() - 30 * _tlDayMs());
    var to = new Date(centerDate.getTime() + 30 * _tlDayMs());
    var url = '/api/search/transactions?keyword=' + encodeURIComponent(q) +
      '&from=' + from.toISOString().slice(0, 10) + '&to=' + to.toISOString().slice(0, 10);
    try {
      var r = await fetch(url);
      var d = await r.json();
      _tlShowTxResults(d.results || []);
    } catch (e) {
      _tlShowTxResults([]);
    }
  }

  function _tlShowTxResults(items) {
    var box = document.getElementById('tl-tx-search-results');
    var already = _tlPendingLinks.map(function(l) { return l.transaction_table + ':' + l.transaction_id; });
    items = items.filter(function(it) {
      var table = it.source === 'card' ? 'CardTransactions' : 'BankTransactions';
      return already.indexOf(table + ':' + it.tx_id) === -1;
    });
    _tlLastSearchResults = items;
    if (!items.length) { box.classList.add('hidden'); return; }
    box.classList.remove('hidden');
    box.innerHTML = items.slice(0, 30).map(function(it, i) {
      return '<div class="tl-tx-search-row" onclick="_tlSelectTx(' + i + ')">' +
        '<span>' + it.date + '</span>' +
        '<span style="flex:1;font-weight:600">' + _esc(it.name) + '</span>' +
        '<span>₪' + Math.abs(it.amount).toLocaleString('he-IL', { maximumFractionDigits: 0 }) + '</span>' +
      '</div>';
    }).join('');
  }

  function _tlSelectTx(idx) {
    var it = _tlLastSearchResults[idx];
    if (!it) return;
    _tlPendingLinks.push({
      transaction_table: it.source === 'card' ? 'CardTransactions' : 'BankTransactions',
      transaction_id: it.tx_id, note: '', tx_name: it.name, tx_date: it.date, tx_amount: it.amount,
    });
    document.getElementById('tl-tx-search-inp').value = '';
    document.getElementById('tl-tx-search-results').classList.add('hidden');
    _tlRenderLinkList();
  }
```

- [ ] **Step 5: Sync links when the event is saved**

In `_tlSubmitEvent` (Task 6), replace:

```javascript
    _tlCloseModal();
    await _loadTimelineTab();
  }
```

(the version at the end of `_tlSubmitEvent`) with:

```javascript
    var eventId = _tlModalMode === 'edit' ? _tlEditingId : r.id;
    var existing = _tlModalMode === 'edit'
      ? ((_timelineEvents || []).find(function(e) { return e.id === eventId; }) || {}).transactions || []
      : [];
    var keptLinkIds = _tlPendingLinks.filter(function(l) { return l.link_id; }).map(function(l) { return l.link_id; });

    for (var i = 0; i < existing.length; i++) {
      if (keptLinkIds.indexOf(existing[i].link_id) === -1) {
        await fetch('/api/timeline/events/' + eventId + '/transactions/' + existing[i].link_id, { method: 'DELETE' });
      }
    }
    for (var j = 0; j < _tlPendingLinks.length; j++) {
      var l = _tlPendingLinks[j];
      if (l.link_id) {
        var orig = existing.find(function(e) { return e.link_id === l.link_id; });
        if (orig && (orig.note || '') !== (l.note || '')) {
          await fetch('/api/timeline/events/' + eventId + '/transactions/' + l.link_id, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note: l.note }),
          });
        }
        continue;
      }
      await fetch('/api/timeline/events/' + eventId + '/transactions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transaction_table: l.transaction_table, transaction_id: l.transaction_id, note: l.note }),
      });
    }

    _tlCloseModal();
    await _loadTimelineTab();
  }
```

- [ ] **Step 6: Verify manually**

Start the app, open the housing panel's Timeline tab, open "+ הוסף אירוע", set a date that falls within ±30 days of at least one real transaction in your DB. Confirm:
1. Typing a few characters of a known transaction name into "קשר עסקאות" shows a dropdown of matching transactions from that ±30-day window (verify it does *not* show matches far outside that window by trying a keyword that also matches an old transaction).
2. Clicking a result adds it to a list below the search box, showing its name/date and a note input; the same transaction no longer appears in a subsequent search (already-linked filtering).
3. Typing into the per-transaction note field and saving the event, then reopening it for edit, shows the note text was persisted.
4. Removing a linked transaction (✕) before saving excludes it from the saved event.
5. Editing an existing event that already has linked transactions: the link list is pre-populated; adding a new link, removing an old one, and changing a note, then saving, correctly reflects all three changes on reload (verify via `curl http://localhost:5050/api/timeline/events` showing the final `transactions` array).

- [ ] **Step 7: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
feat(timeline): link events to transactions with per-transaction notes
EOF
)"
```
Bump `/VERSION` to `1.13.32` and commit:
```bash
git add VERSION
git commit -m "chore: bump version to 1.13.32"
```

---

### Task 8: End-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Full manual walkthrough**

Start the app fresh (`python AppManager.py`), open the housing panel in a browser:
1. Confirm the "סקירה כללית"/"ציר זמן" sub-tabs appear and the existing overview KPIs are unaffected (compare against the panel's appearance before this feature was added, e.g. on `main`).
2. Create two events on the same date (or within a few pixels of each other at low zoom) and confirm their bubbles stack vertically instead of overlapping.
3. Create an event with a linked transaction, reload the whole page (hard refresh), switch to the Timeline tab, and confirm the event and its linked transaction/note both persisted (i.e. came back from the database, not just client memory).
4. Resize to a mobile width (375px) and confirm the timeline remains usable: axis is shorter, bubbles are smaller, add/edit modal still fits the viewport and is scrollable if needed.
5. Delete all test events created during this walkthrough so the DB is left clean.
6. Check the browser console for JS errors throughout (`read_console_messages` if using the Browser pane) — expect none.

- [ ] **Step 2: Confirm no duplicate Flask routes**

Per this project's standing pitfall about duplicate route registration, run:

```bash
grep -n "api/timeline" source/WebApp.py source/routes/*.py
```

Expected: every `/api/timeline/...` route path appears exactly once across both locations (no duplicate `@app.route` registrations that would raise `AssertionError` on startup — confirmed implicitly by the fact the app started successfully in Step 1).

- [ ] **Step 3: Final commit**

If Step 1 surfaced any fixes, commit them individually (each with its own version bump, following the same pattern as Tasks 1–7). If nothing needed fixing, no commit is required for this task.
