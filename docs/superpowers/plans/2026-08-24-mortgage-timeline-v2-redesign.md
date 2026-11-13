# Mortgage Timeline — Vertical Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the existing horizontal timeline widget (housing panel, Timeline sub-tab) into a vertical timeline — newest at top, oldest at bottom — with density-balanced alternating left/right event placement, native wheel/touch scrolling, bolder visual weight, jagged yearly divider lines, a custom modern date picker in the add/edit modal, collision-safe same-date stacking, and clearance from the fixed hamburger menu button.

**Architecture:** All changes are in `source/html/Base_template.html` only (CSS + the existing IIFE-scoped JS). No backend/database changes — the REST API and data model from the original timeline feature are unchanged. This plan rewrites `_tlDrawAxis` (geometry flips from horizontal/`right` to vertical/`top`), removes the now-unnecessary custom horizontal drag-to-pan code (`_tlWireDrag`) in favor of native `overflow-y:auto` scrolling, adds a greedy density-balancing algorithm for left/right marker placement, and adds a self-contained custom calendar-dropdown component that mirrors its selected value into the existing hidden `<input type="date" id="tl-date-inp">` so no other code (`_tlSubmitEvent`, `_tlDoSearchTx`, `_tlOpenAddModal`, `_tlOpenEditModal`) needs to change its date-reading logic.

**Tech Stack:** Same as before — vanilla ES5 JS inside an existing IIFE, inline CSS, no build step, no new libraries.

**Note on verification:** No automated test suite exists in this repo. Verification is manual: run the app and check behavior in a browser (or via Browser pane tooling), per each task's Step. This is the same convention the original timeline feature followed.

---

### Task 1: Vertical axis, native scrolling, bolder styling, menu-button clearance

**Files:**
- Modify: `source/html/Base_template.html`

- [ ] **Step 1: Replace the Timeline widget CSS block**

Find the CSS block starting at `/* ── Timeline widget ──────────────────────────────────────────── */` (currently ends right before `/* ── Timeline event modal ─────────────────────────────────────── */`) — this spans the `.tl-toolbar`, `.tl-toolbar-left`, `.tl-zoom-btn`, `.tl-add-btn`, `.tl-axis-wrap`, `.tl-axis-wrap.dragging`, `.tl-axis-scroll`, `.tl-baseline`, `.tl-tick`, `.tl-tick-label`, `.tl-empty` rules, the `@media (max-width:700px)` block right after them, the `.tl-toggle-wrap`/`.tl-switch`/`.tl-switch-knob` rules, the `.tl-marker`/`.tl-dot`/`.tl-bubble`/`.tl-bubble::after`/`.tl-bubble-date`/minimize-mode rules, and the second `@media (max-width:700px)` block for `.tl-bubble`. Replace that ENTIRE region (all of it, from `/* ── Timeline widget ──` through the `.tl-bubble` mobile media query, i.e. everything currently between the `.hs-subtab-btn.active` rule and the `/* ── Timeline event modal ─` comment) with:

```css
/* ── Housing panel sub-tabs ───────────────────────────────────── */
.hs-subtabs { display:flex; gap:8px; margin-bottom:14px; margin-top:56px; }
.hs-subtab-btn {
  padding:7px 16px; border-radius:20px; border:1.5px solid var(--border);
  background:var(--white); color:var(--text-sub); font-family:inherit;
  font-size:0.85em; font-weight:600; cursor:pointer; transition:all .12s;
}
.hs-subtab-btn:hover { border-color:var(--teal); color:var(--teal); }
.hs-subtab-btn.active { background:var(--teal); border-color:var(--teal); color:#fff; }

/* ── Timeline widget (vertical) ──────────────────────────────────── */
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
  position:relative; overflow-y:auto; overflow-x:hidden; height:560px;
  border:1.5px solid var(--border); border-radius:10px; background:var(--white);
  -webkit-overflow-scrolling:touch; touch-action:pan-y;
}
.tl-axis-scroll { position:relative; width:100%; }
.tl-baseline { position:absolute; top:0; bottom:0; right:50%; width:3px; margin-right:-1.5px; background:var(--navy); opacity:.18; border-radius:2px; }
.tl-tick { position:absolute; right:calc(50% - 8px); width:16px; height:2px; background:var(--text-muted); }
.tl-tick-label { position:absolute; right:calc(50% + 12px); font-size:0.72em; font-weight:700; color:var(--text-muted); white-space:nowrap; transform:translateY(-50%); }
.tl-empty { text-align:center; color:var(--text-muted); padding:60px 20px; }

@media (max-width:700px) {
  .hs-subtabs { margin-top:48px; }
  .tl-axis-wrap { height:440px; }
  .tl-tick-label { font-size:0.65em; }
}

.tl-toggle-wrap { display:flex; align-items:center; gap:7px; font-size:0.8em; color:var(--text-sub); }
.tl-switch { position:relative; width:36px; height:20px; border-radius:12px; background:var(--border); cursor:pointer; transition:background .15s; flex-shrink:0; }
.tl-switch.on { background:var(--teal); }
.tl-switch-knob { position:absolute; top:2px; right:2px; width:16px; height:16px; border-radius:50%; background:#fff; transition:right .15s; box-shadow:0 1px 2px rgba(0,0,0,.2); }
.tl-switch.on .tl-switch-knob { right:18px; }

.tl-marker { position:absolute; }
.tl-marker.tl-side-right { right:50%; margin-right:14px; }
.tl-marker.tl-side-left { left:50%; margin-left:14px; }
.tl-dot {
  position:absolute; top:0; width:14px; height:14px; border-radius:50%;
  border:3px solid #fff; box-shadow:0 0 0 2px rgba(0,0,0,.22); cursor:pointer;
  transform:translateY(-50%);
}
.tl-marker.tl-side-right .tl-dot { right:-21px; }
.tl-marker.tl-side-left .tl-dot { left:-21px; }
.tl-bubble {
  position:relative; top:0; transform:translateY(-50%);
  min-width:90px; max-width:190px; padding:7px 11px; border-radius:9px; color:#fff;
  font-size:0.78em; font-weight:700; cursor:pointer; box-shadow:0 3px 10px rgba(0,0,0,.25);
  transition:opacity .12s, transform .12s;
  background:var(--bubble-color, var(--teal));
}
.tl-marker.tl-side-right .tl-bubble { margin-right:14px; }
.tl-marker.tl-side-left .tl-bubble { margin-left:14px; }
.tl-bubble::after {
  content:''; position:absolute; top:50%; margin-top:-5px;
  border:5px solid transparent;
}
.tl-marker.tl-side-right .tl-bubble::after { right:100%; border-right-color:var(--bubble-color, var(--teal)); }
.tl-marker.tl-side-left .tl-bubble::after { left:100%; border-left-color:var(--bubble-color, var(--teal)); }
.tl-bubble-date { font-weight:500; opacity:.85; font-size:0.9em; }
.tl-axis-wrap.tl-minimize-mode .tl-marker:not(:hover) .tl-bubble { opacity:0; pointer-events:none; transform:translateY(-50%) scale(.6); }
.tl-axis-wrap.tl-minimize-mode .tl-marker:not(:hover) .tl-dot { width:10px; height:10px; }
.tl-axis-wrap.tl-minimize-mode .tl-marker:hover .tl-dot { width:16px; height:16px; }

@media (max-width:700px) {
  .tl-bubble { font-size:0.72em; max-width:140px; padding:6px 9px; }
  .tl-marker.tl-side-right { margin-right:10px; }
  .tl-marker.tl-side-left { margin-left:10px; }
  .tl-marker.tl-side-right .tl-dot { right:-17px; }
  .tl-marker.tl-side-left .tl-dot { left:-17px; }
}
```

Notes on what changed and why:
- `.hs-subtabs` gets `margin-top:56px` (44px on mobile) so the sub-tab pills clear the fixed hamburger button (`top:18px; right:18px; width:42px; height:42px` → bottom edge at 60px).
- `.tl-axis-wrap` switches from `overflow-x:auto;overflow-y:hidden` to `overflow-y:auto;overflow-x:hidden`, drops `cursor:grab`/`.dragging` (no longer needed — native scroll handles wheel and touch), and gets a fixed height (560px desktop / 440px mobile) instead of the old fixed-height-but-horizontal-scroll box.
- `.tl-baseline` is now a vertical line (`top:0;bottom:0;right:50%`), 3px wide (was 2px) for the "bolder" requirement, with a subtle navy tint instead of a flat border color.
- `.tl-dot` grew from 10px to 14px with a 3px border (was 2px) and a stronger shadow (`0 0 0 2px` vs `0 0 0 1px`) — bolder.
- `.tl-bubble` font-weight is 700 (was 600), shadow is stronger, and it now has `.tl-side-left`/`.tl-side-right` variants that position it to either side of the baseline with a sideways-pointing arrow instead of the old always-above, downward-pointing one.
- `.tl-marker` no longer self-centers via `transform:translate(50%,-50%)` — vertical position is set directly via inline `top` (set in JS), and horizontal side is a CSS class.

- [ ] **Step 2: Rewrite `_tlDrawAxis`'s geometry (ticks + click-to-add) for vertical orientation**

Find `_tlDrawAxis` (search `function _tlDrawAxis`). Replace the tick-drawing loop and the `scroll.onclick` handler. The current tick loop (inside `_tlDrawAxis`, right after `scroll.style.width = widthPx + 'px';`) reads:

```javascript
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
```

Replace the whole line `scroll.style.width = widthPx + 'px';` and everything through the end of that tick `while` loop with:

```javascript
    var heightPx = totalDays * _tlPxPerDay;
    scroll.style.height = heightPx + 'px';

    function _tlTopForDate(d) {
      // top = 0 is the most recent (maxD); further down = further back in time.
      return ((maxD - d) / _tlDayMs()) * _tlPxPerDay;
    }

    var html = '<div class="tl-baseline"></div>';
    var cursor = new Date(minD.getFullYear(), minD.getMonth(), 1);
    while (cursor <= maxD) {
      var topPx = _tlTopForDate(cursor);
      html += '<div class="tl-tick" style="top:' + topPx + 'px"></div>';
      html += '<div class="tl-tick-label" style="top:' + topPx + 'px">' +
        (cursor.getMonth() + 1) + '/' + cursor.getFullYear() + '</div>';
      cursor = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
    }
```

(`_tlTopForDate` is a small local helper declared inside `_tlDrawAxis` so it can close over `maxD`; it'll also be used by the marker-placement code added in Task 2 and the year-line code added in Task 3 — both of those tasks assume this helper already exists from this step.)

Then find `scroll.onclick = function(e) { ... }` near the end of `_tlDrawAxis` (currently reads the clicked X position to compute a date). Replace it with a version that reads the clicked Y position instead:

```javascript
    scroll.onclick = function(e) {
      if (e.target.closest('.tl-marker')) return;
      var rect = scroll.getBoundingClientRect();
      var yFromTop = e.clientY - rect.top;
      var days = Math.round(yFromTop / _tlPxPerDay);
      var clickedDate = new Date(maxD.getTime() - days * _tlDayMs());
      if (isNaN(clickedDate)) return;
      _tlOpenAddModal(clickedDate.toISOString().slice(0, 10));
    };
```

(The marker-rendering block between the tick loop and this `scroll.onclick` handler — currently the `columns`/`hasMarkers`/`Object.keys(columns).forEach(...)` code — is fully replaced in Task 2, not this step. Leave it as-is for now; Task 2 rewrites it. It will temporarily still work with `right:`-based positioning even though the axis is now vertical — markers will render in the wrong place until Task 2 lands, which is expected and fine since these tasks are applied in order in the same session.)

- [ ] **Step 3: Delete the now-unnecessary drag-to-pan code**

Native `overflow-y:auto` on `.tl-axis-wrap` already provides mouse-wheel and touch-swipe scrolling for free — the old horizontal drag-to-pan/wheel-remap code is no longer needed and actively wrong for a vertical layout (it manipulated `scrollLeft`). Delete the entire `_tlWireDrag` function:

```javascript
  function _tlWireDrag() {
    var wrap = document.getElementById('tl-axis-wrap');
    if (!wrap) return;

    if (_tlWindowMouseMove) window.removeEventListener('mousemove', _tlWindowMouseMove);
    if (_tlWindowMouseUp) window.removeEventListener('mouseup', _tlWindowMouseUp);

    var isDown = false, startX = 0, startScroll = 0;
    wrap.addEventListener('mousedown', function(e) {
      isDown = true;
      wrap.classList.add('dragging');
      startX = e.pageX;
      startScroll = wrap.scrollLeft;
    });
    _tlWindowMouseUp = function() {
      isDown = false;
      wrap.classList.remove('dragging');
    };
    _tlWindowMouseMove = function(e) {
      if (!isDown) return;
      wrap.scrollLeft = startScroll - (e.pageX - startX);
    };
    window.addEventListener('mouseup', _tlWindowMouseUp);
    window.addEventListener('mousemove', _tlWindowMouseMove);
    wrap.addEventListener('wheel', function(e) {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        wrap.scrollLeft += e.deltaY;
        e.preventDefault();
      }
    }, { passive: false });
  }
```

Also delete its call site in `_renderTimeline` — find:

```javascript
    _tlDrawAxis(events);
    _tlWireDrag();
  }
```

and change it to:

```javascript
    _tlDrawAxis(events);
  }
```

Also delete the now-unused state variables `var _tlWindowMouseMove = null;` and `var _tlWindowMouseUp = null;` (declared near `var _tlPxPerDay = 6;`).

- [ ] **Step 4: Verify manually**

Start the app, open the housing panel, click "ציר זמן". Confirm:
1. The axis is now a tall vertical box with a bold vertical line down the middle.
2. The sub-tab pills ("סקירה כללית"/"ציר זמן") no longer sit under/behind the fixed hamburger button in the top-right corner — there's clear visible space between the button and the pills.
3. Scrolling the mouse wheel while hovered over the axis box scrolls it vertically (not horizontally).
4. On a narrow viewport (resize to ~375px), the axis is shorter (440px) and a touch-drag/swipe scrolls it (if you can simulate touch events; otherwise confirm `overflow-y:auto` and `touch-action:pan-y` are present in the computed style).
5. Month tick labels render down the right side of the baseline (their exact vertical position may look approximately right even though markers themselves are still mispositioned at this point — that's expected, Task 2 fixes marker placement).
6. No console errors (in particular, no `_tlWireDrag is not defined` — confirm it's fully removed, not just emptied).

- [ ] **Step 5: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
feat(timeline): rotate axis to vertical with native scrolling

Newest events now sit at the top, oldest at the bottom. Drops the
custom horizontal drag-to-pan/wheel-remap code in favor of native
overflow-y:auto, which handles mouse wheel and touch-swipe for free.
Also bumps line/dot/bubble visual weight and adds clearance so the
sub-tab pills don't sit under the fixed hamburger menu button.
EOF
)"
```
Bump `/VERSION` (check current value first, increment patch by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```

---

### Task 2: Density-balanced alternating-side marker placement with collision-safe stacking

**Files:**
- Modify: `source/html/Base_template.html`

- [ ] **Step 1: Replace the marker-rendering block in `_tlDrawAxis`**

Find the block in `_tlDrawAxis` that currently reads (this is the bucket/stacking logic from the original horizontal design):

```javascript
    var columns = {};
    var hasMarkers = false;
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
        hasMarkers = true;
        html +=
          '<div class="tl-marker" style="right:' + item.rightPx + 'px" onclick="_tlOpenEditModal(' + ev.id + ')">' +
            '<div class="tl-dot" style="background:' + _esc(ev.color) + '"></div>' +
            '<div class="tl-bubble" style="--bubble-color:' + _esc(ev.color) + ';bottom:' + bubbleBottom + 'px">' +
              _esc(ev.name) + '<div class="tl-bubble-date">' + ev.event_date + '</div>' +
            '</div>' +
          '</div>';
      });
    });

    if (!hasMarkers) {
      html += '<div class="tl-empty">אין אירועים עדיין — לחצו על "הוסף אירוע"</div>';
    }
```

Replace it with a greedy density-balancing placement: events are sorted newest-first (top-to-bottom order), and each one is assigned to whichever side (left/right) currently has more free vertical room, then nudged down if it would overlap the previous marker already placed on that side. A fixed slot height (`TL_SLOT_H`) reserves enough room for a 2-line bubble so same-date/near-date events never visually collide:

```javascript
    var TL_SLOT_H = 64; // px reserved per marker on its side, enough for a 2-line bubble

    var sortedEvents = (events || [])
      .map(function(ev) { return { ev: ev, d: new Date(ev.event_date) }; })
      .filter(function(item) { return !isNaN(item.d); })
      .sort(function(a, b) { return b.d - a.d; }); // newest (top) first

    var hasMarkers = sortedEvents.length > 0;
    var sideBottom = { left: -Infinity, right: -Infinity }; // next available top-px per side

    sortedEvents.forEach(function(item) {
      var ev = item.ev;
      var idealTop = _tlTopForDate(item.d);
      var side = sideBottom.left <= sideBottom.right ? 'left' : 'right';
      var placedTop = Math.max(idealTop, sideBottom[side]);
      sideBottom[side] = placedTop + TL_SLOT_H;

      html +=
        '<div class="tl-marker tl-side-' + side + '" style="top:' + placedTop + 'px" onclick="_tlOpenEditModal(' + ev.id + ')">' +
          '<div class="tl-dot" style="background:' + _esc(ev.color) + '"></div>' +
          '<div class="tl-bubble" style="--bubble-color:' + _esc(ev.color) + '">' +
            _esc(ev.name) + '<div class="tl-bubble-date">' + ev.event_date + '</div>' +
          '</div>' +
        '</div>';
    });

    if (!hasMarkers) {
      html += '<div class="tl-empty">אין אירועים עדיין — לחצו על "הוסף אירוע"</div>';
    }
```

How this satisfies the requirements:
- **Alternating by density, not fixed index:** each event goes to whichever side has more free room (`sideBottom.left <= sideBottom.right`), so under uniform density it naturally alternates left/right/left/right, but under uneven density (e.g. three same-date events) it still balances rather than blindly cycling.
- **Collision-safe:** `placedTop = Math.max(idealTop, sideBottom[side])` means a marker is never placed above the bottom edge of the previous marker on the same side — same-date or near-date events on the same side stack downward with guaranteed `TL_SLOT_H` (64px) separation, which comfortably fits a 2-line wrapped bubble at the sizes set in Task 1's CSS.
- This also naturally subsumes the old "stack vertically" behavior for same-date events — now some go left and some go right instead of all stacking on one line, further reducing crowding.

- [ ] **Step 2: Verify manually**

Start the app, create 4-5 test events spread across a few different dates, including at least 2 on the exact same date. Confirm:
1. Events roughly alternate between the left and right side of the vertical baseline.
2. The 2 same-date events land on different sides (or, if forced to the same side by the balancing logic in an edge case, are clearly vertically separated with no visual overlap).
3. No two bubbles overlap each other anywhere on the timeline, even after zooming out (`−` button) to compress many events into a smaller vertical span — confirm by zooming out until several events are close together and visually inspecting for overlap.
4. Clicking a marker still opens the edit modal for the correct event (side assignment doesn't break the existing `onclick="_tlOpenEditModal(id)"` wiring).
5. Clean up all test events afterward via the UI or `curl -X DELETE`.

- [ ] **Step 3: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
feat(timeline): alternate markers left/right with density balancing

Replaces the old single-side vertical stacking with a greedy
left/right placement that reserves a fixed slot height per marker,
so same-date events spread across both sides of the baseline instead
of piling up in one column, and never visually overlap.
EOF
)"
```
Bump `/VERSION` (check current value first, increment by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```

---

### Task 3: Yearly jagged divider lines

**Files:**
- Modify: `source/html/Base_template.html`

- [ ] **Step 1: Add CSS for the jagged year-divider**

Add this new rule block right after the `.tl-tick-label` rule (from Task 1):

```css
.tl-year-line { position:absolute; right:0; left:0; height:14px; margin-top:-7px; }
.tl-year-line svg { display:block; width:100%; height:100%; }
.tl-year-label {
  position:absolute; right:8px; margin-top:-9px;
  font-size:0.78em; font-weight:800; color:var(--navy);
  background:var(--white); padding:1px 8px; border-radius:6px;
  box-shadow:0 1px 3px rgba(0,0,0,.15);
}
```

- [ ] **Step 2: Add a jagged-line SVG generator and draw one line per year boundary**

Add this helper function right before `_tlDrawAxis` (so `_tlDrawAxis` can call it):

```javascript
  function _tlJaggedLineSVG() {
    var pts = [];
    var segments = 40;
    for (var i = 0; i <= segments; i++) {
      var x = (i / segments) * 100;
      var y = (i % 2 === 0) ? 3 : 11;
      pts.push(x + ',' + y);
    }
    return '<svg viewBox="0 0 100 14" preserveAspectRatio="none">' +
      '<polyline points="' + pts.join(' ') + '" fill="none" stroke="var(--navy)" stroke-width="1.5" opacity="0.35" vector-effect="non-scaling-stroke"></polyline>' +
      '</svg>';
  }
```

Then, inside `_tlDrawAxis`, right after the month-tick `while` loop added in Task 1 (i.e. right after the closing `}` of `while (cursor <= maxD) { ... }` for ticks, and before the marker-placement code from Task 2), add a second loop that walks January 1st boundaries and inserts a jagged line + year label at each:

```javascript
    var yearCursor = new Date(minD.getFullYear(), 0, 1);
    if (yearCursor < minD) yearCursor = new Date(minD.getFullYear() + 1, 0, 1);
    while (yearCursor <= maxD) {
      var yearTop = _tlTopForDate(yearCursor);
      html += '<div class="tl-year-line" style="top:' + yearTop + 'px">' + _tlJaggedLineSVG() + '</div>';
      html += '<div class="tl-year-label" style="top:' + yearTop + 'px">' + yearCursor.getFullYear() + '</div>';
      yearCursor = new Date(yearCursor.getFullYear() + 1, 0, 1);
    }
```

- [ ] **Step 3: Verify manually**

Create a test event dated in a different year than today (e.g. if today is in 2026, create one dated 2025-03-01), so the timeline's date range spans a year boundary. Open the Timeline tab and confirm:
1. A visibly jagged/zigzag horizontal line spans the full width of the axis at the January 1st boundary between the two years.
2. A small year-number label sits near the line.
3. The jagged line doesn't visually block or sit on top of any marker/bubble at that vertical position (if it does in your test data, that's fine — z-ordering/overlap with a marker at the exact same week is an acceptable edge case, not a defect, since real mortgage events rarely land exactly on Jan 1st).
4. Zoom in/out and confirm the line's vertical position moves correctly with the rest of the axis (it's just another absolutely-positioned child of `#tl-axis-scroll`, so it should already move correctly — this is really confirming no arithmetic mistake in `_tlTopForDate` usage).
5. Delete the test event afterward.

- [ ] **Step 4: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
feat(timeline): draw a jagged divider line at each year boundary
EOF
)"
```
Bump `/VERSION` (check current value first, increment by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```

---

### Task 4: Modern custom date picker in the add/edit modal

**Files:**
- Modify: `source/html/Base_template.html`

- [ ] **Step 1: Add date-picker CSS**

Add this new rule block right after the `.tl-field textarea { resize:vertical; min-height:56px; }` rule (in the modal CSS section):

```css
.tl-date-btn {
  display:flex; align-items:center; justify-content:space-between; gap:8px;
  padding:8px 11px; border:1.5px solid var(--border); border-radius:7px;
  font-size:0.87em; font-family:inherit; color:var(--navy); background:var(--white);
  cursor:pointer; text-align:right; width:100%;
}
.tl-date-btn:hover { border-color:var(--teal); }
.tl-date-btn-icon { opacity:.6; font-size:0.95em; }
.tl-cal-wrap { position:relative; }
.tl-cal-dropdown {
  position:absolute; z-index:10; top:calc(100% + 4px); right:0;
  width:260px; background:var(--white); border:1.5px solid var(--teal);
  border-radius:10px; box-shadow:var(--shadow-md); padding:10px;
}
.tl-cal-dropdown.hidden { display:none; }
.tl-cal-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }
.tl-cal-nav-btn {
  width:26px; height:26px; border-radius:6px; border:1px solid var(--border);
  background:var(--white); cursor:pointer; font-weight:700; color:var(--navy);
  display:flex; align-items:center; justify-content:center;
}
.tl-cal-nav-btn:hover { border-color:var(--teal); color:var(--teal); }
.tl-cal-title { font-size:0.85em; font-weight:700; color:var(--navy); }
.tl-cal-grid { display:grid; grid-template-columns:repeat(7,1fr); gap:2px; }
.tl-cal-dow { font-size:0.68em; font-weight:700; color:var(--text-muted); text-align:center; padding:3px 0; }
.tl-cal-day {
  font-size:0.8em; text-align:center; padding:6px 0; border-radius:6px;
  cursor:pointer; color:var(--navy); background:none; border:none; font-family:inherit;
}
.tl-cal-day:hover { background:var(--teal-light); }
.tl-cal-day.tl-cal-day-muted { color:var(--text-muted); opacity:.45; }
.tl-cal-day.tl-cal-day-today { font-weight:700; text-decoration:underline; }
.tl-cal-day.tl-cal-day-sel { background:var(--teal); color:#fff; font-weight:700; }
```

- [ ] **Step 2: Replace the date field markup in `_tlBuildModal`**

Find, inside `_tlBuildModal`'s HTML string:

```javascript
        '<div class="tl-field"><label>תאריך</label><input id="tl-date-inp" type="date"></div>' +
```

Replace it with (a hidden native input keeps the existing `.value` contract every other function relies on; a button + dropdown calendar provide the modern UI on top of it):

```javascript
        '<div class="tl-field">' +
          '<label>תאריך</label>' +
          '<div class="tl-cal-wrap">' +
            '<input id="tl-date-inp" type="date" style="display:none">' +
            '<button type="button" class="tl-date-btn" id="tl-date-btn" onclick="_tlCalToggle()">' +
              '<span id="tl-date-btn-text">בחר תאריך</span>' +
              '<span class="tl-date-btn-icon">📅</span>' +
            '</button>' +
            '<div class="tl-cal-dropdown hidden" id="tl-cal-dropdown"></div>' +
          '</div>' +
        '</div>' +
```

- [ ] **Step 3: Add the calendar-picker JS**

Add these new functions and state variables right after `_tlBuildModal` (before `_tlRenderColorRow`):

```javascript
  var _tlCalViewYear  = null;
  var _tlCalViewMonth = null; // 0-11

  var TL_MONTH_NAMES = ['ינואר','פברואר','מרץ','אפריל','מאי','יוני','יולי','אוגוסט','ספטמבר','אוקטובר','נובמבר','דצמבר'];
  var TL_DOW_NAMES = ['א','ב','ג','ד','ה','ו','ש'];

  function _tlSetDateValue(dateStr) {
    var inp = document.getElementById('tl-date-inp');
    if (inp) inp.value = dateStr;
    var btnText = document.getElementById('tl-date-btn-text');
    if (btnText) btnText.textContent = dateStr || 'בחר תאריך';
    if (dateStr) {
      var d = new Date(dateStr);
      if (!isNaN(d)) {
        _tlCalViewYear = d.getFullYear();
        _tlCalViewMonth = d.getMonth();
      }
    }
  }

  function _tlCalToggle() {
    var dd = document.getElementById('tl-cal-dropdown');
    if (!dd) return;
    if (dd.classList.contains('hidden')) {
      var inp = document.getElementById('tl-date-inp');
      var base = (inp && inp.value) ? new Date(inp.value) : new Date();
      if (isNaN(base)) base = new Date();
      _tlCalViewYear = base.getFullYear();
      _tlCalViewMonth = base.getMonth();
      _tlRenderCalendar();
      dd.classList.remove('hidden');
    } else {
      dd.classList.add('hidden');
    }
  }

  function _tlCalPrevMonth() {
    _tlCalViewMonth--;
    if (_tlCalViewMonth < 0) { _tlCalViewMonth = 11; _tlCalViewYear--; }
    _tlRenderCalendar();
  }

  function _tlCalNextMonth() {
    _tlCalViewMonth++;
    if (_tlCalViewMonth > 11) { _tlCalViewMonth = 0; _tlCalViewYear++; }
    _tlRenderCalendar();
  }

  function _tlRenderCalendar() {
    var dd = document.getElementById('tl-cal-dropdown');
    if (!dd) return;
    var inp = document.getElementById('tl-date-inp');
    var selected = inp && inp.value ? inp.value : '';
    var today = new Date();
    var todayStr = today.toISOString().slice(0, 10);

    var firstOfMonth = new Date(_tlCalViewYear, _tlCalViewMonth, 1);
    var startDow = firstOfMonth.getDay(); // 0=Sunday
    var daysInMonth = new Date(_tlCalViewYear, _tlCalViewMonth + 1, 0).getDate();
    var daysInPrevMonth = new Date(_tlCalViewYear, _tlCalViewMonth, 0).getDate();

    var html = '<div class="tl-cal-header">' +
      '<button type="button" class="tl-cal-nav-btn" onclick="_tlCalNextMonth()">›</button>' +
      '<span class="tl-cal-title">' + TL_MONTH_NAMES[_tlCalViewMonth] + ' ' + _tlCalViewYear + '</span>' +
      '<button type="button" class="tl-cal-nav-btn" onclick="_tlCalPrevMonth()">‹</button>' +
      '</div>' +
      '<div class="tl-cal-grid">';

    TL_DOW_NAMES.forEach(function(n) { html += '<div class="tl-cal-dow">' + n + '</div>'; });

    var cell, cellDate, cellStr, cls;
    for (cell = 0; cell < startDow; cell++) {
      var pd = daysInPrevMonth - startDow + cell + 1;
      html += '<button type="button" class="tl-cal-day tl-cal-day-muted" disabled>' + pd + '</button>';
    }
    for (var day = 1; day <= daysInMonth; day++) {
      cellDate = new Date(_tlCalViewYear, _tlCalViewMonth, day);
      cellStr = cellDate.toISOString().slice(0, 10);
      cls = 'tl-cal-day';
      if (cellStr === todayStr) cls += ' tl-cal-day-today';
      if (cellStr === selected) cls += ' tl-cal-day-sel';
      html += '<button type="button" class="' + cls + '" onclick="_tlCalPick(\'' + cellStr + '\')">' + day + '</button>';
    }
    var totalCells = startDow + daysInMonth;
    var trailing = (7 - (totalCells % 7)) % 7;
    for (cell = 1; cell <= trailing; cell++) {
      html += '<button type="button" class="tl-cal-day tl-cal-day-muted" disabled>' + cell + '</button>';
    }
    html += '</div>';
    dd.innerHTML = html;
  }

  function _tlCalPick(dateStr) {
    _tlSetDateValue(dateStr);
    var dd = document.getElementById('tl-cal-dropdown');
    if (dd) dd.classList.add('hidden');
  }
```

- [ ] **Step 4: Route every existing date-field write through `_tlSetDateValue`**

Three places currently set `document.getElementById('tl-date-inp').value` directly — update them to call `_tlSetDateValue` instead so the button text and calendar view stay in sync.

In `_tlOpenAddModal`, find:
```javascript
    document.getElementById('tl-date-inp').value = prefillDate || new Date().toISOString().slice(0, 10);
```
replace with:
```javascript
    _tlSetDateValue(prefillDate || new Date().toISOString().slice(0, 10));
```

In `_tlOpenEditModal`, find:
```javascript
    document.getElementById('tl-date-inp').value = ev.event_date;
```
replace with:
```javascript
    _tlSetDateValue(ev.event_date);
```

Also, in both `_tlOpenAddModal` and `_tlOpenEditModal`, add this line right after building/showing the modal (i.e. right after the existing `document.getElementById('tl-overlay').classList.remove('hidden');` line in each function) to make sure any open calendar dropdown from a previous use is closed when the modal reopens:
```javascript
    var _ddInit = document.getElementById('tl-cal-dropdown');
    if (_ddInit) _ddInit.classList.add('hidden');
```

- [ ] **Step 5: Close the calendar dropdown when clicking outside it**

Add this at the same place other document-level listeners are wired (or simply right after the `_tlCalPick` function) — a single global click listener that closes the dropdown if the click was outside both the button and the dropdown itself:

```javascript
  document.addEventListener('click', function(e) {
    var dd = document.getElementById('tl-cal-dropdown');
    var btn = document.getElementById('tl-date-btn');
    if (!dd || dd.classList.contains('hidden')) return;
    if (dd.contains(e.target) || (btn && btn.contains(e.target))) return;
    dd.classList.add('hidden');
  });
```

- [ ] **Step 6: Expose the four new onclick-referenced functions on `window`**

The housing script runs inside an IIFE (established pattern throughout this feature) — `_tlCalToggle`, `_tlCalPrevMonth`, `_tlCalNextMonth`, and `_tlCalPick` are all referenced via inline `onclick` and must be added to the existing "expose IIFE-internal functions" block (search for `window._tlSelectTx` — add these four lines near it):

```javascript
  window._tlCalToggle    = _tlCalToggle;
  window._tlCalPrevMonth = _tlCalPrevMonth;
  window._tlCalNextMonth = _tlCalNextMonth;
  window._tlCalPick      = _tlCalPick;
```

- [ ] **Step 7: Verify manually**

Start the app, open the housing panel's Timeline tab, click "+ הוסף אירוע". Confirm:
1. The date field is now a button showing "בחר תאריך" (not a native date input) with a small calendar icon.
2. Clicking it opens a calendar dropdown below the button, showing the current month with day names, today underlined, and prev/next month arrows.
3. Clicking a day selects it (highlighted teal), closes the dropdown, and updates the button text to that date.
4. Clicking outside the dropdown (anywhere else in the modal) closes it without changing the selection.
5. Navigating to a different month via the arrows and picking a day there works correctly (e.g. pick a day in next month, confirm the button shows the correct full date including the new month).
6. Submitting the event with a date picked this way saves correctly (verify via `curl http://localhost:5050/api/timeline/events` that `event_date` matches what was picked).
7. Open an existing event for editing: confirm the button shows its saved date and the calendar opens pre-navigated to that date's month with that day highlighted.
8. Confirm the "קשר עסקאות" transaction search (which reads the date field's value to compute its ±30-day window) still works correctly with a date picked via the new calendar — search for a transaction near the picked date and confirm it appears.
9. No console errors, in particular no `ReferenceError` for any of the four newly-exposed functions.
10. Clean up any test events created.

- [ ] **Step 8: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
feat(timeline): replace native date input with a custom calendar picker

Adds a self-contained dropdown calendar (month nav, day grid, today/
selected highlighting) that mirrors its value into the existing
hidden date input, so no other timeline code needs to change how it
reads the event date.
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

Start the app fresh, open the housing panel, Timeline tab. Walk through every point from the user's request in one continuous session:
1. Confirm the timeline is vertical, newest events at the top, oldest at the bottom (create 3 events with clearly different dates and confirm their top-to-bottom order matches date-descending order).
2. Confirm mouse-wheel scrolling and (if testable) touch-swipe both scroll the axis smoothly.
3. Confirm the line/dots/bubbles read as visually bolder than a "thin" baseline design (this is a subjective check — use judgment, but the baseline should be clearly a solid 3px line, dots clearly larger than a hairline dot, bubble text bold).
4. Confirm at least one jagged yearly divider line renders correctly if your test data spans a year boundary.
5. Confirm the new calendar date picker works end-to-end for both add and edit.
6. Create several same-date events and confirm no visual overlap anywhere, including after zooming in/out.
7. Confirm the sub-tab pills and all timeline toolbar buttons (zoom, minimize toggle, add-event) are fully visible and clickable, not obscured by the fixed hamburger menu button, at both desktop and mobile (375px) widths.
8. Confirm all previously-existing functionality still works: editing an event, deleting an event (with confirm dialog), linking/unlinking transactions with notes, and that the Overview tab is completely unaffected.
9. Check the browser console for errors throughout — expect none.
10. Delete all test events created during this walkthrough.

- [ ] **Step 2: Final commit**

If Step 1 surfaced any fixes, commit them individually (each with its own version bump). If nothing needed fixing, no commit is required for this task.
