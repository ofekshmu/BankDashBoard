"""
AlertsConfig.py — Configuration for the Smart Alerts System
============================================================

Purpose:
    Central configuration for all thresholds and toggles used by the
    SmartAlerts AlertDetector.  Adjust values here to tune sensitivity
    without touching detection logic.

Usage:
    from Configurations.AlertsConfig import ALERTS_CONFIG
    detector = AlertDetector(..., config=ALERTS_CONFIG)

All monetary values are in ILS (₪).
"""

ALERTS_CONFIG: dict = {

    # ------------------------------------------------------------------
    # Price change on a recurring transaction
    # Fires when a known recurring merchant is charged noticeably more
    # or less than their historical average.
    # ------------------------------------------------------------------
    "price_change_threshold_pct": 20,   # % deviation from historical mean
    "price_change_min_abs":        30,  # Minimum absolute ₪ change to care about
                                        # (avoids noise on very small charges)
    "price_change_max_cv":       0.30,  # Maximum coefficient of variation (std/mean)
                                        # allowed for a merchant to qualify.
                                        # Merchants like Wolt/food delivery have high CV
                                        # because order amounts vary naturally — skip them.
                                        # Subscriptions/bills have CV ≈ 0 — flag them.

    # ------------------------------------------------------------------
    # Missing recurring charge
    # Fires when a merchant that appeared every month for the last N
    # months is absent from the current month.
    # ------------------------------------------------------------------
    "recurring_lookback_months": 3,     # Consecutive months required to qualify
                                        # as "recurring"

    # ------------------------------------------------------------------
    # New potential subscription
    # Fires when a first-time merchant charge looks subscription-like
    # (small or round amount, not seen in recent history).
    # ------------------------------------------------------------------
    "new_sub_max_amount": 300,          # Max ₪ amount to consider subscription-like

    # ------------------------------------------------------------------
    # Duplicate charge detection
    # Fires when the same merchant appears ≥ 2 times in one month with
    # nearly identical amounts.
    # ------------------------------------------------------------------
    "duplicate_amount_tolerance": 5,    # ₪ difference still counts as duplicate

    # ------------------------------------------------------------------
    # Category spending spike
    # Fires when a category's monthly total is well above its average.
    # ------------------------------------------------------------------
    "category_spike_multiplier": 1.5,   # Current must exceed mean × this value
    "category_spike_min_abs":    200,   # Minimum ₪ excess over mean

    # ------------------------------------------------------------------
    # Unusually large single transaction
    # Fires when a single charge is much larger than that merchant's
    # historical per-transaction average.
    # ------------------------------------------------------------------
    "large_tx_std_mult": 2.0,           # Standard deviations above mean
    "large_tx_min_abs":  100,           # Minimum ₪ excess over mean

    # ------------------------------------------------------------------
    # High spending month (overall)
    # Fires when total monthly spending (excl. investments) is
    # significantly above the historical average.
    # ------------------------------------------------------------------
    "high_spend_threshold_pct": 25,     # % above historical mean

    # ------------------------------------------------------------------
    # Consecutive spending trend
    # Fires when spending has increased month-over-month for N months.
    # ------------------------------------------------------------------
    "trend_months": 3,                  # Consecutive months of increase required

    # ------------------------------------------------------------------
    # Toggle individual alert types on/off
    # Set any value to False to suppress that alert type entirely.
    # ------------------------------------------------------------------
    "enabled": {
        "price_change":      True,
        "missing_recurring": True,
        "new_subscription":  True,
        "duplicate_charge":  True,
        "category_spike":    True,
        "large_transaction": True,
        "high_spend_month":  True,
        "spending_trend":    True,
    },
}
