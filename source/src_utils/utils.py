from Constants import Settings, ReservedNames, Paths, CC_CHARGE_CATEGORY_NAME
import json
from typing import Union
from datetime import datetime
import shutil
import os
import send2trash
from typing import Tuple
import pandas as pd
from tqdm import tqdm
from src_utils.ExcelReader import ExcelManager


class utils:

    # Set to a callable(row_bank_dict) -> bool by WebApp.py when running in web mode.
    # Used in card_charge_validation to show a web popup instead of a terminal menu.
    _cc_confirm_hook = None

    @staticmethod
    def log(msg: str, category: str = "", e: str = "\n"):

        log_st = ""
        write = False
        match category:
            case 'debug':
                if Settings.DEBUG:
                    write = True
                    log_st += f"[DEBUG]: {msg}"
            case 'system':
                if Settings.SYSTEM:
                    write = True
                    log_st += f"[SYSTEM]: {msg}"
            case 'error':
                write = True
                log_st += f"\n{100*'-'}\n[ERROR]: {msg}\n{100*'-'}\n"
            case 'db':
                write = True
                log_st += f"[DataBase]: {msg}"
            case '':
                write = True
                log_st += f'{msg}'
            case 'warning':
                write = True
                log_st += f"\n<[WARNING]>: {msg}\n"
            case other:
                utils.log(msg=f"Key error in log function: got '{category}'", category='error')

        if write:
            f = open("Log_file.txt", 'a', encoding="utf-8")
            f.write(log_st + "\n")
            f.close()
            print(log_st, end=e)

        if category == "error":
            exit()
        # if category == 'warning':
        #     utils.warning_halt()

    @staticmethod
    def name_he(name: str):
        try:
            i = name[::-1].index(' ')
            j = len(name) - i
            return name[:j][::-1] + " " + name[j:]
        except ValueError:
            return name

    @staticmethod
    def heb_conversion(name: str) -> str:
        """
        Convert strings containing mixed characters (hebrew and english) to a string
        suited for printing.
        """
        def wrapper_hc(lst) -> str:
            if lst == []:
                return ""

            if utils.has_hebrew(lst[0]):
                return wrapper_hc(lst[1:]) + lst[0][::-1] + " "
            return wrapper_hc(lst[1:]) + " " +lst[0]


        if not utils.has_hebrew(name):
            return name

        return wrapper_hc(name.split())

    @staticmethod
    def has_hebrew(string):
        """
        returns True if a string has any hebrew characters in it
        and False otherwise.
        """
        import re
        return bool(re.search(r'[\u0590-\u05FF]', string))

    @staticmethod
    def warning_halt():

        def is_valid(x: str) -> bool:
            if not x.isnumeric():
                return False
            x = int(x)
            if not isinstance(x, int):
                return False
            if x not in [1, 2]:
                return False
            return True

        print("------ [HALT] ------")
        st = "There might be a problem, what do you want to do?\n1 -> Continue\n2 -> Stop and debug"
        print(st)
        while True:
            x = input()
            if not is_valid(x):
                print("Bad input, Try again...")
                continue
            match int(x):
                case 1:
                    break  # Continue
                case 2:
                    exit()
                case _:
                    print("This should not happen")
                    input("stopped.")

    # ------------------------------------------------------------------
    # KPI colour / dot configuration
    # Maps metric label → (dot hex colour, is_positive_default)
    # ------------------------------------------------------------------
    _KPI_CONFIG: dict = {
        "Balance":                  ("#1e9d8b", True),
        "Net Income":               ("#1e9d8b", True),
        "Overall Net Income":       ("#f0b429", True),
        "Monthly Mean":             ("#f0b429", True),
        "Deposit/Spent Cash":       ("#e74c3c", False),
        "Withdrawed/Earned Cash":   ("#1e9d8b", True),
    }

    # Overview chart cards: (title, src_attr_name | None for hover-pairs)
    _CHART_CARDS: list = [
        # (title, src key in Paths or None if hover-pair)
        ("הוצאות לפי קטגוריה",    None),   # hover-pair: Spendings
        ("הכנסות לפי קטגוריה",    None),   # hover-pair: Earnings
        ("השקעות / חיסכון",        None),   # hover-pair: Investments
        ("מידע כללי",              "GENERAL_INFO_GRAPH"),
        ("מזומן",                  None),   # hover-pair: Cash Distribution
    ]

    @staticmethod
    def generate_html(month_num,
                      year,
                      spendings_df,
                      high_std_spendings,
                      earnings_df,
                      high_std_earnings,
                      monthly_balance: int,
                      cards_dict: dict,
                      data: dict,
                      accounts_data: dict,
                      cash_information_data: dict,
                      alerts: list = None,
                      mortgage_data: dict = None,
                      accounts_meta: dict = None,
                      organizer_alerts: list = None) -> None:
        import bs4
        from datetime import datetime
        import calendar

        with open(r"source\html\Base_template.html", encoding="utf-8") as inf:
            soup = bs4.BeautifulSoup(inf.read(), "html.parser")

        month_label = f"{calendar.month_name[month_num]} {year}"

        # ── Page title & month badge ───────────────────────────────────
        title_tag = soup.find("title")
        if title_tag:
            title_tag.string = f"Dashboard — {month_label}"
        month_el = soup.find(id="month-label")
        if month_el:
            month_el.string = month_label

        # ── Alert badge count ──────────────────────────────────────────
        badge_el = soup.find(id="alert-badge")
        if badge_el:
            badge_el.string = str(len(alerts) if alerts else 0)

        # ── Organizer missing-file alerts ──────────────────────────────
        org_el = soup.find(id="organizer-alerts")
        if org_el is not None and organizer_alerts:
            def _otag(name, **attrs):
                t_ = soup.new_tag(name)
                for k, v in attrs.items():
                    t_[k.rstrip("_")] = v
                return t_

            hdr = _otag("div", class_="org-alerts-section-title")
            hdr.string = f"קבצים חסרים לחודש זה — {len(organizer_alerts)}"
            org_el.append(hdr)

            for oa in organizer_alerts:
                row = _otag("div", class_="org-missing-card type-blue")

                icon = _otag("span", class_="org-missing-icon")
                icon.string = "⚠"
                row.append(icon)

                body = _otag("div")
                lbl = _otag("span", class_="org-missing-label")
                lbl.string = f"חסר עסקה — {oa['col']}"
                body.append(lbl)

                ut = oa["untagged"]
                det = _otag("div", class_="org-missing-detail")
                det.string = f"{ut[2]} | ₪{ut[1]} | {ut[0]}"
                body.append(det)

                row.append(body)
                org_el.append(row)

        # ── Helper: new tag shorthand ──────────────────────────────────
        def tag(name, **attrs):
            t = soup.new_tag(name)
            for k, v in attrs.items():
                t[k.rstrip("_")] = v
            return t

        # ── KPI cards ──────────────────────────────────────────────────
        kpi_metrics_main = [
            ("Balance",            monthly_balance,            monthly_balance >= 0,           True),
            ("Net Income",         data["net income"],          data["net income"] >= 0,         False),
            ("Overall Net Income", data["overall net income"],  data["overall net income"] >= 0, False),
        ]
        kpi_metrics_cash = [
            ("Deposit/Spent Cash",     cash_information_data['Monthly Spent Cash'],  False, False),
            ("Withdrawed/Earned Cash", cash_information_data['Monthly Earned Cash'], True,  False),
        ]

        def _make_kpi_card(label, value, is_positive, is_hero):
            dot_color, _ = utils._KPI_CONFIG.get(label, ("#9aa3bb", True))
            val_cls    = "pos" if is_positive else "neg"
            amount_str = f"{value:,.2f}\u20aa" if value >= 0 else f"-{abs(value):,.2f}\u20aa"
            card_cls   = "kpi-card hero" if is_hero else "kpi-card"
            card = tag("div", class_=card_cls)
            lbl  = tag("div", class_="kpi-label")
            dot  = tag("span", class_="kpi-dot")
            dot["style"] = f"background:{dot_color}"
            lbl.append(dot)
            lbl.append(label)
            val = tag("div", class_=f"kpi-value {val_cls}")
            val.string = amount_str
            card.append(lbl)
            card.append(val)
            return card

        kpi_row = soup.find(id="kpi-row")
        for label, value, is_positive, is_hero in kpi_metrics_main:
            kpi_row.append(_make_kpi_card(label, value, is_positive, is_hero))

        def _make_split_cash_card(metrics):
            card = tag("div", class_="kpi-card")
            first = True
            for label, value, is_positive, _ in metrics:
                dot_color, _ = utils._KPI_CONFIG.get(label, ("#9aa3bb", True))
                val_cls = "pos" if is_positive else "neg"
                amount_str = f"{value:,.2f}\u20aa" if value >= 0 else f"-{abs(value):,.2f}\u20aa"
                if not first:
                    card.append(tag("hr", class_="kpi-sep"))
                lbl = tag("div", class_="kpi-label")
                dot = tag("span", class_="kpi-dot")
                dot["style"] = f"background:{dot_color}"
                lbl.append(dot)
                lbl.append(label)
                val = tag("div", class_=f"kpi-value {val_cls}")
                val.string = amount_str
                card.append(lbl)
                card.append(val)
                first = False
            return card

        # Cash KPI data is shown inside the מזומן donut chart instead

        # ── Overview charts (interactive Chart.js) ─────────────────────
        import json as _json

        # Shared donut center-text plugin (renders total in center of doughnut)
        _DONUT_PLUGIN_JS = """
  {
    id: 'centerText',
    beforeDraw(chart) {
      if (chart.config.type !== 'doughnut') return;
      const {ctx, data, chartArea: {top, bottom, left, right}} = chart;
      const cx = (left + right) / 2, cy = (top + bottom) / 2;
      const total = data.datasets[0].data.reduce((a, b, i) =>
        chart.getDataVisibility(i) ? a + b : a, 0);
      ctx.save();
      ctx.font = 'bold 15px Segoe UI,Arial,sans-serif';
      ctx.fillStyle = '#1e2a4a';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('\u20aa' + Math.round(total).toLocaleString('he-IL'), cx, cy);
      ctx.restore();
    }
  }"""

        def _make_donut_card(canvas_id, title, cat_data, palette, full_width=False):
            """Return (chart_card, mobile_legend_card) for a Chart.js doughnut.
            On mobile the built-in legend is hidden and the legend_card (a separate
            card with a category list) is shown instead via CSS."""
            _labels = list(cat_data.keys())
            _values = list(cat_data.values())
            # Cycle palette to cover all slices
            _colors = [palette[i % len(palette)] for i in range(len(_labels))]
            _chart_data = _json.dumps({
                "labels":   _labels,
                "datasets": [{"data": _values, "backgroundColor": _colors,
                              "borderWidth": 1, "borderColor": "#fff",
                              "hoverOffset": 8}]
            }, ensure_ascii=False)

            card_cls = "chart-card full-width" if full_width else "chart-card"
            card = tag("div", class_=card_cls)
            ttl = tag("div", class_="chart-card-title"); ttl.string = title
            card.append(ttl)
            wrap = tag("div", class_="donut-chart-wrap")
            wrap["style"] = "position:relative;height:320px;"
            canvas = tag("canvas"); canvas["id"] = canvas_id
            canvas["style"] = "width:100%;height:100%;"
            wrap.append(canvas)
            card.append(wrap)
            sc = tag("script")
            sc.string = f"""
(function(){{
  var _isMob = window.matchMedia('(max-width:768px)').matches;
  new Chart(document.getElementById('{canvas_id}'), {{
    type: 'doughnut',
    data: {_chart_data},
    options: {{
      responsive: true, maintainAspectRatio: false,
      cutout: '68%',
      plugins: {{
        legend: {{
          display: !_isMob,
          position: 'bottom',
          labels: {{ font: {{ size: 11 }}, padding: 10, boxWidth: 12 }},
          onHover: function(evt, item, legend) {{
            var ch = legend.chart;
            ch.tooltip.setActiveElements([{{datasetIndex: 0, index: item.index}}], evt);
            ch.update();
          }},
          onLeave: function(evt, item, legend) {{
            var ch = legend.chart;
            ch.tooltip.setActiveElements([], evt);
            ch.update();
          }}
        }},
        tooltip: {{
          rtl: true,
          callbacks: {{
            label: function(ctx) {{
              const v = ctx.parsed;
              const ch = ctx.chart;
              const visTotal = ctx.dataset.data.reduce((a,b,i)=>
                ch.getDataVisibility(i) ? a+b : a, 0);
              const pct = visTotal ? (v/visTotal*100).toFixed(1) : 0;
              return '\u20aa' + Math.round(v).toLocaleString('he-IL') + ' (' + pct + '%)';
            }}
          }}
        }}
      }}
    }},
    plugins: [{_DONUT_PLUGIN_JS}]
  }});
}})();
"""
            card.append(sc)

            # \u2500\u2500 Mobile-only category legend card \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            legend_card = tag("div", class_="chart-card mobile-cat-legend-card")
            leg_ttl = tag("div", class_="chart-card-title"); leg_ttl.string = title
            legend_card.append(leg_ttl)
            leg_ul = tag("ul", class_="mobile-cat-list")
            _total = sum(_values) or 1
            for i, (lbl, val) in enumerate(zip(_labels, _values)):
                li = tag("li", class_="mobile-cat-item")
                dot = tag("span", class_="mobile-cat-dot")
                dot["style"] = f"background:{_colors[i]}"
                name_sp = tag("span", class_="mobile-cat-name"); name_sp.string = lbl
                pct = val / _total * 100
                val_sp = tag("span", class_="mobile-cat-value")
                val_sp.string = f"\u20aa{round(val):,} ({pct:.0f}%)"
                li.append(dot); li.append(name_sp); li.append(val_sp)
                leg_ul.append(li)
            legend_card.append(leg_ul)

            return card, legend_card

        # Color palettes per chart type
        _PAL_SPEND  = ["#ef9a9a","#ffab91","#ffcc80","#ffe082","#f48fb1",
                       "#ff8a65","#ffd54f","#f06292","#ffb74d","#e57373"]
        _PAL_EARN   = ["#a5d6a7","#80cbc4","#90caf9","#80deea","#c5e1a5",
                       "#b3e5fc","#b2dfdb","#a5f3d0","#81d4fa","#aed581"]
        _PAL_INVEST = ["#ffcc80","#ffb74d","#ffe082","#ffab91","#a5d6a7",
                       "#80deea","#e6ee9c","#ce93d8","#90caf9","#b0bec5"]

        charts_grid = soup.find(id="overview-charts")

        # Helper: outlier box (defined early so it can be injected next to donuts)
        def _outlier_box(title, items):
            box = tag("div", class_="outlier-box")
            h3  = tag("h3"); h3.string = title
            box.append(h3)
            ul = tag("ul", class_="outlier-list")
            for name, value in items:
                li   = tag("li",   class_="outlier-item")
                n_sp = tag("span", class_="outlier-name");  n_sp.string = name
                v_sp = tag("span", class_="outlier-value"); v_sp.string = f"{value:,.2f}\u20aa"
                li.append(n_sp); li.append(v_sp)
                ul.append(li)
            box.append(ul)
            return box

        # Spendings donut
        if data.get('spendings_by_cat'):
            _c, _l = _make_donut_card(
                "chart-spendings-donut", "הוצאות לפי קטגוריה",
                data['spendings_by_cat'], _PAL_SPEND)
            charts_grid.append(_c); charts_grid.append(_l)

        # Earnings donut
        if data.get('earnings_by_cat'):
            _c, _l = _make_donut_card(
                "chart-earnings-donut", "הכנסות לפי קטגוריה",
                data['earnings_by_cat'], _PAL_EARN)
            charts_grid.append(_c); charts_grid.append(_l)

        # Investments donut
        if data.get('investments_by_name'):
            _c, _l = _make_donut_card(
                "chart-investments-donut", "השקעות / חיסכון",
                data['investments_by_name'], _PAL_INVEST)
            charts_grid.append(_c); charts_grid.append(_l)
        else:
            # Empty state card
            _inv_card = tag("div", class_="chart-card")
            _inv_ttl  = tag("div", class_="chart-card-title"); _inv_ttl.string = "השקעות / חיסכון"
            _inv_empty = tag("div", class_="empty-state")
            _inv_empty.string = "אין נתוני השקעות לחודש זה"
            _inv_card.append(_inv_ttl); _inv_card.append(_inv_empty)
            charts_grid.append(_inv_card)

        # Cash donut (income vs expense)
        _cash_earned = abs(float(cash_information_data.get('Monthly Earned Cash', 0)))
        _cash_spent  = abs(float(cash_information_data.get('Monthly Spent Cash',  0)))
        if _cash_earned + _cash_spent > 0:
            _c, _l = _make_donut_card(
                "chart-cash-donut", "מזומן",
                {f"הכנסה  ₪{_cash_earned:,.0f}": _cash_earned,
                 f"הוצאה  ₪{_cash_spent:,.0f}":  _cash_spent},
                ["#a5d6a7", "#ef9a9a"])
            charts_grid.append(_c); charts_grid.append(_l)
        else:
            _cash_card = tag("div", class_="chart-card")
            _cash_ttl  = tag("div", class_="chart-card-title"); _cash_ttl.string = "מזומן"
            _cash_empty = tag("div", class_="empty-state"); _cash_empty.string = "אין נתוני מזומן לחודש זה"
            _cash_card.append(_cash_ttl); _cash_card.append(_cash_empty)
            charts_grid.append(_cash_card)

        # ── General bar+line chart (full-width) ─────────────────────────
        if data.get('general_months'):
            # Reverse so oldest is on left, most recent on right
            _gen_months = list(reversed(data['general_months']))
            _gen_sp     = list(reversed(data['general_spendings']))
            _gen_inv    = list(reversed(data.get('general_investments', [0]*len(_gen_months))))
            _gen_ea     = list(reversed(data['general_earnings']))
            _gen_net    = list(reversed(data['general_net']))

            _gen_chart_data = _json.dumps({
                "labels": _gen_months,
                "datasets": [
                    {"type": "bar",  "label": "הוצאות",          "data": _gen_sp,
                     "backgroundColor": "rgba(239,154,154,0.80)", "borderColor": "#ef5350",
                     "borderWidth": 1, "order": 2, "stack": "sp"},
                    {"type": "bar",  "label": "השקעות/חיסכון",   "data": _gen_inv,
                     "backgroundColor": "rgba(255,183,77,0.85)",  "borderColor": "#ffb74d",
                     "borderWidth": 1, "order": 2, "stack": "sp"},
                    {"type": "bar",  "label": "הכנסות",           "data": _gen_ea,
                     "backgroundColor": "rgba(165,214,167,0.75)", "borderColor": "#43a047",
                     "borderWidth": 1, "order": 2, "stack": "ea"},
                    {"type": "line", "label": "נטו (ללא השקעות)", "data": _gen_net,
                     "borderColor": "#1e9d8b", "backgroundColor": "rgba(30,157,139,0.08)",
                     "pointRadius": 5, "pointHoverRadius": 8, "tension": 0.35,
                     "fill": True, "borderWidth": 2, "order": 1},
                ]
            }, ensure_ascii=False)

            _gen_card = tag("div", class_="chart-card full-width")

            # Monthly mean banner
            _mean_val = data.get("overall_net_mean", 0)
            _mean_pos = _mean_val >= 0
            _mean_str = f"{_mean_val:,.0f}\u20aa" if _mean_pos else f"-{abs(_mean_val):,.0f}\u20aa"
            _mean_color = "#1e9d8b" if _mean_pos else "#e74c3c"
            _mean_banner = tag("div")
            _mean_banner["style"] = (
                "display:flex;align-items:center;justify-content:space-between;"
                "padding:8px 4px 14px;border-bottom:1.5px solid #eef0f6;margin-bottom:12px;"
            )
            _mean_lbl = tag("span")
            _mean_lbl["style"] = "font-size:0.78em;font-weight:600;color:#888;"
            _mean_lbl.string = "ממוצע חודשי נטו (10 חודשים אחרונים)"
            _mean_num = tag("span")
            _mean_num["style"] = f"font-size:1.4em;font-weight:800;color:{_mean_color};"
            _mean_num.string = _mean_str
            _mean_banner.append(_mean_lbl)
            _mean_banner.append(_mean_num)
            _gen_card.append(_mean_banner)

            _gen_ttl  = tag("div", class_="chart-card-title")
            _gen_ttl.append(bs4.NavigableString("מידע כללי "))
            _gen_info_wrap = tag("span", class_="kpi-info-wrap")
            _gen_info_icon = tag("span", class_="kpi-info-icon"); _gen_info_icon.string = "i"
            _gen_info_tip  = tag("span", class_="kpi-tooltip")
            _gen_info_tip.string = (
                "עמודות: הוצאות חודשיות (אדום) + השקעות/חיסכון (זהב) + הכנסות (ירוק).\n"
                "קו תכלת — נטו חודשי (הכנסות פחות הוצאות בלי השקעות):\n"
                "  נטו = הכנסות − הוצאות (ללא קטגוריית השקעה/חיסכון)\n"
                "ממוצע חודשי מחושב על 10 החודשים האחרונים."
            )
            _gen_info_wrap.append(_gen_info_icon)
            _gen_info_wrap.append(_gen_info_tip)
            _gen_ttl.append(_gen_info_wrap)
            _gen_card.append(_gen_ttl)
            _gen_wrap = tag("div"); _gen_wrap["id"] = "chart-general-wrap"
            _gen_wrap["style"] = "position:relative;height:340px;"
            _gen_canvas = tag("canvas"); _gen_canvas["id"] = "chart-general-bar"
            _gen_canvas["style"] = "width:100%;height:100%;"
            _gen_wrap.append(_gen_canvas)
            _gen_card.append(_gen_wrap)
            _gen_sc = tag("script")
            _gen_sc.string = f"""
(function(){{
  var _isMob = window.matchMedia('(max-width:768px)').matches;
  var _rawData = {_gen_chart_data};
  var _chartData = _rawData;
  if (_isMob) {{
    var _n = 3;
    _chartData = {{
      labels: _rawData.labels.slice(-_n),
      datasets: _rawData.datasets.map(function(ds) {{
        return Object.assign({{}}, ds, {{ data: ds.data.slice(-_n) }});
      }})
    }};
  }}
  new Chart(document.getElementById('chart-general-bar'), {{
    type: 'bar',
    data: _chartData,
    options: {{
      responsive: true, maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ position: 'top', labels: {{ font: {{ size: _isMob ? 10 : 12 }}, padding: 12 }} }},
        tooltip: {{
          rtl: true,
          callbacks: {{
            label: function(ctx) {{
              const v = ctx.parsed.y;
              if (v == null) return null;
              const sign = v >= 0 ? '' : '-';
              return ctx.dataset.label + ': ' + sign + '\u20aa' + Math.abs(Math.round(v)).toLocaleString('he-IL');
            }}
          }}
        }}
      }},
      scales: {{
        x: {{ stacked: true, ticks: {{ font: {{ size: 11 }}, maxRotation: 30 }} }},
        y: {{
          stacked: true,
          ticks: {{
            callback: function(v) {{ return '\u20aa' + Math.round(v).toLocaleString('he-IL'); }},
            font: {{ size: 11 }}
          }}
        }}
      }}
    }}
  }});
}})();
"""
            _gen_card.append(_gen_sc)
            charts_grid.append(_gen_card)

        # ── Installment payments donuts ────────────────────────────────
        # Query card transactions whose Charge_Date is in this exact month —
        # these are the installments the user actually pays this month.
        import pandas as _pd, sqlite3 as _sq, re as _re
        try:
            _mon = str(month_num).zfill(2)
            _yr  = str(year)
            with _sq.connect('ShmuelFamiliy.db') as _pc:
                _rows = _pc.execute(
                    "SELECT Name, Transaction_Value, Charge_Value, Extra_Info "
                    "FROM CardTransactions "
                    "WHERE strftime('%m',Charge_Date)=? AND strftime('%Y',Charge_Date)=?",
                    (_mon, _yr)
                ).fetchall()
            _pay_rows = [r for r in _rows if r[3] and
                         _re.search(r'תשלום\s+\d+\s+מתוך\s+\d+', str(r[3]))]
            if _pay_rows:
                _pay_df = utils.extract_payments_data(
                    _pd.DataFrame(_pay_rows, columns=['Name','Final_Value','Charge_Value','Extra_Info']))
            else:
                _pay_df = _pd.DataFrame()
        except Exception as _pe:
            utils.log(f"payments chart error: {_pe}", "warning")
            _pay_df = _pd.DataFrame()

        _pay_grid = soup.find(id="tx-payments-grid")

        if _pay_grid is not None and _pay_df.empty:
            _pay_empty = tag("div", class_="empty-state")
            _pay_empty["style"] = "padding: 14px 0;"
            _pay_empty.string = "אין תשלומים פעילים החודש"
            _pay_grid.append(_pay_empty)

        if _pay_grid is not None and not _pay_df.empty:

            # Distinct (paid, remaining) color pairs — one per payment
            _PAY_PALETTES = [
                ("#5C6BC0", "#C5CAE9"),  # indigo
                ("#26A69A", "#B2DFDB"),  # teal
                ("#EF5350", "#FFCDD2"),  # red
                ("#FFA726", "#FFE0B2"),  # orange
                ("#AB47BC", "#E1BEE7"),  # purple
                ("#29B6F6", "#B3E5FC"),  # light blue
                ("#66BB6A", "#C8E6C9"),  # green
                ("#EC407A", "#FCE4EC"),  # pink
            ]

            # Center-text plugin: shows "X/Y\nתשלומים"
            _PAY_CENTER_JS = """
  {
    id: 'payCenter',
    beforeDraw(chart) {
      if (chart.config.type !== 'doughnut') return;
      const {ctx, chartArea: {top, bottom, left, right}} = chart;
      const cx = (left + right) / 2, cy = (top + bottom) / 2;
      const [paid, rem] = chart.data.datasets[0].data;
      ctx.save();
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.font = 'bold 15px Segoe UI,Arial,sans-serif';
      ctx.fillStyle = '#1e2a4a';
      ctx.fillText(paid + '/' + (paid + rem), cx, cy - 7);
      ctx.font = '10px Segoe UI,Arial,sans-serif';
      ctx.fillStyle = '#888';
      ctx.fillText('\\u05ea\\u05e9\\u05dc\\u05d5\\u05de\\u05d9\\u05dd', cx, cy + 9);
      ctx.restore();
    }
  }"""

            for _pi, (_, _pr) in enumerate(_pay_df.iterrows()):
                _pname   = str(_pr['Transaction Name'])
                _pnum    = int(_pr['Current Payment Number'])
                _ptotal  = int(_pr['Number of Payments'])
                _pamt    = float(_pr['Current Payment'])
                _premain = _ptotal - _pnum

                _pcol_paid, _pcol_rem = _PAY_PALETTES[_pi % len(_PAY_PALETTES)]
                _pcid    = f"chart-payment-{_pi}"

                _pdata = _json.dumps({
                    "labels": [f"שולם ({_pnum})", f"נותר ({_premain})"],
                    "datasets": [{
                        "data": [_pnum, _premain],
                        "backgroundColor": [_pcol_paid, _pcol_rem],
                        "borderWidth": 2, "borderColor": "#fff",
                        "hoverOffset": 6,
                    }]
                }, ensure_ascii=False)

                _pcard = tag("div", class_="chart-card")

                # Title
                _pttl = tag("div", class_="chart-card-title")
                _pttl.string = (_pname[:28] + "…") if len(_pname) > 28 else _pname
                _pcard.append(_pttl)

                # Canvas
                _pwrap = tag("div"); _pwrap["style"] = "position:relative;height:190px;"
                _pcanvas = tag("canvas"); _pcanvas["id"] = _pcid
                _pcanvas["style"] = "width:100%;height:100%;"
                _pwrap.append(_pcanvas)
                _pcard.append(_pwrap)

                # Footer: monthly amount
                _pfooter = tag("div", class_="payment-footer")
                _pfooter.string = f"₪{_pamt:,.0f} / חודש"
                _pcard.append(_pfooter)

                # Chart script
                _psc = tag("script")
                _psc.string = f"""
(function(){{
  new Chart(document.getElementById('{_pcid}'), {{
    type: 'doughnut',
    data: {_pdata},
    options: {{
      responsive: true, maintainAspectRatio: false,
      cutout: '68%',
      plugins: {{
        legend: {{
          position: 'bottom',
          labels: {{ font: {{ size: 10 }}, padding: 6, boxWidth: 10 }},
          onHover: function(evt, item, legend) {{
            var ch = legend.chart;
            ch.tooltip.setActiveElements([{{datasetIndex: 0, index: item.index}}], evt);
            ch.update();
          }},
          onLeave: function(evt, item, legend) {{
            var ch = legend.chart;
            ch.tooltip.setActiveElements([], evt);
            ch.update();
          }}
        }},
        tooltip: {{
          rtl: true,
          callbacks: {{
            label: function(ctx) {{
              const labels = [
                'שולם: {_pnum} תשלומים מתוך {_ptotal}',
                'נותר: {_premain} תשלומים'
              ];
              return labels[ctx.dataIndex];
            }}
          }}
        }}
      }}
    }},
    plugins: [{_PAY_CENTER_JS}]
  }});
}})();
"""
                _pcard.append(_psc)
                _pay_grid.append(_pcard)

        # ── Card distribution chart (appended to overview-charts grid) ──
        _card_dist = data.get('card_dist', {})
        card_dist_card = tag("div", class_="chart-card full-width")
        card_dist_card["style"] = "margin-top: 16px;"
        card_dist_ttl  = tag("div", class_="chart-card-title")
        card_dist_ttl.string = "התפלגות כרטיסי אשראי"
        card_dist_card.append(card_dist_ttl)

        if _card_dist:
            _cd_labels  = list(_card_dist.keys())
            _cd_amounts = [v['amount'] for v in _card_dist.values()]
            _cd_colors  = [v['color']  for v in _card_dist.values()]
            _cd_status  = [v['status'] for v in _card_dist.values()]
            _cd_chart_data = _json.dumps({
                "labels": _cd_labels,
                "datasets": [{
                    "label": "חיוב חודשי",
                    "data":  _cd_amounts,
                    "backgroundColor": _cd_colors,
                    "borderColor": _cd_colors,
                    "borderWidth": 1,
                }]
            }, ensure_ascii=False)
            _cd_status_json = _json.dumps(_cd_status)

            _cd_wrap = tag("div"); _cd_wrap["style"] = "position:relative;height:240px;"
            _cd_canvas = tag("canvas"); _cd_canvas["id"] = "chart-card-dist"
            _cd_canvas["style"] = "width:100%;height:100%;"
            _cd_wrap.append(_cd_canvas)
            card_dist_card.append(_cd_wrap)
            _cd_sc = tag("script")
            _cd_sc.string = f"""
(function(){{
  const statusArr = {_cd_status_json};
  const statusLabelPlugin = {{
    id: 'statusLabels',
    afterDatasetDraw(chart) {{
      const {{ctx, data, scales: {{x, y}}}} = chart;
      ctx.save();
      ctx.textAlign = 'center';
      ctx.font = '11px Segoe UI,Arial,sans-serif';
      data.datasets[0].data.forEach(function(val, i) {{
        if (data.labels[i] === 'Bank') return;
        const st = statusArr[i];
        const xPos = x.getPixelForValue(i);
        const yPos = y.getPixelForValue(val) - 6;
        ctx.fillStyle = st ? '#1a7a45' : '#b07000';
        ctx.fillText(st ? '\u2705 \u05de\u05d0\u05d5\u05de\u05ea' : '\u26a0 \u05dc\u05d0 \u05de\u05d0\u05d5\u05de\u05ea', xPos, yPos);
      }});
      ctx.restore();
    }}
  }};
  new Chart(document.getElementById('chart-card-dist'), {{
    type: 'bar',
    data: {_cd_chart_data},
    options: {{
      responsive: true, maintainAspectRatio: false,
      layout: {{ padding: {{ top: 24 }} }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          rtl: true,
          callbacks: {{
            label: function(ctx) {{
              const v = ctx.parsed.y;
              const st = statusArr[ctx.dataIndex];
              return '\u20aa' + Math.round(v).toLocaleString('he-IL') + (st ? ' \u2705 \u05de\u05d0\u05d5\u05de\u05ea' : ' \u26a0 \u05dc\u05d0 \u05de\u05d0\u05d5\u05de\u05ea');
            }}
          }}
        }}
      }},
      scales: {{
        x: {{ ticks: {{ font: {{ size: 12 }} }} }},
        y: {{
          ticks: {{
            callback: function(v) {{ return '\u20aa' + Math.round(v).toLocaleString('he-IL'); }},
            font: {{ size: 11 }}
          }}
        }}
      }}
    }},
    plugins: [statusLabelPlugin]
  }});
}})();
"""
            card_dist_card.append(_cd_sc)
        else:
            _cd_empty = tag("div", class_="empty-state")
            _cd_empty.string = "אין נתוני כרטיסים"
            card_dist_card.append(_cd_empty)
        charts_grid.append(card_dist_card)

        # (Outlier boxes are now injected directly inside overview-charts, after the two pie donuts)

        # ── Transaction rows ───────────────────────────────────────────
        def _build_tx_row(item):
            executed_date = (item['Execution_Date']
                             if not pd.isna(item['Execution_Date'])
                             else item['Executed_Date'])
            d = datetime.strptime(str(executed_date).split('.')[0], "%Y-%m-%d %H:%M:%S").strftime('%A %d')

            row = tag("div", class_="num")
            row["data-value"]    = str(item['ID'])
            row["data-tx-table"] = str(item.get('TableName', ''))

            # Mark split rows so the JS can show the revert dialog
            _split_orig = item.get('_split_orig_id', None)
            _is_split   = _split_orig is not None and not (
                isinstance(_split_orig, float) and pd.isna(_split_orig))
            if _is_split:
                row["data-is-split"] = "1"
                row["data-orig-id"]  = str(int(_split_orig))

            if item['TableName'] == 'CardTransactions':
                color = cards_dict[item['CardID']]
            elif item['TableName'] == 'BankTransactions':
                color = cards_dict['Bank']
            else:
                color = cards_dict['Cash']

            box = tag("div", class_="color-box")
            box["style"] = f"background-color:{color}"
            row.append(box)

            name_str = str(item['Name'])
            raw_desc = item['Description']
            has_desc = (
                raw_desc is not None
                and not (isinstance(raw_desc, float) and pd.isna(raw_desc))
                and str(raw_desc).strip()
                and str(raw_desc).strip() != name_str.strip()
            )
            h3 = tag("h3")
            if has_desc:
                span_p = tag("span", class_="tx-primary")
                span_p.string = str(raw_desc).strip()
                span_s = tag("span", class_="tx-secondary")
                span_s.string = name_str
                h3.append(span_p)
                h3.append(span_s)
            else:
                span_p = tag("span", class_="tx-primary")
                span_p.string = name_str
                h3.append(span_p)
            if _is_split:
                badge = tag("span", class_="split-badge")
                badge.string = "✂ פיצול"
                h3.append(badge)
            row.append(h3)

            if not pd.isnull(item['Amount']):
                price1, price2 = f"{item['Amount']:,.2f}\u20aa", ""
            elif item['Charge_Currency'] == item['Value_Currency'] or item['TableName'] == 'BankTransactions':
                price1, price2 = f"{item['Final_Value']:,.2f}\u20aa", ""
            else:
                price1 = f"{item['Final_Value']:,.2f}\u20aa"
                price2 = f"({item['Charge_Value']:,}{item['Charge_Currency']})"

            p_price = tag("p", class_="date")
            p_price.append(price1)
            if price2:
                p_price.append(tag("br"))
                p_price.append(price2)
            row.append(p_price)

            p_cat = tag("p", class_="cat")
            p_cat.string = str(item['Category'])
            row.append(p_cat)

            p_date = tag("p", class_="element4")
            p_date.string = d
            row.append(p_date)

            return row

        # Spendings
        df_cash_sp = cash_information_data['Monthly Cash Transactions']
        df_cash_sp = df_cash_sp[df_cash_sp['Amount'] < 0]
        spendings_df = pd.concat([spendings_df, df_cash_sp], ignore_index=True)

        sp_list  = soup.find(id="spendings-list")
        sp_total = 0.0
        for _, item in spendings_df.sort_values(by='Executed_Date', ascending=True).iterrows():
            sp_list.append(_build_tx_row(item))
            val = item['Amount'] if not pd.isnull(item['Amount']) else item['Final_Value']
            sp_total += abs(float(val))

        sp_sum = soup.find(id="spendings-sum")
        if sp_sum:
            sp_sum.string = f"{sp_total:,.2f}\u20aa"

        # Earnings
        df_cash_ea = cash_information_data['Monthly Cash Transactions']
        df_cash_ea = df_cash_ea[df_cash_ea['Amount'] > 0]
        earnings_df = pd.concat([earnings_df, df_cash_ea], ignore_index=True)

        ea_list  = soup.find(id="earnings-list")
        ea_total = 0.0
        for _, item in earnings_df.sort_values(by='Executed_Date', ascending=True).iterrows():
            ea_list.append(_build_tx_row(item))
            val = item['Amount'] if not pd.isnull(item['Amount']) else item['Final_Value']
            ea_total += abs(float(val))

        ea_sum = soup.find(id="earnings-sum")
        if ea_sum:
            ea_sum.string = f"{ea_total:,.2f}\u20aa"

        # ── Smart Alerts ───────────────────────────────────────────────
        _BG_MAP = {
            "#e74c3c": "#fff5f5",
            "#2ecc71": "#f0fff4",
            "#f0b429": "#fffbeb",
        }
        _LEGEND_ENTRIES = [
            ("🔄", "שינוי מחיר",
             "מוכר חוזר שסכום החיוב שלו השתנה ביחס לממוצע ההיסטורי. "
             "מופעל כשהשינוי עולה על 20% או ₪30."),
            ("🔍", "חיוב חוזר חסר",
             "מוכר שהופיע בכל אחד מ-3 החודשים האחרונים ולא הופיע החודש."),
            ("🆕", "מנוי חדש אפשרי",
             "חיוב ראשון ממוכר חדש בסכום קטן או עגול (עד ₪300)."),
            ("🔁", "חיוב כפול",
             "אותו מוכר חויב פעמיים באותו חודש בסכומים דומים (הפרש עד ₪5)."),
            ("📊", "קפיצה בקטגוריה",
             "סך ההוצאה בקטגוריה עלה פי 1.5 מהממוצע ההיסטורי שלה, ובלפחות ₪200."),
            ("💰", "עסקה חריגה",
             "עסקה בודדת שחורגת מ-95% מהעסקאות ההיסטוריות באותו מוכר או קטגוריה."),
            ("📅", "חודש הוצאות גבוה",
             "סך ההוצאות החודש גבוה ב-25% ומעלה מהממוצע ההיסטורי החודשי."),
            ("📈", "מגמת עלייה בהוצאות",
             "ההוצאות עלו ברציפות במשך 3 חודשים לפחות."),
        ]

        alerts_card = soup.find(id="alerts-card")
        if alerts:
            # Header row: title + count badge
            header = tag("div", class_="alerts-header")
            h2 = tag("h2")
            h2.string = "\u26a0 התראות חכמות"
            badge = tag("span", class_="alerts-count-badge")
            badge.string = f"{len(alerts)} התראות"
            header.append(h2)
            header.append(badge)
            alerts_card.append(header)

            # Alert matrix grid
            matrix = tag("div", class_="alerts-matrix")
            for alert in alerts:
                border_color = alert.color or "#f0b429"
                bg_color     = _BG_MAP.get(border_color, "#fafafa")

                a_div = tag("div", class_="alert-item")
                a_div["style"] = f"border-color:{border_color};background-color:{bg_color};"

                icon_sp = tag("span", class_="alert-icon")
                icon_sp.string = alert.icon or "\u2022"

                body = tag("div", class_="alert-body")
                ttl  = tag("strong")
                ttl.string = alert.title
                desc = tag("p")
                desc.string = alert.description
                body.append(ttl)
                body.append(desc)

                a_div.append(icon_sp)
                a_div.append(body)
                matrix.append(a_div)

            alerts_card.append(matrix)

            # Separated legend section
            legend_section = tag("div", class_="alerts-legend-section")
            legend_title = tag("div", class_="alerts-legend-title")
            legend_title["onclick"] = "toggleAlertLegend(this)"
            legend_title.string = "מקרא — הסבר על סוגי ההתראות"
            chevron = tag("span", class_="legend-chevron")
            chevron.string = "▲"
            legend_title.append(chevron)
            legend_section.append(legend_title)
            legend_grid = tag("div", class_="legend-grid")
            for icon, name, explanation in _LEGEND_ENTRIES:
                row = tag("div", class_="legend-row")
                ic  = tag("span", class_="legend-icon")
                ic.string = icon
                txt = tag("div", class_="legend-text")
                nm  = tag("strong")
                nm.string = name
                ex  = tag("span")
                ex.string = explanation
                txt.append(nm)
                txt.append(ex)
                row.append(ic)
                row.append(txt)
                legend_grid.append(row)
            legend_section.append(legend_grid)
            alerts_card.append(legend_section)
        else:
            empty = tag("div", class_="empty-state")
            es_icon = tag("span", class_="es-icon")
            es_icon.string = "\u2705"
            empty.append(es_icon)
            empty.append("אין התראות לחודש זה")
            alerts_card.append(empty)

        # ── Accounts ───────────────────────────────────────────────────
        import json as _json
        from datetime import date as _date

        VIRTUAL_ACCOUNTS = {"נכס שלום שבזי"}

        # Group classification by account name keywords
        def _acct_group(name):
            _n = name
            if name in VIRTUAL_ACCOUNTS or "נכס" in _n:
                return "נדל\"ן"
            for kw in ["אלטשולר", "אנליסט", "Analyst", "btb", "BTB", "השקעות", "קופ", "גמל", "פנסי", "ביטוח", "Interactive", "Brokers"]:
                if kw in _n:
                    return "השקעות"
            return "כללי"

        _GROUP_ORDER = ["כללי", "השקעות", "נדל\"ן"]

        def _to_date_safe(d):
            if hasattr(d, 'date') and callable(d.date):
                return d.date()
            return d

        _today_d = datetime.now().date()
        _stale_threshold = 30  # days

        # Build rich account info dict
        recent_accounts_data = {}
        total_balance = 0
        for account, values in accounts_data.items():
            if account == 'Total' or not values:
                continue
            sorted_vals = sorted(values, key=lambda x: _to_date_safe(x[0]))
            latest_date  = _to_date_safe(sorted_vals[-1][0])
            latest_value = sorted_vals[-1][1]
            if latest_value == 0:
                continue
            prev_value = sorted_vals[-2][1] if len(sorted_vals) >= 2 else None
            history = [(_to_date_safe(d), float(v)) for d, v in sorted_vals]
            # Find value closest to 1 year ago
            _one_year_ago = _today_d.replace(year=_today_d.year - 1)
            _year_prev = None
            if len(history) >= 2:
                _past = [(abs((d - _one_year_ago).days), v) for d, v in history if d <= latest_date]
                if _past:
                    _best = min(_past, key=lambda x: x[0])
                    # Only use if within 90 days of the target and not the current entry
                    if _best[0] <= 90 and (_to_date_safe(sorted_vals[-1][0]) != _one_year_ago or len(_past) > 1):
                        _year_prev = float(_best[1])
            recent_accounts_data[account] = {
                'date':      latest_date,
                'value':     float(latest_value),
                'prev':      float(prev_value) if prev_value is not None else None,
                'year_prev': _year_prev,
                'history':   history,
                'group':     _acct_group(account),
                'stale':     (_today_d - latest_date).days > _stale_threshold,
            }
            total_balance += float(latest_value)

        # Helper: build SVG sparkline from history (last N points)
        def _sparkline(history, n=12, w=64, h=22):
            pts = history[-n:] if len(history) >= n else history
            if len(pts) < 2:
                return ""
            vals = [v for _, v in pts]
            mn, mx = min(vals), max(vals)
            rng = mx - mn or 1
            xs = [round(i * (w - 2) / (len(pts) - 1) + 1, 1) for i in range(len(pts))]
            ys = [round((1 - (v - mn) / rng) * (h - 4) + 2, 1) for v in vals]
            pts_str = " ".join(f"{x},{y}" for x, y in zip(xs, ys))
            trend_col = "#43a047" if vals[-1] >= vals[0] else "#e53935"
            return (
                f'<svg class="acct-spark" width="{w}" height="{h}" '
                f'viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">'
                f'<polyline points="{pts_str}" fill="none" stroke="{trend_col}" '
                f'stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>'
                f'</svg>'
            )

        # Helper: format change cell
        def _change_cell(current, prev):
            if prev is None or prev == 0:
                return None, None, "acct-change-neu"
            delta = current - prev
            pct   = delta / abs(prev) * 100
            sign  = "+" if delta >= 0 else ""
            amount_text = f"{sign}{delta:,.0f}₪"
            pct_text    = f"{sign}{pct:.1f}%"
            cls   = "acct-change-pos" if delta >= 0 else "acct-change-neg"
            return amount_text, pct_text, cls

        acct_wrap = soup.find(id="accounts-table")
        tbl = tag("table")
        # Header — 7 columns
        _CUR_SYM = {'ILS': '₪', 'USD': '$', 'EUR': '€', 'JPY': '¥'}
        hdr = tag("tr")
        for col in ["חשבון", "יתרה", "שער", "שינוי", "שינוי/שנה", "עדכון אחרון", "מגמה"]:
            th = tag("th")
            if col == "שינוי":
                th.append(bs4.NavigableString("שינוי "))
                wrap = tag("span", class_="kpi-info-wrap")
                icon = tag("span", class_="kpi-info-icon"); icon.string = "i"
                tip  = tag("span", class_="kpi-tooltip")
                tip.string = (
                    "הפרש בין היתרה הנוכחית ליתרה הקודמת\n"
                    "שנרשמה עבור חשבון זה.\n"
                    "ₓ — אם אין רשומה קודמת."
                )
                wrap.append(icon); wrap.append(tip)
                th.append(wrap)
            elif col == "שינוי/שנה":
                th.append(bs4.NavigableString("שינוי/שנה "))
                wrap2 = tag("span", class_="kpi-info-wrap")
                icon2 = tag("span", class_="kpi-info-icon"); icon2.string = "i"
                tip2  = tag("span", class_="kpi-tooltip")
                tip2.string = (
                    "שינוי ביתרה ביחס לרשומה\n"
                    "הקרובה ביותר לפני שנה (±90 יום).\n"
                    "— אם אין נתון."
                )
                wrap2.append(icon2); wrap2.append(tip2)
                th.append(wrap2)
            elif col == "שער":
                th.append(bs4.NavigableString("שער ILS/X "))
                wrap3 = tag("span", class_="kpi-info-wrap")
                icon3 = tag("span", class_="kpi-info-icon"); icon3.string = "i"
                tip3  = tag("span", class_="kpi-tooltip")
                tip3.string = (
                    "שער חליפין נוכחי לחשבונות\n"
                    "שנרשמו ב-2 מטבעות (ILS + מטבע אחד).\n"
                    "— לחשבונות עם מטבע אחד או 3+."
                )
                wrap3.append(icon3); wrap3.append(tip3)
                th.append(wrap3)
            else:
                th.string = col
            hdr.append(th)
        tbl.append(hdr)

        # Group rows by type, with subtotals
        _groups_used = []
        for _grp in _GROUP_ORDER:
            _grp_accounts = {k: v for k, v in recent_accounts_data.items() if v['group'] == _grp}
            if not _grp_accounts:
                continue
            _groups_used.append(_grp)

            # Group header row
            gh_row = tag("tr"); gh_row["class"] = "acct-group-header"
            gh_td  = tag("td"); gh_td["colspan"] = "7"; gh_td.string = _grp; gh_row.append(gh_td)
            tbl.append(gh_row)

            _grp_total = 0.0
            for account, info in _grp_accounts.items():
                row = tag("tr")
                _classes = []
                if account in VIRTUAL_ACCOUNTS:
                    _classes.append("acct-virtual")
                if info['stale']:
                    _classes.append("acct-stale")
                    _days_old = (_today_d - info['date']).days
                    row["title"] = (
                        f"עדכון אחרון: {info['date'].strftime('%Y-%m-%d')} "
                        f"({_days_old} ימים ללא עדכון) — "
                        f"מומלץ לעדכן את היתרה"
                    )
                if _classes:
                    row["class"] = " ".join(_classes)

                # Account name cell
                td_name = tag("td"); td_name.string = account; row.append(td_name)

                # Balance cell — show raw value in last-inserted currency (ILS for ILS accounts)
                _meta     = (accounts_meta or {}).get(account, {})
                _last_cur = _meta.get('last_currency', 'ILS') or 'ILS'
                _last_val = _meta.get('last_raw_value')
                _all_curs = _meta.get('currencies', {'ILS'})
                _rate_cur = _meta.get('rate_cur')
                _rate_val = _meta.get('rate')
                _cur_sym  = _CUR_SYM.get(_last_cur, _last_cur)
                td_val = tag("td")
                if _last_val is not None and _last_cur != 'ILS':
                    td_val.string = f"{_cur_sym}{_last_val:,.2f}"
                else:
                    td_val.string = f"{info['value']:,.2f}\u20aa"
                row.append(td_val)

                # Exchange rate cell — only for exactly-2-currency accounts (ILS + one other)
                td_rate = tag("td"); td_rate["class"] = "acct-rate-cell"
                if len(_all_curs) == 2 and _rate_val and _rate_cur:
                    _rate_dec = 3 if _rate_cur == 'JPY' else 2
                    td_rate.string = f"{_rate_val:.{_rate_dec}f}"
                    td_rate["data-rate-cur"] = _rate_cur
                else:
                    td_rate.string = "\u2014"
                row.append(td_rate)

                # Change cell (vs previous entry)
                chg_amount, chg_pct, chg_cls = _change_cell(info['value'], info['prev'])
                td_chg = tag("td"); td_chg["class"] = chg_cls
                if chg_amount is None:
                    td_chg.string = "—"
                else:
                    amt_span = tag("span"); amt_span.string = chg_amount + " "
                    badge_cls = "acct-pct-badge acct-pct-pos" if chg_cls == "acct-change-pos" else "acct-pct-badge acct-pct-neg"
                    pct_span = tag("span"); pct_span["class"] = badge_cls; pct_span.string = chg_pct
                    td_chg.append(amt_span); td_chg.append(pct_span)
                row.append(td_chg)

                # Year-change cell (vs ~1 year ago)
                yr_amount, yr_pct, yr_cls = _change_cell(info['value'], info['year_prev'])
                td_yr = tag("td"); td_yr["class"] = yr_cls
                if yr_amount is None:
                    td_yr.string = "—"
                else:
                    yr_amt_span = tag("span"); yr_amt_span.string = yr_amount + " "
                    yr_badge_cls = "acct-pct-badge acct-pct-pos" if yr_cls == "acct-change-pos" else "acct-pct-badge acct-pct-neg"
                    yr_pct_span = tag("span"); yr_pct_span["class"] = yr_badge_cls; yr_pct_span.string = yr_pct
                    td_yr.append(yr_amt_span); td_yr.append(yr_pct_span)
                row.append(td_yr)

                # Date cell — with detail tooltip for virtual accounts
                td_date = tag("td")
                if account == "נכס שלום שבזי" and mortgage_data:
                    md = mortgage_data
                    appr = md.get('apartment_appreciated', 0)
                    bal  = md.get('current_balance', 0)
                    rate = md.get('default_rate', 5.0)
                    inc  = md.get('alltime_income', 0)
                    td_date["class"] = "acct-detail-cell"
                    td_date.string = (
                        f"{info['date'].strftime('%Y-%m-%d')} | "
                        f"שוק: ₪{appr:,.0f} | "
                        f"משכנתא: ₪{bal:,.0f} | "
                        f"הכנסות: ₪{inc:,.0f} | "
                        f"{rate:.0f}%/שנה"
                    )
                else:
                    td_date.string = info['date'].strftime('%Y-%m-%d')
                row.append(td_date)

                # Sparkline cell
                td_spark = tag("td")
                td_spark["class"] = "acct-detail-cell"
                spark_svg = _sparkline(info['history'])
                if spark_svg:
                    td_spark.append(bs4.BeautifulSoup(spark_svg, 'html.parser'))
                else:
                    td_spark.string = "—"
                row.append(td_spark)

                tbl.append(row)
                _grp_total += info['value']

            # Subtotal row (ILS)
            sub_row = tag("tr"); sub_row["class"] = "acct-subtotal"
            td_sub_name = tag("td"); td_sub_name.string = f"סה\"כ {_grp}"; sub_row.append(td_sub_name)
            td_sub_val  = tag("td"); td_sub_val.string = f"{_grp_total:,.2f}\u20aa"; sub_row.append(td_sub_val)
            for _ in range(5):
                sub_row.append(tag("td"))
            tbl.append(sub_row)

        # Grand total row (ILS)
        tot_row = tag("tr"); tot_row["class"] = "acct-total"
        td_tot_name = tag("td"); td_tot_name.string = "סה\"כ כל החשבונות"; tot_row.append(td_tot_name)
        td_tot_val  = tag("td"); td_tot_val.string  = f"{total_balance:,.2f}\u20aa"; tot_row.append(td_tot_val)
        for _ in range(5):
            tot_row.append(tag("td"))
        tbl.append(tot_row)
        acct_wrap.append(tbl)

        # ── Interactive accounts chart (Chart.js) with % toggle + annotation ──
        _all_dates = sorted(set(
            (d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10])
            for vals in accounts_data.values() for d, _ in vals
        ))

        _PALETTE = [
            "#90caf9",  # gentle blue
            "#ffcc80",  # gentle amber
            "#a5d6a7",  # gentle green
            "#ef9a9a",  # gentle red
            "#ce93d8",  # gentle purple
            "#b0bec5",  # gentle blue-grey
            "#f48fb1",  # gentle pink
            "#80deea",  # gentle cyan
            "#e6ee9c",  # gentle lime
            "#ffab91",  # gentle deep-orange
            "#80cbc4",  # gentle teal
            "#c5e1a5",  # gentle light-green
            "#bcaaa4",  # gentle brown
        ]

        _datasets = []
        for _i, (_aname, _vals) in enumerate(accounts_data.items()):
            _val_map = {
                (d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10]): round(float(v), 2)
                for d, v in _vals
            }
            _col = _PALETTE[_i % len(_PALETTE)]
            _datasets.append({
                "label":           _aname,
                "data":            [_val_map.get(d) for d in _all_dates],
                "borderColor":     _col,
                "backgroundColor": _col,
                "pointRadius":     4,
                "pointHoverRadius":8,
                "tension":         0.35,
                "spanGaps":        True,
            })

        _chart_json = _json.dumps({"labels": _all_dates, "datasets": _datasets}, ensure_ascii=False)

        # Mortgage start annotation
        _annot_date = (mortgage_data or {}).get('first_payment_date', '')
        _annot_js = ""
        if _annot_date:
            _annot_js = f"""
        annotation: {{
          annotations: {{
            mortgageStart: {{
              type: 'line',
              xMin: '{_annot_date}',
              xMax: '{_annot_date}',
              borderColor: '#ef9a9a',
              borderWidth: 2,
              borderDash: [6, 3],
              label: {{
                display: true,
                content: 'תחילת משכנתא',
                position: 'start',
                yAdjust: -14,
                backgroundColor: 'rgba(239,154,154,0.85)',
                color: '#fff',
                font: {{ size: 11 }},
                padding: {{ x: 6, y: 3 }},
              }}
            }}
          }}
        }},"""

        _canvas = tag("canvas"); _canvas["id"] = "acct-chart-canvas"
        _canvas["style"] = "width:100%;height:100%;"

        _script = tag("script")
        _script.string = f"""
(function(){{
  const ctx = document.getElementById('acct-chart-canvas').getContext('2d');
  new Chart(ctx, {{
    type: 'line',
    data: {_chart_json},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      layout: {{ padding: {{ top: 28 }} }},
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{
          position: 'top',
          labels: {{ font: {{ size: 12 }}, padding: 16 }}
        }},
        tooltip: {{
          rtl: true,
          callbacks: {{
            label: function(ctx) {{
              const v = ctx.parsed.y;
              if (v == null) return null;
              return ctx.dataset.label + ': \u20aa' + Math.round(v).toLocaleString('he-IL');
            }},
            title: function(items) {{ return items[0]?.label ?? ''; }}
          }}
        }},{_annot_js}
      }},
      scales: {{
        x: {{
          ticks: {{ maxRotation: 45, autoSkip: true, maxTicksLimit: 18, font: {{ size: 11 }} }}
        }},
        y: {{
          ticks: {{
            callback: function(v) {{ return '\u20aa' + Math.round(v).toLocaleString('he-IL'); }},
            font: {{ size: 11 }}
          }}
        }}
      }}
    }}
  }});
}})();
"""

        acct_chart = soup.find(id="accounts-chart")
        acct_chart.append(_canvas)
        acct_chart.append(_script)

        # ── Housing / Mortgage panel ───────────────────────────────────
        if mortgage_data:
            from src_utils.mortgage import TRACKS

            housing_panel = soup.find(id="panel-housing")

            def _h_kpi(label, value_str, color="#1e9d8b", sublabel=None, info=None,
                       elem_id=None, sublabel_id=None, tooltip_id=None):
                card = tag("div", class_="kpi-card")
                lbl  = tag("div", class_="kpi-label")
                lbl.append(bs4.NavigableString(label))
                if info:
                    wrap = tag("span", class_="kpi-info-wrap")
                    icon = tag("span", class_="kpi-info-icon")
                    icon.string = "i"
                    tip  = tag("span", class_="kpi-tooltip")
                    tip.string = info
                    if tooltip_id:
                        tip["id"] = tooltip_id
                    wrap.append(icon)
                    wrap.append(tip)
                    lbl.append(wrap)
                val  = tag("div", class_="kpi-value")
                val.string = value_str
                val["style"] = f"color:{color}"
                if elem_id:
                    val["id"] = elem_id
                card.append(lbl)
                card.append(val)
                if sublabel:
                    sub = tag("div", class_="kpi-sublabel")
                    sub.string = sublabel
                    if sublabel_id:
                        sub["id"] = sublabel_id
                    card.append(sub)
                return card

            md = mortgage_data

            apt_price    = md['apartment_price']
            cur_bal      = md['current_balance']
            apt_appr     = md['apartment_appreciated']
            eq_appr      = md['equity_appreciated']
            mo_appr      = md['monthly_appreciation']
            yrs          = md['years_elapsed']
            cat          = md['mortgage_category']
            def_rate     = md['default_rate']
            net_inv      = md['net_invested']
            tot_ret      = md['total_return_pct']
            ann_ret      = md['annual_return_pct']
            init_pmt     = md['initial_apartment_payment']

            def _section(title):
                t = tag("div", class_="housing-section-title")
                t.string = title
                housing_panel.append(t)

            def _row2(card_a, card_b, extra_class=""):
                row = tag("div", class_=f"housing-2col-row {extra_class}".strip())
                row.append(card_a)
                row.append(card_b)
                housing_panel.append(row)

            # ── Rate slider control card ───────────────────────────────
            rate_card = tag("div", class_="kpi-card housing-rate-control")
            rate_top  = tag("div", class_="rate-control-top")
            rate_lbl  = tag("div", class_="rate-label")
            rate_lbl.string = "שיעור עליית ערך שנתי"
            rate_val  = tag("span", class_="rate-value-display")
            rate_val["id"] = "hs-rate-display"
            rate_val.string = f"{def_rate:.1f}%"
            rate_top.append(rate_lbl)
            rate_top.append(rate_val)
            slider    = tag("input")
            slider["type"]  = "range"
            slider["id"]    = "hs-rate-slider"
            slider["min"]   = "0"
            slider["max"]   = "20"
            slider["step"]  = "0.5"
            slider["value"] = str(def_rate)
            slider["class"] = "rate-slider"
            rate_hint = tag("div", class_="rate-hint")
            rate_hint.string = "ברירת מחדל 5% | גרור לשינוי"
            rate_card.append(rate_top)
            rate_card.append(slider)
            rate_card.append(rate_hint)
            # rate_card is appended AFTER the balance row (see below)

            # ── Row 1: Balance + Equity (big) ─────────────────────────
            down_pmt       = md['down_payment']                   # theoretical (apt_price - mortgage)
            init_pay       = md['initial_apartment_payment']       # actual cash paid upfront
            mort_orig      = md['mortgage_amount']                # original mortgage
            principal_paid = mort_orig - cur_bal                  # equity built via payments
            appr_gain_val  = apt_appr - apt_price                 # appreciation gain

            def _pct(v): return round(v / apt_appr * 100, 2)
            pct_mtg  = _pct(cur_bal)
            pct_down = _pct(init_pay)
            pct_prin = _pct(principal_paid)
            pct_appr = _pct(appr_gain_val)

            # הון עצמי card — built manually to include the 4-segment breakdown bar
            alltime_inc_val = md['alltime_income']
            eq_with_inc     = eq_appr + alltime_inc_val   # equity + total income received

            equity_card = tag("div", class_="kpi-card")
            eq_lbl = tag("div", class_="kpi-label")
            eq_lbl.append(bs4.NavigableString("הון עצמי"))
            eq_info_wrap = tag("span", class_="kpi-info-wrap")
            eq_icon = tag("span", class_="kpi-info-icon"); eq_icon.string = "i"
            eq_tip  = tag("span", class_="kpi-tooltip")
            eq_tip.string = (
                f"הון עצמי = מקדמה + קרן שנפרעה + עליית ערך + סה״כ הכנסות\n"
                f"  מקדמה:          {init_pay:,.0f}₪\n"
                f"  קרן שנפרעה:    {principal_paid:,.0f}₪\n"
                f"  עליית ערך:     {appr_gain_val:,.0f}₪\n"
                f"  סה״כ הכנסות:   {alltime_inc_val:,.0f}₪\n"
                f"  = סה״כ:         {eq_with_inc:,.0f}₪"
            )
            eq_info_wrap.append(eq_icon); eq_info_wrap.append(eq_tip)
            eq_lbl.append(eq_info_wrap)
            eq_val = tag("div", class_="kpi-value")
            eq_val.string = f"{eq_with_inc:,.0f}\u20aa"
            eq_val["style"] = "color:#1e9d8b"
            eq_val["id"] = "hs-equity"
            eq_sub = tag("div", class_="kpi-sublabel")
            eq_sub.string = "כולל עליית ערך והכנסות"

            # 4-segment bar: מקדמה | קרן שנפרעה | עליית ערך | הכנסות
            eq_total   = max(eq_with_inc, 1)
            peq_down   = round(init_pay         / eq_total * 100, 2)
            peq_prin   = round(principal_paid   / eq_total * 100, 2)
            peq_appr   = round(appr_gain_val    / eq_total * 100, 2)
            peq_inc    = round(alltime_inc_val  / eq_total * 100, 2)

            C_DOWN  = "#81c784"   # gentle green — down payment
            C_PRIN  = "#4db6ac"   # gentle teal  — principal repaid
            C_APPR  = "#64b5f6"   # gentle blue  — appreciation
            C_INC   = "#aed581"   # gentle lime  — income received

            eq_bar_wrap = tag("div", class_="equity-bar-wrap")
            eq_bar      = tag("div", class_="equity-bar")

            def _bar_seg(elem_id, pct, color, title_txt):
                s = tag("div", class_="equity-bar-seg")
                s["id"]    = elem_id
                s["style"] = f"width:{pct}%;background:{color}"
                s["title"] = title_txt
                return s

            eq_bar.append(_bar_seg("hs-bar-down", peq_down, C_DOWN,
                                   f"מקדמה ₪{init_pay:,.0f}"))
            eq_bar.append(_bar_seg("hs-bar-prin", peq_prin, C_PRIN,
                                   f"קרן שנפרעה ₪{principal_paid:,.0f}"))
            eq_bar.append(_bar_seg("hs-bar-appr", peq_appr, C_APPR,
                                   f"עליית ערך ₪{appr_gain_val:,.0f}"))
            eq_bar.append(_bar_seg("hs-bar-inc",  peq_inc,  C_INC,
                                   f"סה״כ הכנסות ₪{alltime_inc_val:,.0f}"))

            # Legend: 4 items
            eq_bar_labels = tag("div", class_="equity-bar-labels equity-bar-labels-4")

            def _lbl(text, color, elem_id=None):
                s = tag("span")
                s.string = f"\u25cf {text}"
                s["style"] = f"color:{color}"
                if elem_id: s["id"] = elem_id
                return s

            eq_bar_labels.append(_lbl(f"מקדמה ₪{init_pay:,.0f}",             C_DOWN, "hs-lbl-down"))
            eq_bar_labels.append(_lbl(f"קרן שנפרעה ₪{principal_paid:,.0f}",  C_PRIN, "hs-lbl-prin"))
            eq_bar_labels.append(_lbl(f"עליית ערך ₪{appr_gain_val:,.0f}",   C_APPR, "hs-lbl-appr"))
            eq_bar_labels.append(_lbl(f"הכנסות ₪{alltime_inc_val:,.0f}",    C_INC,  "hs-lbl-inc"))

            eq_bar_wrap.append(eq_bar); eq_bar_wrap.append(eq_bar_labels)
            equity_card.append(eq_lbl); equity_card.append(eq_val)
            equity_card.append(eq_sub); equity_card.append(eq_bar_wrap)

            _row2(
                _h_kpi("יתרת משכנתא", f"{cur_bal:,.0f}\u20aa", "#e74c3c",
                       info="הקרן שנותרה לתשלום על המשכנתא.\nמחושב לפי לוח סילוקין תיאורטי."),
                equity_card,
                "housing-balance-row"
            )

            # ── Rate slider (appears below balance cards) ──────────────
            housing_panel.append(rate_card)

            # ── Row 2: Purchase price | Monthly appreciation | Appreciated value ──
            row2 = tag("div", class_="housing-3col-row")
            row2.append(_h_kpi("מחיר רכישה", f"{apt_price:,.0f}\u20aa", "#1a3a5c",
                                info="מחיר הרכישה המקורי של הדירה (יולי 2025)."))
            row2.append(_h_kpi("עליית ערך חודשית", f"+{mo_appr:,.0f}\u20aa", "#1e9d8b",
                                sublabel=f"לפי {def_rate:.1f}%/שנה",
                                info="הרווח החודשי מעליית ערך הדירה.\n"
                                     "מחושב: שווי משוער × (1+שיעור)^(1/12) − 1).",
                                elem_id="hs-monthly-appr"))
            row2.append(_h_kpi("שווי שוק משוער", f"{apt_appr:,.0f}\u20aa", "#5b8dee",
                                sublabel=f"{def_rate:.1f}% עלייה שנתית | {yrs:.1f} שנים",
                                info=f"מחושב לפי: {apt_price:,.0f}₪ × (1+שיעור)^{yrs:.1f} שנים.\n"
                                     "ניתן לשנות את השיעור בסליידר למעלה.",
                                elem_id="hs-appr-price"))
            housing_panel.append(row2)

            # ── Row 3: Sale return ─────────────────────────────────────
            alltime_inc   = md['alltime_income']
            appr_gain     = apt_appr - apt_price          # appreciation gain only
            sale_proceeds = eq_appr                       # appreciated_price - cur_balance
            total_back    = sale_proceeds + alltime_inc   # everything you'd receive
            profit_val    = total_back - net_inv          # net profit

            ret_color = "#1e9d8b" if tot_ret >= 0 else "#e74c3c"
            ret_info  = (
                f"חישוב רווח ממכירה:\n"
                f"  שווי שוק:          {apt_appr:>12,.0f}₪\n"
                f"  עליית ערך:         {appr_gain:>+12,.0f}₪  ({def_rate:.1f}%/שנה × {yrs:.1f} שנים)\n"
                f"  יתרת משכנתא:      {-cur_bal:>12,.0f}₪  (תשלום לבנק)\n"
                f"  = הון עצמי:        {sale_proceeds:>12,.0f}₪\n"
                f"  + סה״כ הכנסות:    {alltime_inc:>12,.0f}₪  (שכירות + קטגוריה)\n"
                f"  ─────────────────────────────\n"
                f"  סה״כ תקבולים:     {total_back:>12,.0f}₪\n"
                f"  − סה״כ הוצאות:   {-net_inv:>12,.0f}₪\n"
                f"  = רווח נקי:        {profit_val:>+12,.0f}₪\n"
                f"\n⚠ לא כולל: מס שבח, עמלות תיווך, עלויות מכירה"
            )
            _row2(
                _h_kpi("תשואה כוללת ממכירה", f"{tot_ret:+.1f}%", ret_color,
                       sublabel=f"רווח נקי: {profit_val:+,.0f}₪",
                       info=ret_info,
                       elem_id="hs-total-return",
                       sublabel_id="hs-return-sublabel",
                       tooltip_id="hs-return-tooltip"),
                _h_kpi("תשואה שנתית (IRR)", f"{ann_ret:+.1f}%", ret_color,
                       sublabel=f"על פני {yrs:.1f} שנים",
                       info="תשואה שנתית מחושבת לפי: (1 + תשואה כוללת)^(1/שנים) − 1.\n"
                            "ניתן לשנות את שיעור עליית הערך בסליידר למעלה.",
                       elem_id="hs-annual-return")
            )

            # ── Section: All-time ──────────────────────────────────────
            _section("סיכום כולל — כל הזמנים")

            # Build spending card with breakdown bar
            _at_out      = md['alltime_out']
            _at_mort     = md['alltime_mortgage_payments']
            _at_init     = md['initial_apartment_payment']
            _at_other    = max(_at_out - _at_mort - _at_init, 0.0)

            def _spend_pct(v): return round(v / _at_out * 100, 2) if _at_out > 0 else 0

            _sp_out_card = tag("div", class_="kpi-card")

            # header row with info icon
            _sp_hdr = tag("div", class_="kpi-info-wrap")
            _sp_lbl = tag("div", class_="kpi-label"); _sp_lbl.string = "סה״כ הוצאות"
            _sp_ico = tag("span", class_="kpi-info-icon"); _sp_ico.string = "ⓘ"
            _sp_tip = tag("span", class_="kpi-tooltip")
            _sp_tip.string = (
                f"סך כל ההוצאות בקטגוריה '{cat}' מאז תחילת הנתונים.\n"
                f"  תשלומי משכנתא:        {_at_mort:>10,.0f}₪\n"
                f"  תשלום ראשוני לדירה:   {_at_init:>10,.0f}₪\n"
                f"  הוצאות אחרות:          {_at_other:>10,.0f}₪"
            )
            _sp_ico.append(_sp_tip); _sp_hdr.append(_sp_lbl); _sp_hdr.append(_sp_ico)
            _sp_out_card.append(_sp_hdr)

            _sp_val = tag("div", class_="kpi-value"); _sp_val.string = f"{_at_out:,.2f}₪"
            _sp_val["style"] = "color:#e74c3c"
            _sp_out_card.append(_sp_val)

            # Spending breakdown bar
            _sp_bar_wrap = tag("div", class_="equity-bar-wrap")
            _sp_bar      = tag("div", class_="equity-bar")

            SC_MORT  = "#e57373"   # gentle red — mortgage payments
            SC_INIT  = "#ef9a9a"   # lighter gentle red — initial purchase
            SC_OTHER = "#ffb74d"   # gentle amber — other spending

            def _sp_seg(pct, color, title_txt):
                s = tag("div", class_="equity-bar-seg")
                s["style"] = f"width:{pct}%;background:{color}"
                s["title"] = title_txt
                return s

            _sp_bar.append(_sp_seg(_spend_pct(_at_mort),  SC_MORT,
                                   f"תשלומי משכנתא ₪{_at_mort:,.0f}"))
            _sp_bar.append(_sp_seg(_spend_pct(_at_init),  SC_INIT,
                                   f"תשלום ראשוני לדירה ₪{_at_init:,.0f}"))
            _sp_bar.append(_sp_seg(_spend_pct(_at_other), SC_OTHER,
                                   f"הוצאות אחרות ₪{_at_other:,.0f}"))
            _sp_bar_wrap.append(_sp_bar)

            # Legend
            _sp_labels = tag("div", class_="equity-bar-labels-4")
            for txt, col in [
                (f"תשלומי משכנתא ₪{_at_mort:,.0f}",   SC_MORT),
                (f"תשלום ראשוני ₪{_at_init:,.0f}",     SC_INIT),
                (f"הוצאות אחרות ₪{_at_other:,.0f}",    SC_OTHER),
            ]:
                sp = tag("span"); sp.string = f"● {txt}"; sp["style"] = f"color:{col}"
                _sp_labels.append(sp)

            _sp_bar_wrap.append(_sp_labels)
            _sp_out_card.append(_sp_bar_wrap)

            _row2(
                _sp_out_card,
                _h_kpi("סה״כ הכנסות", f"{md['alltime_income']:,.2f}\u20aa", "#1e9d8b",
                       info=f"סך כל ההכנסות בקטגוריה '{cat}' מאז תחילת הנתונים.\nכולל כל תשלומי השכירות.")
            )

            # ── Rent-missing alert banner ──────────────────────────────
            if not md["rent_found"]:
                banner = tag("div", class_="housing-alert-banner")
                banner.string = (
                    f"\u26a0\ufe0f לא נמצאה הכנסת שכירות לחודש זה בקטגוריה \"{md.get('mortgage_category','שלום שבזי 7')}\" — "
                    "יש לבדוק אם התשלום התקבל."
                )
                housing_panel.append(banner)

            # ── Charts (Chart.js — inline, no PNG downloads) ─────────
            import json as _jmort
            charts_row = tag("div", class_="charts-grid")

            def _mort_chart_card(canvas_id, title, full_width=False):
                cls  = "chart-card full-width" if full_width else "chart-card"
                card = tag("div", class_=cls)
                ttl  = tag("div", class_="chart-card-title")
                ttl.string = title; card.append(ttl)
                wrap = tag("div"); wrap["style"] = "position:relative;height:280px;"
                cv   = tag("canvas"); cv["id"] = canvas_id; cv["style"] = "width:100%;height:100%;"
                wrap.append(cv); card.append(wrap)
                return card, wrap

            TRACK_COLORS = {"fixed": "#1e9d8b", "variable": "#f0b429", "prime": "#5b8dee"}

            # 1. Balance chart (full-width line)
            cb = md.get("chart_balance", {})
            if cb:
                card_b, _ = _mort_chart_card("chart-mort-balance", "יתרת משכנתא לאורך הזמן", full_width=True)
                _datasets_b = []
                for _tn, _td in cb.get("tracks", {}).items():
                    _datasets_b.append({
                        "label": _tn, "data": _td["balance"],
                        "borderColor": TRACK_COLORS.get(_td["track_type"], "#aaa"),
                        "backgroundColor": "transparent",
                        "borderWidth": 1.3, "pointRadius": 0, "tension": 0.3,
                    })
                _datasets_b.append({
                    "label": 'סה"כ', "data": cb["total"],
                    "borderColor": "#1a3a5c", "backgroundColor": "transparent",
                    "borderWidth": 2.6, "pointRadius": 0, "tension": 0.3,
                })
                _today_key = cb.get("today", "")
                sc_b = tag("script")
                sc_b.string = f"""(function(){{
  var _todayKey = {_jmort.dumps(_today_key)};
  var ch = new Chart(document.getElementById('chart-mort-balance'), {{
    type: 'line',
    data: {_jmort.dumps({"labels": cb["months"], "datasets": _datasets_b})},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }}, padding: 8, boxWidth: 12 }} }},
        annotation: {{ annotations: [] }},
        tooltip: {{ rtl: true, callbacks: {{ label: function(c) {{
          return c.dataset.label + ': ₪' + Math.round(c.parsed.y).toLocaleString('he-IL');
        }} }} }}
      }},
      scales: {{
        x: {{ ticks: {{ maxTicksLimit: 12, maxRotation: 30, font: {{ size: 10 }} }} }},
        y: {{ ticks: {{ callback: function(v) {{ return '₪' + Math.round(v/1000) + 'K'; }}, font: {{ size: 10 }} }} }}
      }}
    }}
  }});
  // Draw "today" vertical line
  var todayIdx = {_jmort.dumps(cb["months"])}.indexOf(_todayKey);
  if (todayIdx >= 0) {{
    Chart.register({{
      id: 'todayLine-mort-balance',
      afterDraw(chart) {{
        var meta = chart.getDatasetMeta(chart.data.datasets.length - 1);
        var pt = meta.data[todayIdx];
        if (!pt) return;
        var ctx2 = chart.ctx, x = pt.x;
        ctx2.save();
        ctx2.strokeStyle = '#e74c3c'; ctx2.lineWidth = 1.5;
        ctx2.setLineDash([4, 3]);
        ctx2.beginPath(); ctx2.moveTo(x, chart.chartArea.top); ctx2.lineTo(x, chart.chartArea.bottom);
        ctx2.stroke(); ctx2.restore();
      }}
    }});
    ch.update();
  }}
}})();"""
                card_b.append(sc_b)
                charts_row.append(card_b)

            # 2. Breakdown chart (stacked bar)
            cbk = md.get("chart_breakdown", {})
            if cbk:
                card_br, _ = _mort_chart_card("chart-mort-breakdown", "פירוט קרן וריבית")
                _data_br = _jmort.dumps({
                    "labels": cbk["months"],
                    "datasets": [
                        {"label": "ריבית",  "data": cbk["interest"],  "backgroundColor": "#f66b85", "stack": "s"},
                        {"label": "קרן",    "data": cbk["principal"], "backgroundColor": "#1e9d8b", "stack": "s"},
                    ]
                })
                sc_br = tag("script")
                sc_br.string = f"""(function(){{
  new Chart(document.getElementById('chart-mort-breakdown'), {{
    type: 'bar',
    data: {_data_br},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }}, padding: 8, boxWidth: 12 }} }},
        tooltip: {{ rtl: true, callbacks: {{ label: function(c) {{
          return c.dataset.label + ': ₪' + Math.round(c.parsed.y).toLocaleString('he-IL');
        }} }} }}
      }},
      scales: {{
        x: {{ stacked: true, ticks: {{ maxTicksLimit: 8, font: {{ size: 10 }} }} }},
        y: {{ stacked: true, ticks: {{ callback: function(v) {{ return '₪' + Math.round(v).toLocaleString('he-IL'); }}, font: {{ size: 10 }} }} }}
      }}
    }}
  }});
}})();"""
                card_br.append(sc_br)
                charts_row.append(card_br)

            # 3. Cashflow chart (grouped bar — actual transactions, projected future)
            ccf = md.get("chart_cashflow", {})
            if ccf:
                card_cf, _ = _mort_chart_card("chart-mort-cashflow", "תזרים מזומנים — דיור")
                _is_proj   = ccf.get("is_proj", [False] * len(ccf.get("months", [])))
                # Actual bars: solid; projected bars: 50% opacity
                _pay_colors = ["rgba(246,107,133,0.45)" if p else "#f66b85" for p in _is_proj]
                _inc_colors = ["rgba(30,157,139,0.45)"  if p else "#1e9d8b" for p in _is_proj]
                _data_cf = _jmort.dumps({
                    "labels": ccf["months"],
                    "datasets": [
                        {"label": "הוצאות דיור",   "data": ccf["payments"],
                         "backgroundColor": _pay_colors},
                        {"label": "הכנסות דיור",   "data": ccf["rentals"],
                         "backgroundColor": _inc_colors},
                    ]
                })
                _proj_flags = _jmort.dumps(_is_proj)
                sc_cf = tag("script")
                sc_cf.string = f"""(function(){{
  var _isProj = {_proj_flags};
  new Chart(document.getElementById('chart-mort-cashflow'), {{
    type: 'bar',
    data: {_data_cf},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }}, padding: 8, boxWidth: 12 }} }},
        tooltip: {{ rtl: true, callbacks: {{ label: function(c) {{
          var suffix = _isProj[c.dataIndex] ? ' (חיזוי)' : '';
          return c.dataset.label + ': ₪' + Math.round(c.parsed.y).toLocaleString('he-IL') + suffix;
        }} }} }}
      }},
      scales: {{
        x: {{ ticks: {{ maxTicksLimit: 14, font: {{ size: 10 }} }} }},
        y: {{ ticks: {{ callback: function(v) {{ return '₪' + Math.round(v).toLocaleString('he-IL'); }}, font: {{ size: 10 }} }} }}
      }}
    }}
  }});
}})();"""
                card_cf.append(sc_cf)
                charts_row.append(card_cf)

            housing_panel.append(charts_row)

            # ── Milestone table ───────────────────────────────────────
            ms_wrap = tag("div", class_="housing-milestones card")
            ms_ttl  = tag("div", class_="card-title")
            ms_ttl.string = "אבני דרך — יתרה משוערת"
            ms_wrap.append(ms_ttl)

            tbl  = tag("table", class_="milestone-table")
            # Header
            hdr  = tag("tr")
            for col in ["יתרת מטרה (₪)", "חודש משוער", "שנים מתחילת המשכנתא"]:
                th = tag("th"); th.string = col; hdr.append(th)
            tbl.append(hdr)
            # Rows
            for ms in md["milestones"]:
                row = tag("tr")
                d   = ms["date"]
                d_str = d.strftime("%m/%Y") if hasattr(d, "strftime") else str(d)
                for txt in [f"{ms['threshold']:,.0f}₪", d_str, f"{ms['years_from_start']}"]:
                    td = tag("td"); td.string = txt; row.append(td)
                tbl.append(row)
            ms_wrap.append(tbl)
            housing_panel.append(ms_wrap)

            # ── Track breakdown table ──────────────────────────────────
            tr_wrap = tag("div", class_="housing-tracks card")
            tr_ttl  = tag("div", class_="card-title")
            tr_ttl.string = "פירוט מסלולי משכנתא"
            tr_wrap.append(tr_ttl)

            tr_tbl = tag("table", class_="milestone-table")
            tr_hdr = tag("tr")
            for col in ["מסלול", "קרן מקורית (₪)", "ריבית שנתית", "תשלום חודשי (₪)", "סוג"]:
                th = tag("th"); th.string = col; tr_hdr.append(th)
            tr_tbl.append(tr_hdr)
            type_labels = {"fixed": "קבועה", "variable": "משתנה אג\"ח", "prime": "פריים"}
            for t_info in TRACKS:
                row = tag("tr")
                for txt in [
                    t_info["name"],
                    f"{t_info['principal']:,.0f}",
                    f"{t_info['annual_rate']:.2f}%",
                    f"{t_info['monthly_payment']:,.2f}",
                    type_labels.get(t_info["type"], t_info["type"]),
                ]:
                    td = tag("td"); td.string = txt; row.append(td)
                tr_tbl.append(row)
            # Total row
            tot = tag("tr", class_="track-total")
            for txt in ["סה״כ", f"{sum(t['principal'] for t in TRACKS):,.0f}", "—",
                        f"{sum(t['monthly_payment'] for t in TRACKS):,.2f}", "—"]:
                td = tag("td"); td.string = txt; tot.append(td)
            tr_tbl.append(tot)
            tr_wrap.append(tr_tbl)
            housing_panel.append(tr_wrap)

            # ── All transactions table ─────────────────────────────────
            txn_df = md.get("housing_transactions")
            if txn_df is not None and not txn_df.empty:
                txn_wrap = tag("div", class_="housing-txn-table card")
                txn_hdr  = tag("div", class_="card-title housing-txn-hdr")
                ttl_span = tag("span")
                ttl_span.string = f"כל העסקאות — {md['mortgage_category']}"
                cnt_span = tag("span", class_="panel-count", id="housing-footer-count")
                txn_hdr.append(ttl_span)
                txn_hdr.append(cnt_span)
                txn_wrap.append(txn_hdr)

                # Search box
                srch_wrap = tag("div", class_="txn-search-wrap")
                srch_inp  = tag("input", class_="txn-search", id="housing-txn-search",
                                type="text", placeholder="חיפוש עסקה...")
                srch_inp["oninput"] = "filterHousingTxns(this.value)"
                srch_wrap.append(srch_inp)
                txn_wrap.append(srch_wrap)

                txn_tbl = tag("table", class_="milestone-table housing-txn", id="housing-txn-tbl")
                hdr = tag("tr")
                for col in ["תאריך", "שם", "תיאור", "הוצאה (₪)", "הכנסה (₪)"]:
                    th = tag("th"); th.string = col; hdr.append(th)
                txn_tbl.append(hdr)

                for _, row in txn_df.iterrows():
                    tr = tag("tr")
                    # Date
                    td_date = tag("td")
                    td_date.string = str(row["Date"])[:10]
                    tr.append(td_date)
                    # Name
                    td_name = tag("td")
                    td_name.string = str(row["Name"] or "")
                    tr.append(td_name)
                    # Description
                    td_desc = tag("td")
                    desc_val = row.get("Description", "") if hasattr(row, "get") else ""
                    td_desc.string = str(desc_val) if desc_val and str(desc_val) != "nan" else "—"
                    td_desc["style"] = "color:#888; font-size:.88em;"
                    tr.append(td_desc)
                    # Out
                    td_out = tag("td")
                    out_val = row["Out"]
                    if out_val and float(out_val) > 0:
                        td_out.string = f"{float(out_val):,.2f}"
                        td_out["style"] = "color:#e74c3c; font-weight:600;"
                    else:
                        td_out.string = "—"
                    tr.append(td_out)
                    # Income
                    td_inc = tag("td")
                    inc_val = row["Income"]
                    if inc_val and float(inc_val) > 0:
                        td_inc.string = f"{float(inc_val):,.2f}"
                        td_inc["style"] = "color:#1e9d8b; font-weight:600;"
                    else:
                        td_inc.string = "—"
                    tr.append(td_inc)
                    txn_tbl.append(tr)

                txn_wrap.append(txn_tbl)

                # Totals footer (sum only — count is in the header)
                footer = tag("div", class_="txn-footer", id="housing-txn-footer")
                fs = tag("span", id="housing-footer-sum", class_="txn-footer-sum")
                footer.append(fs)
                txn_wrap.append(footer)

                housing_panel.append(txn_wrap)

            # ── Live rate slider JS ────────────────────────────────────
            js_vars = (
                f"const APT_PRICE={apt_price};"
                f"const CUR_BAL={cur_bal};"
                f"const N_MONTHS={md['months_elapsed']};"
                f"const NET_INV={net_inv};"
                f"const ALLTIME_INC={md['alltime_income']};"
                f"const INIT_PMT={init_pmt};"
                f"const DOWN_PMT={init_pay};"
                f"const PRIN_PAID={principal_paid};"
            )
            js_code = js_vars + r"""
const fmtNum  = n => Math.round(Math.abs(n)).toLocaleString('he-IL');
const fmtShek = n => (n < 0 ? '-' : '') + '₪' + fmtNum(n);
const fmtPct  = n => (n >= 0 ? '+' : '') + n.toFixed(1) + '%';

function hsRecalc(rate) {
  const yrs    = N_MONTHS / 12;
  const appr   = APT_PRICE * Math.pow(1 + rate / 100, yrs);
  const equity = appr - CUR_BAL;
  const moAppr = appr * (Math.pow(1 + rate / 100, 1 / 12) - 1);
  const apprGain = appr - APT_PRICE;

  // Sale return: profit = equity + all income - all spending
  const totalBack = equity + ALLTIME_INC;
  const profit    = totalBack - NET_INV;
  const totRet    = NET_INV > 0 ? profit / NET_INV * 100 : 0;
  const annRet    = N_MONTHS > 0 ? (Math.pow(1 + totRet / 100, 12 / N_MONTHS) - 1) * 100 : 0;
  const retColor  = totRet >= 0 ? '#1e9d8b' : '#e74c3c';

  // Update value elements
  document.getElementById('hs-appr-price').textContent   = fmtShek(appr);
  document.getElementById('hs-equity').textContent       = fmtShek(equity);
  document.getElementById('hs-monthly-appr').textContent = '+' + fmtShek(moAppr);
  const trEl = document.getElementById('hs-total-return');
  const arEl = document.getElementById('hs-annual-return');
  trEl.textContent = fmtPct(totRet);  trEl.style.color = retColor;
  arEl.textContent = fmtPct(annRet);  arEl.style.color = retColor;
  document.getElementById('hs-rate-display').textContent = rate.toFixed(1) + '%';

  // Update equity bar (4 segments: down payment, principal, appreciation, income)
  const apprGainVal = Math.max(apprGain, 0);
  const eqWithInc = equity + ALLTIME_INC;
  const eqTotal   = eqWithInc || 1;
  const pDown = DOWN_PMT      / eqTotal * 100;
  const pPrin = PRIN_PAID     / eqTotal * 100;
  const pAppr = apprGainVal   / eqTotal * 100;
  const pInc  = ALLTIME_INC   / eqTotal * 100;

  document.getElementById('hs-equity').textContent = fmtShek(eqWithInc);

  const _upSeg = (id, pct, label) => {
    const el = document.getElementById(id);
    if (el) { el.style.width = Math.max(pct, 0).toFixed(2) + '%'; el.title = label; }
  };
  _upSeg('hs-bar-down', pDown, 'מקדמה ₪'        + fmtNum(DOWN_PMT));
  _upSeg('hs-bar-prin', pPrin, 'קרן שנפרעה ₪'   + fmtNum(PRIN_PAID));
  _upSeg('hs-bar-appr', pAppr, 'עליית ערך ₪'    + fmtNum(apprGainVal));
  _upSeg('hs-bar-inc',  pInc,  'סה״כ הכנסות ₪'  + fmtNum(ALLTIME_INC));

  const _upLbl = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = '● ' + text; };
  _upLbl('hs-lbl-down', 'מקדמה ₪'        + fmtNum(DOWN_PMT));
  _upLbl('hs-lbl-prin', 'קרן שנפרעה ₪'   + fmtNum(PRIN_PAID));
  _upLbl('hs-lbl-appr', 'עליית ערך ₪'    + fmtNum(apprGainVal));
  _upLbl('hs-lbl-inc',  'הכנסות ₪'       + fmtNum(ALLTIME_INC));

  // Update sublabel (רווח נקי)
  const sl = document.getElementById('hs-return-sublabel');
  if (sl) sl.textContent = 'רווח נקי: ' + (profit >= 0 ? '+' : '') + fmtShek(profit);

  // Update tooltip breakdown
  const tt = document.getElementById('hs-return-tooltip');
  if (tt) tt.textContent =
    'חישוב רווח ממכירה:\n' +
    '  שווי שוק:          ' + fmtShek(appr)      + '\n' +
    '  עליית ערך:         ' + (apprGain >= 0 ? '+' : '') + fmtShek(apprGain) +
        '  (' + rate.toFixed(1) + '%/שנה × ' + yrs.toFixed(1) + ' שנים)\n' +
    '  יתרת משכנתא:      -' + fmtShek(CUR_BAL)   + '  (תשלום לבנק)\n' +
    '  = הון עצמי:        '  + fmtShek(equity)    + '\n' +
    '  + סה\u05bfכ הכנסות:    +' + fmtShek(ALLTIME_INC) + '  (שכירות + קטגוריה)\n' +
    '  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n' +
    '  סה\u05bfכ תקבולים:     ' + fmtShek(totalBack) + '\n' +
    '  \u2212 סה\u05bfכ הוצאות:   -' + fmtShek(NET_INV)   + '\n' +
    '  = רווח נקי:        ' + (profit >= 0 ? '+' : '') + fmtShek(profit) + '\n\n' +
    '\u26a0 לא כולל: מס שבח, עמלות תיווך, עלויות מכירה';
}

const slider = document.getElementById('hs-rate-slider');
if (slider) {
  slider.addEventListener('input', () => hsRecalc(parseFloat(slider.value)));
  hsRecalc(parseFloat(slider.value));
}
function _parseHousingAmt(text) {
  text = (text || '').trim().replace(/,/g, '');
  if (!text || text === '\u2014') return 0;
  return parseFloat(text) || 0;
}
function _fmtHousingSum(n) {
  var abs = Math.abs(n).toLocaleString('he-IL', {minimumFractionDigits:0, maximumFractionDigits:0});
  return n < 0 ? '(' + abs + ') \u20aa' : abs + ' \u20aa';
}
function _updateHousingFooter(rows) {
  var totalOut = 0, totalInc = 0, visible = 0;
  rows.forEach(function(row) {
    if (row.style.display === 'none') return;
    visible++;
    var cells = row.querySelectorAll('td');
    if (cells[2]) totalOut += _parseHousingAmt(cells[2].textContent);
    if (cells[3]) totalInc += _parseHousingAmt(cells[3].textContent);
  });
  var fc = document.getElementById('housing-footer-count');
  if (fc) fc.textContent = visible + ' \u05e2\u05e1\u05e7\u05d0\u05d5\u05ea';
  var fs = document.getElementById('housing-footer-sum');
  if (fs) {
    var net = totalInc - totalOut;
    fs.textContent = '\u05d4\u05d5\u05e6\u05d0\u05d5\u05ea: ' + _fmtHousingSum(totalOut) + '  |  \u05d4\u05db\u05e0\u05e1\u05d5\u05ea: ' + _fmtHousingSum(totalInc);
    fs.className = 'txn-footer-sum';
  }
}
function filterHousingTxns(q) {
  q = q.trim().toLowerCase();
  var tbl = document.getElementById('housing-txn-tbl');
  if (!tbl) return;
  var rows = tbl.querySelectorAll('tr:not(:first-child)');
  rows.forEach(function(row) {
    var cells = row.querySelectorAll('td');
    var text = Array.from(cells).map(function(c) { return c.textContent.toLowerCase(); }).join(' ');
    row.style.display = (!q || text.indexOf(q) !== -1) ? '' : 'none';
  });
  _updateHousingFooter(rows);
}
document.addEventListener('DOMContentLoaded', function() {
  var tbl = document.getElementById('housing-txn-tbl');
  if (tbl) _updateHousingFooter(tbl.querySelectorAll('tr:not(:first-child)'));
});
"""
            script = tag("script")
            script.string = js_code
            housing_panel.append(script)

        # ── Stamp body with month key and generation timestamp ─────────
        import os as _os
        from datetime import datetime as _dt
        _generated_at = _dt.now().strftime("%d/%m/%Y %H:%M")
        soup.body['data-month']     = f"{year:04d}_{month_num:02d}"
        soup.body['data-generated'] = _generated_at

        # ── Write output ───────────────────────────────────────────────
        _html_text = soup.prettify()

        with open(r"source\html\output.html", "w", encoding="utf-8") as outf:
            outf.write(_html_text)

        # ── Also write to Outputs/general_analysis/YYYY_MM.html ────────
        _utils_dir   = _os.path.dirname(_os.path.abspath(__file__))   # src_utils/
        _src_dir     = _os.path.dirname(_utils_dir)                    # source/
        _project_dir = _os.path.dirname(_src_dir)                      # BankProject/
        _ga_dir      = _os.path.join(_project_dir, 'Outputs', 'general_analysis')
        _os.makedirs(_ga_dir, exist_ok=True)
        _ga_path     = _os.path.join(_ga_dir, f"{year:04d}_{month_num:02d}.html")
        with open(_ga_path, "w", encoding="utf-8") as outf:
            outf.write(_html_text)

    @staticmethod
    def template_menu(options: list[str], msg: str = "Choose one of the following:\n", exit: bool = False, sort: bool = False, col_space: int = 27, row_count: int = 6 ) -> int:
        """
        The function creates a template menu that is printed out for the user.
        Inputs are @options - a list of strings containing different options.
                   @msg - str with a menu message
                   @sort - for sorting the options alphabetically
                   @exit - for adding a "Return" option at the top of the list (output of value 0)
        return a numbers from 0 to len(options) - 1 representing the chosen option.
        if input does not match a valid option, the function asks for a valid one.
        """
        if sort:
            options = sorted(options)
        
        if exit:
            # append to the head of the list for comfort reason
            options.insert(0, "[Return]")

        utils.log(msg + '\n', 'system')
        utils.pretty_print([f"{str(i) + ' -> ':6s}{utils.heb_conversion(x)}" for i, x in enumerate(options, start=0)], const=row_count, col_space=col_space)

        while True:
            x = input()
            if not x.isnumeric():
                continue
            x = int(x)
            if x < 0 or x >= len(options):
                utils.log('Insert a valid index number!', 'system')
                continue
            return x
        
    @staticmethod
    def typer_template_menu(options: list[str], msg: str = "Choose one of the following:\n", sort: bool = False) -> Tuple[int, list[str]]:
        """
        The function creates a template menu that is printed out for the user.
        The user is requested to insert a substring or a valid option number.
        If the substring existis in one of the printed options, the list of options will reduce to fit the substring.
        Inputs are @options - a list of strings containing different options.
                   @msg - str with a menu message
        return a numbers from 0 to len(options) - 1 representing the chosen option.
        """
        def get_substrings(lst: list[str], substring: str) -> list:
            substrings_lst = []

            for st in lst:
                if substring in st:
                    substrings_lst.append(st)
            
            return substrings_lst

        if sort:
            options = sorted(options)

        utils.log(msg + '\n', 'system')

        while True:
            utils.pretty_print([f"{str(i) + ' -> ':6s}{utils.heb_conversion(x)}" for i, x in enumerate(options, start=0)])
            x = input()
            if x.isnumeric(): 
                x = int(x)
                if x < 0 or x >= len(options):
                    continue
                return x, options
            else:   # x is text
                sub_options = get_substrings(options, x)
                if len(sub_options) == 0:
                    continue
                utils.pretty_print([f"{str(i) + ' -> ':6s}{utils.heb_conversion(x)}" for i, x in enumerate(sub_options, start=0)])
                x = input()
                if not x.isnumeric():
                    continue
                x = int(x)
                if x < 0 or x >= len(sub_options):
                    continue
                return x, sub_options

    @staticmethod
    def get_saved_categories(add_options: bool = False, sort: bool = True) -> list[str]:
        """
        returns the categories stored on the local config json
        in the path specified in CATE_JSON_PATH.
        The following options: ["「Create a new category」", "「Skip」", "「Back to menu」"]
        can be added to the list using the function argument @add_options.
        """
        cat_lst = json.load(open(Paths.CATEGORY_JSON, encoding='utf-8'))
        if sort:
            cat_lst = sorted(cat_lst)
        if add_options:
            cat_lst += ["「Create a new category」", "「Skip」", "「Back to menu」"]
        return cat_lst

    @staticmethod
    def update_categories_file(data: list, append: bool = True) -> None:
        """
        The function will write/append new category data to the category json file.
        """
        if append:
            old_data = utils.get_saved_categories(sort=False)
            json.dump(old_data + data, open(Paths.CATEGORY_JSON, "w", encoding='utf-8'))
        else:
            json.dump(data, open(Paths.CATEGORY_JSON, "w", encoding='utf-8'))

    @staticmethod
    def handle_categories() -> Tuple[str, str]:
        """
        The function returns a category name and its description as entered by the user.
        The categories are read from a json file and displayed with 3 adittional options.
        """
        # utils.log("Choose one of the existsing categories:")
        options = utils.get_saved_categories(add_options=True)
        # ----------- Input category and description -------------
        st = "Please insert your selection and description in the following format:\n*Number* - *Description*" + '\n'
        utils.log(st, 'system')
        utils.pretty_print([f"{str(i) + ' -> ':6s}{utils.heb_conversion(x)}" for i, x in enumerate(options, start=0)], const=8)

        number = -1
        description = ""
        while True:
            x = input()
            parts = x.split('-', 1)

            if not len(parts) in [1, 2]:
                utils.log("Bad format... try again.", 'system')
                continue

            if len(parts) >= 1:
                number_str = parts[0]
                number_str = number_str.strip()

                if not number_str.isdigit():
                    utils.log("first clause is not a number, try again...", "system")
                    continue

                number = int(number_str)

                if number < 0 or number >= len(options):
                    utils.log("Bad number, try again...", "system")
                    continue

            if len(parts) == 2:
                description = parts[1].strip()
            break

        res = number
        # ----------------------------------------------------------
        if options[res] == "「Create a new category」":
            while True:
                cat = input("Insert a category name: ")
                if cat in utils.get_saved_categories():
                    utils.log("This category name already exists...", "system")
                    continue
                utils.log("Are you sure?\n1-> Yes\n2-> No")
                x = input()
                if x == "1":
                    json.dump(utils.get_saved_categories() + [cat], open(Paths.CATEGORY_JSON, "w", encoding='utf-8'))
                    return cat, description
                else:
                    utils.log("Please Try again...", "system")
                    continue

        return options[res], description

    @staticmethod
    def is_headers_valid(format: str, file_name: str, headers: list, initial_row: int, header_col_index: int) -> bool:
        '''
        The function validates the table headers in the file.
        The values of the headers and the initial row are given in the Constants.py.

        The function will check nearby cells recursively until it finds the headers.
        Recursion will stop when the header is found or when the the offset is 5 cells away from the initial row/column.
        '''
        em = ExcelManager().set_active_sheet(Paths.INPUT_FOLDER + "\\" + file_name)
        
        col_max_offset = 2
        row_max_offset = 6
        
        col_range = \
            [i for i in range(header_col_index, header_col_index - col_max_offset, -1) if i >= 0] + \
            [i for i in range(header_col_index + 1, header_col_index + col_max_offset)] #range(max(0, header_col_index - col_max_offset), header_col_index + col_max_offset)  
        row_range = \
            [i for i in range(initial_row, initial_row - row_max_offset, -1) if i > 0] + \
            [i for i in range(initial_row + 1, initial_row + row_max_offset)]

        for i in row_range:
            for j in col_range:

                valid = True
                col = j
                row = i

                debug_list = [] # debug feature

                for name in headers:
                    value = em.read_cell(row, col)
                    
                    debug_list.append(value) # debug feature

                    if not value == name:
                        if col > j:
                            utils.log(f"Header Validation Failed halfway: {value} != {name}", "warning")
                        valid = False
                        break
                    col += 1
                if valid:
                    if row != initial_row:
                        utils.log(f"Headers were found at line {row}, Not in {initial_row} as specified.", "warning")
                    initial_row = row
                    return True
                utils.log(f"Header Validation Failed for {file_name} with format {format}\n extracted headers: {debug_list} ", "debug")
                continue
        return False

    @staticmethod
    def date_ready(date: str) -> datetime:
        """
        Converts a date string into a datetime object. The string has to be in one
        of the following formats: "%d-%m-%Y", "%d/%m/%Y", "%d/%m/%y"
        """
        formats = ["%d-%m-%Y", "%d/%m/%Y", "%d/%m/%y", "%d.%m.%y", "%d.%m.%Y"] # forth & fifth field added for Isra-Card-2026

        for fmt in formats:
            try:
                return datetime.strptime(date, fmt)
            except TypeError as e:
                utils.log(f"Got a Type error: date is of type {type(date)}, Should be str.", "error")
            except Exception as e:
                continue

        utils.log(f"func date_ready: Invalid date format. Please use '-' or '/' as separators...\n got the value: {date} of type {type(date)}.", "error")
        # following date will never be returned. placed for linter.
        return datetime(1, 1, 1)

    @staticmethod
    def amount_ready(value) -> int:
        if value == ' ':
            return 0
        return value

    @staticmethod
    def move_file_to_directory(file_path, destination_directory, create_dst: bool = True):
        try:
            # Check if the file exists
            if not os.path.isfile(file_path):
                utils.log(f"The specified file does not exist -> {file_path}", "error")

            # Get the base name of the file (the file name without the directory path)
            file_name = os.path.basename(file_path)

            if create_dst and not os.path.exists(destination_directory):
                utils.log(f"New directory made: {destination_directory}", "system")
                os.makedirs(destination_directory)

            ExcelManager().close_and_kill_excel()
            # Join the destination directory path with the file name to get the new file path
            new_file_path = os.path.join(destination_directory, file_name)

            # If the file is already at the destination (e.g. a previous move copied the
            # file but failed to delete the source because it was locked in Excel), just
            # remove the leftover source copy — the verified copy is already safe.
            if os.path.isfile(new_file_path):
                os.remove(file_path)
                utils.log(f"File already at destination; removed source copy: {file_path}", "system")
                return

            # Move the file to the destination directory
            shutil.move(file_path, new_file_path)

            utils.log(f"File moved successfully to {new_file_path}", "system")
        except Exception as e:
            utils.log(f"Something happend.. Could not move the file -> {e}", "warning")

    @staticmethod
    def move_to_recycle_bin(file_path):
        try:
            send2trash.send2trash(file_path)
            utils.log(f"File '{file_path}' sent to recycle bin.", 'system')
        except Exception as e:
            utils.log(f"Failed to send '{file_path}' to recycle bin: {e}", 'system')

    @staticmethod
    def reg_extract(rule: str, text: str) -> str:
        """
        The function returns the first match from the text according to the given rule.
        """
        import re

        matches = re.findall(rule, text)

        if matches:
            return matches[0]
        else:
            utils.log(f"In function reg_extract, No match was found for\n \
                       rule: {rule}     |   string: {text}", "error")
            return "Code won't reach here"

    @staticmethod
    def next_month(date: datetime) -> datetime:
        """
        receives a month - a number between 1 - 12 describing 
        returns the next month/year 
        """
        from dateutil.relativedelta import relativedelta

        # Get the next month by adding a relativedelta of 1 month
        return date + relativedelta(months=1)
    
    @staticmethod
    def previous_month(date: datetime) -> datetime:
        """
        receives a month - a number between 1 - 12 describing 
        returns the next month/year 
        """
        from dateutil.relativedelta import relativedelta

        # Get the next month by adding a relativedelta of 1 month
        return date - relativedelta(months=1)


    @staticmethod
    def subtract_month(month: int, year: int) -> Tuple[str, str]:
        """
        Function returns the date, one month before the given one (not including the day)
        The format is: MM, YYYY
        """

        if month == 1:
            month = 12
            year -= 1
        elif 1 < month <= 12:
            month -= 1
        else:
            utils.log("Month must be between 1 and 12, inclusive.", 'error')

        str_month = str(month)
        if len(str_month) == 1:
            str_month = '0' + str_month

        return str_month, str(year)

    @staticmethod
    def next_day(date: datetime) -> datetime:
        from datetime import datetime, timedelta

        # Assuming your datetime object is stored in the variable `current_datetime`
        current_datetime = datetime.now()  # Replace this with your datetime object

        # Get the next day by adding a timedelta of 1 day
        return current_datetime + timedelta(days=1)


    @staticmethod
    def remove_leumi(df: pd.DataFrame) -> pd.DataFrame:
        return df[(df['Name'] != 'לאומי ויזה') & (df['Category'] != 'IGNORE')]

    @staticmethod
    def pretty_print(lst: list, const: int = 6, col_space: int = 27) -> None:
        """
        The function prints the given list in a rectangle shaped pattern.
        The elements are indexed from 0 to n - 1.
        The rectangle is set to have a maximun of @const elements per column.
        The col_space argument indicates the the space between each column.
        """
        n = len(lst)
        m = 1 + n // const
        for i in range(0, const):
            for j in range(0, m):
                index = i + const*j
                if index >= len(lst):
                    break
                print(f"{lst[index]:{col_space}s}", end="")
            print()


    @staticmethod
    def validate_constants() -> Union[str, bool]:
        """
        check if all the category values under USER_DEFINED_CATEGORIES exist in the categories.json file.
        """
        from Constants import GeneralPlot

        # Read the categories from the JSON file
        with open(Paths.CATEGORY_JSON, encoding='utf-8') as file:
            categories = json.load(file)
        # Check if all user-defined categories exist in the JSON file
        for category in GeneralPlot.USER_DEFINED_CATEGORIES:
            if category not in categories:
                return f"Category '{category}' not found in categories.json - Check (USER_DEFINED_CATEGORIES) in Constants.py"


        return True

    @staticmethod
    def validate_formats() -> Union[str, bool]:
        """
        The function Checks the validity of the formats filled in by the user
        According to the rules. (The rules are not yet documented).
        If an error accures, a string is returned, otherwise, True is returned.
        """
        from Configurations.Formats import Formats, Identification_Method, Context_class, Sortion_Method
        formats = Formats.FORMATS
        utils.log(f'Total number of formats: {len(formats)}', 'debug')

        # Check that all keys are present in present formats
        card_keys = ['Format Name',
                    'Context',
                    'Identification method',
                    'Identification data',
                    'Sortion method',
                    'Sortion key',
                    'Card number cell',
                    'Card string format',
                    'Adittional data field',
                    'TimeStamp',
                    'TimeStamp Format', 
                    'TimeStamp location',
                    'Headers',
                    'Double tables',
                    'Secondary Headers',
                    'Header row index',
                    'Header col index',
                    'Independent']
        bank_keys = ['Format Name',
                    'Context',
                    'Identification method',
                    'Identification data',
                    'Sortion method',
                    'Sortion key',
                    'Adittional data field',
                    'Headers',
                    'Double tables',
                    'Secondary Headers',
                    'Header row index',
                    'Header col index',
                    'Independent']
        
        for format_name, format_data in tqdm(formats.items(), desc=f"{'Validating formats: Overall info':42s}", unit="formats"):
            dict_i_keys = list(format_data.keys())
            if format_data['Context'] == Context_class.Card:
                keys_to_test = card_keys
            else:
                keys_to_test = bank_keys
            for key in keys_to_test:
                if key not in dict_i_keys:
                    return f"The key ({key}) is missing from format ({format_name})"

        def check_multiple(key: str, secondary_key) -> list:
            lst = []
            for format_name_i, format_data_i in formats.items():
                for format_name_j, format_data_j in formats.items():
                    if format_name_i == format_name_j:
                        continue
                    if format_data_i[key] == format_data_j[key]:
                        lst.append((format_name_i, format_name_j))
            
            res = []
            for tup in lst:
                format_1 = tup[0]
                format_2 = tup[1]
                if formats[format_1][secondary_key] == Identification_Method.HEADERS or \
                    formats[format_2][secondary_key] == Identification_Method.HEADERS:
                    res.append(tup)
            
            return res

        for format_key, format_data in tqdm(formats.items(), desc=f"{'Validating formats: Overall info':42s}", unit="formats"):
            if format_key != format_data['Format Name']:
                return f"Format name missmatch for {format_key}"

            if not isinstance(format_data['Context'], Context_class):
                return f"Context Enum was not used for {format_key}"

            if not isinstance(format_data['Identification method'], Identification_Method):
                return f"Identification_Method Enum was not used for {format_key}"

            if format_data['Identification method'] == Identification_Method.NONE:
                return 'Identification_Method should not be Identification_Method.NONE'

            data = format_data['Identification data']
            match format_data['Identification method']:
                case Identification_Method.FILE_NAME:
                    if not isinstance(data, str):
                        return f'Identification data should be a string when using "Identification_Method.FILE_NAME" in format {format_key}'
                case Identification_Method.CELL:
                    if not isinstance(data, tuple):
                        return f'Identification data should be a tuple indicating row, col when using "Identification_Method.CELL" in format {format_key}'
                case Identification_Method.HEADERS:
                    if data is not None:
                        return f'Identification data should be None when using "Identification_Method.Headers" in format {format_key}'
                    if len(format_data['Headers']) == 0:
                        return f'Headers were not specified'
                    # if format_key in header_duplicates:
                    #     return f'The "Header Identification" field for {format_key} Cannot be set to "HEADERS". Because there is another format with identical headers.'
                case _:
                    return f'Internal ERROR, should not happen.'
                
            sortion_key = format_data['Sortion key']
            match format_data['Sortion method']:
                case Sortion_Method.BY_NAME_SERIAL:
                    if sortion_key is not None:
                        return f'Bad sortion key for format {format_key}'
                case Sortion_Method.BY_NAME_DATE:
                    if sortion_key is not None:
                        return f'Bad sortion key for format {format_key}'
                case _:
                    return f'Please indicate a sortion method for {format_key}'

            add_data = format_data['Adittional data field']

            if add_data is Tuple:
                if add_data[0] < 1:
                    return f'Bad row value {add_data[0]} in format {format_key}, please use values greater than 0.'
                if add_data[1] < 0:
                    return f'Bad col value {add_data[1]} in format {format_key}, please use positive values.'
            if add_data is not None and (not isinstance(add_data, tuple) and not isinstance(add_data, list)):
                return f"Bad input type {type(add_data)} at 'adittional data field' in format {format_key}."
            
            if not isinstance(format_data['Headers'], list):
                return f'Bad header format {type(format_data["Headers"])} in format {format_key}.'
            if len(format_data['Headers']) < 1:
                return f'Headers list is too short for format {format_key}.'
            
            if type(format_data['Double tables']) != bool:
                return f'Bad format for key "Double tables", in {format_key}. Should be of type bool.'
            
            if format_data['Double tables']:
                if type(format_data['Secondary Headers']) != list:
                    return f'Bad Secondary Headers format {type(format_data["Secondary Headers"])} in format {format_key}.'
                if len(format_data['Secondary Headers']) < 1:
                    return f'Secondary Headers list is too short for format {format_key}.'
            else:
                if format_data['Secondary Headers'] != []:
                    return f'"Secondary Headers" should be [] (empty list) for "Double tables" == True in format {format_key}.'
                
            if type(format_data['Independent']) != bool:
                f'Bad format for key "Independent" {format_data["Independent"]}, in format {format_key}.'
        
        for format_name_i, data_i in tqdm(formats.items(), desc=f"{'Validating formats: identification method':42s}", unit="formats"):
            for format_name_j, data_j in formats.items():
                if format_name_i != format_name_j:
                    if tuple(data_i['Headers']) == tuple(data_j['Headers']) and \
                        data_i['Identification method'] == data_j['Identification method'] and \
                        data_i['Identification data'] == data_j['Identification data']:
                        return f"「{format_name_i}」 and 「{format_name_j}」has identical identification system\n\
\t  Make sure that the the following keys: 'Identification method', 'Identification data', 'Headers' are unique\
\t  Between formats."

        tuple_lst = check_multiple("Headers", "Identification method")
        st = ""
        for tup in tuple_lst:
            st += f"[LOGIC ERROR]: The following formats: {tup[0]} and {tup[1]} Have the same 'Headers',\n\
Therefore, they cannot be identified by them. \
Please Make sure that none of the following formats have their 'Identifications Method' set to 'IdentificationsMethod.Header'.\n"
        
        if tuple_lst != []:
            return st

        return True
    
    @staticmethod
    def read_present_table(progress_callback=None):
        """
        The function reads the file table from the database and creates two dataframes:
        1. df - with the same index and columns as the file table, but with the "Last update" value in the cells.
        2. color_coded_df - with the same index and columns as the file table, but with the "Status" value in the cells.

        Status values are color coded in the html file, according to the following rules:
        - "Verified" -> Green
        - "Not verified" -> Red
        - "Missing file" -> Gray

        progress_callback: optional callable(int 0-100) called after each row is processed.
        """
        from database import DataBase
        from dateutil.relativedelta import relativedelta

        file_df = DataBase().get_file_table()

        # Sort from earliest to latest
        file_df.sort_values(by='Date', inplace=True)

        # The following line, converts the column, from string value dates, to date object of the following format: example: "November, 2023"
        # Because the date represent the Charge date of the transactions, one month is taken back to represent the month
        # the trasnactions were taken in.
        file_df['Date'] = file_df['Date'].apply(lambda x: (datetime.strptime(x, "%Y-%m-%d %H:%M:%S" )  - relativedelta(months=1)).strftime("%B, %Y"))

        indexes = file_df['Date'].unique().tolist()
        # columns = file_df['Format'].unique().tolist()
        columns = (file_df['Format'].astype(str) + " | " + file_df['Card_Number']).unique().tolist()

        df = pd.DataFrame(index=indexes, columns=columns)
        color_coded_df = pd.DataFrame(index=indexes, columns=columns)

        from src_utils.AppManagerUtils import AppManagerUtils
        total = file_df.shape[0]
        _month_cache = {}
        for i, (_, row) in enumerate(tqdm(file_df.iterrows(), total=total, desc="Processing data")):
            last_update = row["Last_update"]
            date = row["Date"]
            format_name = row["Format"]
            card_number = row["Card_Number"]
            col_name =  format_name + " | " + card_number
            df.at[date, col_name] = last_update

            dt = datetime.strptime(row["Date"], "%B, %Y")
            if dt not in _month_cache:
                processed_df = AppManagerUtils.retrieve_and_initialize_data(dt, std_out=False)
                _month_cache[dt] = utils.card_charge_validation(processed_df, dt)
            test_df = _month_cache[dt]
            status_series = test_df.loc[test_df['CardID'] == card_number, 'Status']

            if not status_series.empty:
                result = status_series.values[0]
            else:
                result = None

            color_coded_df.at[date, col_name] = result

            if progress_callback and total > 0:
                progress_callback(int((i + 1) / total * 100))

        return df, color_coded_df

    @staticmethod
    def get_organizer_alerts_for_month(t):
        """
        Returns missing-file alerts for month t, mirroring the organizer table logic.
        Each entry dict: {'col', 'fmt', 'card', 'has_untagged', 'untagged'}
        Only columns that have appeared at least once in the file table are considered.
        """
        from database import DataBase
        from dateutil.relativedelta import relativedelta
        from Configurations.Formats import Formats

        try:
            file_df = DataBase().get_file_table()
        except Exception:
            return []
        if file_df.empty:
            return []

        def _parse(d):
            try:
                return datetime.strptime(str(d), "%Y-%m-%d %H:%M:%S")
            except Exception:
                return None

        file_df = file_df.copy()
        file_df['_dt'] = file_df['Date'].apply(_parse)
        file_df = file_df.dropna(subset=['_dt'])

        charge_dt = t + relativedelta(months=1)

        all_cols = {
            f"{row['Format']} | {row['Card_Number']}"
            for _, row in file_df.iterrows()
        }
        present_cols = {
            f"{row['Format']} | {row['Card_Number']}"
            for _, row in file_df.iterrows()
            if row['_dt'].month == charge_dt.month and row['_dt'].year == charge_dt.year
        }

        missing = all_cols - present_cols

        filtered = []
        for col in missing:
            fmt, card = col.split(' | ', 1)
            if fmt == 'Isra-Card-2026' and t.year < 2026:
                continue
            filtered.append((fmt, card, col))

        if not filtered:
            return []

        try:
            _untagged, _desc = DataBase().get_untagged(table='BankTransactions')
            _DFMT = '%Y-%m-%d %H:%M:%S'
            _DLEN = 10
        except Exception:
            _untagged, _desc = [], []

        results = []
        for fmt, card, col in sorted(filtered):
            card_names = Formats.FORMATS.get(fmt, {}).get('Transaction Names', {})
            possible = set(card_names.get(card, []))
            if not possible or not _untagged:
                continue
            match = utils._find_untagged_transaction_match(
                _untagged, _desc, possible, None, None, t, _DFMT, _DLEN
            )
            if match is None:
                continue
            results.append({
                'col':      col,
                'fmt':      fmt,
                'card':     card,
                'untagged': match,
            })
        return results

    @staticmethod
    def _find_untagged_transaction_match(untagged_transactions, desc, possible_names, value, status, 
                                         row_month_year, date_format_full, date_string_length):
        """
        Find a matching untagged transaction for a given cell value.
        Uses the original logic: iterate through list and remove matched transaction.
        
        @param untagged_transactions: List of untagged transaction rows from DB (modified if match found)
        @param desc: Column descriptions from database
        @param possible_names: Set of possible transaction names for this card/format
        @param value: Cell value to match
        @param status: Cell status (Verified/Not Verified)
        @param row_month_year: datetime object representing the month/year of the cell
        @param date_format_full: Date format string for parsing transaction dates
        @param date_string_length: Expected length of date string
        
        @return: Tuple (trans_date, val, name, match_type) if match found, None otherwise
        """
        from datetime import datetime
        
        for row in untagged_transactions:
            name = row[desc.index('Name')]
            date_str = row[desc.index('Date')] if 'Date' in desc else None
            val = row[desc.index('Out')] if 'Out' in desc else None
            
            if name not in possible_names or not date_str:
                continue
                
            try:
                trans_date = datetime.strptime(date_str, date_format_full).date()
            except Exception:
                continue
            
            # Match month and year
            if trans_date.month - 1 != row_month_year.month or trans_date.year != row_month_year.year:
                continue
            
            # Determine match type based on cell state
            is_empty = pd.isna(value) or value == "" or value is None
            is_not_verified_date = (isinstance(value, str) and len(value) == date_string_length and 
                                    '-' in value and status == 'Not Verified')
            
            if is_empty:  # Cell is empty
                untagged_transactions.remove(row)
                return (trans_date, val, name, "missing")
            elif is_not_verified_date:  # Cell has unverified date
                return (trans_date, val, name, "not_verified")
        
        return None

    @staticmethod
    def create_html_with_colored_dates(df: pd.DataFrame, 
                                       color_coded_df: pd.DataFrame,
                                       output_file_path: str='output.html'):
        """
        @param df: DataFrame with dates and values (columns are card names and rows are dates as seen in the html).
        @param color_coded_df: DataFrame with the same index and columns as df, but with color-coded status values.
        @param output_file_path: Path to save the generated HTML file.
        """
        from jinja2 import Template
        from Configurations.Formats import Formats
        from database import DataBase
        from Constants import BANK_CARD_NUMBER
        from datetime import datetime

        # Constants
        TITLE_SEPARATOR = " | "
        DATE_FORMAT_MONTH_YEAR = "%B, %Y"
        DATE_FORMAT_FULL = "%Y-%m-%d %H:%M:%S"
        DATE_STRING_LENGTH = 10

        # Change all 1 in df to "Verified", all 0 to "Not Verified"
        color_coded_df = color_coded_df.replace({1: 'Verified', 0: 'Not Verified'})

        # 1. Get all untagged transaction names from the DB
        untagged_transactions, desc = DataBase().get_untagged(table="BankTransactions")

        # 2. Build a lookup for untagged-match cells (for both empty and not-verified date cells)
        untagged_match_cells = dict()  # (row_idx, col) -> (date, value, cell_type)
        for col in df.columns:  #columns are string combined of "Format Name | Card Number"
            
            try:
                format_name, card_number = col.split(TITLE_SEPARATOR)
            except Exception as e:
                utils.log(f"Error in organizer process when splitting '{col}': {e}", "error")
                continue

            format_dict = Formats.FORMATS.get(format_name, {})
            card_names_dict = format_dict.get("Transaction Names", {})
            
            if card_number in card_names_dict:
                possible_names = set(card_names_dict[card_number])
                for idx in df.index:
                    value = df.at[idx, col]
                    status = color_coded_df.at[idx, col] if idx in color_coded_df.index and col in color_coded_df.columns else None
                    # Parse the month and year from the table row index (e.g. "November, 2023")
                    try:
                        row_month_year = datetime.strptime(str(idx), DATE_FORMAT_MONTH_YEAR)
                    except Exception:
                        continue
                    
                    # Find a matching untagged transaction for this card/format/date
                    match = utils._find_untagged_transaction_match(
                        untagged_transactions, desc, possible_names, value, status, 
                        row_month_year, DATE_FORMAT_FULL, DATE_STRING_LENGTH
                    )
                    if match:
                        untagged_match_cells[(idx, col)] = match
    
            elif BANK_CARD_NUMBER != card_number:   # Bank formats will not trigger the following warning
                utils.log(f"Column '{col}' does not have a valid card number in the format dictionary, skipping...", "warning")

        # 5. Legend text
        legend_text = {
            "green": "✓ Verified - file was parsed and the card's transaction sum matched a bank charge in the following month.",
            "green-bank": "Bank - bank statement file recorded. Verification is not applicable for bank columns.",
            "yellow-unverified": "⚠ Unverified File - file was parsed and card had transactions, but no matching bank charge was found (verification failed).",
            "yellow-no-transactions": "⚠ No Transactions - file was recorded but no card transactions existed for that month, so verification could not run.",
            "red": "No File - no file was found for the given format, card and charge date.",
            "blue-missing": "Missing File - an untagged transaction matching the format's charge transaction name was found for this card and charge date, but no file was uploaded.",
            "blue-not-verified": "Value Mismatch - an untagged transaction matching the charge name was found, but its value differs from the expected charge.",
            "gray": "Invalid Format Date - Isra-Card-2026 format is only valid for dates in 2026 and onwards."
        }

        # 6. HTML template (add .untagged-match-missing and .untagged-match-not-verified and legend)
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>File Organizer</title>
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', sans-serif;
                    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                    min-height: 100vh;
                    padding: 40px 20px;
                    color: #333;
                }
                
                h1 {
                    text-align: center;
                    color: #2c3e50;
                    margin-bottom: 10px;
                    font-size: 2.5em;
                    font-weight: 600;
                    letter-spacing: -0.5px;
                }
                
                .subtitle {
                    text-align: center;
                    color: #7f8c8d;
                    font-size: 0.95em;
                    margin-bottom: 30px;
                }
                
                .legend-container {
                    max-width: 95%;
                    margin: 0 auto 40px;
                    padding: 25px;
                    background: white;
                    border-radius: 12px;
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                }
                
                .legend-title {
                    font-weight: 600;
                    margin-bottom: 15px;
                    color: #2c3e50;
                    font-size: 1.2em;
                }
                
                .legend-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
                    gap: 12px;
                }
                
                .legend-item {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    font-size: 0.9em;
                    color: #555;
                }
                
                .legend-color {
                    width: 20px;
                    height: 20px;
                    border-radius: 4px;
                    flex-shrink: 0;
                    border: 1px solid rgba(0, 0, 0, 0.1);
                }
                
                .legend-green { background: #c2f0c2; }
                .legend-yellow { background: #fff7b2; }
                .legend-red { background: #ffb3b3; }
                .legend-blue-missing { background: #b3d1ff; }
                .legend-blue-not-verified { background: #d1eaff; }
                .legend-gray { background: #e0e0e0; }
                
                .table-wrapper {
                    max-width: 98%;
                    margin: 0 auto;
                    background: white;
                    border-radius: 12px;
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                }
                
                table {
                    width: 100%;
                    border-collapse: collapse;
                    table-layout: fixed;
                }
                
                th {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 16px 12px;
                    text-align: center;
                    font-weight: 600;
                    font-size: 0.95em;
                    border: none;
                    position: sticky;
                    top: 0;
                }
                
                td {
                    border: 1px solid #e8eef5;
                    padding: 14px 12px;
                    text-align: center;
                    font-size: 0.9em;
                }
                
                tbody tr {
                    transition: background-color 0.2s ease;
                }
                
                tbody tr:hover {
                    background-color: #f9fafb;
                }
                
                tbody tr:nth-child(even) {
                    background-color: #f9fafb;
                }
                
                .verified {
                    background-color: #c2f0c2 !important;
                    font-weight: 500;
                    color: #2d5016;
                }
                
                .not-verified {
                    background-color: #fff7b2 !important;
                    font-weight: 500;
                    color: #7f6b00;
                }
                
                .other-status {
                    background-color: #ffb3b3 !important;
                    font-weight: 500;
                    color: #7f0000;
                }
                
                .untagged-match-missing {
                    background-color: #b3d1ff !important;
                    color: #003d99;
                    font-size: 0.85em;
                    padding: 10px !important;
                }
                
                .untagged-match-missing div {
                    text-align: left;
                    line-height: 1.5;
                }
                
                .untagged-match-missing b {
                    color: #002966;
                }
                
                .untagged-match-not-verified {
                    background-color: #d1eaff !important;
                    color: #003d99;
                    font-size: 0.85em;
                    padding: 10px !important;
                }
                
                .untagged-match-not-verified div {
                    text-align: left;
                    line-height: 1.5;
                }
                
                .untagged-match-not-verified b {
                    color: #002966;
                }
                
                .invalid-format-date {
                    background-color: #e0e0e0 !important;
                    color: #555 !important;
                    font-weight: 500;
                    font-style: italic;
                }
            </style>
        </head>
        <body>
            <h1>📊 File Organizer</h1>
            <p class="subtitle">Transaction file verification and status tracking</p>
            
            <div class="legend-container">
                <div class="legend-title">Status Legend</div>
                <div class="legend-grid">
                    <div class="legend-item"><span class="legend-color legend-green"></span>{{ legend.green }}</div>
                    <div class="legend-item"><span class="legend-color legend-green"></span>{{ legend['green-bank'] }}</div>
                    <div class="legend-item"><span class="legend-color legend-yellow"></span>{{ legend['yellow-unverified'] }}</div>
                    <div class="legend-item"><span class="legend-color legend-yellow"></span>{{ legend['yellow-no-transactions'] }}</div>
                    <div class="legend-item"><span class="legend-color legend-red"></span>{{ legend.red }}</div>
                    <div class="legend-item"><span class="legend-color legend-blue-missing"></span>{{ legend['blue-missing'] }}</div>
                    <div class="legend-item"><span class="legend-color legend-blue-not-verified"></span>{{ legend['blue-not-verified'] }}</div>
                    <div class="legend-item"><span class="legend-color legend-gray"></span>{{ legend.gray }}</div>
                </div>
            </div>
            
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>Date</th>
                            {% for col in columns %}
                                <th>{{ col }}</th>
                            {% endfor %}
                        </tr>
                    </thead>
                    <tbody>
                        {% for index, row in data.iterrows() %}
                            <tr>
                                <td style="font-weight: 500; color: #667eea;">{{ index }}</td>
                                {% for col in columns %}
                                    {% set value = row[col] %}
                                    {% set status = color_coded_df.at[index, col] %}
                                    {% set is_date = false %}
                                    {% if value is string and ('-' in value or '/' in value) %}
                                        {% set is_date = true %}
                                    {% endif %}
                                    {% set cell_key = (index, col) %}
                                    {# Check if this is Isra-Card-2026 with date before 2026 #}
                                    {% set is_invalid_date = false %}
                                    {% if 'Isra-Card-2026' in col %}
                                        {% set year_str = index.split(', ')[-1] %}
                                        {% if year_str.isdigit() and year_str|int < 2026 %}
                                            {% set is_invalid_date = true %}
                                        {% endif %}
                                    {% endif %}
                                    
                                    {# Invalid dates always show "Not available" regardless of other matches #}
                                    {% if is_invalid_date %}
                                        <td class="invalid-format-date">Not available</td>
                                    {% elif cell_key in untagged_match_cells %}
                                        {% set match = untagged_match_cells[cell_key] %}
                                        {% if match[3] == "missing" %}
                                            <td class="untagged-match-missing">
                                                <div>
                                                    <b>⚠ Missing file</b><br>
                                                    <span style="color:#003d99;">
                                                        Name: {{ match[2] if match[2] else "?" }}<br>
                                                        Value: {{ match[1] if match[1] else "?" }}<br>
                                                        Date: {{ match[0] if match[0] else "?" }}<br>
                                                    </span>
                                                </div>
                                            </td>
                                        {% elif match[3] == "not_verified" %}
                                            <td class="untagged-match-not-verified">
                                                <div>
                                                    <b>⚠ Value Mismatch</b><br>
                                                    <span style="color:#003d99;">
                                                        Name: {{ match[2] if match[2] else "?" }}<br>
                                                        Value: {{ match[1] if match[1] else "?" }}<br>
                                                        Date: {{ match[0] if match[0] else "?" }}<br>
                                                        File Date: {{ value if value else "?" }}<br>
                                                    </span>
                                                </div>
                                            </td>
                                        {% endif %}
                                    {% else %}
                                        {% set card_num = col.split(' | ')[-1] %}
                                        <td class="{% if card_num == BANK_CARD_NUMBER and is_date %}verified{%
                                            elif status == 'Verified' %}verified{%
                                            elif status == 'Not Verified' or is_date %}not-verified{%
                                            else %}other-status{% endif %}">
                                            {% if card_num == BANK_CARD_NUMBER and is_date %}
                                                <b>Bank</b><br><span style="font-size: 0.85em;">{% if value is string %}{{ value[:10] }}{% else %}{{ value }}{% endif %}</span>
                                            {% elif status == 'Verified' %}
                                                <b>&#10003; Verified</b><br><span style="font-size: 0.85em;">{% if is_date and value is string %}{{ value[:10] }}{% else %}{{ value }}{% endif %}</span>
                                            {% elif status == 'Not Verified' and card_num != BANK_CARD_NUMBER %}
                                                <b>⚠ Unverified File</b><br><span style="font-size: 0.85em;">{% if is_date and value is string %}{{ value[:10] }}{% else %}{{ value }}{% endif %}</span>
                                            {% elif is_date and status != 'Not Verified' %}
                                                <b>⚠ No Transactions</b><br><span style="font-size: 0.85em;">{% if value is string %}{{ value[:10] }}{% else %}{{ value }}{% endif %}</span>
                                            {% else %}
                                                {% if is_date and value is string %}{{ value[:10] }}{% else %}{{ value }}{% endif %}
                                            {% endif %}
                                        </td>
                                    {% endif %}
                                {% endfor %}
                            </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </body>
        </html>
        """

        # 7. Render template
        template = Template(html_template)
        rendered_html = template.render(
            data=df,
            columns=df.columns,
            pd=pd,
            color_coded_df=color_coded_df,
            legend=legend_text,
            untagged_match_cells=untagged_match_cells,
            BANK_CARD_NUMBER=BANK_CARD_NUMBER
        )

        with open(output_file_path, 'w', encoding='utf-8') as html_file:
            html_file.write(rendered_html)

        import webbrowser
        webbrowser.open(output_file_path)
    @staticmethod
    def seperate_high_std(df: pd.DataFrame, numerical_col_name: str) -> Tuple[pd.DataFrame, list]:
        """
        The function receives 
        1. A data frame (pd.DataFrame)
        2. A name (str) representing the column name of the relevant numerical value (probably price values)
        The function will return a sub section of the data frame, along with a list.
        The data frame will include only transactions that have lower prices than the total std of the transactions.
        The transactions that were removed, will be appended to the returned list in the following format:
        [(category_0, total_sum_0), (category_1, total_sum_1), ... , (category_n, total_sum_n)]
        """
        std = df[numerical_col_name].std()
        mean = df[numerical_col_name].mean()
        total = df[numerical_col_name].sum()

        lower_treshold = total*0.02
        #lower_treshold = lower_treshold if lower_treshold > 0 else 0.05*mean 

        high_treshold = df[numerical_col_name].max()  + 10

        conditions = (df[numerical_col_name] < high_treshold) & (df[numerical_col_name] > lower_treshold)
        sub_df = df[conditions]
        counter_sub_df = df[~conditions]

        counter_list = [(utils.heb_conversion(category), row[numerical_col_name]) for category, row in counter_sub_df.iterrows()]
        # create a list -> trans_name, numerical_col_name
        return sub_df, counter_list
    
    @staticmethod
    def create_html_name_analysis(data: dict) -> None:
        import json
        import os as _os
        from datetime import datetime as _dt

        display_name  = data.get('Category/business name', '')
        type_         = data.get('type', 'category')
        slug          = data.get('slug', '')
        type_label    = 'קטגוריה' if type_ == 'category' else 'עסק'
        generated     = _dt.now().strftime('%d/%m/%Y %H:%M')

        def _fmt(v):
            if v is None or (isinstance(v, float) and v != v):
                return '—'
            return f"({abs(v):,.0f}) ₪" if v < 0 else f"{v:,.0f} ₪"

        monthly_avg  = data.get('Monthly Average', 0) or 0
        recent_avg   = data.get('Recent Monthly Average', 0) or 0
        total_spent  = data.get('Total Spendings', 0) or 0
        total_income = data.get('Total Income', 0) or 0

        monthly_chart_data = data.get('monthly_chart_data', [])
        spending_pie_data  = data.get('spending_pie_data', [])
        earning_pie_data   = data.get('earning_pie_data', [])
        monthly_json       = json.dumps(monthly_chart_data, ensure_ascii=False)
        spending_pie_json  = json.dumps(spending_pie_data, ensure_ascii=False)
        earning_pie_json   = json.dumps(earning_pie_data, ensure_ascii=False)

        # Pie charts — shown only if >= 2 distinct entries (otherwise not meaningful)
        _pie_dim = 'לפי עסק' if type_ == 'category' else 'לפי קטגוריה'
        _show_spend_pie = len(spending_pie_data) >= 2
        _show_earn_pie  = len(earning_pie_data) >= 2

        def _pie_card(canvas_id, title, subtitle):
            return (
                f'<div class="chart-card">'
                f'<div class="chart-card-title">{title}'
                f'<span class="chart-card-sub">{subtitle}</span></div>'
                f'<div class="chart-wrap"><canvas id="{canvas_id}"></canvas></div>'
                f'</div>'
            )

        pie_cards_html = ''
        if _show_spend_pie:
            pie_cards_html += _pie_card('pie-spend', f'פילוג הוצאות', _pie_dim)
        if _show_earn_pie:
            pie_cards_html += _pie_card('pie-earn', f'פילוג הכנסות', _pie_dim)

        # Layout: if any pie exists use 2-col (monthly + pies column), else 1-col
        _has_pies = _show_spend_pie or _show_earn_pie
        _charts_grid_cls = 'charts-2col' if _has_pies else 'charts-1col'

        # Build transaction rows
        txn_rows = ''
        # In category analysis the category column is redundant (all same); hide it
        _show_cat_col  = (type_ != 'category')
        # Helpers for safe date parsing
        def _parse_date(raw):
            raw = str(raw)
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try: return _dt.strptime(raw, fmt).strftime("%d/%m/%Y")
                except Exception: pass
            return raw[:10]

        transactions = data.get('transactions')
        _has_charge = transactions is not None and 'Charge_Date' in transactions.columns

        if transactions is not None and not transactions.empty:
            for _, row in transactions.sort_values(by='Date', ascending=False).iterrows():
                txn_id   = str(row.get('ID', ''))
                name     = str(row.get('Description') or row.get('Name', ''))
                date_str = _parse_date(row.get('Date', ''))
                value    = row.get('Final_Value', 0)
                cat      = row.get('Category', '')
                vcls     = 'neg' if value < 0 else 'pos'
                vstr     = f"({abs(value):,.0f}) ₪" if value < 0 else f"{value:,.0f} ₪"

                # Date type badge: bank vs card
                table_name = str(row.get('TableName', ''))
                is_card    = table_name == 'CardTransactions'
                date_badge = (
                    '<span class="td-date-badge td-card">אשראי</span>' if is_card
                    else '<span class="td-date-badge td-bank">בנק</span>'
                )
                # Charge date for card (only if different from execution date)
                charge_html = ''
                if is_card and _has_charge:
                    c_raw = str(row.get('Charge_Date', ''))
                    if c_raw and c_raw not in ('nan', '', str(row.get('Date', ''))):
                        charge_html = f'<span class="td-charge">חיוב {_parse_date(c_raw)}</span>'

                cat_td = f'<td class="td-cat">{cat}</td>' if _show_cat_col else ''
                txn_rows += (
                    f'<tr>'
                    f'<td class="td-id">{txn_id}</td>'
                    f'<td class="td-date">{date_str}{date_badge}{charge_html}</td>'
                    f'<td class="td-name">{name}</td>'
                    f'<td class="td-val {vcls}">{vstr}</td>'
                    f'{cat_td}</tr>\n'
                )

        txn_count = len(transactions) if transactions is not None else 0

        # ── Additional analytics ──────────────────────────────────────────────
        # Monthly totals stats
        _monthly_spend_std = ''
        _std_months_count  = 0
        if transactions is not None and not transactions.empty:
            import pandas as _pd2
            _tmp = transactions.copy()
            _tmp['_month'] = _pd2.to_datetime(_tmp['Date']).dt.to_period('M')
            _monthly_sums = _tmp.groupby('_month')['Final_Value'].sum()
            _std_months_count = len(_monthly_sums)
            if _std_months_count >= 2:
                _std = _monthly_sums.std()
                _monthly_spend_std = f"{abs(_std):,.0f} ₪"
        display_name_js = json.dumps(display_name, ensure_ascii=False)
        slug_js  = json.dumps(slug, ensure_ascii=False)
        type_js  = json.dumps(type_, ensure_ascii=False)


        html = f'''<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>ניתוח: {display_name}</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --teal:#1e9d8b;--teal-light:#e8f7f5;--teal-glow:rgba(30,157,139,.30);
  --navy:#1e2a4a;--bg:#f4f6f9;--white:#ffffff;--border:#eef0f6;
  --text-muted:#888;--red:#e74c3c;--green:#2ecc71;--amber:#f0b429;
  --shadow-sm:0 2px 10px rgba(0,0,0,.06);--shadow-md:0 6px 20px rgba(0,0,0,.10);
  --radius:14px;--radius-sm:8px;
}}
body{{font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);display:flex;
     min-height:100vh;direction:rtl;color:var(--navy);font-size:14px}}

/* Hamburger sidebar — matches app-wide unified nav */
.ham-btn{{position:fixed;top:18px;right:18px;width:42px;height:42px;background:var(--white);border:1.5px solid var(--border);border-radius:10px;display:flex;align-items:center;justify-content:center;cursor:pointer;z-index:400;box-shadow:var(--shadow-sm);color:var(--navy);transition:background .15s,color .15s,border-color .15s}}
.ham-btn:hover{{background:var(--teal);border-color:var(--teal);color:#fff}}
.ham-btn.open{{opacity:0;pointer-events:none}}
.nav-overlay{{position:fixed;inset:0;background:rgba(15,22,45,.26);z-index:390;opacity:0;pointer-events:none;transition:opacity .22s ease}}
.nav-overlay.open{{opacity:1;pointer-events:all}}
.sidebar{{position:fixed;top:0;right:0;height:100vh;width:230px;background:var(--white);z-index:395;transform:translate3d(100%,0,0);transition:transform .22s cubic-bezier(.4,0,.2,1);will-change:transform;box-shadow:-4px 0 24px rgba(0,0,0,.09);display:flex;flex-direction:column}}
.sidebar.open{{transform:translate3d(0,0,0)}}
.sidebar-header{{display:flex;align-items:center;padding:20px 20px 16px;border-bottom:1px solid var(--border);flex-shrink:0}}
.sidebar-app-name{{font-size:.95em;font-weight:700;color:var(--navy)}}
.sidebar-close-btn{{margin-right:auto;background:none;border:none;cursor:pointer;font-size:1.1em;color:var(--text-sub);line-height:1;padding:4px 6px;border-radius:6px;transition:background .12s,color .12s;font-family:inherit}}
.sidebar-close-btn:hover{{background:var(--teal-light);color:var(--teal)}}
.sidebar-scroll{{flex:1;overflow-y:auto;overflow-x:hidden;padding:8px 0 16px}}
.nav-item{{display:flex;align-items:center;padding:10px 20px;text-decoration:none;color:var(--text-sub);font-size:.875em;font-weight:500;transition:background .1s,color .1s;cursor:pointer;border:none;background:none;width:100%;text-align:right;position:relative;letter-spacing:.1px;font-family:inherit}}
.nav-item::before{{content:'';position:absolute;right:0;top:22%;height:56%;width:3px;border-radius:3px 0 0 3px;background:transparent;transition:background .1s}}
.nav-item:hover{{background:var(--teal-light);color:var(--teal)}}
.nav-item:hover::before{{background:var(--teal)}}
.nav-item.active{{color:#b8c0d0;cursor:default;pointer-events:none}}
.nav-sep{{height:1px;background:var(--border);margin:8px 16px}}
/* Back button — fixed top-left, bold arrow only */
.back-btn{{position:fixed;top:18px;left:18px;width:42px;height:42px;padding:0;background:var(--white);border:1.5px solid var(--border);border-radius:10px;display:flex;align-items:center;justify-content:center;cursor:pointer;z-index:400;box-shadow:var(--shadow-sm);color:var(--text-sub);font-size:1.25em;font-weight:900;text-decoration:none;transition:background .15s,color .15s,border-color .15s;line-height:1}}
.back-btn:hover{{background:var(--teal-light);border-color:var(--teal);color:var(--teal)}}

/* Main */
.main{{flex:1;padding:0 28px 60px;min-width:0}}

/* Category roller — matches month-roller styling */
.cat-roller{{width:100%;overflow:hidden;position:sticky;top:0;z-index:50;
  padding:14px 0;margin-bottom:18px;background:var(--bg);box-shadow:0 2px 8px rgba(0,0,0,.06)}}
.cat-roller::before,.cat-roller::after{{content:'';position:absolute;top:0;bottom:0;
  width:100px;z-index:3;pointer-events:none}}
.cat-roller::before{{left:0;background:linear-gradient(to right,var(--bg) 30%,transparent)}}
.cat-roller::after{{right:0;background:linear-gradient(to left,var(--bg) 30%,transparent)}}
.roller-track{{display:flex;align-items:center;direction:ltr;will-change:transform}}
.cm-item{{flex-shrink:0;width:140px;display:flex;flex-direction:column;align-items:center;
  justify-content:center;padding:6px 4px;cursor:pointer;user-select:none;
  border-radius:10px;opacity:.2;transform:scale(.82);
  transition:opacity .35s ease,transform .35s ease,background .18s,filter .12s}}
.cm-item:not(.active):hover{{background:rgba(30,157,139,.12);filter:brightness(1.04)}}
.cm-item:not(.active):active{{background:rgba(30,157,139,.22);filter:brightness(.9);
  transition:background .05s,filter .05s}}
@keyframes cmTap{{0%{{filter:brightness(1)}}30%{{filter:brightness(.82)}}100%{{filter:brightness(1)}}}}
.cm-item.tapped{{animation:cmTap .28s ease}}
.cm-item.dist-2{{opacity:.45;transform:scale(.88)}}
.cm-item.dist-1{{opacity:.68;transform:scale(.94)}}
.cm-item.active{{opacity:1;transform:scale(1.08);cursor:default;background:rgba(30,157,139,.08)}}
.cm-item.active:hover{{background:rgba(30,157,139,.16);filter:brightness(1.03)}}
.cm-label{{font-size:.78em;font-weight:600;color:#999;text-align:center;
  line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:130px;
  transition:color .35s ease,font-size .35s ease}}
.cm-type-tag{{font-size:.6em;color:#bbb;margin-top:1px}}
.cm-item.dist-1 .cm-label{{color:#666;font-size:.80em}}
.cm-item.dist-2 .cm-label{{color:#888;font-size:.78em}}
.cm-item.active .cm-label{{color:var(--teal);font-size:.90em;font-weight:700}}
.cm-item.active .cm-type-tag{{color:var(--teal)}}
.cm-dot{{width:5px;height:5px;border-radius:50%;margin-top:5px;background:#d0d4e0;
  transition:background .3s,width .3s,height .3s}}
.cm-item.has-file .cm-dot{{background:var(--teal)}}
.cm-item.active.has-file .cm-dot{{width:7px;height:7px}}

/* Page header */
.page-header{{display:flex;justify-content:space-between;align-items:center;
  margin-bottom:20px;flex-wrap:wrap;gap:10px}}
.page-header h1{{font-size:1.7em;font-weight:700;color:var(--navy)}}
.type-badge{{display:inline-block;background:var(--teal);color:#fff;
  padding:3px 12px;border-radius:14px;font-size:.72em;font-weight:600;margin-right:10px}}
.page-header-right{{display:flex;align-items:center;gap:10px;flex-shrink:0}}
.generated-label{{font-size:.72em;color:var(--text-muted);white-space:nowrap}}
.reload-btn{{padding:5px 14px;border:1.5px solid var(--teal);border-radius:20px;
  background:var(--white);color:var(--teal);font-size:.78em;font-weight:600;
  cursor:pointer;transition:background .15s,color .15s;white-space:nowrap;display:none}}
.reload-btn:hover{{background:var(--teal);color:#fff}}
.reload-btn.running{{opacity:.6;cursor:wait}}

/* KPI grid */
.kpi-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:22px}}
@media(max-width:900px){{.kpi-grid{{grid-template-columns:1fr 1fr}}}}
.kpi-card{{background:var(--white);border-radius:var(--radius);padding:18px 20px 16px;
  box-shadow:var(--shadow-sm);display:flex;flex-direction:column;gap:7px;
  transition:transform .18s,box-shadow .18s}}
.kpi-card:hover{{transform:translateY(-3px);box-shadow:var(--shadow-md)}}
.kpi-dot{{width:10px;height:10px;border-radius:50%;display:inline-block;
  margin-left:7px;flex-shrink:0}}
.kpi-label{{font-size:.76em;color:var(--text-muted);display:flex;align-items:center;font-weight:500}}
.kpi-value{{font-size:1.45em;font-weight:700;color:var(--navy);line-height:1.1}}
.kpi-value.neg{{color:var(--red)}}
.kpi-value.pos{{color:var(--teal)}}
.kpi-sublabel{{font-size:.68em;color:var(--text-muted);margin-top:4px}}

/* Charts row */
.charts-2col{{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:22px}}
@media(max-width:900px){{.charts-2col{{grid-template-columns:1fr}}}}
.chart-card{{background:var(--white);border-radius:var(--radius);
  padding:20px 22px;box-shadow:var(--shadow-sm)}}
.chart-card-title{{font-size:.82em;font-weight:700;color:var(--text-muted);
  text-transform:uppercase;letter-spacing:.5px;margin-bottom:14px;
  display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}}
.chart-card-sub{{font-size:.78em;font-weight:400;text-transform:none;
  letter-spacing:0;color:#b0b8c8}}
.chart-wrap{{position:relative;height:220px}}
.charts-1col{{display:grid;grid-template-columns:1fr;gap:14px;margin-bottom:22px}}
.pie-col{{display:flex;flex-direction:column;gap:14px}}

/* Transactions panel */
.panel{{background:var(--white);border-radius:var(--radius);
  padding:20px 22px;box-shadow:var(--shadow-sm)}}
.panel-header{{font-size:.82em;font-weight:700;color:var(--text-muted);
  text-transform:uppercase;letter-spacing:.5px;margin-bottom:14px;
  display:flex;justify-content:space-between;align-items:center}}
.panel-count{{font-size:.9em;color:var(--navy);font-weight:600}}
.txn-table-wrap{{overflow-x:auto;max-height:420px;overflow-y:auto}}
.txn-table{{width:100%;border-collapse:collapse;font-size:.84em}}
.txn-table th{{padding:8px 12px;text-align:right;font-weight:600;color:var(--text-muted);
  border-bottom:2px solid var(--border);position:sticky;top:0;background:var(--white);
  user-select:none}}
.txn-table th.th-sortable{{cursor:pointer;white-space:nowrap}}
.txn-table th.th-sortable:hover{{color:var(--teal)}}
.th-sort-icon{{display:inline-block;margin-right:4px;font-size:.75em;opacity:.35;
  transition:opacity .15s}}
.txn-table th.sort-asc .th-sort-icon,
.txn-table th.sort-desc .th-sort-icon{{opacity:1;color:var(--teal)}}
.txn-table td{{padding:8px 12px;border-bottom:1px solid var(--border);vertical-align:middle}}
.txn-table tr:last-child td{{border-bottom:none}}
.txn-table tr:hover td{{background:#fafbfd}}
.td-id{{color:#b0b8c8;font-size:.75em;font-family:monospace;white-space:nowrap;
  text-align:right;padding-right:6px;min-width:40px}}
.td-date{{color:var(--text-muted);white-space:nowrap;font-size:.9em;text-align:right}}
.td-date-badge{{display:inline-block;font-size:.6em;font-weight:700;border-radius:4px;
  padding:1px 5px;margin-right:5px;vertical-align:middle;letter-spacing:.3px}}
.td-bank{{background:#e8f4ff;color:#3498db}}
.td-card{{background:#fef3e8;color:#e67e22}}
.td-charge{{display:block;font-size:.72em;color:#b0b8c8;margin-top:1px}}
.td-name{{max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.td-val{{font-weight:600;white-space:nowrap;text-align:right}}
.td-val.neg{{color:var(--red)}}
.td-val.pos{{color:var(--teal)}}
.td-cat{{font-size:.85em;color:var(--text-muted);text-align:right}}
/* Analytics extras */
.kpi-trend{{font-size:.95em;font-weight:700}}

/* Search bar */
.txn-search-wrap{{margin-bottom:12px}}
.txn-search{{width:100%;padding:8px 14px;border:1.5px solid var(--border);
  border-radius:8px;font-size:.84em;color:var(--navy);background:var(--white);
  outline:none;transition:border-color .18s,box-shadow .18s;direction:rtl}}
.txn-search:focus{{border-color:var(--teal);box-shadow:0 0 0 3px var(--teal-light)}}
.txn-no-results{{text-align:center;padding:28px;color:var(--text-muted);
  font-size:.85em;display:none}}
.txn-footer{{display:flex;justify-content:space-between;align-items:center;
  padding:8px 12px;margin-top:6px;border-top:2px solid var(--border);
  font-size:.82em;font-weight:600;color:var(--navy);background:var(--bg);
  border-radius:0 0 8px 8px}}
.txn-footer-sum.neg{{color:var(--red)}}
.txn-footer-sum.pos{{color:var(--teal)}}

/* Log drawer */
.log-drawer{{position:fixed;bottom:0;left:0;right:0;background:var(--navy);
  z-index:300;max-height:220px;display:flex;flex-direction:column;
  transition:transform .3s ease;transform:translateY(calc(100% - 36px))}}
.log-drawer.expanded{{transform:translateY(0)}}
.log-drawer-header{{display:flex;align-items:center;gap:8px;padding:8px 16px;
  cursor:pointer;flex-shrink:0}}
.log-drawer-title{{font-size:.8em;color:#aaa;font-weight:600;flex:1}}
.log-drawer-toggle{{color:#aaa;font-size:.75em}}
.log-drawer-body{{overflow-y:auto;flex:1;padding:6px 16px 10px;font-size:.75em;
  color:#cdd;font-family:monospace;line-height:1.6}}
.log-ind{{width:8px;height:8px;border-radius:50%;background:#555;flex-shrink:0}}
.log-ind.active{{background:#1e9d8b;animation:pulse 1s infinite}}
.log-ind.error{{background:var(--red)}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
</head>
<body data-slug={slug_js} data-generated="{generated}" data-type={type_js} data-name={display_name_js}>

<!-- Hamburger -->
<button class="ham-btn" id="ham-btn" onclick="toggleNav()" aria-label="תפריט">
  <svg width="18" height="14" viewBox="0 0 18 14" fill="none">
    <rect width="18" height="2" rx="1" fill="currentColor"/>
    <rect y="6" width="18" height="2" rx="1" fill="currentColor"/>
    <rect y="12" width="18" height="2" rx="1" fill="currentColor"/>
  </svg>
</button>
<a class="back-btn" href="/categories" title="חזרה לקטגוריות">&#8592;</a>
<div class="nav-overlay" id="nav-overlay" onclick="toggleNav()"></div>
<nav class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <span class="sidebar-app-name">Menu</span>
    <button class="sidebar-close-btn" onclick="closeNav()">✕</button>
  </div>
  <div class="sidebar-scroll">
    <a class="nav-item" href="/">ניתוח חודשי</a>
    <a class="nav-item" href="/">עסקאות</a>
    <div class="nav-sep"></div>
    <a class="nav-item" href="/accounts">חשבונות</a>
    <a class="nav-item" href="/housing">דיור</a>
    <a class="nav-item" href="/organizer">ארגונית</a>
    <a class="nav-item active" href="/categories">ניתוח קטגוריאלי</a>
    <a class="nav-item" href="/search">חיפוש</a>
    <a class="nav-item" href="/spotify">Spotify Tracker</a>
    <div class="nav-sep"></div>
    <a class="nav-item" href="/tagger">תייגן</a>
    <a class="nav-item" href="/files">קבצים</a>
  </div>
</nav>

<!-- Log drawer -->
<div class="log-drawer" id="log-drawer">
  <div class="log-drawer-header" onclick="toggleLogDrawer()">
    <span class="log-ind" id="log-ind"></span>
    <span class="log-drawer-title">לוג מערכת</span>
    <span class="log-drawer-toggle">▲</span>
  </div>
  <div class="log-drawer-body" id="log-body"></div>
</div>

<!-- Main -->
<div class="main">

  <!-- Category roller -->
  <div class="cat-roller" id="cat-roller" style="display:none">
    <div class="roller-track" id="roller-track"></div>
  </div>

  <div class="page-header">
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
      <h1>{display_name}</h1>
      <span class="type-badge">{type_label}</span>
    </div>
    <div class="page-header-right">
      <span class="generated-label" id="generated-label">נוצר: {generated}</span>
      <button class="reload-btn" id="reload-btn" onclick="reloadCurrent()">&#8635; חשב מחדש</button>
    </div>
  </div>

  <!-- KPI cards -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label"><span class="kpi-dot" style="background:#1e9d8b"></span>ממוצע חודשי</div>
      <div class="kpi-value {'neg' if monthly_avg < 0 else 'pos'}">{_fmt(monthly_avg)}</div>
      <div class="kpi-sublabel">על פני כל הזמן</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label"><span class="kpi-dot" style="background:#f0b429"></span>ממוצע אחרון</div>
      <div class="kpi-value {'neg' if recent_avg < 0 else 'pos'}">{_fmt(recent_avg)}</div>
      <div class="kpi-sublabel">5 חודשים אחרונים</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label"><span class="kpi-dot" style="background:#9b59b6"></span>סטיית תקן חודשית</div>
      <div class="kpi-value">{_monthly_spend_std or '—'}</div>
      <div class="kpi-sublabel">{'על פני ' + str(_std_months_count) + ' חודשים' if _std_months_count >= 2 else 'אין מספיק נתונים'}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label"><span class="kpi-dot" style="background:#e74c3c"></span>סה"כ הוצאות</div>
      <div class="kpi-value neg">{_fmt(total_spent)}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label"><span class="kpi-dot" style="background:#2ecc71"></span>סה"כ הכנסות</div>
      <div class="kpi-value pos">{_fmt(total_income)}</div>
    </div>
  </div>

  <!-- Charts -->
  <div class="{_charts_grid_cls}">
    <div class="chart-card">
      <div class="chart-card-title">הוצאות והכנסות — 6 חודשים אחרונים</div>
      <div class="chart-wrap"><canvas id="monthly-chart"></canvas></div>
    </div>
    {f'<div class="pie-col">{pie_cards_html}</div>' if _has_pies else ''}
  </div>

  <!-- Transactions panel -->
  <div class="panel">
    <div class="panel-header">
      עסקאות
      <span class="panel-count" id="panel-count">{txn_count} עסקאות</span>
    </div>
    <div class="txn-search-wrap">
      <input class="txn-search" id="txn-search" type="text" placeholder="חיפוש עסקה..." oninput="filterTxns(this.value)">
    </div>
    <div class="txn-table-wrap">
      <table class="txn-table" id="txn-table">
        <thead><tr>
          <th class="td-id" style="color:var(--text-muted)">מזהה</th>
          <th class="th-sortable" id="th-date" onclick="sortTxns('date')">תאריך <span class="th-sort-icon">▼</span></th>
          <th>שם</th>
          <th class="th-sortable" id="th-val" onclick="sortTxns('val')">סכום <span class="th-sort-icon">▼</span></th>
          {'<th>קטגוריה</th>' if _show_cat_col else ''}
        </tr></thead>
        <tbody>
{txn_rows}        </tbody>
      </table>
      <div class="txn-no-results" id="txn-no-results">לא נמצאו עסקאות תואמות</div>
    </div>
    <div class="txn-footer" id="txn-footer">
      <span class="txn-footer-sum" id="txn-footer-sum"></span>
    </div>
  </div>

</div>

<script>
// ── Nav helpers ───────────────────────────────────────────
function openNav() {{
  document.getElementById('sidebar').classList.add('open');
  document.getElementById('nav-overlay').classList.add('open');
  document.getElementById('ham-btn').classList.add('open');
  document.body.style.overflow = 'hidden';
}}
function closeNav() {{
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('nav-overlay').classList.remove('open');
  document.getElementById('ham-btn').classList.remove('open');
  document.body.style.overflow = '';
}}
function toggleNav() {{
  var sidebar = document.getElementById('sidebar');
  if (sidebar.classList.contains('open')) {{ closeNav(); }} else {{ openNav(); }}
}}
document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') closeNav(); }});

// ── Embedded data ──────────────────────────────────────────
const MONTHLY_DATA   = {monthly_json};
const SPEND_PIE_DATA = {spending_pie_json};
const EARN_PIE_DATA  = {earning_pie_json};
const SLUG           = {slug_js};
const TYPE           = {type_js};
const NAME           = {display_name_js};

// ── Chart.js — Monthly bar ────────────────────────────────
(function() {{
  var ctx = document.getElementById('monthly-chart');
  if (!ctx || !MONTHLY_DATA.length) return;
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: MONTHLY_DATA.map(function(d) {{ return d.month; }}),
      datasets: [
        {{
          label: 'הוצאות',
          data: MONTHLY_DATA.map(function(d) {{ return d.spending; }}),
          backgroundColor: 'rgba(231,76,60,0.75)',
          borderColor: 'rgba(231,76,60,1)',
          borderWidth: 1,
          borderRadius: 5,
          order: 1
        }},
        {{
          label: 'הכנסות',
          data: MONTHLY_DATA.map(function(d) {{ return d.income; }}),
          backgroundColor: 'rgba(46,204,113,0.72)',
          borderColor: 'rgba(46,204,113,1)',
          borderWidth: 1,
          borderRadius: 5,
          order: 2
        }}
      ]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{ legend: {{ position: 'top', labels: {{ font: {{ size: 11 }} }} }} }},
      scales: {{
        x: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 11 }} }} }},
        y: {{ beginAtZero: true, ticks: {{ font: {{ size: 11 }}, callback: function(v) {{ return v.toLocaleString() + ' ₪'; }} }} }}
      }}
    }}
  }});
}})();

// ── Chart.js — Doughnut distributions ────────────────────
(function() {{
  var COLORS = ['#e74c3c','#f0b429','#e67e22','#c0392b','#d35400','#e91e63','#9c27b0','#ff5722','#95a5a6'];
  function makePie(canvasId, pieData) {{
    var ctx = document.getElementById(canvasId);
    if (!ctx || !pieData || pieData.length < 2) return;
    new Chart(ctx, {{
      type: 'doughnut',
      data: {{
        labels: pieData.map(function(d) {{ return d.name; }}),
        datasets: [{{
          data: pieData.map(function(d) {{ return d.value; }}),
          backgroundColor: COLORS.slice(0, pieData.length),
          borderWidth: 2,
          borderColor: '#fff'
        }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
          legend: {{ position: 'bottom', labels: {{ font: {{ size: 10 }}, boxWidth: 12, padding: 8 }} }},
          tooltip: {{
            callbacks: {{
              label: function(c) {{
                var total = c.dataset.data.reduce(function(a,b){{return a+b;}},0);
                var pct = total > 0 ? (c.parsed / total * 100).toFixed(1) : 0;
                return ' ' + c.parsed.toLocaleString() + ' ₪ (' + pct + '%)';
              }}
            }}
          }}
        }}
      }}
    }});
  }}
  makePie('pie-spend', SPEND_PIE_DATA);
  var earnColors = ['#1e9d8b','#3498db','#2ecc71','#1abc9c','#27ae60','#2980b9','#16a085','#8e44ad','#95a5a6'];
  var ctx2 = document.getElementById('pie-earn');
  if (ctx2 && EARN_PIE_DATA && EARN_PIE_DATA.length >= 2) {{
    new Chart(ctx2, {{
      type: 'doughnut',
      data: {{
        labels: EARN_PIE_DATA.map(function(d) {{ return d.name; }}),
        datasets: [{{
          data: EARN_PIE_DATA.map(function(d) {{ return d.value; }}),
          backgroundColor: earnColors.slice(0, EARN_PIE_DATA.length),
          borderWidth: 2, borderColor: '#fff'
        }}]
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{
          legend: {{ position: 'bottom', labels: {{ font: {{ size: 10 }}, boxWidth: 12, padding: 8 }} }},
          tooltip: {{
            callbacks: {{
              label: function(c) {{
                var total = c.dataset.data.reduce(function(a,b){{return a+b;}},0);
                var pct = total > 0 ? (c.parsed / total * 100).toFixed(1) : 0;
                return ' ' + c.parsed.toLocaleString() + ' ₪ (' + pct + '%)';
              }}
            }}
          }}
        }}
      }}
    }});
  }}
}})();

// ── Category roller ───────────────────────────────────────
var _activeIdx   = -1;
var _viewIdx     = -1;   // currently centred item (may differ from active when wheel-browsing)
var _rollerList  = [];
var _idleTimer   = null;
var _ITEM_W      = 140;
var _currentSlug = SLUG;

function _buildRoller(list) {{
  var track = document.getElementById('roller-track');
  if (!track) return;
  track.innerHTML = '';
  _activeIdx = -1;
  _rollerList = list;

  list.forEach(function(item, i) {{
    var el = document.createElement('div');
    el.className = 'cm-item' + (item.hasFile ? ' has-file' : '');
    el.dataset.slug = item.slug;

    var lbl = document.createElement('span');
    lbl.className = 'cm-label';
    lbl.textContent = item.name;
    lbl.title = item.name;

    var tag = document.createElement('span');
    tag.className = 'cm-type-tag';
    tag.textContent = item.type === 'category' ? 'קטגוריה' : 'עסק';

    var dot = document.createElement('span');
    dot.className = 'cm-dot';

    el.appendChild(lbl);
    el.appendChild(tag);
    el.appendChild(dot);

    el.addEventListener('click', function() {{
      if (item.slug === _currentSlug) return;
      el.classList.add('tapped');
      setTimeout(function() {{
        location.href = '/category/' + encodeURIComponent(item.slug) + '?name=' + encodeURIComponent(item.name);
      }}, 200);
    }});

    track.appendChild(el);
    if (item.slug === _currentSlug) _activeIdx = i;
  }});

  _viewIdx = _activeIdx;

  var roller = document.getElementById('cat-roller');
  if (roller) {{
    roller.style.display = '';
    // Attach wheel listener once (same pattern as month roller)
    if (!roller._wheelBound) {{
      roller._wheelBound = true;
      roller.addEventListener('wheel', function(e) {{
        e.preventDefault();
        var delta = e.deltaY > 0 ? 1 : -1;
        _viewIdx = Math.max(0, Math.min(_rollerList.length - 1, _viewIdx + delta));
        _positionToView(_viewIdx, true);
        _applyDist();
        // Snap back to active after 5 s idle
        clearTimeout(_idleTimer);
        if (_viewIdx !== _activeIdx) {{
          _idleTimer = setTimeout(function() {{
            _viewIdx = _activeIdx;
            _centerActive(true);
            _applyDist();
          }}, 5000);
        }}
      }}, {{ passive: false }});
    }}
  }}
  _applyDist();
  _centerActive(false);
}}

function _applyDist() {{
  var items = document.querySelectorAll('#roller-track .cm-item');
  items.forEach(function(el, i) {{
    var dView   = Math.abs(i - _viewIdx);
    var isActive = (i === _activeIdx);
    el.classList.remove('active','dist-1','dist-2');
    if (isActive)      el.classList.add('active');
    if (dView === 1)   el.classList.add('dist-1');
    if (dView === 2)   el.classList.add('dist-2');
  }});
}}

function _positionToView(idx, animate) {{
  var track  = document.getElementById('roller-track');
  var roller = document.getElementById('cat-roller');
  if (!track || !roller || idx < 0) return;
  var offset = roller.offsetWidth / 2 - idx * _ITEM_W - _ITEM_W / 2;
  track.style.transition = animate ? 'transform .45s cubic-bezier(.25,.46,.45,.94)' : 'none';
  track.style.transform  = 'translateX(' + offset + 'px)';
  if (!animate) {{ void track.offsetWidth; track.style.transition = 'transform .45s cubic-bezier(.25,.46,.45,.94)'; }}
}}

function _centerActive(animate) {{
  _positionToView(_activeIdx, animate);
}}

window.addEventListener('resize', function() {{ _viewIdx = _activeIdx; _centerActive(false); }});

// ── Reload current ────────────────────────────────────────
function reloadCurrent() {{
  var btn = document.getElementById('reload-btn');
  btn.classList.add('running'); btn.disabled = true;
  var drawer = document.getElementById('log-drawer');
  if (!drawer.classList.contains('expanded')) toggleLogDrawer();
  document.getElementById('log-body').innerHTML = '';
  setLogInd('active');

  fetch('/api/category/run', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{slug: SLUG, type: TYPE, name: NAME}})
  }}).then(function(r) {{
    if (r.status === 409) {{ btn.classList.remove('running'); btn.disabled = false; return; }}
    var es = new EventSource('/api/logs');
    es.onmessage = function(evt) {{
      var d = evt.data;
      if (!d || d === '__CONNECTED__') return;
      if (d.startsWith('__DONE__')) {{
        es.close(); setLogInd('');
        btn.classList.remove('running'); btn.disabled = false;
        setTimeout(function() {{ location.reload(); }}, 600);
        return;
      }}
      if (d === '__ERROR__') {{ es.close(); setLogInd('error'); btn.classList.remove('running'); btn.disabled = false; return; }}
      appendLog(d);
    }};
    es.onerror = function() {{ es.close(); btn.classList.remove('running'); btn.disabled = false; }};
  }});
}}

// ── Log helpers ───────────────────────────────────────────
function toggleLogDrawer() {{
  document.getElementById('log-drawer').classList.toggle('expanded');
}}
function setLogInd(state) {{
  var el = document.getElementById('log-ind');
  el.className = 'log-ind' + (state ? ' ' + state : '');
}}
function appendLog(msg) {{
  var body = document.getElementById('log-body');
  var line = document.createElement('div');
  line.textContent = msg;
  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
}}

// ── Transaction sort ──────────────────────────────────────
var _sortCol = 'date';
var _sortDir = -1;  // -1 = desc (newest first by default)

function sortTxns(col) {{
  if (_sortCol === col) {{
    _sortDir = -_sortDir;
  }} else {{
    _sortCol = col;
    _sortDir = col === 'date' ? -1 : 1;
  }}

  // Update header indicators
  ['th-date','th-val'].forEach(function(id) {{
    var th = document.getElementById(id);
    if (!th) return;
    th.classList.remove('sort-asc','sort-desc');
    var icon = th.querySelector('.th-sort-icon');
    if (icon) icon.textContent = '▼';
  }});
  var activeId = col === 'date' ? 'th-date' : 'th-val';
  var activeTh = document.getElementById(activeId);
  if (activeTh) {{
    activeTh.classList.add(_sortDir === 1 ? 'sort-asc' : 'sort-desc');
    var icon = activeTh.querySelector('.th-sort-icon');
    if (icon) icon.textContent = _sortDir === 1 ? '▲' : '▼';
  }}

  var tbody = document.querySelector('#txn-table tbody');
  if (!tbody) return;
  var rows = Array.from(tbody.querySelectorAll('tr'));
  rows.sort(function(a, b) {{
    var aEl, bEl, aVal, bVal;
    if (col === 'date') {{
      aEl = a.querySelector('.td-date'); bEl = b.querySelector('.td-date');
      // Parse dd/mm/yyyy → comparable string yyyymmdd
      function parseDate(s) {{
        if (!s) return '';
        var p = (s.textContent || s).trim().split('/');
        return p.length === 3 ? p[2] + p[1] + p[0] : s;
      }}
      aVal = parseDate(aEl); bVal = parseDate(bEl);
      return _sortDir * (aVal < bVal ? -1 : aVal > bVal ? 1 : 0);
    }} else {{
      aEl = a.querySelector('.td-val'); bEl = b.querySelector('.td-val');
      aVal = _parseTxnAmt((aEl || {{}}).textContent || '');
      bVal = _parseTxnAmt((bEl || {{}}).textContent || '');
      return _sortDir * (aVal - bVal);
    }}
  }});
  rows.forEach(function(r) {{ tbody.appendChild(r); }});
  filterTxns(document.getElementById('txn-search').value || '');
}}

// ── Transaction search ────────────────────────────────────
function _parseTxnAmt(text) {{
  text = (text || '').trim().replace('₪','').replace(/\s/g,'');
  if (!text || text === '\u2014') return 0;
  if (text.startsWith('(') && text.endsWith(')'))
    return -(parseFloat(text.slice(1,-1).replace(/,/g,'')) || 0);
  return parseFloat(text.replace(/,/g,'')) || 0;
}}
function _fmtSum(n) {{
  var abs = Math.abs(n).toLocaleString('he-IL', {{minimumFractionDigits:0, maximumFractionDigits:0}});
  return n < 0 ? '(' + abs + ') \u20aa' : abs + ' \u20aa';
}}
function filterTxns(q) {{
  q = q.trim().toLowerCase();
  var rows = document.querySelectorAll('.txn-table tbody tr');
  var visible = 0; var sum = 0;
  rows.forEach(function(row) {{
    var name = (row.querySelector('.td-name') || document.createElement('td')).textContent || '';
    var date = (row.querySelector('.td-date') || document.createElement('td')).textContent || '';
    var match = !q || name.toLowerCase().indexOf(q) !== -1 || date.indexOf(q) !== -1;
    row.style.display = match ? '' : 'none';
    if (match) {{
      visible++;
      var valEl = row.querySelector('.td-val');
      if (valEl) sum += _parseTxnAmt(valEl.textContent);
    }}
  }});
  var count = document.getElementById('panel-count');
  if (count) count.textContent = visible + ' \u05e2\u05e1\u05e7\u05d0\u05d5\u05ea';
  var noRes = document.getElementById('txn-no-results');
  if (noRes) noRes.style.display = (visible === 0 && q) ? '' : 'none';
  var fc = document.getElementById('txn-footer-count');
  if (fc) fc.textContent = visible + ' \u05e2\u05e1\u05e7\u05d0\u05d5\u05ea';
  var fs = document.getElementById('txn-footer-sum');
  if (fs) {{ fs.textContent = '\u05e1\u05d4"\u05db: ' + _fmtSum(sum); fs.className = 'txn-footer-sum ' + (sum < 0 ? 'neg' : 'pos'); }}
}}
function _initTxnFooter() {{
  var rows = document.querySelectorAll('.txn-table tbody tr');
  var sum = 0;
  rows.forEach(function(row) {{
    var valEl = row.querySelector('.td-val');
    if (valEl) sum += _parseTxnAmt(valEl.textContent);
  }});
  var fc = document.getElementById('txn-footer-count');
  if (fc) fc.textContent = rows.length + ' \u05e2\u05e1\u05e7\u05d0\u05d5\u05ea';
  var fs = document.getElementById('txn-footer-sum');
  if (fs) {{ fs.textContent = '\u05e1\u05d4"\u05db: ' + _fmtSum(sum); fs.className = 'txn-footer-sum ' + (sum < 0 ? 'neg' : 'pos'); }}
}}
document.addEventListener('DOMContentLoaded', _initTxnFooter);

// ── Flask detection ───────────────────────────────────────
(function detectFlask() {{
  fetch('/api/status', {{method: 'GET'}})
    .then(function(r) {{ return r.json(); }})
    .then(function() {{
      document.getElementById('reload-btn').style.display = 'inline-block';
      var _lt = document.getElementById('log-toggle-btn'); if (_lt) _lt.style.display = '';
      fetch('/api/category/list')
        .then(function(r) {{ return r.json(); }})
        .then(function(list) {{ _buildRoller(list); }})
        .catch(function() {{}});
    }})
    .catch(function() {{}});
}})();
</script>
</body>
</html>'''

        # Determine output paths
        _this   = _os.path.abspath(__file__)
        _src    = _os.path.dirname(_os.path.dirname(_this))   # source/
        _proj   = _os.path.dirname(_src)                       # BankProject/
        _html_out = _os.path.join(_src, 'html', 'Category_output.html')

        with open(_html_out, 'w', encoding='utf-8') as _f:
            _f.write(html)

        if slug:
            _cat_dir = _os.path.join(_proj, 'Outputs', 'category_analysis')
            _os.makedirs(_cat_dir, exist_ok=True)
            with open(_os.path.join(_cat_dir, f'{slug}.html'), 'w', encoding='utf-8') as _f:
                _f.write(html)

    @staticmethod
    def auto_tagger(name: str, category: str = None) -> str:
        """
        The function is responsible for editing the json config file depending on the inputs.
        The function receives:
        a Bussines name, and a category name.
        In case category was not inserted, or specified as None, json file will be updated with
        name: None
        In case both were given, and not None, the pair will be appended or changed depending on
        the current status of the keys on the dictionary.

        The function returns the category that is currently associated with the given name, after the update.

        """
        if os.path.exists(Paths.AUTO_TAGGER_JSON):
            with open(Paths.AUTO_TAGGER_JSON, 'r', encoding='utf-8') as f:
                at_dict = json.load(f)

        else:
            at_dict = {}

        if category is None:
            if name not in at_dict:
                at_dict[name] = None
        else:
            if name in at_dict:
                match at_dict[name]:
                    case None:
                        at_dict[name] = category
                    case "No Match":
                        msg =f"The name {name} is already matched with a 'No Match' string. \
                            but you are trying to change it to {category}, do you aprrove?"
                        if utils.template_menu(['no', 'yes'], msg):
                            at_dict[name] = category
                    case _:
                        msg =f"The name {name} is already matched with the category \
                            {utils.heb_conversion(dict_at[name])} but you are trying \
                            to change it to {category}, do you aprrove?"
                        if utils.template_menu(['no', 'yes'], msg):
                            at_dict[name] = category
            else:
                at_dict[name] = category


        with open(Paths.AUTO_TAGGER_JSON, 'w', encoding='utf-8') as f:
            json.dump(at_dict, f, ensure_ascii=False)
        #utils.log(f"The following key:value pair has been updated in auto_tagger.json to -> {utils.heb_conversion(name)} : {category}",'system')

        return at_dict[name]

    @staticmethod
    def tagger_refresh() -> None:
        """
        The function uses the json config file, in order to try and auto tag transactions
        with no category tagging.
        """
        from database import DataBase

        dirty_bit = False
        logs = "\n\n ----- The following transactions have been tagged: -----\n\n"
        lst, desc = DataBase().get_untagged()
        untagged_transactions_df = pd.DataFrame(lst, columns=desc)
        for _, row in untagged_transactions_df.iterrows():
            res = utils.auto_tagger(row['Name'])
            if res == 'No Match':
                continue
            if res is not None:
                dirty_bit = True
                DataBase().set_category(table_name=row['TableName'], id=row['ID'], category=res)
                logs += f"transaction {utils.heb_conversion(row['Name'])} ({row['TableName']}) ({row['ID']}) was tagged to {utils.heb_conversion(res)}\n"

        if dirty_bit:
            utils.log(logs, 'system')
            DataBase().commit_changes()
        else:
            utils.log('No transactions were Auto tagged...', 'system')

    @staticmethod
    def match_BeinLeumi_headers(table: list[list]) -> list[list]:
        """

        """
        from Configurations.Formats import Formats
        if not Formats.FORMATS["BeinLeumi-Bank"]["Headers"] == \
                ['תאריך',
                'סוג פעולה',
                'תיאור',
                'אסמכתא',
                'זכות',
                'חובה',
                'תאריך ערך',
                'יתרה']:
            raise ValueError("Headers Changed!")
        if not Formats.FORMATS["BeinLeumi-Bank-Date-Range"]["Headers"] == \
                ['יתרה',
                'תאריך ערך',  #1
                'זכות',       #2
                'חובה',       #3
                'תאור',       #4
                'אסמכתא',     #5
                'סוג פעולה',  #6
                'תאריך']:
            raise ValueError("Headers Changed!")
        new_column_order = [7, 6, 4, 5, 2, 3, 1, 0]
        reordered_data = [[row[i] for i in new_column_order] for row in table]
        return reordered_data

    @staticmethod
    def validate_BankTransactions() -> bool:
        """
        
        """
        from datetime import datetime
        from database import DataBase

        def is_valid_balance(value):
            return isinstance(value, (int, float))

        personal_conf_dict = json.load(open(Paths.PERSONAL_CONFIG, encoding='utf-8'))
        date_str = personal_conf_dict['bank_transactions_last_valid_date']
        last_valid_date = datetime.strptime(date_str, "%Y-%m-%d")
        df = DataBase().query_Bank_Transactions_for_validation(last_valid_date)
        df = df.sort_values(by=['Date', 'ID'], ascending=[True, False])
        #print(df.to_markdown())
        balance = "Initial Value"
        for _, row in df.iterrows():
            if balance == "Initial Value":
                if is_valid_balance(row['Balance']):
                    balance = row['Balance']
            else:
                balance += row['Income'] - row['Out']
                if is_valid_balance(row['Balance']):
                    if abs(balance - row['Balance']) > 0.001:
                        utils.log(f"Bank Transaction Validation FAILED!\nDetails:\n\
                                    tried comparing a calculated balance of {balance}\n\
                                    with the given balance of {row['Balance']}\n\
                                    given transaction is associated with ID: {row['ID']}\n\
                                    Transaction date is {row['Date']}", "error")
                    else:
                        last_valid_date = row['Date']
                        print(type(last_valid_date))

        if isinstance(last_valid_date, datetime):
            last_valid_date = last_valid_date.strftime("%Y-%m-%d")
        else:
            # Convert the string to a datetime object
            date_object = datetime.strptime(last_valid_date, "%Y-%m-%d %H:%M:%S")

            # Define the format for the string without the timestamp
            date_format_without_timestamp = "%Y-%m-%d"

            # Convert the datetime object back to a string without the timestamp
            last_valid_date = date_object.strftime(date_format_without_timestamp)
            
        personal_conf_dict['bank_transactions_last_valid_date'] = last_valid_date
        json.dump(personal_conf_dict, open(Paths.PERSONAL_CONFIG, "w", encoding='utf-8'))
        return True

    @staticmethod
    def change_an_existing_category_name():
        """
        The function allows the user to change an existing category name.
        The function will ask the user to choose a category name to replace, and then 
        to choose a new name for it
        """
        current_category_list = utils.get_saved_categories()
        index, sub_category_list = utils.typer_template_menu(current_category_list, msg = "Please choose a category name to replace:", sort = True)
        chosen_category_to_replace = sub_category_list[index]
        
        while True:
            index, sub_category_list = utils.typer_template_menu(options=current_category_list + ["「Choose a new category name」"], 
                                                        msg= "Pick a category from the existing list or choose to create a new one:",
                                                        sort=True,
                                                        )
            new_chosen_category = sub_category_list[index]
            if new_chosen_category == "「Choose a new category name」":
                new_chosen_category = utils.parse_str_from_user(message=f"Please insert a new name for category {(chosen_category_to_replace)}",)
            
            if chosen_category_to_replace == new_chosen_category:
                utils.log("You have chosen the same category name to replace, please choose a different one", 'system')
                continue
            
            if new_chosen_category in ["「Skip」", "「Back to menu」"]:
                utils.log("Choose a valid catregory name...", 'system')
                continue
            
            break
        
        from database import DataBase
        DataBase().replace_category(frm=chosen_category_to_replace, to=new_chosen_category)
        DataBase().commit_changes()
        new_category_lst = current_category_list.copy() 
        new_category_lst.remove(chosen_category_to_replace)
        new_category_lst.append(new_chosen_category)
        utils.update_categories_file(new_category_lst, append=False)
        utils.log(f"({chosen_category_to_replace}) has been replaced by ({new_chosen_category})")

    @staticmethod
    def delete_a_transaction() -> None:
        """
        The function asks the user for card transactions ids to delete from the data base.
        The user can pick multiple ids to delete. Note that after the function is executed,
        there will be no documentation of the deleted transaction.
        """
        utils.log("Please insert the id's of the transactions you want to delete, and -1 to stop", 'system')
        id_lst = []
        while True:
            x = input()
            if x == '-1':
                break
            if not x.isdigit() or int(x) < -1 or int(x) == 0:
                utils.log("Please insert a valid input number...", 'system')
                continue

            id_lst.append(x)

        from database import DataBase
        DataBase().delete_transactions(id_lst)
        DataBase().commit_changes()

    @staticmethod
    def accumulate_cash_Balance() -> int:
        """
        The function will sum all Cash transaction:
        1. transactions created by the user, queried in the Cash Transsaction table
        2. Withdrawlls specified in the Bank Transactions table
            (can be reognized by the Category name "withdrawal" in the Bank Transactions table)
        The function will return the total cash balance.
        """
        from database import DataBase
        from Constants import ReservedNames

        bank_withdrawals_df = DataBase().get_transactions_by_category(ReservedNames.WHITDRAWAL_CATEGORY)

        total_cash = 0

        if not bank_withdrawals_df.empty:
            # Only bank withdrawals (not card transactions tagged 'withdrawal')
            bank_withdrawals_df = bank_withdrawals_df[bank_withdrawals_df['TableName'] == 'BankTransactions']
            total_cash += bank_withdrawals_df['Out/Transaction_value'].sum()

        cash_df = DataBase().get_Cash_Transactions()

        if not cash_df.empty:
            # utils.log(f"Cash Transactions found:\n{utils.df_to_markdown(cash_df)}", 'system')
            total_cash += cash_df['Amount'].sum()


        return total_cash

    @staticmethod
    def cash_monthly_history() -> list:
        """
        Compute the accumulated cash balance (ILS) at the first of each calendar month,
        from the earliest cash transaction up to today.
        Non-ILS currencies are converted using live FX rates.
        Returns [(datetime, ils_balance), ...] sorted by date (month starts + today).
        """
        from database import DataBase
        from Constants import ReservedNames
        import urllib.request as _ureq, json as _json_fx
        from datetime import date as _date, datetime as _dt2

        # Fetch FX rates (ILS-base: currency → ILS multiplier)
        try:
            with _ureq.urlopen('https://api.exchangerate-api.com/v4/latest/ILS', timeout=5) as _r:
                _ils_to_x = _json_fx.loads(_r.read()).get('rates', {})
            _fx_to_ils = {c: 1.0 / r for c, r in _ils_to_x.items() if r}
            _fx_to_ils['ILS'] = 1.0
        except Exception:
            _fx_to_ils = {'ILS': 1.0, 'USD': 3.72, 'EUR': 4.01, 'JPY': 0.025}

        events = []  # list of (date, ils_amount)

        # 1. Bank withdrawals only (not card) — always ILS
        withdrawals_df = DataBase().get_transactions_by_category(ReservedNames.WHITDRAWAL_CATEGORY)
        if not withdrawals_df.empty:
            # get_transactions_by_category UNIONs BankTransactions + CardTransactions;
            # only bank withdrawals represent physical cash received.
            withdrawals_df = withdrawals_df[withdrawals_df['TableName'] == 'BankTransactions']
            withdrawals_df['Date/Executed_Date'] = pd.to_datetime(
                withdrawals_df['Date/Executed_Date'], errors='coerce')
            for _, row in withdrawals_df.iterrows():
                d = row['Date/Executed_Date']
                if pd.notna(d):
                    events.append((d.date(), float(row['Out/Transaction_value'])))

        # 2. Manual CashTransactions — any currency, convert to ILS
        cash_df = DataBase().get_Cash_Transactions()
        if not cash_df.empty:
            cash_df['Execution_Date'] = pd.to_datetime(cash_df['Execution_Date'], errors='coerce')
            for _, row in cash_df.iterrows():
                d = row['Execution_Date']
                if pd.notna(d):
                    cur  = str(row.get('Currency', 'ILS') or 'ILS').strip().upper()
                    rate = _fx_to_ils.get(cur, 1.0)
                    events.append((d.date(), float(row['Amount']) * rate))

        if not events:
            return []

        events.sort(key=lambda x: x[0])

        # Generate first-of-each-month dates from earliest event to today
        today = _date.today()
        cur_m = events[0][0].replace(day=1)
        months = []
        while cur_m <= today:
            months.append(cur_m)
            if cur_m.month == 12:
                cur_m = cur_m.replace(year=cur_m.year + 1, month=1)
            else:
                cur_m = cur_m.replace(month=cur_m.month + 1)

        # Cumulative balance at each month start (events strictly before that month)
        result = []
        ev_idx = 0
        cumulative = 0.0
        for m in months:
            while ev_idx < len(events) and events[ev_idx][0] < m:
                cumulative += events[ev_idx][1]
                ev_idx += 1
            result.append((_dt2.combine(m, _dt2.min.time()), round(cumulative, 2)))

        # Final point: today's full balance (all remaining events)
        while ev_idx < len(events):
            cumulative += events[ev_idx][1]
            ev_idx += 1
        from datetime import datetime as _dt3
        result.append((_dt3.now(), round(cumulative, 2)))

        return result
    
    @staticmethod
    def get_cash_transactions(datetime: datetime | None = None) -> pd.DataFrame:
        """
        The function will return all Cash transaction:
        1. transactions created by the user, queried in the Cash Transsaction table
        2. Withdrawlls specified in the Bank Transactions table
            (can be reognized by the Category name "withdrawal" in the Bank Transactions table)
        Given a datetime object which is not None, the function will filter the transactions to only include those from the specified month and year.
        The function will return a data frame with all queried columns
        """
        from database import DataBase
        from Constants import ReservedNames
        from src_utils.calculations import SimpleMath

        bank_withdrawals_df = DataBase().get_transactions_by_category(ReservedNames.WHITDRAWAL_CATEGORY)
        # Only bank withdrawals represent physical cash received — exclude card transactions
        # tagged 'withdrawal' to match the logic in accumulate_cash_Balance().
        if not bank_withdrawals_df.empty:
            bank_withdrawals_df = bank_withdrawals_df[bank_withdrawals_df['TableName'] == 'BankTransactions']
        # Convert 'Date/Executed_Date' to datetime before filtering.
        # Use dayfirst=True to handle Israeli DD/MM/YYYY and DD.MM.YYYY formats correctly.
        bank_withdrawals_df['Date/Executed_Date'] = pd.to_datetime(
            bank_withdrawals_df['Date/Executed_Date'], errors='coerce', dayfirst=True)
        bank_withdrawals_df = bank_withdrawals_df[
            (bank_withdrawals_df['Date/Executed_Date'].dt.month == datetime.month) &
            (bank_withdrawals_df['Date/Executed_Date'].dt.year == datetime.year)
        ]
        bank_withdrawals_df = bank_withdrawals_df[['ID','Date/Executed_Date', 'Out/Transaction_value', 'Name', 'Category']]
        bank_withdrawals_df = bank_withdrawals_df.rename(columns={'Date/Executed_Date': 'Execution_Date',
                                                                  'Out/Transaction_value': 'Amount',})

        cash_df = DataBase().get_Cash_Transactions(datetime)
        # Exclude filler transactions — they represent balance adjustments (all-time gap), not
        # real monthly income or spending. Including them would inflate the monthly totals.
        if not cash_df.empty and hasattr(ReservedNames, 'CASH_FILLER_CATEGORY'):
            cash_df = cash_df[cash_df['Category'] != ReservedNames.CASH_FILLER_CATEGORY]
        cash_df['Execution_Date'] = pd.to_datetime(cash_df['Execution_Date'], errors='coerce')

        cash_df = cash_df[['ID', 'Execution_Date', 'Amount', 'Name', 'Category']]

        combined_cash_df = pd.concat([cash_df, bank_withdrawals_df], ignore_index=True)
        combined_cash_df = combined_cash_df.sort_values(by='Execution_Date', ascending=False).reset_index(drop=True)

        # Convert 'Amount' column to numeric
        combined_cash_df['Amount'] = pd.to_numeric(combined_cash_df['Amount'], errors='coerce')

        return combined_cash_df

    @staticmethod
    def df_to_markdown(df: pd.DataFrame) -> str:
        """
        Converts a DataFrame to markdown format while properly handling Hebrew text.
        Applies heb_conversion to all string values to ensure correct RTL display.
        """
        # Create a copy to avoid modifying the original DataFrame
        df_display = df.copy()
        
        # Convert all object/string columns that may contain Hebrew
        for col in df_display.select_dtypes(include=['object']):
            df_display[col] = df_display[col].apply(lambda x: utils.heb_conversion(str(x)) if pd.notna(x) else x)
            
        # Convert column names that may contain Hebrew
        df_display.columns = [utils.heb_conversion(str(col)) for col in df_display.columns]
        
        return df_display.to_markdown()

    @staticmethod
    def generate_date(date_str: str, date_format: str) -> datetime:
        """
        Convert string date to datetime with validation for dates after 2020.
        
        Args:
            date_str: Date string to convert
            date_format: Expected format of date_str (e.g. "%d/%m/%Y")
            
        Returns:
            datetime object if valid
            
        Raises:
            Logs error and exits if date is invalid or before 2020
        """
        try:
            # Convert to datetime
            date = datetime.strptime(date_str, date_format)
            
            # Validate year
            if date.year < 2020:
                utils.log(f"Date {date_str} is before 2020. Only dates from 2020 onwards are allowed.", "error")
            
            return date
            
        except ValueError as e:
            utils.log(f"Invalid date format: {date_str}\nExpected format: {date_format}\nError: {str(e)}", "error")
        except Exception as e:
            utils.log(f"Error processing date: {date_str}\nError: {str(e)}", "error")


    @staticmethod
    def card_charge_validation(processed_df: pd.DataFrame, date: datetime) -> pd.DataFrame:
        """
        @prama processed_df: The function will receive the processed monthly transactions data frame.  
        @param date: monthly date inserted by the user, the date will be used to query the bank transactions in the following month.

        The function will try and validate all credit card charges present in the given month by comparing
        the total sum of all transaction executed withing a specific card with a bank transaction in the following month.
        match will be found when the price of the summed  transaction will be equal to a bank transaction in the following month
        and also the bank transaction main name will match the possible names specified by the user.

        The function will return a data frame with the following columns:
        - CardID: The card identifier
        - Status: Verified (1) / Not Verified (0)
        - Out/Transaction_value: The total sum of all transactions executed with the given card in the given month

        """
        # ----- New Code Here -------------------------------------
        from database import DataBase
        from Constants import Settings, Trans_Type

        wip_df = processed_df.copy()

        # Define the nan values for all bank transaction to a valid value: "Bank" for easier use
        wip_df['CardID'] = wip_df.apply(lambda row: 'Bank' if row['TableName'] == 'BankTransactions' else row['CardID'], axis=1)
        # Group by and drop irellevant columns
        wip_df = wip_df[['CardID', 'Final_Value']].groupby('CardID').sum().reset_index()
        wip_df['Status'] = False

        bank_df = DataBase().get_Bank_Transactions(utils.next_month(date).month,
                                                    utils.next_month(date).year)

        for _, row_card in wip_df.iterrows():
            # Skip the row that summes all bank transactions because validation is not required for it
            if row_card['CardID'] == 'Bank':
                continue
            for _, row_bank in bank_df.iterrows():
                card_charge_sum = abs(round(row_card['Final_Value'], 2))
                card_id = row_card['CardID']
                possible_bank_transaction_match =  round(row_bank['Out'], 2)
                if card_charge_sum == possible_bank_transaction_match:
                    wip_df.loc[wip_df['CardID'] == card_id, 'Status'] = True
                    if row_bank['Category'] == CC_CHARGE_CATEGORY_NAME:
                        break

                    hook = utils._cc_confirm_hook
                    if hook is not None:
                        approved = hook(row_bank.to_dict())
                    else:
                        approved = utils.template_menu(['No', 'Yes'], f"App found this transaction to be a credit card:\n\
                                        {row_bank}\n Do you Agree?")
                    if approved:
                        DataBase().set_category('BankTransactions', row_bank['ID'], CC_CHARGE_CATEGORY_NAME)
                        DataBase().commit_changes()
                        break
                    else:
                        utils.log('ignored...', 'system')
        
        if Settings.DEBUG:
            for index, row in wip_df.iterrows():
                if row['Status'] == 'Not Verified':
                    # Perform your action here
                    utils.log(f"information for card at index: {index},\n {wip_df[wip_df['CardID'] == row['CardID']].to_markdown()}", 'debug')
        
        return wip_df

        # format_name, card_number = col.split(" | ")
        # format_dict = Formats.FORMATS.get(format_name, {})
        # card_names_dict = format_dict.get("Transaction Names", {})
   

    @staticmethod
    def handle_withdrawals() -> Tuple[bool, str, pd.DataFrame]:
        """
        The function is responsible for handling withdrawals transactions present in both
        Bank Transactions and Card Transactions.
        The function will match transactions from both tables.
        Withdrawals transactions in Card Transactions are identified by a ReservedName "משיכת מזומנים"
        and the corresponding transaction in Bank Transactions is identified by the Card charge name, the same price, and charge month
        and will be tagged with the category "withdrawal".
        withdrawals are not calculated in the Analysis phase.
        
        The function will return a tuple with the following values:
        - bool: True is returned if no unpaired witdrawals were found, and False if withdrawals with no match were found.
        - str: A message indicating the result of the operation.
        - pd.DataFrame: 
        """
        from database import DataBase
        from Constants import ReservedNames
        from Configurations.Formats import Formats

        # Get all card transactions with the reserved name "משיכת מזומנים"
        card_withdrawals_df = DataBase().get_transactions_by_name(table_name="CardTransactions", name=ReservedNames.WITHDRAWAL)
        if card_withdrawals_df.empty:
            return True, "No Withdrawal transactions found", pd.DataFrame()
        
        #utils.log(f"{utils.df_to_markdown(card_withdrawals_df)}")

        # Remove transactions that have already been tagged as withdrawals
        card_withdrawals_df = card_withdrawals_df[card_withdrawals_df['Category'] != ReservedNames.WHITDRAWAL_CATEGORY]
        
        # Remove unnecessary columns
        card_withdrawals_df = card_withdrawals_df[['ID', 'CardID', 'Executed_Date', 'Transaction_Value']]

        total_matched_transactions_df = pd.DataFrame()

        for _, row in card_withdrawals_df.iterrows():
            # extract all the keys represting card numbers in the Transaction Names dictionary for each format dictionary
            possible_bank_transaction_names = [name for format_config in Formats.FORMATS.values() for card_id, names in format_config["Transaction Names"].items() for name in names if card_id == row['CardID']]
        
            # Get all bank transactions for the month of the first withdrawal
            transaction_date = datetime.strptime(row['Executed_Date'], "%Y-%m-%d %H:%M:%S")
            bank_transactions_df = DataBase().get_Bank_Transactions(transaction_date.month, transaction_date.year)

            #check if transaction matches in the bank_transactions_df
            matched_transactions_df = bank_transactions_df[
                (bank_transactions_df['Out'] == row['Transaction_Value']) &
                (bank_transactions_df['Name'].isin(possible_bank_transaction_names))
            ]
            
            #utils.log(f"{utils.df_to_markdown(matched_transactions_df)}")

            if matched_transactions_df.empty:
                return False, f"No matching transactions found for withdrawal ID: {row['ID']}, CardID: {row['CardID']}, Executed Date: {row['Executed_Date']}", pd.DataFrame()

            # if the size of the df is larger than 1, it means that there are multiple transactions that match the withdrawal.
            # Only the first one will be matched, and the rest will be ignored.
            # This case will happen when there were more than one withdrawal of the same amount in the same month.
            # The ignored transaction will be matched in the next iteration.
            if matched_transactions_df.shape[0] > 1:
                utils.log(f"Multiple matching transactions found for withdrawal ID: {row['ID']}, CardID: {row['CardID']}, Executed Date: {row['Executed_Date']}. This will trigger incorrect tagging for a case where there are more than one withdrawal per month.", 'warning')
                matched_transactions_df = matched_transactions_df.head(1)

            # this can probably be romoved
            if matched_transactions_df.empty:
                continue  # matching transactions were already matched before, skip to the next withdrawal

            # The set category function receives a ID of type int to set\
            else:
                # x is an integer holding the id of the first row in the df
                DataBase().set_category('CardTransactions', int(row['ID']), ReservedNames.WHITDRAWAL_CATEGORY)
                DataBase().set_category('BankTransactions', int(matched_transactions_df['ID'].iloc[0]), ReservedNames.WHITDRAWAL_CATEGORY)
                DataBase().set_description('CardTransactions', int(row['ID']),f"Matched with Bank Transaction ID: {matched_transactions_df['ID'].iloc[0]}")
                DataBase().set_description('BankTransactions', int(matched_transactions_df['ID'].iloc[0]), f"Matched with Card Transaction ID: {int(row['ID'])}")
                DataBase().commit_changes()
                total_matched_transactions_df = pd.concat([total_matched_transactions_df, matched_transactions_df], ignore_index=True)


        if total_matched_transactions_df.empty:
            return True, "Witdrawals Check Executed, None found", total_matched_transactions_df
        else:
            return True, "All withdrawals matched successfully", total_matched_transactions_df
        

    @staticmethod
    def exclude_transaction() -> None:
        """
        Lets the user choose a table and transaction ID to exclude.
        Sets category and description to 'EXCLUDE'.
        """
        tables = ['BankTransactions', 'CardTransactions']
        result_table = utils.template_menu(tables, 'Please choose a table to exclude a transaction from:')
        # choose a valid id and if not valid try again until user inserts -1
        result_id = input(f"Please insert the ID of the transaction you want to exclude from {tables[result_table]}: ")
        while not result_id.isdigit() or int(result_id) < 0:
            if result_id == '-1':
                return
            result_id = input("Invalid ID. Please insert a valid ID or -1 to exit: ")
        
        from database import DataBase
        from Constants import ReservedNames

        DataBase().set_category(tables[result_table], int(result_id), ReservedNames.EXCLUDED_CATEGORY)
        DataBase().commit_changes()
        utils.log(f"Transaction {result_id} from table {tables[result_table]} has been excluded.", 'system')


    @staticmethod
    def extract_payments_data(df: pd.DataFrame) -> pd.DataFrame:
        """
        extract the following data from the spending df recived:
        1. Transaction Name
        2. Current Payment
        3. Total transaction amount
        4. number of payments
        5. current payment number

        payments are identified by the data in the 'Extra_Info' column, which should contain the following string:
        'תשלום b  מתוך a'
        where a is the total number of payments and b is the current payment number.
        """
        import re

        records = []

        # Iterate through each row in the DataFrame
        for _, row in df.iterrows():
            extra_info = row['Extra_Info']
            if pd.isna(extra_info):
                continue
            # Use regex to find the payment information
            match = re.search(r'תשלום\s+(\d+)\s+מתוך\s+(\d+)', extra_info)
            if match:
                current_payment = int(match.group(1))
                total_payments = int(match.group(2))
                
                # Append the extracted data to the new DataFrame
                records.append({
                    'Transaction Name': row['Name'],
                    'Current Payment': abs(row['Final_Value']),
                    'Total Amount': row['Charge_Value'],
                    'Number of Payments': total_payments,
                    'Current Payment Number': current_payment})
            else:
                continue
        
        return pd.DataFrame(records)

    @staticmethod
    def detect_continuous_payments() -> None:
        """
        Detects untagged payment transactions that are sequential installments of a prior payment.
        
        A continuous payment is identified when:
        1. Current transaction is an untagged payment (Extra_Info matches 'תשלום X מתוך Y')
        2. There exists a prior payment with:
           - Same transaction name
           - Same total payments count (Y)
           - Same charge_value (important: charge_value not transaction_value, as they may differ)
           - Earlier charge_date (ensuring it was already executed)
           - Lower payment number (X_prior < X_current)
           - Is categorized (NotCategorized != Category)
        
        For matched continuous payments, the function applies the prior payment's category and description.
        """
        import re
        from database import DataBase
        
        try:
            utils.log("Scanning untagged transactions for continuous payment sequences...", "system")
            
            db = DataBase()
            
            # Get untagged card payment transactions
            untagged_list, desc = db.get_untagged_card_payments()
            if not untagged_list:
                utils.log("No untagged CardTransactions found for continuous payment detection.", "debug")
                return
            
            untagged_df = pd.DataFrame(untagged_list, columns=desc)
            
            if untagged_df.empty:
                utils.log("No untagged transactions with payment info found.", "debug")
                return
            
            # Extract payment transaction data from untagged transactions
            untagged_payments = []
            for idx, row in untagged_df.iterrows():
                try:
                    extra_info = row['Extra_Info']
                    # Filter for payment transactions only
                    if not extra_info or extra_info == '':
                        continue
                    
                    match = re.search(r'תשלום\s+(\d+)\s+מתוך\s+(\d+)', extra_info)
                    if match:
                        current_payment = int(match.group(1))
                        total_payments = int(match.group(2))
                        
                        untagged_payments.append({
                            'ID': row['ID'],
                            'Name': row['Name'],
                            'Current_Payment': current_payment,
                            'Total_Payments': total_payments,
                            'Charge_Value': row['Charge_Value'],
                            'Charge_Date': row['Charge_Date'],
                            'Extra_Info': extra_info
                        })
                except (KeyError, ValueError, AttributeError) as e:
                    utils.log(f"Error parsing payment info from transaction ID {row.get('ID', 'unknown')}: {str(e)}", "warning")
                    continue
            
            if not untagged_payments:
                utils.log("No untagged payment transactions found.", "debug")
                return
            
            continuous_payments_matched = []
            
            # For each untagged payment, search the DB for a matching prior payment
            for candidate in untagged_payments:
                try:
                    current_id = candidate['ID']
                    current_name = candidate['Name']
                    current_payment_num = candidate['Current_Payment']
                    total_payments = candidate['Total_Payments']
                    charge_value = candidate['Charge_Value']
                    charge_date = candidate['Charge_Date']
                    prior_payment_num = current_payment_num - 1
                    
                    # Look for prior payment in the database
                    # Query all transactions with same name and filter for matching criteria
                    all_same_name = db.get_transactions_by_name('CardTransactions', current_name)
                    
                    if all_same_name.empty:
                        continue
                    
                    # Filter for prior payment with specific criteria:
                    # 1. Is a payment transaction (has Extra_Info with payment pattern)
                    # 2. Same total payments count
                    # 3. Same charge_value
                    # 4. Earlier charge_date (already executed)
                    # 5. Is categorized
                    prior_candidates = all_same_name[
                        (all_same_name['Extra_Info'].notna()) &
                        (all_same_name['Extra_Info'] != '') &
                        (all_same_name['Category'] != 'NotCategorized') &
                        (all_same_name['Category'].notna()) &
                        (all_same_name['Charge_Date'] < charge_date) &
                        (all_same_name['Charge_Value'] == charge_value)
                    ]
                    
                    if prior_candidates.empty:
                        continue
                    
                    # Extract payment number from Extra_Info to find matching prior payment
                    for _, prior_row in prior_candidates.iterrows():
                        try:
                            prior_extra_info = prior_row['Extra_Info']
                            prior_match = re.search(r'תשלום\s+(\d+)\s+מתוך\s+(\d+)', prior_extra_info)
                            if prior_match:
                                prior_payment = int(prior_match.group(1))
                                prior_total = int(prior_match.group(2))
                                
                                # Check if same payment series and prior payment is from earlier in the sequence
                                if prior_total == total_payments and prior_payment < current_payment_num:
                                    prior_category = prior_row['Category']
                                    prior_description = prior_row['Description']
                                    
                                    continuous_payments_matched.append({
                                        'current_id': current_id,
                                        'current_payment_num': current_payment_num,
                                        'prior_id': prior_row['ID'],
                                        'prior_payment_num': prior_payment,
                                        'name': current_name,
                                        'total_payments': total_payments,
                                        'category': prior_category,
                                        'description': prior_description
                                    })
                                    break
                        except (ValueError, AttributeError):
                            continue
                    
                except Exception as candidate_error:
                    utils.log(f"Error processing candidate payment ID {candidate.get('ID', 'unknown')}: {str(candidate_error)}", "debug")
                    continue
            
            # Apply categorization to matched continuous payments
            if continuous_payments_matched:
                successful_updates = 0
                for match in continuous_payments_matched:
                    try:
                        db.set_category('CardTransactions', match['current_id'], match['category'])
                        if match['description'] is not None and match['description'] != '':
                            db.set_transaction_description(match['description'], 'CardTransactions', match['current_id'])
                        
                        log_msg = f"Continuous payment auto-tagged: ID {match['current_id']} (payment {match['current_payment_num']}/{match['total_payments']}) " \
                                  f"'{utils.heb_conversion(match['name'])}' → {utils.heb_conversion(str(match['category']))}"
                        utils.log(log_msg, "system")
                        successful_updates += 1
                    except Exception as update_error:
                        utils.log(f"Error categorizing transaction ID {match['current_id']}: {str(update_error)}", "warning")
                        continue
                
                if successful_updates > 0:
                    try:
                        db.commit_changes()
                        utils.log(f"Continuous payment detection complete: {successful_updates} transactions auto-tagged", "system")
                    except Exception as commit_error:
                        utils.log(f"Error committing continuous payment updates: {str(commit_error)}", "error")
                else:
                    utils.log("No continuous payments were successfully updated.", "debug")
            else:
                utils.log("No continuous payment sequences were detected in untagged transactions.", "system")
        
        except Exception as main_error:
            utils.log(f"Critical error in detect_continuous_payments(): {str(main_error)}", "error")
            import traceback
            utils.log(traceback.format_exc(), "error")

    @staticmethod
    def parse_date_from_user(return_type: str = "str", day: bool = True) -> str | datetime:
        """
        Asks the user for a date and returns it as a string or datetime object.
        The date is returned in "%Y-%m-%d" format (string) or as a datetime object.
        Args:
            return_type (str): "str" for string output, "datetime" for datetime object.
            day (bool): If True, day is also parsed. If False, only month and year are parsed.
                day will be set as 1 for Arg day=False.
        Returns:
            str or datetime: The date in the requested format.
        """
        while True:
            try:
                if day:
                    date_input = input("Please enter a date (YYYY-MM-DD): ")
                    date_obj = datetime.strptime(date_input, "%Y-%m-%d")
                else:
                    date_input = input("Please enter a date (YYYY-MM): ")
                    date_obj = datetime.strptime(date_input, "%Y-%m")
                
                if return_type == "str":
                    return date_obj.strftime("%Y-%m-%d") if day else date_obj.strftime("%Y-%m")
                elif return_type == "datetime":
                    return date_obj
                else:
                    utils.log("Invalid return_type specified. Use 'str' or 'datetime'.", "error")
            except ValueError:
                utils.log("Invalid date format. Please try again.", "system")

    @staticmethod
    def delete_cash_transaction_by_id() -> bool:
        """
        The function will ask the user for an integer, representing a valid ID from
        the Cash Transactions table, and will delete the transaction with the given ID.
        The input will be asked until a valid input was received.
        the function will return True if the transaction was deleted successfully, and False otherwise.
        """
        from database import DataBase

        while True:
            user_input = input("Please enter the ID of the Cash Transaction to delete (or -1 to exit): ")
            if user_input == '-1':
                return False
            if not user_input.isdigit() or int(user_input) <= 0:
                utils.log("Invalid input. Please enter a positive integer ID or -1 to exit.",'system')
                continue
            
            transaction_id = int(user_input)
            if not DataBase().is_cash_transaction_exists(transaction_id):
                print(f"No Cash Transaction found with ID: {transaction_id}. Please try again.")
                continue
            
            # Confirm deletion
            confirm = utils.template_menu(['no', 'yes'], "Are you sure you want to delete the Cash Transaction with ID {transaction_id}? This action cannot be undone. (yes/no): ")

            if confirm == 1:  # User confirmed deletion
                DataBase().delete_cash_transaction(transaction_id)
                DataBase().commit_changes()
                utils.log(f"Cash Transaction with ID {transaction_id} has been deleted.", 'system')
                return True
            else:
                utils.log("Deletion cancelled. No changes made.", 'system')
                return False

    @staticmethod       
    def parse_str_from_user(message: str = "Please enter a non-empty string: ") -> str:
        """
        Asks the user for a non-empty string input.
        Returns the input string.
        """
        while True:
            user_input = input(message).strip()
            if user_input:
                return user_input
            else:
                utils.log("Input cannot be empty. Please try again.", "system")
