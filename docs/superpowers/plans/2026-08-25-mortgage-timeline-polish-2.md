# Mortgage Timeline — Polish Round 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three fixes to the vertical timeline: make the baseline/scroll content always fill the entire visible axis box (no blank trailing space, no tick labels appearing disconnected from the line), add a small directional arrowhead at the top of the baseline, and replace the full-width "glow" scroll indicators — which have a real bug where they scroll away with the content instead of staying pinned to the box's edges — with small, subtle sticky arrow icons.

**Architecture:** All changes are in `source/html/Base_template.html` only. No backend changes.

**Root cause of the two real bugs being fixed here:**
1. **Baseline/blank-space bug:** `#tl-axis-scroll`'s height is set in JS purely from the computed date range (`totalDays * _tlPxPerDay`). When the visible event date range is short, that computed height can be LESS than `.tl-axis-wrap`'s fixed CSS height (560px desktop / 440px mobile). Since `.tl-baseline` is `top:0;bottom:0` relative to `#tl-axis-scroll` (not the wrap), the line and every tick/marker only occupy the top portion of the box, leaving the rest of the visible box as literal blank space below the last tick — which is exactly what reads as "the line doesn't reach it, it just stands there."
2. **Scroll-glow bug:** `#tl-scroll-glow-top`/`#tl-scroll-glow-bottom` are `position:absolute` DIRECT CHILDREN of `.tl-axis-wrap`, which is itself the `overflow-y:auto` scrolling element. Per standard CSS behavior, absolutely-positioned descendants whose containing block is the scrolling element itself scroll along with that element's content — they do NOT stay pinned to the visible viewport edges the way the feature intended. This is why the user observes the glow "staying at the same location" relative to content while scrolling, instead of staying fixed at the box's top/bottom regardless of scroll position.

**Note on verification:** No automated test suite exists in this repo. Verification is manual: run the app, log in with the local `.env` `ADMIN_PASSWORD` (don't echo it), and check behavior in a browser. A prior round in this branch found that `position:fixed`/`position:absolute`-in-scrolling-container bugs are genuinely invisible to static CSS reasoning — treat live scroll testing as mandatory for Task 3 specifically, not optional.

---

### Task 1: Make the baseline/scroll content always fill the visible axis box

**Files:**
- Modify: `source/html/Base_template.html`

- [ ] **Step 1: Clamp the scroll content's height to at least the wrap's visible height**

Find, in `_tlDrawAxis`:
```javascript
    var totalDays = Math.max(1, Math.round((maxD - minD) / _tlDayMs()));
    var heightPx = totalDays * _tlPxPerDay;
    scroll.style.height = heightPx + 'px';
```
Replace with:
```javascript
    var totalDays = Math.max(1, Math.round((maxD - minD) / _tlDayMs()));
    var heightPx = totalDays * _tlPxPerDay;
    var wrapEl = document.getElementById('tl-axis-wrap');
    if (wrapEl && wrapEl.clientHeight > heightPx) heightPx = wrapEl.clientHeight;
    scroll.style.height = heightPx + 'px';
```
(`#tl-axis-wrap` is already a real element in the DOM at this point — `_renderTimeline` builds its markup via `innerHTML` before calling `_tlDrawAxis`, and the wrap's height is a fixed CSS value (560px/440px), so `clientHeight` is reliably readable synchronously here, no layout timing issue. This guarantees the scrollable content — and therefore `.tl-baseline`, which is `top:0;bottom:0` relative to this same element — always spans at least the full visible box, eliminating any blank trailing space below the last real tick/marker. When the actual date-range content is taller than the box (the common case), this clamp has no effect and scrolling works exactly as before.)

- [ ] **Step 2: Verify manually**

Start the app, log in (repo's own `.env` `ADMIN_PASSWORD`, don't echo it), open the housing panel's Timeline tab. Test with a SHORT date range (e.g. delete all events except one dated close to today, so the computed content height is small):
1. Confirm the vertical baseline now extends all the way to the bottom of the visible axis box — no blank white space below it.
2. Confirm every visible month tick label has the line running through/past it — none should appear "floating" disconnected from the baseline.
3. Now test with a LONG date range (several events spanning many months, or zoom in a lot via the `+` button) to confirm normal scrolling still works correctly and nothing regressed — the baseline should still correctly extend the full (now-scrollable) content height, and scrolling to the bottom should still show the baseline ending at the actual last tick, not artificially extended further than the real data.
4. Resize to mobile width (375px) and repeat the short-range check (box height is 440px there, not 560px).

- [ ] **Step 3: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
fix(timeline): make the baseline fill the full axis box, not just the data range

#tl-axis-scroll's height came only from the computed date-range span,
which could be shorter than the axis box's fixed CSS height, leaving
blank space below the last tick with the baseline appearing to stop
short of it. Clamp the scroll content's height to at least the box's
visible clientHeight.
EOF
)"
```
Bump `/VERSION` (check current value first, increment by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```

---

### Task 2: Add a directional arrowhead at the top of the baseline

**Files:**
- Modify: `source/html/Base_template.html`

- [ ] **Step 1: Add the arrowhead CSS**

Find:
```css
.tl-baseline { position:absolute; top:0; bottom:0; right:50%; width:3px; margin-right:-1.5px; background:var(--navy); opacity:.18; border-radius:2px; }
```
Add this new rule immediately after it:
```css
.tl-baseline::before {
  content:''; position:absolute; top:-9px; left:50%; transform:translateX(-50%);
  width:0; height:0;
  border-left:6px solid transparent; border-right:6px solid transparent;
  border-bottom:9px solid var(--navy); opacity:.55;
}
```
(`.tl-baseline`'s own box IS the 3px-wide line, so centering the triangle within it via `left:50%; transform:translateX(-50%)` is more reliable than trying to reuse the parent's `right:50%; margin-right` trick at a different width. The triangle sits just above the baseline's top edge, pointing upward — since "up" is where the newest/most-recent events are (per the vertical redesign's newest-at-top convention), this visually shows which direction the timeline is headed.)

- [ ] **Step 2: Verify manually**

Start the app, open the housing panel's Timeline tab. Confirm a small upward-pointing triangle/arrowhead renders at the very top of the vertical baseline, subtly visible (not overly bold — it uses the same `opacity` weight as similar existing elements), centered on the line. Scroll down and confirm the arrowhead scrolls out of view along with the top of the content (it's not meant to stay sticky — it marks the actual top of the timeline's data, not a fixed UI chrome element).

- [ ] **Step 3: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
feat(timeline): add a directional arrowhead at the top of the baseline
EOF
)"
```
Bump `/VERSION` (check current value first, increment by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```

---

### Task 3: Replace the scroll glow with small, correctly-pinned scroll arrows

**Files:**
- Modify: `source/html/Base_template.html`

- [ ] **Step 1: Remove the old glow CSS and add the new arrow-icon CSS**

Find and DELETE this entire block (added in a prior round):
```css
.tl-scroll-glow {
  position:absolute; right:0; left:0; height:34px; pointer-events:none;
  z-index:5; opacity:0; transition:opacity .2s;
}
.tl-scroll-glow-top { top:0; background:linear-gradient(to bottom, rgba(30,157,139,.35), transparent); }
.tl-scroll-glow-bottom { bottom:0; background:linear-gradient(to top, rgba(30,157,139,.35), transparent); }
.tl-scroll-glow.show { opacity:1; animation:tlGlowPulse 1.6s ease-in-out infinite; }
@keyframes tlGlowPulse { 0%,100% { opacity:.55; } 50% { opacity:1; } }
```
Replace it with:
```css
.tl-scroll-arrow-wrap { position:sticky; height:0; z-index:6; pointer-events:none; }
.tl-scroll-arrow-wrap.tl-arrow-top { top:0; }
.tl-scroll-arrow-wrap.tl-arrow-bottom { bottom:0; }
.tl-scroll-arrow {
  position:absolute; right:10px; width:24px; height:24px; border-radius:50%;
  background:var(--white); box-shadow:0 2px 8px rgba(0,0,0,.16);
  display:flex; align-items:center; justify-content:center;
  color:var(--teal); font-size:0.75em; line-height:1;
  opacity:0; transition:opacity .2s;
}
.tl-scroll-arrow-wrap.tl-arrow-top .tl-scroll-arrow { top:8px; }
.tl-scroll-arrow-wrap.tl-arrow-bottom .tl-scroll-arrow { bottom:8px; }
.tl-scroll-arrow.show { opacity:.85; }
.tl-scroll-arrow-wrap.tl-arrow-top .tl-scroll-arrow.show { animation:tlArrowPulseUp 1.8s ease-in-out infinite; }
.tl-scroll-arrow-wrap.tl-arrow-bottom .tl-scroll-arrow.show { animation:tlArrowPulseDown 1.8s ease-in-out infinite; }
@keyframes tlArrowPulseUp { 0%,100% { opacity:.5; transform:translateY(0); } 50% { opacity:1; transform:translateY(-3px); } }
@keyframes tlArrowPulseDown { 0%,100% { opacity:.5; transform:translateY(0); } 50% { opacity:1; transform:translateY(3px); } }
```
(Why `position:sticky` on a zero-height wrapper instead of `position:absolute`: this is the actual fix for the "scrolls with content" bug — `position:sticky` keeps an element pinned to the edge of its nearest scrolling ancestor's VIEWPORT as that ancestor scrolls, rather than being fixed to a point within the scrolled content. Giving the sticky wrapper `height:0` means it doesn't add any extra scrollable height to the content — the actual visible circle icon is an absolutely-positioned child INSIDE that zero-height sticky wrapper, so it renders at the sticky wrapper's pinned position without affecting layout. `right:10px` places the icon near the LEFT visual edge of the box in this RTL page — note this app's RTL panel means `right:10px` positions it toward what reads as the LEFT side when the panel is read right-to-left. If the on-screen result doesn't match "left side" during Step 3's manual check, swap to `left:10px` there.)

- [ ] **Step 2: Update the markup**

In `_renderTimeline`, find:
```javascript
      '<div class="tl-axis-wrap' + (_tlMinimizeMode ? ' tl-minimize-mode' : '') + '" id="tl-axis-wrap">' +
        '<div class="tl-axis-scroll" id="tl-axis-scroll"></div>' +
        '<div class="tl-scroll-glow tl-scroll-glow-top" id="tl-scroll-glow-top"></div>' +
        '<div class="tl-scroll-glow tl-scroll-glow-bottom" id="tl-scroll-glow-bottom"></div>' +
      '</div>';
```
Replace with:
```javascript
      '<div class="tl-axis-wrap' + (_tlMinimizeMode ? ' tl-minimize-mode' : '') + '" id="tl-axis-wrap">' +
        '<div class="tl-scroll-arrow-wrap tl-arrow-top"><div class="tl-scroll-arrow" id="tl-scroll-arrow-top">▲</div></div>' +
        '<div class="tl-axis-scroll" id="tl-axis-scroll"></div>' +
        '<div class="tl-scroll-arrow-wrap tl-arrow-bottom"><div class="tl-scroll-arrow" id="tl-scroll-arrow-bottom">▼</div></div>' +
      '</div>';
```
(Order matters for `position:sticky`: the top-sticky wrapper must appear BEFORE the scrollable content in DOM order, and the bottom-sticky wrapper AFTER, for each to correctly stick to its respective edge as the container scrolls.)

- [ ] **Step 3: Update the JS — rename the functions/targets and keep the same wiring**

Find `_tlUpdateScrollGlow`/`_tlWireScrollGlow`:
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
Replace with:
```javascript
  function _tlUpdateScrollArrows() {
    var wrap = document.getElementById('tl-axis-wrap');
    var top = document.getElementById('tl-scroll-arrow-top');
    var bottom = document.getElementById('tl-scroll-arrow-bottom');
    if (!wrap || !top || !bottom) return;
    top.classList.toggle('show', wrap.scrollTop > 4);
    bottom.classList.toggle('show', wrap.scrollTop + wrap.clientHeight < wrap.scrollHeight - 4);
  }

  function _tlWireScrollArrows() {
    var wrap = document.getElementById('tl-axis-wrap');
    if (!wrap) return;
    wrap.addEventListener('scroll', _tlUpdateScrollArrows);
    _tlUpdateScrollArrows();
  }
```
Then find and update BOTH call sites — in `_renderTimeline`:
```javascript
    _tlDrawAxis(events);
    _tlWireScrollGlow();
  }
```
becomes:
```javascript
    _tlDrawAxis(events);
    _tlWireScrollArrows();
  }
```
and in `_tlZoom`:
```javascript
    _tlDrawAxis(_timelineEvents || []);
    _tlUpdateScrollGlow();
  }
```
becomes:
```javascript
    _tlDrawAxis(_timelineEvents || []);
    _tlUpdateScrollArrows();
  }
```
(Same show/hide LOGIC as before — only the target element IDs and function names changed, since the underlying "is there more to scroll in this direction" calculation was already correct; only the CSS positioning mechanism was the actual bug.)

- [ ] **Step 4: Verify manually — this is the critical live check for this task**

Start the app, log in, open the housing panel's Timeline tab with enough events (or zoom in enough) that the axis is taller than its visible box.
1. At the very top of the scroll range: confirm only the BOTTOM arrow icon shows (small, subtle, near the left side of the box — not a full-width glow band).
2. Scroll down slowly and WATCH the arrow icons carefully — confirm they STAY VISUALLY FIXED at the top/bottom edges of the visible box as you scroll (this is the actual bug being fixed — in the old version they would drift/scroll away with the content; confirm that no longer happens).
3. Scroll to the middle — both arrows visible, both still pinned to the box edges, not to any particular piece of content.
4. Scroll to the bottom — only the TOP arrow shows, still pinned to the top edge of the box.
5. Confirm the arrows are visually subtle/gentle (small circular icon, soft shadow, gentle pulse) — not a large glowing gradient band across the whole width.
6. Zoom in/out and confirm arrow visibility still updates correctly immediately (via the preserved `_tlUpdateScrollArrows()` call in `_tlZoom`).
7. Confirm the arrows sit near the LEFT side of the box visually (check this explicitly since the CSS note in Step 1 flags this as worth confirming given RTL — if they render on the right instead, swap `right:10px`→`left:10px` in both `.tl-scroll-arrow` rules and re-verify).
8. No console errors, in particular no leftover references to the old `_tlUpdateScrollGlow`/`_tlWireScrollGlow`/`tl-scroll-glow-*` names anywhere (grep the file to confirm the rename was applied everywhere, not just in the two call sites shown above).

- [ ] **Step 5: Commit**

```bash
git add source/html/Base_template.html
git commit -m "$(cat <<'EOF'
fix(timeline): pin scroll arrows to the box edges instead of the content

The old glow indicators were position:absolute direct children of the
scrolling element itself, so they scrolled away with the content
instead of staying fixed at the visible box's top/bottom edges.
Replaced with small circular arrow icons in a zero-height
position:sticky wrapper, which correctly stays pinned to the
scrollport regardless of scroll position, and is visually much
subtler than the previous full-width glow band per user feedback.
EOF
)"
```
Bump `/VERSION` (check current value first, increment by 1) and commit:
```bash
git add VERSION
git commit -m "chore: bump version to <new version>"
```

---

### Final: End-to-end verification, then push

After all 3 tasks land, do one last combined pass: open the housing panel's Timeline tab, confirm the baseline always fills the box (short and long date ranges), the arrowhead shows at the top, and the scroll arrows stay correctly pinned while scrolling — all together, no regressions, no console errors, on both desktop and mobile widths. Clean up any test data. Then commit the plan doc itself and push the branch to `origin/Dev/Timeline`, since the user is away and asked for changes to be pushed when done — do not wait for further confirmation before pushing.
