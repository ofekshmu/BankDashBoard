"""
Spotify Family Plan Tracker — business logic and PDF generation.
"""
import math
import io
import os

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

def get_charge_suggestions(db) -> list:
    """
    Find outgoing transactions whose Name contains 'spotify' (case-insensitive)
    from both BankTransactions and CardTransactions, excluding months that already
    have a confirmed SpotifyMonthlyCharge.
    db: DataBase instance (already initialised, tables ensured).
    Returns list of {tx_id, date, name, amount, month, source}.
    """
    confirmed_months = {
        r[0] for r in db.cursor.execute(
            "SELECT Month FROM SpotifyMonthlyCharge WHERE Confirmed = 1"
        ).fetchall()
    }

    candidates = []

    # r: (ID[0], Date[1], Name[2], out[3])
    for row in db.cursor.execute("""
        SELECT ID, Date, Name, out
        FROM BankTransactions
        WHERE LOWER(Name) LIKE %s AND out > 0
        ORDER BY Date DESC LIMIT 24
    """, ('%spotify%',)).fetchall():
        month = str(row[1] or '')[:7]
        if month and month not in confirmed_months:
            candidates.append({
                'tx_id':  row[0],
                'date':   str(row[1]) if row[1] else None,
                'name':   row[2],
                'amount': float(row[3] or 0),
                'month':  month,
                'source': 'BankTransactions',
            })

    # r: (ID[0], Executed_Date[1], Name[2], Charge_Value[3])
    for row in db.cursor.execute("""
        SELECT ID, Executed_Date, Name, Charge_Value
        FROM CardTransactions
        WHERE LOWER(Name) LIKE %s AND Charge_Value > 0
        ORDER BY Executed_Date DESC LIMIT 24
    """, ('%spotify%',)).fetchall():
        month = str(row[1] or '')[:7]
        if month and month not in confirmed_months:
            candidates.append({
                'tx_id':  row[0],
                'date':   str(row[1]) if row[1] else None,
                'name':   row[2],
                'amount': float(row[3] or 0),
                'month':  month,
                'source': 'CardTransactions',
            })

    by_month = {}
    for c in candidates:
        m = c['month']
        if m not in by_month or c['amount'] > by_month[m]['amount']:
            by_month[m] = c

    return sorted(by_month.values(), key=lambda x: x['month'], reverse=True)


def get_unmatched_payments(db) -> list:
    """
    Return income transactions that look like Spotify family-member reimbursements
    and have not yet been assigned to any SpotifyMemberPayment.

    A transaction that has been split is now represented by its split parts, so
    the original row is never recommended directly. Each split part is offered
    as its own candidate instead, whenever the part itself (or the original
    transaction it came from) looks Spotify-related.
    db: DataBase instance (already initialised, tables ensured).
    """
    assigned = {
        r[0] for r in db.cursor.execute(
            "SELECT TX_ID FROM SpotifyMemberPayments WHERE TX_ID IS NOT NULL"
        ).fetchall()
    }
    dismissed = {
        r[0] for r in db.cursor.execute(
            "SELECT TX_ID FROM SpotifyDismissedPayments"
        ).fetchall()
    }
    excluded = assigned | dismissed

    # split_parents: {Original_ID -> [ {split_id, amount, description, category}, ... ]}
    split_parents = {}
    for row in db.cursor.execute("""
        SELECT ID, Original_ID, Amount, Description, Category
        FROM TransactionSplits
        WHERE Original_Table = 'BankTransactions'
    """).fetchall():
        split_parents.setdefault(row[1], []).append({
            'split_id':    row[0],
            'amount':      float(row[2] or 0),
            'description': row[3] or '',
            'category':    row[4] or '',
        })

    # r: (ID[0], Date[1], Name[2], Income[3], Description[4], Category[5])
    orig_rows = {}
    for row in db.cursor.execute("""
        SELECT ID, Date, Name, Income, Description, Category
        FROM BankTransactions
        WHERE Income > 0
          AND (
            LOWER(Name)        LIKE %s
            OR LOWER(Description) LIKE %s
            OR LOWER(Category)    LIKE %s
          )
        ORDER BY Date DESC LIMIT 200
    """, ('%spotify%', '%spotify%', '%spotify%')).fetchall():
        orig_rows[row[0]] = row

    # A split original might not itself mention "spotify" (e.g. a generic bank
    # transfer that was later split and one part tagged/described as Spotify),
    # so fetch those too — they still need to be evaluated part-by-part below.
    for orig_id in split_parents:
        if orig_id not in orig_rows:
            row = db.cursor.execute("""
                SELECT ID, Date, Name, Income, Description, Category
                FROM BankTransactions WHERE ID = %s
            """, (orig_id,)).fetchone()
            if row and float(row[3] or 0) > 0:
                orig_rows[orig_id] = row

    results = []
    for tx_id, row in orig_rows.items():
        _, date, name, income, description, category = row
        splits = split_parents.get(tx_id)
        if splits:
            parent_matches = any(
                'spotify' in (v or '').lower() for v in (name, description, category)
            )
            for s in splits:
                if s['split_id'] in excluded:
                    continue
                child_matches = (
                    'spotify' in s['description'].lower() or 'spotify' in s['category'].lower()
                )
                if not (parent_matches or child_matches):
                    continue
                results.append({
                    'id':          s['split_id'],
                    'date':        str(date) if date else None,
                    'name':        name,
                    'amount':      s['amount'],
                    'description': s['description'] or description or '',
                    'source':      'split',
                    'category':    s['category'] or category or '',
                })
            continue
        if tx_id not in excluded:
            results.append({
                'id':          tx_id,
                'date':        str(date) if date else None,
                'name':        name,
                'amount':      float(income or 0),
                'description': description or '',
                'source':      'BankTransactions',
                'category':    category or '',
            })

    results.sort(key=lambda x: x['date'] or '', reverse=True)
    return results


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
