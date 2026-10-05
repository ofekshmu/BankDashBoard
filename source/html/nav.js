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
  }

  var boxes = document.querySelectorAll('.sidebar-scroll[data-nav]');
  for (var i = 0; i < boxes.length; i++) render(boxes[i]);
})();
