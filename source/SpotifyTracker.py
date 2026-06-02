"""
Spotify Family Plan Tracker — business logic and PDF generation.
"""
import math
import io
import os
import sqlite3

# ── Balance calculation ────────────────────────────────────────────────────────

def compute_balance(member_payments: list, charges: list) -> dict:
    """
    Compute running balance for one paying member.

    member_payments: list of dicts with at least {'amount': float}
    charges:         list of dicts {month, total_amount, member_count, confirmed}

    Returns:
        balance:       float  (positive = credit, negative = owes)
        current_share: float  (latest confirmed month's per-person share)
        months_status: int    (positive = months ahead, negative = months owed, 0 = even)
        status:        'ahead' | 'even' | 'owes'
    """
    confirmed = [c for c in charges if c.get('confirmed')]
    total_debited = sum(c['total_amount'] / c['member_count'] for c in confirmed)
    total_credited = sum(float(p['amount']) for p in member_payments)
    balance = round(total_credited - total_debited, 2)

    current_share = 0.0
    if confirmed:
        latest = max(confirmed, key=lambda c: c['month'])
        current_share = round(latest['total_amount'] / latest['member_count'], 2)

    months_status = 0
    if current_share > 0:
        if balance < -0.01:
            months_status = -math.ceil(abs(balance) / current_share)
        elif balance > 0.01:
            months_status = math.floor(balance / current_share)

    if balance < -0.01:
        status = 'owes'
    elif balance > 0.01:
        status = 'ahead'
    else:
        status = 'even'

    return {
        'balance': balance,
        'current_share': current_share,
        'months_status': months_status,
        'status': status,
    }


def compute_all_balances(db) -> list:
    """
    Return balance summary for every paying member (is_exempt=0, is_active=1).
    db: DataBase instance
    """
    members  = db.get_spotify_members()
    charges  = db.get_spotify_charges()
    payments = db.get_spotify_payments()

    result = []
    for m in members:
        if m['is_exempt'] or not m['is_active']:
            continue
        m_payments = [p for p in payments if p['member_id'] == m['id']]
        bal = compute_balance(m_payments, charges)
        last_payment = max((p['payment_date'] for p in m_payments), default=None)
        result.append({
            'member_id':     m['id'],
            'name':          m['name'],
            'balance':       bal['balance'],
            'current_share': bal['current_share'],
            'months_status': bal['months_status'],
            'status':        bal['status'],
            'last_payment':  last_payment,
            'payment_count': len(m_payments),
        })
    return result


# ── Transaction suggestions ────────────────────────────────────────────────────

def get_charge_suggestions(db_path: str) -> list:
    """
    Find outgoing transactions whose Name contains 'spotify' (case-insensitive)
    from both BankTransactions and CardTransactions, excluding months that already
    have a confirmed SpotifyMonthlyCharge.
    Returns list of {tx_id, date, name, amount, month, source}.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        confirmed_months = {
            r[0] for r in conn.execute(
                "SELECT Month FROM SpotifyMonthlyCharge WHERE Confirmed = 1"
            ).fetchall()
        }

        candidates = []

        for row in conn.execute("""
            SELECT ID, Date, Name, Out AS amount
            FROM BankTransactions
            WHERE LOWER(Name) LIKE '%spotify%' AND Out > 0
            ORDER BY Date DESC LIMIT 24
        """).fetchall():
            month = (row['Date'] or '')[:7]
            if month and month not in confirmed_months:
                candidates.append({
                    'tx_id':  row['ID'],
                    'date':   row['Date'],
                    'name':   row['Name'],
                    'amount': float(row['amount'] or 0),
                    'month':  month,
                    'source': 'BankTransactions',
                })

        for row in conn.execute("""
            SELECT ID, Executed_Date AS date, Name, Charge_Value AS amount
            FROM CardTransactions
            WHERE LOWER(Name) LIKE '%spotify%' AND Charge_Value > 0
            ORDER BY date DESC LIMIT 24
        """).fetchall():
            month = (row['date'] or '')[:7]
            if month and month not in confirmed_months:
                candidates.append({
                    'tx_id':  row['ID'],
                    'date':   row['date'],
                    'name':   row['Name'],
                    'amount': float(row['amount'] or 0),
                    'month':  month,
                    'source': 'CardTransactions',
                })

        # Keep highest-amount candidate per month
        by_month = {}
        for c in candidates:
            m = c['month']
            if m not in by_month or c['amount'] > by_month[m]['amount']:
                by_month[m] = c

        return sorted(by_month.values(), key=lambda x: x['month'], reverse=True)
    finally:
        conn.close()


def get_unmatched_payments(db_path: str) -> list:
    """
    Return income transactions that look like Spotify family-member reimbursements
    and have not yet been assigned to any SpotifyMemberPayment.

    Matches BankTransactions (income side) where the transaction name, description,
    or category contains 'spotify' (case-insensitive).  Card transactions are
    excluded here because card charges are outgoing costs, not incoming payments.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        assigned = {
            r[0] for r in conn.execute(
                "SELECT TX_ID FROM SpotifyMemberPayments WHERE TX_ID IS NOT NULL"
            ).fetchall()
        }

        results = []

        for row in conn.execute("""
            SELECT ID, Date, Name, Income AS amount, Description, Category
            FROM BankTransactions
            WHERE Income > 0
              AND (
                LOWER(Name)        LIKE '%spotify%'
                OR LOWER(Description) LIKE '%spotify%'
                OR LOWER(Category)    LIKE '%spotify%'
              )
            ORDER BY Date DESC LIMIT 200
        """).fetchall():
            if row['ID'] not in assigned:
                results.append({
                    'id':       row['ID'],
                    'date':     row['Date'],
                    'name':     row['Name'],
                    'amount':   float(row['amount'] or 0),
                    'source':   'BankTransactions',
                    'category': row['Category'] or '',
                })

        results.sort(key=lambda x: x['date'] or '', reverse=True)
        return results
    finally:
        conn.close()


# ── PDF generation ─────────────────────────────────────────────────────────────

def _heb(text) -> str:
    """Apply bidi algorithm for correct visual RTL ordering in PDF."""
    try:
        from bidi.algorithm import get_display
        return get_display(str(text))
    except Exception:
        return str(text)


def _register_font() -> str:
    """Register a Unicode font supporting Hebrew. Returns font name."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    candidates = [
        r'C:\Windows\Fonts\arial.ttf',
        r'C:\Windows\Fonts\ARIAL.TTF',
        '/usr/share/fonts/truetype/msttcorefonts/Arial.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    ]
    for fp in candidates:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont('HebFont', fp))
                return 'HebFont'
            except Exception:
                pass
    return 'Helvetica'


def generate_pdf_report(member_ids: list, db) -> bytes:
    """
    Generate a PDF report for the given member IDs.
    member_ids: list of int member IDs. Pass [] for all paying members.
    Returns bytes of the PDF.
    """
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm

    font = _register_font()

    members  = db.get_spotify_members()
    charges  = db.get_spotify_charges()
    payments = db.get_spotify_payments()

    paying = [m for m in members if not m['is_exempt'] and m['is_active']]
    if member_ids:
        paying = [m for m in paying if m['id'] in member_ids]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    title_style = ParagraphStyle('title', fontName=font, fontSize=16, spaceAfter=6)
    sub_style   = ParagraphStyle('sub',   fontName=font, fontSize=10, spaceAfter=12, textColor=colors.grey)
    head_style  = ParagraphStyle('head',  fontName=font, fontSize=12, spaceAfter=6, spaceBefore=14)

    from datetime import date
    story = [
        Paragraph(_heb('Spotify Family Tracker — Report'), title_style),
        Paragraph(_heb(f'Generated: {date.today().strftime("%d/%m/%Y")}'), sub_style),
    ]

    teal = colors.HexColor('#1e9d8b')

    story.append(Paragraph(_heb('Balance Summary'), head_style))
    summary_data = [[_heb('Member'), _heb('Total Paid'), _heb('Balance'), _heb('Status')]]
    for m in paying:
        m_payments = [p for p in payments if p['member_id'] == m['id']]
        bal = compute_balance(m_payments, charges)
        status_str = {
            'owes':  f"Owes {chr(8362)}{abs(bal['balance']):.2f} ({abs(bal['months_status'])} mo.)",
            'even':  'Even',
            'ahead': f"Ahead {chr(8362)}{bal['balance']:.2f} ({bal['months_status']} mo.)",
        }[bal['status']]
        total_paid = sum(p['amount'] for p in m_payments)
        summary_data.append([
            _heb(m['name']),
            f"{chr(8362)}{total_paid:.2f}",
            f"{chr(8362)}{bal['balance']:+.2f}",
            _heb(status_str),
        ])

    summary_table = Table(summary_data, colWidths=[5*cm, 3.5*cm, 3.5*cm, 5*cm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), teal),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,-1), font),
        ('FONTSIZE',   (0,0), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f4f6f9')]),
        ('GRID',       (0,0), (-1,-1), 0.5, colors.HexColor('#eef0f6')),
        ('ALIGN',      (0,0), (-1,-1), 'CENTER'),
        ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(summary_table)

    for m in paying:
        m_payments = [p for p in payments if p['member_id'] == m['id']]
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph(_heb(f'Payment History — {m["name"]}'), head_style))

        pdata = [[_heb('Date'), _heb('Amount'), _heb('Note')]]
        for p in sorted(m_payments, key=lambda x: x['payment_date'] or '', reverse=True):
            pdata.append([
                p['payment_date'] or '—',
                f"{chr(8362)}{p['amount']:.2f}",
                _heb(p['note'] or ''),
            ])
        if len(pdata) == 1:
            pdata.append([_heb('No payments recorded'), '', ''])

        ptable = Table(pdata, colWidths=[4*cm, 4*cm, 9*cm])
        ptable.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), teal),
            ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
            ('FONTNAME',   (0,0), (-1,-1), font),
            ('FONTSIZE',   (0,0), (-1,-1), 9),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f4f6f9')]),
            ('GRID',       (0,0), (-1,-1), 0.5, colors.HexColor('#eef0f6')),
            ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(ptable)

    doc.build(story)
    return buf.getvalue()
