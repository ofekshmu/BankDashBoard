/* Side-menu links shared by every page — the one place to add, rename or reorder a menu item.
 *
 * A page leaves its list empty, <div class="sidebar-scroll" data-nav="KEY"></div>, and loads
 * <script src="/nav.js"></script> right after the sidebar. The script runs synchronously, so
 * the page's own scripts further down already find the links (e.g. #nav-bills-dot).
 *   data-nav="<item key>"  that item is marked as the current page
 *   data-nav=""            no current item (the landing page)
 *   data-nav="monthly-page" the monthly analysis page: its first two items switch panels in
 *                          place (#nav-overview / #nav-accounts, as its script expects)
 */
(function () {
  var ITEMS = [
    ['monthly', 'ניתוח חודשי', '/monthly'],
    '-',
    ['accounts', 'חשבונות', '/accounts'],
    ['cards', 'כרטיסים', '/card-analysis'],
    ['housing', 'דיור', '/housing'],
    ['timeline', 'ציר זמן', '/timeline'],
    ['organizer', 'ארגונית', '/organizer'],
    ['bills', 'מעקב חשבונות', '/bills'],
    ['categories', 'ניתוח קטגוריאלי', '/categories'],
    ['search', 'חיפוש', '/search'],
    ['spotify', 'Spotify Tracker', '/spotify'],
    ['plants', 'מעקב עציצים', '/plants'],
    ['recurring', 'חיובים חוזרים', '/recurring'],
    '-',
    ['tagger', 'תייגן', '/tagger'],
    ['files', 'קבצים', '/files']
  ];
  var PANEL_BUTTONS = { monthly: 'nav-overview', accounts: 'nav-accounts' };

  /* Rolling number ("roll, don't jump"): the digits of a figure turn like an odometer to their new values,
   * one digit after the other (100ms apart), each easing out with a small overshoot (~650ms). Unchanged
   * digits stay still. rollNumber(el, "1,234₪", key): `key` remembers the last value of a figure whose element
   * is rebuilt on every render, so only what changed rolls (the first time every digit rolls up from 0).
   * Text without digits is just set. Skipped under prefers-reduced-motion. */
  var RN_CSS =
    '.rn{display:inline-block;direction:ltr;unicode-bidi:isolate;white-space:nowrap;font-variant-numeric:tabular-nums}' +
    '.rn-d{display:inline-block;height:1.2em;line-height:1.2em;overflow:hidden;vertical-align:top}' +
    '.rn-c{display:block}.rn-c>i{display:block;height:1.2em;font-style:normal}' +
    '.rn-s{display:inline-block;height:1.2em;line-height:1.2em;white-space:pre;vertical-align:top}';
  var RN_PREV = {};
  window.rollNumber = function (el, text, key) {
    if (!el) return;
    text = String(text == null ? '' : text);
    var prevText = key ? RN_PREV[key] : el._rnText;
    if (key) RN_PREV[key] = text; else el._rnText = text;
    var chars = Array.from(text);
    var isDigit = function (c) { return c >= '0' && c <= '9'; };
    var digits = chars.filter(isDigit);
    el.setAttribute('aria-label', text);
    if (!digits.length) { el.textContent = text; return; }
    if (prevText === text && el.querySelector('.rn')) return;                 // nothing changed
    if (!document.getElementById('rn-style')) {
      var st = document.createElement('style');
      st.id = 'rn-style';
      st.textContent = RN_CSS;
      document.head.appendChild(st);
    }
    var prevDigits = prevText ? Array.from(prevText).filter(isDigit) : [];
    var animate = !!el.animate && !(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
    var wrap = document.createElement('span');
    wrap.className = 'rn';
    wrap.setAttribute('aria-hidden', 'true');
    var di = 0, order = 0;
    chars.forEach(function (c) {
      if (!isDigit(c)) {
        var s = document.createElement('span');
        s.className = 'rn-s';
        s.textContent = c;
        wrap.appendChild(s);
        return;
      }
      var to = +c;
      var fromIdx = prevDigits.length - (digits.length - di);                   // aligned from the right
      var from = fromIdx >= 0 ? +prevDigits[fromIdx] : 0;
      di++;
      var d = document.createElement('span');
      d.className = 'rn-d';
      var col = document.createElement('span');
      col.className = 'rn-c';
      col.innerHTML = '0123456789'.replace(/./g, '<i>$&</i>');
      col.style.transform = 'translateY(' + (-to * 10) + '%)';
      d.appendChild(col);
      wrap.appendChild(d);
      if (animate && from !== to) {
        col.animate([{ transform: 'translateY(' + (-from * 10) + '%)' }, { transform: 'translateY(' + (-to * 10) + '%)' }],
          { duration: 650, delay: Math.min(order, 6) * 100, easing: 'cubic-bezier(.34,1.35,.64,1)', fill: 'backwards' });
        order++;
      }
    });
    el.textContent = '';
    el.appendChild(wrap);
  };

  /* The success mark every "done" message uses: the circle draws, then the tick (styles in motion.css). */
  window.okDraw = function () {
    return '<svg class="ok-draw" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M7.5 12.5l3 3 6-6.5"/></svg>';
  };

  /* Items rise one after another each time the menu opens: one animation (0.4s), each item waits 40ms x its
   * position (--i, capped at 12). Same rule as the lists in design-system.css, kept here because this
   * script is on every page. */
  var STAGGER_CSS =
    '@keyframes nav-rise{from{opacity:0;transform:translateY(8px)}}' +
    '.sidebar.open .sidebar-scroll>.nav-item,.sidebar.open .sidebar-scroll>.cp-field{' +
    'animation:nav-rise .4s backwards;animation-delay:calc(var(--i,0)*40ms)}' +
    '@media (prefers-reduced-motion:reduce){.sidebar.open .sidebar-scroll>.nav-item,' +
    '.sidebar.open .sidebar-scroll>.cp-field{animation:none}}';
  var STAGGER_MAX = 12;

  /** Open the last viewed month directly (the server's /monthly picks the latest one). */
  function toLastMonth(e) {
    try {
      var k = localStorage.getItem('lv_month');
      if (k) { e.preventDefault(); location.href = '/general/' + k; }
    } catch (_) {}
  }

  /** On the monthly page: switch panels in place, as the page's own buttons did. */
  function panelButton(key) {
    var b = document.createElement('button');
    b.id = PANEL_BUTTONS[key];
    b.onclick = function () {
      if (key === 'monthly') window._navToMonthly(this); else window.showPanel('accounts', this);
      window.closeNav();
    };
    return b;
  }

  function render(box) {
    var current = box.getAttribute('data-nav') || '';
    var spa = current === 'monthly-page';
    var order = 0;
    function stagger(el) { el.style.setProperty('--i', Math.min(order++, STAGGER_MAX)); }
    ['stagger', 'motion'].forEach(function (name) {   // lists/menus entrance, expand/collapse — every page
      if (document.getElementById(name + '-css')) return;
      var lk = document.createElement('link');
      lk.id = name + '-css';
      lk.rel = 'stylesheet';
      lk.href = '/' + name + '.css';
      document.head.appendChild(lk);
    });
    if (!document.getElementById('nav-stagger-style')) {
      var st = document.createElement('style');
      st.id = 'nav-stagger-style';
      st.textContent = STAGGER_CSS;
      document.head.appendChild(st);
    }
    box.textContent = '';
    ITEMS.forEach(function (item) {
      if (item === '-') {
        var sep = document.createElement('div');
        sep.className = 'nav-sep';
        box.appendChild(sep);
        return;
      }
      var key = item[0], el;
      if (spa && PANEL_BUTTONS[key]) {
        el = panelButton(key);
      } else {
        el = document.createElement('a');
        el.href = item[2];
        if (key === 'monthly') el.addEventListener('click', toLastMonth);
      }
      el.className = 'nav-item' + (key === current ? ' active' : '');
      el.textContent = item[1];
      stagger(el);
      if (key === 'bills') {           // pages light this dot when a bill needs attention
        el.id = 'nav-bills-link';
        var dot = document.createElement('span');
        dot.className = 'nav-alert-dot';
        dot.id = 'nav-bills-dot';
        dot.style.display = 'none';
        el.appendChild(dot);
      }
      box.appendChild(el);
    });
    var gearSep = document.createElement('div');            // settings stand apart from the page links
    gearSep.className = 'nav-sep';
    box.appendChild(gearSep);
    var gear = document.createElement('button');            // opens the settings sub-menu in place of the links
    gear.type = 'button';
    gear.className = 'nav-item nav-settings';
    gear.textContent = 'הגדרות';
    gear.addEventListener('click', function () { showSettings(box); });
    stagger(gear);
    box.appendChild(gear);
    var sep = document.createElement('div');
    sep.className = 'nav-sep';
    box.appendChild(sep);
    var copy = copyLinkButton();
    stagger(copy);
    box.appendChild(copy);
  }

  /* Copy-link field: the address with a copy chip. On tap the chip morphs copy glyph → circle with a
   * progress ring → blue check, the address is highlighted like a selection and a "הועתק!" bubble pops
   * up above the chip; after a hold everything eases back. Timings (ms): press 0, ring 270, done 500,
   * hold 1600, reset 330. */
  var COPY_CSS =
    '.cp-field{position:relative;direction:ltr;display:flex;align-items:center;justify-content:space-between;' +
    'height:36px;margin:32px 12px 6px;padding:0 4px 0 10px;background:#34393c;border:1px solid rgba(52,178,123,.55);' +
    'border-radius:10px;cursor:pointer;user-select:none;-webkit-tap-highlight-color:transparent;outline:none}' +
    '.cp-field:focus-visible{box-shadow:0 0 0 2px #34b27b}' +
    '.cp-url{font:500 12.5px/1.2 "Segoe UI",Arial,sans-serif;letter-spacing:.02em;color:#eef1ef;padding:2px 4px;border-radius:4px;' +
    'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;transition:background .2s,color .2s}' +
    '.cp-field.ring .cp-url{background:rgba(52,178,123,.35);color:#fff}' +
    '.cp-chip{position:relative;flex:none;width:28px;height:28px;border-radius:8px;background:rgba(255,255,255,.12);color:#d5dbd8;' +
    'transition:transform .15s}' +
    '.cp-chip:before{content:"";position:absolute;inset:0;border-radius:8px;opacity:0;transition:opacity .15s;' +
    'background:linear-gradient(180deg,#43c98c,#34b27b 60%,#25905f)}' +
    '.cp-field.done .cp-chip:before{opacity:1}' +
    '.cp-chip svg{position:absolute;inset:0;width:28px;height:28px;fill:none;overflow:visible}' +
    '.cp-glyph{stroke:currentColor;stroke-width:1.8;transition:opacity .2s,transform .2s;transform-origin:50% 50%}' +
    '.cp-field.press .cp-glyph{opacity:0;transform:scale(.55)}' +
    '.cp-disc{opacity:0;transition:opacity .2s}' +
    '.cp-field.press .cp-disc{opacity:1}' +
    '.cp-field.done .cp-disc{opacity:0;transition-duration:.1s}' +
    '.cp-arc{stroke:#43c98c;stroke-width:2;stroke-linecap:round;stroke-dasharray:88;stroke-dashoffset:88;' +
    'transform:rotate(-90deg);transform-origin:17px 17px}' +
    '.cp-field.ring .cp-arc{stroke-dashoffset:0;transition:stroke-dashoffset .23s ease-out}' +
    '.cp-check{stroke:#fff;stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:20;stroke-dashoffset:20;' +
    'transition:stroke-dashoffset .17s ease-out}' +
    '.cp-okc{stroke:#fff;stroke-width:1.8;stroke-dasharray:76;stroke-dashoffset:76;transition:stroke-dashoffset .3s ease-out}' +
    '.cp-field.done .cp-okc{stroke-dashoffset:0}' +
    '.cp-field.done .cp-check{stroke-dashoffset:0;transition-delay:.3s}' +
    '.cp-halo{position:absolute;inset:-4px;border-radius:11px;border:2px solid rgba(52,178,123,.6);opacity:0;' +
    'transform:scale(.8);transition:opacity .25s,transform .25s}' +
    '.cp-field.press .cp-halo{opacity:1;transform:scale(1)}' +
    '.cp-field.done .cp-halo{opacity:0;transition-delay:.25s}' +
    '.cp-tip{direction:rtl;box-shadow:0 2px 8px rgba(0,0,0,.3);position:absolute;right:0;bottom:calc(100% + 8px);padding:5px 10px;border-radius:8px;background:#8a9190;color:#26292b;' +
    'font:700 12px/1.2 "Segoe UI",Arial,sans-serif;white-space:nowrap;pointer-events:none;opacity:0;' +
    'transform:scale(.25);transform-origin:calc(100% - 18px) 100%;' +
    'transition:transform .2s ease-in,opacity .2s ease-in,background .2s}' +
    '.cp-tip:after{content:"";position:absolute;top:100%;right:13px;border:5px solid transparent;border-top-color:#8a9190;transition:border-color .2s}' +
    '.cp-field.ring .cp-tip{opacity:1}' +
    '.cp-field.done .cp-tip{opacity:1;transform:scale(1);background:#fff;' +
    'transition:transform .15s cubic-bezier(.34,1.56,.64,1),opacity .1s,background .1s}' +
    '.cp-field.done .cp-tip:after{border-top-color:#fff;transition-duration:.1s}' +
    '.cp-field.fail .cp-chip:before{opacity:0}.cp-field.fail .cp-check{stroke-dashoffset:20}.cp-field.fail .cp-okc{stroke-dashoffset:76}' +
    '.cp-field.fail .cp-tip{background:#f2c9c9}.cp-field.fail .cp-tip:after{border-top-color:#f2c9c9}' +
    '@media (prefers-reduced-motion:reduce){.cp-field *,.cp-field *:before{transition-duration:.01s!important;transition-delay:0s!important}}';

  function copyText(text, cb) {
    function fallback() {
      var t = document.createElement('textarea');
      t.value = text;
      t.style.position = 'fixed';
      t.style.opacity = '0';
      document.body.appendChild(t);
      t.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (_) {}
      document.body.removeChild(t);
      cb(ok);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { cb(true); }, fallback);
    } else fallback();
  }

  /** The app's address in a field with a copy chip (the animation described above). */
  function copyLinkButton() {
    if (!document.getElementById('cp-style')) {
      var st = document.createElement('style');
      st.id = 'cp-style';
      st.textContent = COPY_CSS;
      document.head.appendChild(st);
    }
    var f = document.createElement('div');
    f.className = 'cp-field';
    f.setAttribute('role', 'button');
    f.setAttribute('tabindex', '0');
    f.setAttribute('aria-label', 'העתק קישור לאפליקציה');
    f.innerHTML =
      '<span class="cp-url"></span>' +
      '<span class="cp-chip">' +
        '<svg class="cp-glyph" viewBox="0 0 34 34"><rect x="13" y="8" width="12" height="12" rx="3"/><rect x="8" y="13" width="12" height="12" rx="3"/></svg>' +
        '<svg viewBox="0 0 34 34"><circle class="cp-disc" cx="17" cy="17" r="11" fill="rgba(197,208,224,.35)"/>' +
        '<circle class="cp-arc" cx="17" cy="17" r="14"/></svg>' +
        '<svg viewBox="0 0 34 34"><circle class="cp-okc" cx="17" cy="17" r="12" transform="rotate(-90 17 17)"/><path class="cp-check" d="M11 17.5l4 4 8-8.5"/></svg>' +
        '<span class="cp-halo"></span>' +
      '</span>' +
      '<span class="cp-tip" aria-live="polite">הועתק!</span>';
    f.querySelector('.cp-url').textContent = location.host;
    var tip = f.querySelector('.cp-tip');
    var busy = false;

    function run() {
      if (busy) return;
      busy = true;
      var link = location.origin + '/';
      f.className = 'cp-field press';
      copyText(link, function (ok) {
        setTimeout(function () { f.classList.add('ring'); }, 270);
        setTimeout(function () {
          if (ok) f.classList.add('done');
          else { tip.textContent = 'לא הועתק'; f.classList.add('done', 'fail'); }
        }, 500);
        setTimeout(function () { f.className = 'cp-field'; }, 2300);
        setTimeout(function () { tip.textContent = 'הועתק!'; busy = false; }, 2650);
      });
    }
    f.addEventListener('click', run);
    f.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); run(); }
    });
    return f;
  }

  /* Button press: sink to 95%, then spring back (a little past 100%, then settle). Every button on every page,
   * through delegated pointer events and the individual `scale` property, so a button's own transform and
   * transitions are untouched. Big buttons sink less (98%); the side-menu rows and disabled buttons are skipped. */
  function initPress() {
    if (window._pressInit || !document.documentElement.animate) return;
    window._pressInit = true;
    var SEL = 'button, [role="button"], input[type="button"], input[type="submit"], .btn';
    var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)');
    var held = null;     // { el, anim, from }

    function pressable(el) {
      var b = el && el.closest && el.closest(SEL);
      if (!b || b.disabled || b.getAttribute('aria-disabled') === 'true' || b.classList.contains('nav-item')) return null;
      return b;
    }
    function release(springy) {
      if (!held) return;
      var h = held;
      held = null;
      var now = getComputedStyle(h.el).scale;
      h.anim.cancel();
      var start = now === 'none' ? String(h.from) : now;
      h.el.animate(springy
        // spring: past 100%, back under it, then settle (each leg eases out)
        ? [{ scale: start }, { scale: '1.04', offset: .35 }, { scale: '.99', offset: .65 }, { scale: '1.005', offset: .85 }, { scale: '1' }]
        : [{ scale: start }, { scale: '1' }],
        { duration: springy ? 520 : 140, easing: 'ease-out' });
    }
    document.addEventListener('pointerdown', function (e) {
      if (reduce && reduce.matches) return;
      if (e.button > 0) return;
      var b = pressable(e.target);
      if (!b) return;
      release(false);
      var from = b.getBoundingClientRect().width > 240 ? 0.98 : 0.95;
      held = { el: b, from: from, anim: b.animate([{ scale: '1' }, { scale: String(from) }],
        { duration: 120, easing: 'ease-out', fill: 'forwards' }) };
    }, true);
    document.addEventListener('pointerup', function () { release(true); }, true);
    document.addEventListener('pointercancel', function () { release(false); }, true);
    document.addEventListener('pointerleave', function () { release(false); }, true);
  }
  initPress();

  /* A list that is redrawn (rows replaced in one go: after tagging a row, a filter, a search) must not rise
   * again; only a list going from empty/loading to filled does. The observer marks such a container with
   * .stg-still, and stagger.css zeroes the animation duration and delays under it. */
  function initStill() {
    if (window._stillInit || !window.MutationObserver) return;
    window._stillInit = true;
    function placeholder(n) {
      return n.nodeType !== 1 || n.classList.contains('sq-loading') || n.classList.contains('skel-card');
    }
    function hasReal(nodes) {
      for (var i = 0; i < nodes.length; i++) if (!placeholder(nodes[i])) return true;
      return false;
    }
    function risesItems(r) {   // the new rows are stagger items (they animate with `rise`), so the target is a stagger list
      for (var i = 0; i < r.addedNodes.length; i++) {
        var n = r.addedNodes[i];
        if (n.nodeType === 1) return getComputedStyle(n).animationName === 'rise';
      }
      return false;
    }
    function hasOtherReal(parent, added) {
      for (var c = parent.firstElementChild; c; c = c.nextElementSibling) {
        if (!placeholder(c) && Array.prototype.indexOf.call(added, c) < 0) return true;
      }
      return false;
    }
    new MutationObserver(function (records) {
      records.forEach(function (r) {
        var t = r.target;
        if (r.type !== 'childList' || t.nodeType !== 1 || !r.addedNodes.length) return;
        if (hasReal(r.removedNodes)) { if (risesItems(r)) t.classList.add('stg-still'); }   // real rows replaced: a re-render
        else if (t.classList.contains('stg-still') && !hasOtherReal(t, r.addedNodes)) t.classList.remove('stg-still');  // empty/loading -> filled
      });
    }).observe(document.documentElement, { childList: true, subtree: true });
  }
  initStill();


  /* Palette-aware chart colours. Chart.js / canvas colours live in JS, so CSS variables cannot reach them:
   *  - bdCat(colors)  categorical lists (pie slices, legend dots): in a palette, index i -> the palette's ramp[i]
   *    (tints of its three colours), so the chart and its DOM legend (built from the same list) match.
   *  - a Chart.js plugin recolours every dataset colour (keeping alpha): reds/oranges/yellows -> --c-neg,
   *    greens -> --c-pos, teals -> --teal, blues/purples -> --c-alt, neutrals untouched; lists use the ramp.
   * With no palette both are no-ops. Switching palette reloads a page that has charts. */
  var RAMPS = {
    'pistachio-cocoa-red':    ['#C8173F', '#2E1B14', '#E0788F', '#6A5646', '#EFB3C0', '#9A8A7A', '#A41234', '#B5BFA0'],
    'gunmetal-concrete-gold': ['#FFB800', '#B4ADA2', '#FFD666', '#8C867D', '#FFE6A3', '#D9D4CC', '#E0A000', '#5B6676'],
    'volcano-cream-indigo':   ['#3D2BFF', '#E2551F', '#8F85FF', '#F29A74', '#1E1410', '#B9B2FF', '#6B5846', '#2F1FD0']
  };
  function activeRamp() { return RAMPS[document.documentElement.getAttribute('data-palette')] || null; }
  window.bdCat = function (colors) {
    var r = activeRamp();
    return r ? colors.map(function (_, i) { return r[i % r.length]; }) : colors;
  };
  function cssVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
  function parseColor(c) {
    var m = /^#([0-9a-f]{6})$/i.exec(c);
    if (m) return [parseInt(m[1].slice(0, 2), 16), parseInt(m[1].slice(2, 4), 16), parseInt(m[1].slice(4), 16), 1];
    m = /^#([0-9a-f]{3})$/i.exec(c);
    if (m) return [0, 1, 2].map(function (i) { return parseInt(m[1][i] + m[1][i], 16); }).concat(1);
    m = /^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)(?:[\s,/]+([\d.]+))?\s*\)$/i.exec(c);
    return m ? [+m[1], +m[2], +m[3], m[4] == null ? 1 : +m[4]] : null;
  }
  function recolor(c) {
    var p = typeof c === 'string' ? parseColor(c.trim()) : null;
    if (!p) return c;
    var r = p[0] / 255, g = p[1] / 255, b = p[2] / 255, mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
    if (mx === 0 || d / mx < 0.045 || (mx < 0.30 && d / mx < 0.5)) return c;       // neutral: keep
    var h = d === 0 ? 0 : mx === r ? ((g - b) / d + 6) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
    h *= 60;
    var role = (h <= 50 || h >= 325) ? '--c-neg' : h < 160 ? '--c-pos' : h <= 195 ? '--teal' : '--c-alt';
    var t = parseColor(cssVar(role));
    return t ? 'rgba(' + t[0] + ',' + t[1] + ',' + t[2] + ',' + p[3] + ')' : c;
  }
  var CHART_PROPS = ['backgroundColor', 'borderColor', 'pointBackgroundColor', 'pointBorderColor', 'hoverBackgroundColor', 'hoverBorderColor'];
  function initChartPalette() {
    if (!window.Chart || window._bdChartInit || !activeRamp()) return;
    window._bdChartInit = true;
    var ramp = activeRamp();
    Chart.defaults.color = cssVar('--text-sub') || Chart.defaults.color;
    Chart.defaults.borderColor = cssVar('--border') || Chart.defaults.borderColor;
    Chart.register({
      id: 'bdPalette',
      beforeUpdate: function (chart) {
        chart.data.datasets.forEach(function (ds) {
          var done = ds._bdDone || (ds._bdDone = {});
          CHART_PROPS.forEach(function (k) {
            var v = ds[k];
            if (v == null || done[k] === v) return;
            var out = Array.isArray(v) ? v.map(function (_, i) { return ramp[i % ramp.length]; })
                                       : typeof v === 'string' ? recolor(v) : v;
            ds[k] = out; done[k] = out;
          });
        });
      }
    });
  }
  initChartPalette();

  /* Colour-palette picker: one button per palette in the side menu (above the footer). The choice is kept in
   * localStorage ("bd-palette"; absent = the original look) and set as <html data-palette>; the colours live in
   * palettes.css, and each page's <head> re-applies the saved value before first paint. */
  var PALETTES = [
    ['default', 'ברירת מחדל'],
    ['pistachio-cocoa-red', 'פיסטוק וקקאו'],
    ['gunmetal-concrete-gold', 'כחול מתכתי וזהב'],
    ['volcano-cream-indigo', 'כתום ואינדיגו']
  ];
  function currentPalette() {
    var p = document.documentElement.getAttribute('data-palette') || 'default';
    return PALETTES.some(function (x) { return x[0] === p; }) ? p : 'default';
  }
  /* Apply + remember a palette id ('default' clears it); updates every picker button on the page. */
  function setPalette(id) {
    var root = document.documentElement;
    if (id === 'default') root.removeAttribute('data-palette'); else root.setAttribute('data-palette', id);
    try { if (id === 'default') localStorage.removeItem('bd-palette'); else localStorage.setItem('bd-palette', id); } catch (e) {}
    var btns = document.querySelectorAll('.pal-opt');
    for (var i = 0; i < btns.length; i++) btns[i].setAttribute('aria-pressed', String(btns[i].getAttribute('data-pal') === id));
    if (window.Chart) location.reload();      // chart colours are set in JS: redraw the page with the new palette
  }
  /* Build the palette buttons (one per palette, with its 60/30/10 swatch) into `parent`. */
  function buildPalettePicker(parent) {
    var row = document.createElement('div');
    row.className = 'pal-picker-row';
    row.setAttribute('role', 'group');
    row.setAttribute('aria-label', 'ערכת צבעים');
    var cur = currentPalette();
    PALETTES.forEach(function (p) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'pal-opt';
      b.setAttribute('data-pal', p[0]);
      b.setAttribute('aria-pressed', String(p[0] === cur));
      b.innerHTML = '<span class="pal-sw" aria-hidden="true"><i></i><i></i><i></i></span><span class="pal-name"></span>';
      b.lastChild.textContent = p[1];
      b.addEventListener('click', function () { setPalette(p[0]); });
      row.appendChild(b);
    });
    parent.appendChild(row);
  }

  /* ── Settings sub-menus ─────────────────────────────────────────────────────────────────────────────
   * "הגדרות" in the side menu swaps the page links for a settings list (the links come back with "חזור").
   * Every sub-menu has a back button as its first row. To add a setting: one entry in SETTINGS —
   * [id, label, builder(parent)] — the builder fills that setting's own sub-menu. */
  var SETTINGS = [
    ['palettes', 'ערכות צבעים', buildPalettePicker]
  ];
  /* Replace the menu content with a sub-menu: back button, title, then whatever build(box) adds. */
  function subMenu(box, title, onBack, build) {
    box.textContent = '';
    var order = 0;
    function put(el) { el.style.setProperty('--i', order++); box.appendChild(el); return el; }
    var back = document.createElement('button');
    back.type = 'button';
    back.className = 'nav-item nav-back';
    back.textContent = '→ חזור';
    back.addEventListener('click', onBack);
    put(back);
    var h = document.createElement('div');
    h.className = 'nav-view-title';
    h.textContent = title;
    put(h);
    build(put);
    box.scrollTop = 0;
  }
  function showSettings(box) {
    subMenu(box, 'הגדרות', function () { render(box); }, function (put) {
      SETTINGS.forEach(function (st) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'nav-item nav-setting-link';
        b.textContent = st[1];
        b.addEventListener('click', function () {
          subMenu(box, st[1], function () { showSettings(box); }, function (put2) {
            var holder = document.createElement('div');
            holder.className = 'pal-picker';
            st[2](holder);
            put2(holder);
          });
        });
        put(b);
      });
    });
  }

  var boxes = document.querySelectorAll('.sidebar-scroll[data-nav]');
  for (var i = 0; i < boxes.length; i++) render(boxes[i]);
})();
