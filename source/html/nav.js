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
    var sep = document.createElement('div');
    sep.className = 'nav-sep';
    box.appendChild(sep);
    box.appendChild(copyLinkButton());
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
    '.cp-check{stroke:#fff;stroke-width:2.6;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:20;stroke-dashoffset:20;' +
    'transition:stroke-dashoffset .12s}' +
    '.cp-field.done .cp-check{stroke-dashoffset:0;transition-delay:.05s}' +
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
    '.cp-field.fail .cp-chip:before{opacity:0}.cp-field.fail .cp-check{stroke-dashoffset:20}' +
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
        '<svg viewBox="0 0 34 34"><path class="cp-check" d="M10 17.5l4.5 4.5L24 12"/></svg>' +
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
        setTimeout(function () { f.className = 'cp-field'; }, 2100);
        setTimeout(function () { tip.textContent = 'הועתק!'; busy = false; }, 2450);
      });
    }
    f.addEventListener('click', run);
    f.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); run(); }
    });
    return f;
  }

  var boxes = document.querySelectorAll('.sidebar-scroll[data-nav]');
  for (var i = 0; i < boxes.length; i++) render(boxes[i]);
})();
