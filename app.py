"""
Flask web application for BankDashBoard.

This web layer provides a read/analytics interface to the PostgreSQL database.
File parsing (Excel → DB) is still done locally via the CLI (source/main.py).
"""

import os
import sys
from datetime import datetime

from flask import Flask, jsonify, request, render_template_string
from dotenv import load_dotenv

load_dotenv()

# Make source/ importable so we can reuse database.py directly
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'source'))

app = Flask(__name__)


def get_db():
    """Return a fresh DataBase instance per request (avoids stale connections)."""
    import database as _db_module
    _db_module.DataBase._DataBase__instance = None  # reset singleton for each request
    from database import DataBase
    return DataBase()


# ── API routes ────────────────────────────────────────────────────────────────

@app.route('/api/categories')
def api_categories():
    """Spending by category for the current month."""
    try:
        today = datetime.now()
        df = get_db().get_monthly_spendings(today.year, today.month)
        if df.empty:
            return jsonify([])
        col = 'Out/Transaction_value'
        by_cat = df.groupby('Category')[col].sum().sort_values(ascending=False)
        return jsonify([{'category': k, 'amount': round(float(v), 2)}
                        for k, v in by_cat.items()])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/monthly-summary')
def api_monthly_summary():
    """Spending and income totals for the past 6 months."""
    try:
        db = get_db()
        today = datetime.now()
        result = []
        for i in range(5, -1, -1):
            m = today.month - i
            y = today.year
            while m <= 0:
                m += 12
                y -= 1
            spendings = db.get_monthly_spendings(y, m)
            earnings  = db.get_monthly_earnings(y, m)
            spend_col = 'Out/Transaction_value'
            earn_col  = 'Income/Charge_Value'
            result.append({
                'month':    f"{y}-{m:02d}",
                'spending': round(float(spendings[spend_col].sum()), 2) if not spendings.empty else 0,
                'earnings': round(float(earnings[earn_col].sum()),    2) if not earnings.empty else 0,
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/transactions')
def api_transactions():
    """Search transactions with optional filters: name, category, from, to."""
    try:
        params = {}
        if request.args.get('name'):
            params['name'] = request.args['name']
        if request.args.get('category'):
            params['category'] = request.args['category']
        if request.args.get('from') and request.args.get('to'):
            params['date_range'] = (request.args['from'], request.args['to'])
        df = get_db().search_transactions(params)
        return jsonify(df.head(100).fillna('').to_dict(orient='records'))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/balance')
def api_balance():
    try:
        return jsonify({'balance': get_db().get_latest_Balance()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Main dashboard ────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    today = datetime.now()
    ctx = {
        'month': today.strftime('%B %Y'),
        'error': None,
        'balance': 'N/A',
        'total_spend': 0,
        'total_earn': 0,
        'card_count': 0,
    }
    try:
        db = get_db()
        ctx['balance']     = db.get_latest_Balance() or 'N/A'
        spendings          = db.get_monthly_spendings(today.year, today.month)
        earnings           = db.get_monthly_earnings(today.year, today.month)
        ctx['total_spend'] = float(spendings['Out/Transaction_value'].sum()) if not spendings.empty else 0
        ctx['total_earn']  = float(earnings['Income/Charge_Value'].sum())    if not earnings.empty else 0
        ctx['card_count']  = len(db.get_card_ids())
    except Exception as e:
        ctx['error'] = str(e)
    return render_template_string(_DASHBOARD_HTML, **ctx)


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Bank Dashboard</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
  <style>
    body { background:#f4f6fb; font-family: 'Segoe UI', sans-serif; }
    .stat-card { border-left: 5px solid; border-radius: 8px; }
    .stat-balance { border-color:#0d6efd; }
    .stat-spend   { border-color:#dc3545; }
    .stat-earn    { border-color:#198754; }
    .stat-cards   { border-color:#fd7e14; }
    .section-title { font-size:.85rem; text-transform:uppercase; letter-spacing:.08em; color:#6c757d; }
  </style>
</head>
<body>
<div class="container py-4">

  <div class="d-flex justify-content-between align-items-center mb-4">
    <div>
      <h2 class="mb-0 fw-bold">Bank Dashboard</h2>
      <span class="text-muted">{{ month }}</span>
    </div>
  </div>

  {% if error %}
  <div class="alert alert-danger">
    <strong>Connection error:</strong> {{ error }}<br>
    <small>Make sure <code>DATABASE_URL</code> is set in your Vercel environment variables.</small>
  </div>
  {% endif %}

  <!-- Summary cards -->
  <div class="row g-3 mb-4">
    <div class="col-6 col-md-3">
      <div class="card stat-card stat-balance h-100 shadow-sm">
        <div class="card-body">
          <div class="section-title">Balance</div>
          <div class="fs-4 fw-bold mt-1">₪{{ balance }}</div>
        </div>
      </div>
    </div>
    <div class="col-6 col-md-3">
      <div class="card stat-card stat-spend h-100 shadow-sm">
        <div class="card-body">
          <div class="section-title">Monthly Spending</div>
          <div class="fs-4 fw-bold text-danger mt-1">₪{{ "%.0f"|format(total_spend) }}</div>
        </div>
      </div>
    </div>
    <div class="col-6 col-md-3">
      <div class="card stat-card stat-earn h-100 shadow-sm">
        <div class="card-body">
          <div class="section-title">Monthly Income</div>
          <div class="fs-4 fw-bold text-success mt-1">₪{{ "%.0f"|format(total_earn) }}</div>
        </div>
      </div>
    </div>
    <div class="col-6 col-md-3">
      <div class="card stat-card stat-cards h-100 shadow-sm">
        <div class="card-body">
          <div class="section-title">Credit Cards</div>
          <div class="fs-4 fw-bold mt-1">{{ card_count }}</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Charts -->
  <div class="row g-3 mb-4">
    <div class="col-md-5">
      <div class="card shadow-sm h-100">
        <div class="card-header bg-white fw-semibold">Spending by Category</div>
        <div class="card-body d-flex align-items-center justify-content-center">
          <canvas id="catChart" style="max-height:260px"></canvas>
        </div>
      </div>
    </div>
    <div class="col-md-7">
      <div class="card shadow-sm h-100">
        <div class="card-header bg-white fw-semibold">6-Month Trend</div>
        <div class="card-body">
          <canvas id="trendChart" style="max-height:260px"></canvas>
        </div>
      </div>
    </div>
  </div>

  <!-- Transaction search -->
  <div class="card shadow-sm">
    <div class="card-header bg-white fw-semibold">Search Transactions</div>
    <div class="card-body">
      <div class="row g-2 mb-3">
        <div class="col-md-4">
          <input type="text" id="sName" class="form-control" placeholder="Name or description">
        </div>
        <div class="col-md-3">
          <input type="text" id="sCat" class="form-control" placeholder="Category">
        </div>
        <div class="col-md-2">
          <input type="date" id="sFrom" class="form-control">
        </div>
        <div class="col-md-2">
          <input type="date" id="sTo" class="form-control">
        </div>
        <div class="col-md-1">
          <button class="btn btn-primary w-100" onclick="doSearch()">Go</button>
        </div>
      </div>
      <div style="max-height:380px; overflow-y:auto;">
        <table class="table table-sm table-hover mb-0">
          <thead class="table-light sticky-top">
            <tr>
              <th>Date</th><th>Name</th><th>Category</th>
              <th class="text-end">Amount</th><th>Source</th>
            </tr>
          </thead>
          <tbody id="txBody">
            <tr><td colspan="5" class="text-center text-muted py-3">Enter filters and press Go</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

</div>

<script>
// Category doughnut
fetch('/api/categories').then(r => r.json()).then(data => {
  if (!Array.isArray(data) || !data.length) return;
  new Chart(document.getElementById('catChart'), {
    type: 'doughnut',
    data: {
      labels: data.map(d => d.category),
      datasets: [{ data: data.map(d => d.amount), borderWidth: 1 }]
    },
    options: { plugins: { legend: { position: 'right', labels: { boxWidth: 12 } } } }
  });
});

// 6-month trend bar chart
fetch('/api/monthly-summary').then(r => r.json()).then(data => {
  if (!Array.isArray(data)) return;
  new Chart(document.getElementById('trendChart'), {
    type: 'bar',
    data: {
      labels: data.map(d => d.month),
      datasets: [
        { label: 'Spending', data: data.map(d => d.spending), backgroundColor: 'rgba(220,53,69,.65)' },
        { label: 'Income',   data: data.map(d => d.earnings), backgroundColor: 'rgba(25,135,84,.65)' }
      ]
    },
    options: { scales: { y: { beginAtZero: true } }, plugins: { legend: { position: 'top' } } }
  });
});

// Transaction search
function doSearch() {
  const params = new URLSearchParams();
  const name = document.getElementById('sName').value;
  const cat  = document.getElementById('sCat').value;
  const from = document.getElementById('sFrom').value;
  const to   = document.getElementById('sTo').value;
  if (name) params.set('name', name);
  if (cat)  params.set('category', cat);
  if (from) params.set('from', from);
  if (to)   params.set('to', to);

  document.getElementById('txBody').innerHTML =
    '<tr><td colspan="5" class="text-center text-muted">Loading…</td></tr>';

  fetch('/api/transactions?' + params).then(r => r.json()).then(rows => {
    if (rows.error) {
      document.getElementById('txBody').innerHTML =
        `<tr><td colspan="5" class="text-danger">${rows.error}</td></tr>`;
      return;
    }
    if (!rows.length) {
      document.getElementById('txBody').innerHTML =
        '<tr><td colspan="5" class="text-center text-muted">No results</td></tr>';
      return;
    }
    document.getElementById('txBody').innerHTML = rows.map(r => {
      const amt   = r.Out_Transaction_Value || r.Income_Charge_Value || 0;
      const isOut = parseFloat(amt) > 0;
      return `<tr>
        <td>${r.Date_Executed_Date || ''}</td>
        <td>${r.Name || ''}</td>
        <td>${r.Category || ''}</td>
        <td class="text-end ${isOut ? 'text-danger' : 'text-success'}">${amt}</td>
        <td><small class="text-muted">${r.TableName || ''}</small></td>
      </tr>`;
    }).join('');
  });
}
</script>
</body>
</html>"""


if __name__ == '__main__':
    app.run(debug=True, port=5000)
