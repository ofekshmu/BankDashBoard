# Mortgage Timeline — Polish Round 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Six independent UX fixes to the already-shipped vertical timeline (housing panel): float the sub-tabs beside the hamburger menu button instead of below it, replace the native scrollbar with "glow" scroll-availability indicators, fix markers drifting off the baseline when not hovered, fix the bubble's pointer arrow rendering on the wrong side, split the event modal into a clean read-only view mode (with an explicit Edit button) versus the existing edit form, and add a "Today" button plus fix the calendar dropdown's positioning/clipping in the date picker.

**Architecture:** All changes are in `source/html/Base_template.html` only (CSS + the existing IIFE-scoped JS). No backend/database changes. Each task is independent and can be implemented/reviewed in any order, though Task 5 (view/edit split) is the largest and touches the modal markup that Task 6 (date picker) also touches — implement Task 5 before Task 6 to avoid merge-order confusion within the same file.

**Tech Stack:** Same as before — vanilla ES5 JS inside an existing IIFE, inline CSS, no build step, no new libraries.

**Note on verification:** No automated test suite exists in this repo. Verification is manual: run the app and check behavior in a browser. Several of these fixes (Task 4's arrow direction, Task 6's dropdown positioning) describe the BUG and the INTENDED fix direction, but ask the implementer to confirm the exact visual result empirically with a live screenshot rather than trusting static CSS reasoning alone — these are exactly the kind of thing that's easy to get backwards without actually looking at the render.

---

### Task 1: Float the sub-tabs beside the hamburger menu button

**Files:**
- Modify: `source/html/Base_template.html`

- [ ] **Step 1: Reposition `.hs-subtabs` as a fixed floating bar next to the hamburger button**

Find:
```css
.hs-subtabs { display:flex; gap:8px; margin-bottom:14px; margin-top:64px; }
```
Replace with:
```css
.hs-subtabs {
  position:fixed; top:18px; right:70px; z-index:401;
  display:flex; gap:6px; margin:0;
  background:var(--white); padding:4px; border-radius:24px;
  border:1.5px solid var(--border); box-shadow:var(--shadow-sm);
}
#housing-overview, #housing-timeline { margin-top:64px; }
```
(The hamburger button — `.ham-btn` — is `position:fixed; top:18px; right:18px; width:42px; height:42px`, so its bottom edge is at y=60px and its left edge is at 60px from the screen's right edge. `right:70px` gives the tabs bar a 10px gap to the button's left. Since `.hs-subtabs` is no longer in normal document flow, the vertical space it used to reserve via `margin-top` is moved onto the two content wrappers that follow it — `#housing-overview` and `#housing-timeline` — so the actual panel content (KPIs, or the timeline toolbar/axis) still starts below the fixed row, "right under it," per the request. `z-index:401` is one above `.ham-btn`'s `z-index:400` so the tabs bar's own hover/click target isn't ever occluded by the button, though they shouldn't overlap given the horizontal gap.)

- [ ] **Step 2: Adjust the mobile media query**

Find, inside the existing `@media (max-width:700px) { ... }` block that currently contains:
```css
  .hs-subtabs { margin-top:60px; }
```
Replace that one line with:
```css
  .hs-subtabs { right:62px; gap:4px; padding:3px; }
  .hs-subtab-btn { padding:6px 11px; font-size:0.78em; }
  #housing-overview, #housing-timeline { margin-top:60px; }
```
(Smaller gap-to-button on mobile since the button is the same fixed size but there's less horizontal room; slightly smaller pill padding/font so both pills comfortably fit beside the button on a 375px-wide screen.)

- [ ] **Step 3: Verify manually**

Start the app, open the housing panel. Confirm:
1. The "סקירה כללית"/"ציר זמן" pills now sit to the LEFT of the hamburger button, on the same horizontal row near the top of the viewport, not below it.
2. Scrolling the page (or the timeline's own internal scroll) does NOT move the pills — they stay fixed in place at the top, always visible, exactly like the hamburger button.
3. The panel's actual content (KPI cards in Overview, or the toolbar+axis in Timeline) starts clearly below that fixed row with no overlap.
4. At mobile width (375px), both pills are still fully visible and clickable beside the button, not clipped off-screen or overlapping it.
5. Switching to a different panel (e.g. "חשבונות" via the sidebar) correctly hides the pills entirely (since they're generated inside `#panel-housing`, which itself gets hidden) — no orphaned floating pills left on other pages.

- [ ] **Step 4: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
feat(timeline): float sub-tabs beside the hamburger button

The pills now sit fixed at the top of the viewport to the hamburger
button's left instead of pushed below it in the document flow, so
they stay visible during scroll and share the same header row.
EOF
)"
```
Bump `/VERSION` (check current value first, increment patch by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```

---

### Task 2: Replace the scrollbar with "glow" scroll-availability indicators

**Files:**
- Modify: `source/html/Base_template.html`

- [ ] **Step 1: Hide the native scrollbar and add glow-indicator CSS**

Add these rules right after the `.tl-axis-wrap { ... }` rule:
```css
.tl-axis-wrap { scrollbar-width:none; -ms-overflow-style:none; }
.tl-axis-wrap::-webkit-scrollbar { display:none; }
.tl-scroll-glow {
  position:absolute; right:0; left:0; height:34px; pointer-events:none;
  z-index:5; opacity:0; transition:opacity .2s;
}
.tl-scroll-glow-top { top:0; background:linear-gradient(to bottom, rgba(30,157,139,.35), transparent); }
.tl-scroll-glow-bottom { bottom:0; background:linear-gradient(to top, rgba(30,157,139,.35), transparent); }
.tl-scroll-glow.show { opacity:1; animation:tlGlowPulse 1.6s ease-in-out infinite; }
@keyframes tlGlowPulse { 0%,100% { opacity:.55; } 50% { opacity:1; } }
```
(`.tl-axis-wrap`'s own rule already has `overflow-y:auto` from a prior task — these new declarations just add to that same selector's rule block; don't create a second, separate `.tl-axis-wrap { }` block, add the two scrollbar-hiding lines into the EXISTING one.)

- [ ] **Step 2: Add the glow-indicator markup**

In `_renderTimeline`, find:
```javascript
      '<div class="tl-axis-wrap' + (_tlMinimizeMode ? ' tl-minimize-mode' : '') + '" id="tl-axis-wrap">' +
        '<div class="tl-axis-scroll" id="tl-axis-scroll"></div>' +
      '</div>';
```
Replace with:
```javascript
      '<div class="tl-axis-wrap' + (_tlMinimizeMode ? ' tl-minimize-mode' : '') + '" id="tl-axis-wrap">' +
        '<div class="tl-axis-scroll" id="tl-axis-scroll"></div>' +
        '<div class="tl-scroll-glow tl-scroll-glow-top" id="tl-scroll-glow-top"></div>' +
        '<div class="tl-scroll-glow tl-scroll-glow-bottom" id="tl-scroll-glow-bottom"></div>' +
      '</div>';
```

- [ ] **Step 3: Add the glow-update logic and wire it to scroll + zoom**

Add these two new functions right after `_tlDrawAxis` (or anywhere alongside the other `_tl*` helpers):
```javascript
  function _tlUpdateScrollGlow() {
    var wrap = document.getElementById('tl-axis-wrap');
    var top = document.getElementById('tl-scroll-glow-top');
    var bottom = document.getElementById('tl-scroll-glow-bottom');
    if (!wrap || !top || !bottom) return;
    top.classList.toggle('show', wrap.scrollTop > 4);
    bottom.classList.toggle('show', wrap.scrollTop + wrap.clientHeight < wrap.scrollHeight - 4);
  }

  function _tlWireScrollGlow() {
    var wrap = document.getElementById('tl-axis-wrap');
    if (!wrap) return;
    wrap.addEventListener('scroll', _tlUpdateScrollGlow);
    _tlUpdateScrollGlow();
  }
```
In `_renderTimeline`, find:
```javascript
    _tlDrawAxis(events);
  }
```
(the end of the function) and change it to:
```javascript
    _tlDrawAxis(events);
    _tlWireScrollGlow();
  }
```
In `_tlZoom`, find:
```javascript
  function _tlZoom(factor) {
    _tlPxPerDay = Math.max(1.5, Math.min(80, _tlPxPerDay * factor));
    _tlDrawAxis(_timelineEvents || []);
  }
```
and change it to:
```javascript
  function _tlZoom(factor) {
    _tlPxPerDay = Math.max(1.5, Math.min(80, _tlPxPerDay * factor));
    _tlDrawAxis(_timelineEvents || []);
    _tlUpdateScrollGlow();
  }
```
(Zoom changes the scrollable content's height without firing a native `scroll` event, so the glow state needs an explicit refresh there — otherwise, e.g., zooming out to where everything fits without scrolling would leave a stale "more below" glow showing.)

Note: `_tlWireScrollGlow` attaching a fresh `scroll` listener on every `_renderTimeline()` call is safe here (unlike the old drag-listener bug from an earlier task) because `#tl-axis-wrap` itself is a brand-new DOM node every time `_renderTimeline` rewrites `tl.innerHTML` — the listener is scoped to that specific node and is garbage-collected along with it when the node is replaced, not attached to `window`/`document`.

- [ ] **Step 4: Verify manually**

Start the app, open the housing panel's Timeline tab with enough events (or a wide enough zoomed-in date range) that the axis is taller than its visible box. Confirm:
1. No visible scrollbar track/thumb anywhere on `.tl-axis-wrap`, in any browser you can check.
2. At the very top of the scroll range, only the BOTTOM glow bar is visible (softly pulsing), indicating more content below.
3. Scroll down partway — both top and bottom glows are visible.
4. Scroll to the very bottom — only the TOP glow is visible.
5. If the content fits entirely without scrolling (e.g. very few events, or zoomed far out), neither glow shows.
6. Zoom in/out via the +/− buttons and confirm the glow state updates correctly immediately (not just after the next manual scroll).
7. Mouse wheel and (if testable) touch-swipe scrolling both still work exactly as before — this task doesn't change scroll mechanics, only the visual chrome.

- [ ] **Step 5: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
feat(timeline): replace the axis scrollbar with glow scroll indicators

Hides the native scrollbar and adds pulsing top/bottom gradient
glows that appear only when there's more content to scroll in that
direction, updated on scroll and on zoom.
EOF
)"
```
Bump `/VERSION` (check current value first, increment by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```

---

### Task 3: Fix markers drifting off the baseline when not hovered

**Files:**
- Modify: `source/html/Base_template.html`

- [ ] **Step 1: Understand and fix the root cause**

`.tl-dot`'s horizontal offset (`right:-21px` for the right side, `left:-21px` for the left side) was tuned assuming the dot is always 14px wide (its base size). In "minimize" mode, the not-hovered state currently shrinks the dot by changing its `width`/`height` directly:
```css
.tl-axis-wrap.tl-minimize-mode .tl-marker:not(:hover) .tl-dot { width:10px; height:10px; }
.tl-axis-wrap.tl-minimize-mode .tl-marker:hover .tl-dot { width:16px; height:16px; }
```
Changing `width`/`height` on an absolutely-positioned element with a FIXED `right`/`left` offset shifts its center, because the offset is measured from one edge, not the center — so a 10px dot with the same `right:-21px` as a 14px dot ends up a couple of pixels off from where the 14px dot was centered, which is why markers look slightly off the baseline specifically in their default (not-hovered, minimized) state.

Fix: keep the dot's box always 14px (matching the `right`/`left:-21px` offset it was tuned for) and use a CSS `transform: scale(...)` for the minimize/hover size change instead — `transform` scales visually from the element's center without moving its box-model position, so the dot's center stays pinned to the baseline in every state.

Find:
```css
.tl-axis-wrap.tl-minimize-mode .tl-marker:not(:hover) .tl-dot { width:10px; height:10px; }
.tl-axis-wrap.tl-minimize-mode .tl-marker:hover .tl-dot { width:16px; height:16px; }
```
Replace with:
```css
.tl-axis-wrap.tl-minimize-mode .tl-marker:not(:hover) .tl-dot { transform:translateY(-50%) scale(0.72); }
.tl-axis-wrap.tl-minimize-mode .tl-marker:hover .tl-dot { transform:translateY(-50%) scale(1.15); }
```
(`.tl-dot`'s base rule already has `transform:translateY(-50%);` for vertical centering — these overrides must include that same `translateY(-50%)` alongside the `scale(...)`, since setting `transform` replaces the whole value rather than adding to it. 0.72× of 14px ≈ 10px and 1.15× ≈ 16px, matching the old sizes' visual weight without moving the anchor point.)

- [ ] **Step 2: Verify manually**

Start the app, open the housing panel's Timeline tab with at least one event, with the minimize toggle ON (default "הקטן בריחוף" mode). Confirm:
1. In the default (not-hovered) state, the dot visually sits exactly centered ON the vertical baseline — not offset to one side of it.
2. Hovering over a marker still enlarges the dot (now via scale) and it still stays centered on the baseline while enlarged, not drifting further off.
3. Toggle to "הצג תמיד" (always-show) mode and confirm dots still sit centered on the baseline (this mode doesn't apply the minimize-mode CSS at all, so it should already have been fine, but confirm as a regression check).
4. Test on both left-side and right-side markers (create events that land on both sides) to confirm the fix applies symmetrically.

- [ ] **Step 3: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
fix(timeline): keep markers centered on the baseline in minimize mode

Resizing the dot via width/height shifted its center relative to its
fixed right/left offset. Use transform:scale() instead, which resizes
from the element's own center and leaves the baseline anchor intact.
EOF
)"
```
Bump `/VERSION` (check current value first, increment by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```

---

### Task 4: Fix the bubble's pointer arrow rendering on the wrong side

**Files:**
- Modify: `source/html/Base_template.html`

- [ ] **Step 1: Diagnose live, then fix**

The bubble's small triangular pointer (the `.tl-bubble::after` pseudo-element) is meant to point FROM the bubble TOWARD its dot/the baseline. The user reports it currently renders on the opposite side — i.e., pointing away from the baseline instead of toward it — on both the left-side and right-side markers.

Current CSS:
```css
.tl-bubble::after {
  content:''; position:absolute; top:50%; margin-top:-5px;
  border:5px solid transparent;
}
.tl-marker.tl-side-right .tl-bubble::after { right:100%; border-right-color:var(--bubble-color, var(--teal)); }
.tl-marker.tl-side-left .tl-bubble::after { left:100%; border-left-color:var(--bubble-color, var(--teal)); }
```

Do NOT just statically re-derive the correct values from reading the CSS — start the app, create a test event on each side (or enough events that density-balancing puts at least one on each side — check `ev.id`/marker DOM to confirm which is which), and actually LOOK at the rendered result (screenshot or zoomed screenshot) to see which direction the arrow currently points relative to where that marker's dot actually is.

Once you've confirmed visually which sides are swapped: the fix is to swap the `right:100%`/`border-right-color` and `left:100%`/`border-left-color` pairing between the two selectors — i.e., if `.tl-side-right`'s arrow currently points the wrong way, change it to use `left:100%; border-left-color:...` instead (and correspondingly flip `.tl-side-left`'s to `right:100%; border-right-color:...`). Only make this swap if your live check actually confirms the arrows are backwards — if your live check shows they're already correct (pointing toward the dot/baseline on both sides), report that finding instead of making a speculative change.

- [ ] **Step 2: Verify manually**

After any fix, re-screenshot and confirm: for a right-side marker, the bubble's arrow points left, toward the dot and the baseline (which sit to the bubble's left). For a left-side marker, the bubble's arrow points right, toward its dot and the baseline. Test with at least 2 events (one per side) and zoom in enough to clearly see the arrow shape and its direction relative to the dot.

- [ ] **Step 3: Commit** (only if a change was needed)

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
fix(timeline): point the bubble arrow toward its dot, not away from it
EOF
)"
```
Bump `/VERSION` (check current value first, increment by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```
If your live check found the arrows were already correct, skip this step and report that finding instead — no code change, no commit needed.

---

### Task 5: Split the event modal into a read-only view mode and the existing edit mode

**Files:**
- Modify: `source/html/Base_template.html`

- [ ] **Step 1: Add view-mode CSS**

Add this new rule block after `.tl-link-row-note { ... }` (in the modal CSS section, wherever the transaction-linking styles from an earlier task end):
```css
.tl-view-content { display:flex; flex-direction:column; gap:12px; }
.tl-view-row { display:flex; flex-direction:column; gap:2px; }
.tl-view-label { font-size:0.74em; font-weight:600; color:var(--text-sub); }
.tl-view-value { font-size:0.92em; color:var(--navy); }
.tl-view-color-dot { display:inline-block; width:14px; height:14px; border-radius:50%; vertical-align:middle; margin-left:6px; }
.tl-view-tx-row { display:flex; flex-direction:column; gap:2px; padding:8px 10px; background:var(--teal-light); border-radius:7px; font-size:0.85em; }
.tl-view-tx-name-row { display:flex; justify-content:space-between; gap:8px; font-weight:600; }
.tl-view-tx-note { color:var(--text-muted); font-style:italic; font-size:0.9em; }
.tl-view-empty { color:var(--text-muted); font-size:0.85em; }
```

- [ ] **Step 2: Restructure `_tlBuildModal`'s markup to hold both a view block and the existing edit-fields block**

Find `_tlBuildModal`'s full `div.innerHTML = ...` assignment:
```javascript
    div.innerHTML =
      '<div class="tl-modal">' +
        '<button class="tl-modal-close" onclick="_tlCloseModal()">✕</button>' +
        '<h2 class="tl-modal-title" id="tl-modal-title">הוסף אירוע</h2>' +
        '<div class="tl-field"><label>שם האירוע</label><input id="tl-name-inp" type="text" maxlength="80" placeholder="למשל: תשלום מקדמה"></div>' +
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
        '<div class="tl-field"><label>תיאור (אופציונלי)</label><textarea id="tl-desc-inp" placeholder="פרטים נוספים…"></textarea></div>' +
        '<div class="tl-field"><label>צבע</label><div class="tl-color-row" id="tl-color-row"></div></div>' +
        '<div class="tl-field">' +
          '<label>קשר עסקאות (אופציונלי)</label>' +
          '<input id="tl-tx-search-inp" type="text" placeholder="חפש עסקה בסביבת התאריך…" oninput="_tlSearchTx(this.value)">' +
          '<div class="tl-tx-search-results hidden" id="tl-tx-search-results"></div>' +
          '<div class="tl-link-list" id="tl-link-list"></div>' +
        '</div>' +
        '<div class="tl-status" id="tl-status"></div>' +
        '<div class="tl-modal-actions">' +
          '<button class="tl-btn tl-btn-danger" onclick="_tlDeleteEvent()" id="tl-delete-btn" style="display:none">מחק אירוע</button>' +
          '<div class="tl-modal-actions-right">' +
            '<button class="tl-btn" onclick="_tlCloseModal()">ביטול</button>' +
            '<button class="tl-btn tl-btn-primary" onclick="_tlSubmitEvent()">שמור</button>' +
          '</div>' +
        '</div>' +
      '</div>';
```
Replace it with (adds `id="tl-modal"` to the outer div, wraps everything from the name field through the transaction-linking field in a new `#tl-edit-fields` container, adds a new `#tl-view-content` container right before it, and adds an `#tl-view-edit-btn` "Edit" button to the actions row):
```javascript
    div.innerHTML =
      '<div class="tl-modal" id="tl-modal">' +
        '<button class="tl-modal-close" onclick="_tlCloseModal()">✕</button>' +
        '<h2 class="tl-modal-title" id="tl-modal-title">הוסף אירוע</h2>' +
        '<div class="tl-view-content" id="tl-view-content" style="display:none"></div>' +
        '<div id="tl-edit-fields">' +
          '<div class="tl-field"><label>שם האירוע</label><input id="tl-name-inp" type="text" maxlength="80" placeholder="למשל: תשלום מקדמה"></div>' +
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
          '<div class="tl-field"><label>תיאור (אופציונלי)</label><textarea id="tl-desc-inp" placeholder="פרטים נוספים…"></textarea></div>' +
          '<div class="tl-field"><label>צבע</label><div class="tl-color-row" id="tl-color-row"></div></div>' +
          '<div class="tl-field">' +
            '<label>קשר עסקאות (אופציונלי)</label>' +
            '<input id="tl-tx-search-inp" type="text" placeholder="חפש עסקה בסביבת התאריך…" oninput="_tlSearchTx(this.value)">' +
            '<div class="tl-tx-search-results hidden" id="tl-tx-search-results"></div>' +
            '<div class="tl-link-list" id="tl-link-list"></div>' +
          '</div>' +
        '</div>' +
        '<div class="tl-status" id="tl-status"></div>' +
        '<div class="tl-modal-actions">' +
          '<button class="tl-btn tl-btn-danger" onclick="_tlDeleteEvent()" id="tl-delete-btn" style="display:none">מחק אירוע</button>' +
          '<div class="tl-modal-actions-right">' +
            '<button class="tl-btn tl-btn-primary" onclick="_tlSwitchToEditMode()" id="tl-view-edit-btn" style="display:none">ערוך</button>' +
            '<button class="tl-btn" onclick="_tlCloseModal()" id="tl-cancel-btn">ביטול</button>' +
            '<button class="tl-btn tl-btn-primary" onclick="_tlSubmitEvent()" id="tl-save-btn">שמור</button>' +
          '</div>' +
        '</div>' +
      '</div>';
```

- [ ] **Step 3: Add `_tlOpenViewModal`, `_tlRenderViewContent`, and `_tlSwitchToEditMode`**

Add these new functions right after `_tlOpenAddModal` (before `_tlOpenEditModal`):
```javascript
  function _tlOpenViewModal(eventId) {
    var ev = (_timelineEvents || []).find(function(e) { return e.id === eventId; });
    if (!ev) return;
    _tlEditingId = eventId;
    _tlBuildModal();
    document.getElementById('tl-modal-title').textContent = 'פרטי אירוע';
    _tlRenderViewContent(ev);
    document.getElementById('tl-view-content').style.display = '';
    document.getElementById('tl-edit-fields').style.display = 'none';
    document.getElementById('tl-status').textContent = '';
    document.getElementById('tl-delete-btn').style.display = 'none';
    document.getElementById('tl-cancel-btn').style.display = 'none';
    document.getElementById('tl-save-btn').style.display = 'none';
    document.getElementById('tl-view-edit-btn').style.display = '';
    document.getElementById('tl-overlay').classList.remove('hidden');
    var _ddInit = document.getElementById('tl-cal-dropdown');
    if (_ddInit) _ddInit.classList.add('hidden');
  }

  function _tlRenderViewContent(ev) {
    var el = document.getElementById('tl-view-content');
    if (!el) return;
    var txns = ev.transactions || [];
    var txHtml = txns.length
      ? txns.map(function(t) {
          return '<div class="tl-view-tx-row">' +
            '<div class="tl-view-tx-name-row"><span>' + _esc(t.tx_name || '') + '</span><span>' + (t.tx_date || '') + '</span></div>' +
            (t.note ? '<div class="tl-view-tx-note">' + _esc(t.note) + '</div>' : '') +
          '</div>';
        }).join('')
      : '<div class="tl-view-empty">אין עסקאות מקושרות</div>';

    el.innerHTML =
      '<div class="tl-view-row">' +
        '<span class="tl-view-label">שם האירוע</span>' +
        '<span class="tl-view-value"><span class="tl-view-color-dot" style="background:' + _esc(ev.color) + '"></span>' + _esc(ev.name) + '</span>' +
      '</div>' +
      '<div class="tl-view-row"><span class="tl-view-label">תאריך</span><span class="tl-view-value">' + (ev.event_date || '') + '</span></div>' +
      (ev.description
        ? '<div class="tl-view-row"><span class="tl-view-label">תיאור</span><span class="tl-view-value">' + _esc(ev.description) + '</span></div>'
        : '') +
      '<div class="tl-view-row"><span class="tl-view-label">עסקאות מקושרות</span>' + txHtml + '</div>';
  }

  function _tlSwitchToEditMode() {
    if (_tlEditingId == null) return;
    _tlOpenEditModal(_tlEditingId);
  }
```

- [ ] **Step 4: Make `_tlOpenEditModal` and `_tlOpenAddModal` explicitly restore edit-mode visibility**

`_tlOpenViewModal` (Step 3) hides several elements that `_tlOpenEditModal`/`_tlOpenAddModal` need to explicitly show again, since the modal is a reused singleton and could be switching FROM view mode.

In `_tlOpenAddModal`, find:
```javascript
    document.getElementById('tl-modal-title').textContent = 'הוסף אירוע';
    document.getElementById('tl-delete-btn').style.display = 'none';
    document.getElementById('tl-status').textContent = '';
```
replace with:
```javascript
    document.getElementById('tl-modal-title').textContent = 'הוסף אירוע';
    document.getElementById('tl-view-content').style.display = 'none';
    document.getElementById('tl-edit-fields').style.display = '';
    document.getElementById('tl-view-edit-btn').style.display = 'none';
    document.getElementById('tl-cancel-btn').style.display = '';
    document.getElementById('tl-save-btn').style.display = '';
    document.getElementById('tl-delete-btn').style.display = 'none';
    document.getElementById('tl-status').textContent = '';
```

In `_tlOpenEditModal`, find:
```javascript
    document.getElementById('tl-modal-title').textContent = 'ערוך אירוע';
    document.getElementById('tl-delete-btn').style.display = '';
    document.getElementById('tl-status').textContent = '';
```
replace with:
```javascript
    document.getElementById('tl-modal-title').textContent = 'ערוך אירוע';
    document.getElementById('tl-view-content').style.display = 'none';
    document.getElementById('tl-edit-fields').style.display = '';
    document.getElementById('tl-view-edit-btn').style.display = 'none';
    document.getElementById('tl-cancel-btn').style.display = '';
    document.getElementById('tl-save-btn').style.display = '';
    document.getElementById('tl-delete-btn').style.display = '';
    document.getElementById('tl-status').textContent = '';
```

- [ ] **Step 5: Wire marker clicks to open view mode instead of edit mode directly**

Find, in `_tlDrawAxis`'s marker-rendering code:
```javascript
        '<div class="tl-marker tl-side-' + side + '" style="top:' + placedTop + 'px" onclick="_tlOpenEditModal(' + ev.id + ')">' +
```
replace with:
```javascript
        '<div class="tl-marker tl-side-' + side + '" style="top:' + placedTop + 'px" onclick="_tlOpenViewModal(' + ev.id + ')">' +
```
(The empty-timeline-space click handler, `scroll.onclick`'s call to `_tlOpenAddModal(...)`, is UNCHANGED — clicking empty space still goes straight to the add form, since there's no existing event to "view" there.)

- [ ] **Step 6: Expose the two new onclick-referenced functions on `window`**

The housing script runs inside an IIFE — `_tlSwitchToEditMode` is referenced via inline `onclick` and must be exposed. `_tlOpenViewModal` is referenced via inline `onclick` in marker HTML too (replacing the old `_tlOpenEditModal` reference there) — `_tlOpenEditModal` itself is already exposed from an earlier task and must STAY exposed (it's still called directly by `_tlSwitchToEditMode`, just no longer wired to marker clicks). Find the existing exposure block (search for `window._tlOpenEditModal = _tlOpenEditModal;`) and add two new lines near it:
```javascript
  window._tlOpenViewModal    = _tlOpenViewModal;
  window._tlSwitchToEditMode = _tlSwitchToEditMode;
```

- [ ] **Step 7: Verify manually**

Start the app, create a test event with a description and at least one linked transaction with a note. Then:
1. Click the marker — confirm a clean read-only view opens: title "פרטי אירוע", the event's name (with its color dot), date, description, and the linked transaction with its note, all as plain text — NO input fields, NO color swatches, NO save/cancel/delete buttons visible. Only a "✕" close button and a "ערוך" (Edit) button should be visible in the actions row.
2. Click "ערוך" — confirm it switches, within the same modal, to the familiar editable form (title "ערוך אירוע", all fields editable, Save/Cancel/Delete all visible), pre-filled with the event's current data.
3. Make an edit and save — confirm it works exactly as before this task.
4. Close the modal and click the same marker again — confirm it opens back in VIEW mode (not stuck in edit mode from the previous interaction).
5. Click "+ הוסף אירוע" (add a new event) — confirm it goes straight to the editable add form (no view mode involved), exactly as before.
6. Click empty timeline space — confirm it also goes straight to the editable add form, prefilled with the clicked date.
7. Test an event with NO linked transactions — confirm the view mode shows "אין עסקאות מקושרות" instead of an empty section.
8. Test an event with NO description — confirm the view mode simply omits that row rather than showing an empty label.
9. No console errors throughout, in particular no `ReferenceError` for `_tlOpenViewModal`/`_tlSwitchToEditMode`.
10. Clean up the test event afterward.

- [ ] **Step 8: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
feat(timeline): add a read-only view mode for events, opened by default

Clicking a marker now opens a clean, non-editable summary (name,
date, description, linked transactions/notes) with an explicit Edit
button that switches to the existing editable form. Adding a new
event or clicking empty timeline space still goes straight to the
editable form, unchanged.
EOF
)"
```
Bump `/VERSION` (check current value first, increment by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```

---

### Task 6: Add a "Today" button and fix the calendar dropdown's positioning

**Files:**
- Modify: `source/html/Base_template.html`

- [ ] **Step 1: Diagnose the positioning bug**

`.tl-cal-dropdown` is currently `position:absolute` relative to `.tl-cal-wrap`, with `top:calc(100% + 4px); right:0`. On paper this should render directly below the date button, right-aligned to it. The likely real cause of the reported "appears on the opposite side" bug: `.tl-cal-dropdown` is a descendant of `.tl-modal`, and `.tl-modal` has `overflow-y:auto` (it's a scrollable container, `max-height:90vh`). An `overflow: auto|hidden|scroll` ancestor clips ALL descendants that visually overflow its box — including `position:absolute` children positioned relative to a DIFFERENT, nested ancestor (`.tl-cal-wrap`) — so when the dropdown would extend below the currently-scrolled-into-view portion of the modal, it gets clipped/cut off by the modal's own scroll boundary, which can look like it's rendering somewhere unexpected or "on the wrong side" once part of it is invisible.

The robust fix: make the dropdown `position:fixed` (escapes ANY ancestor's `overflow` clipping, since fixed positioning is relative to the viewport) and compute its `top`/`right` coordinates in JS from the button's actual on-screen position (via `getBoundingClientRect()`) every time it's opened, instead of relying on a static CSS anchor.

- [ ] **Step 2: Update the CSS**

Find:
```css
.tl-cal-dropdown {
  position:absolute; z-index:10; top:calc(100% + 4px); right:0;
  width:260px; background:var(--white); border:1.5px solid var(--teal);
  border-radius:10px; box-shadow:var(--shadow-md); padding:10px;
}
```
Replace with:
```css
.tl-cal-dropdown {
  position:fixed; z-index:750;
  width:260px; background:var(--white); border:1.5px solid var(--teal);
  border-radius:10px; box-shadow:var(--shadow-md); padding:10px;
}
```
(`z-index:750` is above `.tl-overlay`'s `z-index:700`, so the dropdown reliably paints above the modal it's opened from. `top`/`right` are no longer set in CSS — they're computed and set inline by JS every time the dropdown opens, per Step 3.)

- [ ] **Step 3: Compute the dropdown's position from the button's real screen location**

Find `_tlCalToggle`:
```javascript
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
```
Replace with:
```javascript
  function _tlCalToggle() {
    var dd = document.getElementById('tl-cal-dropdown');
    var btn = document.getElementById('tl-date-btn');
    if (!dd || !btn) return;
    if (dd.classList.contains('hidden')) {
      var inp = document.getElementById('tl-date-inp');
      var base = (inp && inp.value) ? new Date(inp.value) : new Date();
      if (isNaN(base)) base = new Date();
      _tlCalViewYear = base.getFullYear();
      _tlCalViewMonth = base.getMonth();
      _tlRenderCalendar();
      var rect = btn.getBoundingClientRect();
      dd.style.top = (rect.bottom + 4) + 'px';
      dd.style.right = (window.innerWidth - rect.right) + 'px';
      dd.style.left = 'auto';
      dd.classList.remove('hidden');
    } else {
      dd.classList.add('hidden');
    }
  }
```

- [ ] **Step 4: Add a "Today" button to the calendar header**

Add this CSS right after the `.tl-cal-title { ... }` rule:
```css
.tl-cal-today-row { display:flex; justify-content:center; margin-bottom:6px; }
.tl-cal-today-btn {
  font-size:0.72em; font-weight:700; color:var(--teal); background:var(--teal-light);
  border:none; border-radius:14px; padding:4px 14px; cursor:pointer; font-family:inherit;
}
.tl-cal-today-btn:hover { background:var(--teal); color:#fff; }
```

In `_tlRenderCalendar`, find:
```javascript
    var html = '<div class="tl-cal-header">' +
      '<button type="button" class="tl-cal-nav-btn" onclick="_tlCalNextMonth()">›</button>' +
      '<span class="tl-cal-title">' + TL_MONTH_NAMES[_tlCalViewMonth] + ' ' + _tlCalViewYear + '</span>' +
      '<button type="button" class="tl-cal-nav-btn" onclick="_tlCalPrevMonth()">‹</button>' +
      '</div>' +
      '<div class="tl-cal-grid">';
```
replace with:
```javascript
    var html = '<div class="tl-cal-today-row"><button type="button" class="tl-cal-today-btn" onclick="_tlCalGoToday()">היום</button></div>' +
      '<div class="tl-cal-header">' +
      '<button type="button" class="tl-cal-nav-btn" onclick="_tlCalNextMonth()">›</button>' +
      '<span class="tl-cal-title">' + TL_MONTH_NAMES[_tlCalViewMonth] + ' ' + _tlCalViewYear + '</span>' +
      '<button type="button" class="tl-cal-nav-btn" onclick="_tlCalPrevMonth()">‹</button>' +
      '</div>' +
      '<div class="tl-cal-grid">';
```

Add this new function right after `_tlCalPick`:
```javascript
  function _tlCalGoToday() {
    var d = new Date();
    _tlCalPick(_tlFmtLocalDate(d.getFullYear(), d.getMonth(), d.getDate()));
  }
```

- [ ] **Step 5: Expose `_tlCalGoToday` on `window`**

Find the existing exposure block (search for `window._tlCalPick`) and add a line near it:
```javascript
  window._tlCalGoToday = _tlCalGoToday;
```

- [ ] **Step 6: Verify manually**

Start the app, open the housing panel's Timeline tab, click "+ הוסף אירוע". Confirm:
1. Clicking the date button opens the calendar DIRECTLY below the button, aligned with it — not clipped, not appearing detached, not appearing on the opposite side of the modal.
2. Scroll the modal itself (if it's tall enough to scroll, e.g. after linking several transactions) and open the calendar again — confirm it still correctly positions itself relative to the button's CURRENT on-screen position (not the button's original unscrolled position), since it's now computed fresh via `getBoundingClientRect()` each time.
3. A "היום" (Today) button appears at the top of the calendar dropdown, above the month header.
4. Clicking "היום" immediately selects today's actual date, updates the button text, and closes the dropdown — same as clicking today's date cell directly.
5. Click-outside-to-close still works correctly with the new fixed-position dropdown.
6. Re-verify there's no timezone off-by-one on the "Today" button specifically (it should use the same `_tlFmtLocalDate` helper as everything else, not `.toISOString()`) — confirm the date it selects matches the actual local calendar day.
7. Test in the edit-mode flow too (open an existing event via the view mode's "ערוך" button from Task 5, then open its date picker) to confirm the dropdown positioning and Today button work there as well.
8. Clean up any test events created.

- [ ] **Step 7: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
feat(timeline): add a Today button and fix date-picker dropdown clipping

The dropdown was position:absolute inside a scrollable modal, so it
could get clipped by the modal's own overflow boundary. Switching it
to position:fixed with coordinates computed from the button's actual
on-screen position keeps it correctly anchored regardless of modal
scroll state.
EOF
)"
```
Bump `/VERSION` (check current value first, increment by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```

---

### Final: End-to-end verification

After all 6 tasks land, do one last combined pass: open the housing panel, confirm the floating tabs, glow scrolling, centered markers, correctly-pointing bubble arrows, view/edit modal split, and the improved date picker all work together without regressions, on both desktop and mobile widths, with no console errors. Clean up all test data. No separate commit needed unless this pass finds something — if it does, fix it following the same patterns as the tasks above and commit with a version bump.
