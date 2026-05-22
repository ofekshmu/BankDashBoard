"""
mortgage.py — Amortization engine for שלום שבזי 7 apartment.
Bank document date: 13/07/2025 | Loan: 712,500 ₪ | Duration: 30 years

Tracks (from official bank breakdown):
  Part 7  — קבועה לא צמודה     128,500 ₪  @ 4.80%  →  674.19 ₪/mo
  Part 10 — קבועה לא צמודה     113,500 ₪  @ 4.80%  →  595.50 ₪/mo
  Part 8  — משתנה לא צמודה אג״ח 285,000 ₪  @ 4.53%  → 1,449.14 ₪/mo
  Part 9  — משתנה פריים         185,500 ₪  @ 5.40%  → 1,053.66 ₪/mo
"""
from datetime import date
from dateutil.relativedelta import relativedelta
import pandas as pd

# ─── Property & loan constants ────────────────────────────────────────────────
APARTMENT_PRICE   = 950_000
MORTGAGE_AMOUNT   = 712_500
DOWN_PAYMENT      = APARTMENT_PRICE - MORTGAGE_AMOUNT   # 237,500 ₪
RENTAL_INCOME_PM  = 2_800        # monthly rental income (שלום שבזי 7 earnings)
MORTGAGE_CATEGORY = "שלום שבאזי 7"

MORTGAGE_START = date(2025, 7, 13)
FIRST_PAYMENT  = date(2025, 8,  1)
TERM_MONTHS    = 360              # 30 years

# ─── Track definitions ────────────────────────────────────────────────────────
TRACKS = [
    {"id": 7,  "name": "קבועה (7)",    "principal": 128_500, "annual_rate": 4.80, "monthly_payment": 674.19,   "type": "fixed"},
    {"id": 10, "name": "קבועה (10)",   "principal": 113_500, "annual_rate": 4.80, "monthly_payment": 595.50,   "type": "fixed"},
    {"id": 8,  "name": 'אג"ח (8)',     "principal": 285_000, "annual_rate": 4.53, "monthly_payment": 1449.14,  "type": "variable"},
    {"id": 9,  "name": "פריים (9)",    "principal": 185_500, "annual_rate": 5.40, "monthly_payment": 1053.66,  "type": "prime"},
]

TOTAL_MONTHLY_PAYMENT = round(sum(t["monthly_payment"] for t in TRACKS), 2)   # 3,772.49 ₪
NET_MONTHLY_COST      = round(TOTAL_MONTHLY_PAYMENT - RENTAL_INCOME_PM, 2)    #   972.49 ₪


# ─── Amortization helpers ─────────────────────────────────────────────────────

def _track_amortization(track: dict) -> pd.DataFrame:
    """Month-by-month amortization schedule for a single mortgage track."""
    monthly_rate   = track["annual_rate"] / 100 / 12
    balance        = float(track["principal"])
    pmt            = track["monthly_payment"]
    rows: list     = []
    d              = FIRST_PAYMENT

    for _ in range(TERM_MONTHS):
        interest       = balance * monthly_rate
        principal_paid = pmt - interest
        balance        = max(balance - principal_paid, 0.0)
        rows.append({
            "month":          d,
            "payment":        round(pmt, 2),
            "interest":       round(interest, 2),
            "principal_paid": round(principal_paid, 2),
            "balance":        round(balance, 2),
            "track":          track["name"],
            "track_type":     track["type"],
        })
        d = d + relativedelta(months=1)
        if balance < 0.01:
            break

    return pd.DataFrame(rows)


def full_schedule() -> tuple:
    """
    Compute full 30-year amortization across all tracks.

    Returns:
        monthly_totals (DataFrame) — one aggregated row per month
        per_track      (DataFrame) — long format, one row per (track × month)
    """
    frames    = [_track_amortization(t) for t in TRACKS]
    per_track = pd.concat(frames, ignore_index=True)

    monthly_totals = (
        per_track.groupby("month")
        .agg(
            total_payment   =("payment",        "sum"),
            total_interest  =("interest",       "sum"),
            total_principal =("principal_paid", "sum"),
            total_balance   =("balance",        "sum"),
        )
        .reset_index()
    )
    return monthly_totals, per_track


def months_elapsed_and_balance(monthly_totals: pd.DataFrame, today: date) -> tuple:
    """Return (months_elapsed, current_balance) as of *today*."""
    paid = monthly_totals[
        monthly_totals["month"].apply(
            lambda d: d.date() if hasattr(d, "date") else d
        ) <= today
    ]
    if paid.empty:
        return 0, float(MORTGAGE_AMOUNT)
    last = paid.iloc[-1]
    return len(paid), float(last["total_balance"])


def actual_payments() -> pd.DataFrame:
    """
    Query real mortgage payments from DB (name contains 'משכנתא', category שלום שבזי 7).
    Returns DataFrame with columns: month (date, first of month), total_paid (₪).
    """
    from database import DataBase
    raw = DataBase().get_mortgage_payments(MORTGAGE_CATEGORY, "משכנתא")
    if raw.empty:
        return pd.DataFrame(columns=["month", "total_paid"])

    raw["Date"] = pd.to_datetime(raw["Date"])
    raw["month"] = raw["Date"].apply(lambda d: d.replace(day=1).date())
    return (
        raw.groupby("month")["Amount"]
        .sum()
        .reset_index()
        .rename(columns={"Amount": "total_paid"})
    )


def actual_rental_income() -> pd.DataFrame:
    """
    Query real rental income from DB (Income > 0 in שלום שבזי 7 category).
    Returns DataFrame with columns: month (date, first of month), total_income (₪).
    """
    from database import DataBase
    raw = DataBase().get_housing_income(MORTGAGE_CATEGORY)
    if raw.empty:
        return pd.DataFrame(columns=["month", "total_income"])
    raw["Date"] = pd.to_datetime(raw["Date"])
    raw["month"] = raw["Date"].apply(lambda d: d.replace(day=1).date())
    raw = raw[raw.apply(lambda r: _is_rent(r.get("Name", ""), r["Income"]), axis=1)]
    return (
        raw.groupby("month")["Income"]
        .sum()
        .reset_index()
        .rename(columns={"Income": "total_income"})
    )


INITIAL_APARTMENT_PAYMENT = 237_500   # ₪ — initial apartment down payment

RENT_MIN = 2_400   # ₪ — minimum single payment considered as rent
RENT_MAX = 3_200   # ₪ — maximum single payment considered as rent
RENT_NAME_KEYWORDS = ["ספיאשוילי"]   # name-based rent identifiers (any match → rent)


def _is_rent(name: str, amount: float) -> bool:
    """Return True if a transaction is a rent payment (by amount range OR by name)."""
    if name and any(kw in name for kw in RENT_NAME_KEYWORDS):
        return True
    return bool(amount and RENT_MIN <= amount <= RENT_MAX)


def current_month_data(year: int, month: int) -> dict:
    """
    Return actual housing data for a specific month:
      payment       – actual mortgage payment (sum of Name∋'משכנתא', Out)
      rental        – actual rent received (single income in RENT_MIN–RENT_MAX range)
      rent_found    – bool, False triggers an alert in the dashboard
      net           – payment - rental (positive = out of pocket)
      month_out     – total spending (Out) in the category this month
      month_income  – total income in the category this month
    """
    from database import DataBase
    import calendar

    last_day = calendar.monthrange(year, month)[1]
    d1 = f"{year}-{month:02d}-01 00:00:00"
    d2 = f"{year}-{month:02d}-{last_day:02d} 23:59:59"

    rows = DataBase().cursor.execute("""
        SELECT Name, Out, Income
        FROM BankTransactions
        WHERE Category = ?
          AND Date >= ?
          AND Date <= ?
    """, (MORTGAGE_CATEGORY, d1, d2)).fetchall()

    payment      = sum(r[1] for r in rows if r[1] and "משכנתא" in (r[0] or ""))
    # Rent: by amount range OR by known renter name
    rental       = sum(r[2] for r in rows if r[2] and _is_rent(r[0] or "", r[2]))
    found        = rental > 0
    month_out    = sum(r[1] for r in rows if r[1] and r[1] > 0)
    month_income = sum(r[2] for r in rows if r[2] and r[2] > 0)

    return {
        "payment":      round(payment,      2),
        "rental":       round(rental,       2),
        "rent_found":   found,
        "net":          round(payment - rental, 2),
        "month_out":    round(month_out,    2),
        "month_income": round(month_income, 2),
    }


def alltime_category_data() -> dict:
    """
    Return all-time totals for the housing category:
      alltime_out    – total spending (Out > 0) across all time
      alltime_income – total income (Income > 0) across all time
      alltime_net    – income − spending (negative = net cost to date)
    """
    from database import DataBase
    db = DataBase()

    out_df = db.get_housing_spending(MORTGAGE_CATEGORY)
    inc_df = db.get_housing_income(MORTGAGE_CATEGORY)

    total_out    = float(out_df["Out"].sum())    if not out_df.empty    else 0.0
    total_income = float(inc_df["Income"].sum()) if not inc_df.empty    else 0.0

    return {
        "alltime_out":    round(total_out,              2),
        "alltime_income": round(total_income,           2),
        "alltime_net":    round(total_income - total_out, 2),
    }


def milestone_schedule(monthly_totals: pd.DataFrame) -> list:
    """
    Return list of dicts: when the total balance crosses each threshold.
    Each dict: {threshold, date, balance, years_from_start}
    """
    thresholds = [700_000, 600_000, 500_000, 400_000, 300_000, 200_000, 100_000, 0]
    result = []
    for thr in thresholds:
        below = monthly_totals[monthly_totals["total_balance"] <= thr]
        if not below.empty:
            row = below.iloc[0]
            d   = row["month"]
            if hasattr(d, "date"):
                d = d.date()
            years = round((d - FIRST_PAYMENT).days / 365.25, 1)
            result.append({
                "threshold":        thr,
                "date":             d,
                "balance":          round(float(row["total_balance"]), 0),
                "years_from_start": years,
            })
    return result
