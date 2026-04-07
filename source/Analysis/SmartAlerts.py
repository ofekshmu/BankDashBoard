"""
SmartAlerts.py — Smart Alert Detection for Monthly Financial Analysis
======================================================================

Purpose:
    Analyses the current month's transaction data against historical data
    to surface notable financial events — price changes, missing charges,
    spending spikes, duplicates, and more.  The results are passed to
    generate_html() and rendered as a coloured alert section at the top
    of the monthly HTML dashboard.

Usage:
    from Analysis.SmartAlerts import AlertDetector
    from Configurations.AlertsConfig import ALERTS_CONFIG

    detector = AlertDetector(
        current_df=transactions_df,    # current month, processed
        history_dfs=history_dfs,       # [1-month-ago df, 2-months-ago df, ...]
        config=ALERTS_CONFIG,
    )
    alerts = detector.detect_all()     # returns list[Alert], critical-first

Alert Types:
    price_change      — Recurring merchant charged ≠ their usual amount
    missing_recurring — Expected monthly merchant absent this month
    new_subscription  — First-time charge that looks like a subscription
    duplicate_charge  — Same merchant charged twice with same amount
    category_spike    — Category total well above its historical average
    large_transaction — Single charge much bigger than merchant's usual
    high_spend_month  — Overall spending significantly above average
    spending_trend    — Spending increased N months in a row

Severity levels:
    critical  → red    (#e74c3c)   — Requires attention
    warning   → orange (#f39c12)   — Worth reviewing
    info      → blue   (#3498db)   — Informational

Dependencies:
    numpy, pandas
    Constants (INVESTMENT_CATEGORY, CC_CHARGE_CATEGORY_NAME)
    Configurations.AlertsConfig (ALERTS_CONFIG)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

import numpy as np
import pandas as pd

from Constants import INVESTMENT_CATEGORY, CC_CHARGE_CATEGORY_NAME

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Alert:
    """
    Represents a single smart alert surfaced during monthly analysis.

    Attributes:
        alert_type:  Machine-readable type key (e.g. 'price_change').
        severity:    'critical' | 'warning' | 'info'
        title:       Short Hebrew label displayed in bold in the HTML.
        description: Full Hebrew description including ₪ amounts and percentages.
        merchant:    Related merchant/business name (empty string if N/A).
        category:    Related spending category (empty string if N/A).
        icon:        Emoji displayed on the alert card (set per alert type).
        color:       CSS hex color for the card border and background tint.
    """
    alert_type:  str
    severity:    str   # "critical" | "warning" | "info"
    title:       str
    description: str
    merchant:    str = field(default="")
    category:    str = field(default="")
    icon:        str = field(default="•")
    color:       str = field(default="#f0b429")  # amber/yellow — general default


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class AlertDetector:
    """
    Runs all configured alert detectors against the current month's data and
    returns a severity-sorted list of Alert objects.

    Constructor Args:
        current_df (pd.DataFrame):
            Processed transaction DataFrame for the month being analysed.
            Expected columns: Name, Final_Value, Category.
            Final_Value is positive for income, negative for spending.

        history_dfs (list[pd.DataFrame]):
            Ordered list of processed transaction DataFrames for past months.
            Index 0 = one month ago, index 1 = two months ago, etc.
            Built using the same SimpleMath.process_prices() pipeline as the
            current month.

        config (dict):
            Threshold and toggle configuration.  Use ALERTS_CONFIG from
            Configurations.AlertsConfig, or a custom dict with the same keys.

    Internal filtering:
        All detectors work on *spending* transactions only (Final_Value < 0)
        and exclude the investment and credit-card-charge categories since
        those fluctuate by design and would generate false positives.
    """

    # Categories whose transactions are excluded from alert analysis.
    # Investment amounts vary by design; credit-card-charge entries are internal.
    _SKIP_CATEGORIES: frozenset = frozenset({INVESTMENT_CATEGORY, CC_CHARGE_CATEGORY_NAME})

    def __init__(
        self,
        current_df:  pd.DataFrame,
        history_dfs: list[pd.DataFrame],
        config:      dict,
    ) -> None:
        self._current = current_df
        self._history = history_dfs
        self._cfg     = config

        # Pre-filter spending DataFrames (used by most detectors)
        self._current_spend  = self._filter_spending(current_df)
        self._history_spend  = [self._filter_spending(df) for df in history_dfs]

        logger.debug(
            f"[SmartAlerts] Initialised: {len(self._current_spend)} current spend transactions, "
            f"{len(history_dfs)} history month(s)"
        )

    # -----------------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------------

    def detect_all(self) -> List[Alert]:
        """
        Run all enabled alert detectors and return a sorted list of Alert objects.

        Returns:
            Alerts sorted by severity: critical → warning → info.
            Empty list if no anomalies detected or insufficient history.
        """
        enabled = self._cfg.get("enabled", {})
        alerts: List[Alert] = []

        runners = [
            ("price_change",      self._price_change),
            ("missing_recurring", self._missing_recurring),
            ("new_subscription",  self._new_subscription),
            ("duplicate_charge",  self._duplicate_charge),
            ("category_spike",    self._category_spike),
            ("large_transaction", self._large_transaction),
            ("high_spend_month",  self._high_spend_month),
            ("spending_trend",    self._spending_trend),
        ]

        for key, fn in runners:
            if enabled.get(key, True):
                try:
                    found = fn()
                    alerts.extend(found)
                    if found:
                        logger.debug(f"[SmartAlerts] '{key}' fired {len(found)} alert(s)")
                except Exception as exc:
                    # Never let an alert detector crash the analysis
                    logger.warning(f"[SmartAlerts] '{key}' detector raised an exception: {exc}")

        # Sort: critical first, then warning, then info
        _order = {"critical": 0, "warning": 1, "info": 2}
        alerts.sort(key=lambda a: _order.get(a.severity, 99))

        logger.info(f"[SmartAlerts] {len(alerts)} alert(s) generated for this month")
        return alerts

    # -----------------------------------------------------------------------
    # Detectors
    # -----------------------------------------------------------------------

    def _price_change(self) -> List[Alert]:
        """
        Detect recurring merchants whose charge amount changed significantly
        compared to their historical average.

        A merchant qualifies as "recurring" if they appear in at least 2 of
        the last N history months.  The current month's total charge for that
        merchant is compared to the historical mean.

        Returns:
            List of critical Alerts, one per affected merchant.
        """
        if len(self._history_spend) < 2:
            return []

        threshold_pct = self._cfg.get("price_change_threshold_pct", 20) / 100
        min_abs       = self._cfg.get("price_change_min_abs", 30)
        max_cv        = self._cfg.get("price_change_max_cv", 0.30)

        # Build {merchant_name: [monthly_total, ...]} from history.
        # Only months where the merchant appeared are included.
        merchant_history: dict[str, list[float]] = {}
        for hist_df in self._history_spend:
            for name, group in hist_df.groupby("Name"):
                merchant_history.setdefault(str(name), []).append(
                    abs(float(group["Final_Value"].sum()))
                )

        # Keep only merchants that appear in ≥ 2 history months
        merchant_history = {k: v for k, v in merchant_history.items() if len(v) >= 2}

        # Current month charge totals per merchant
        current_charges: dict[str, float] = {
            str(name): abs(float(group["Final_Value"].sum()))
            for name, group in self._current_spend.groupby("Name")
        }

        alerts: List[Alert] = []
        for name, current_total in current_charges.items():
            if name not in merchant_history:
                continue

            hist_vals   = merchant_history[name]
            hist_mean   = float(np.mean(hist_vals))
            hist_std    = float(np.std(hist_vals))

            if hist_mean == 0:
                continue

            # Skip naturally-variable merchants (food delivery, supermarkets, etc.)
            # whose charge amounts differ every month by design.
            # Coefficient of variation = std / mean:
            #   low CV (≈0) → consistent charger (subscription, phone bill) → alert
            #   high CV     → variable charger (Wolt, restaurants)          → skip
            cv = hist_std / hist_mean
            if cv > max_cv:
                logger.debug(
                    f"[SmartAlerts] price_change skipped '{name}': "
                    f"CV={cv:.2f} exceeds max_cv={max_cv}"
                )
                continue

            change_pct  = (current_total - hist_mean) / hist_mean
            abs_change  = abs(current_total - hist_mean)

            if abs(change_pct) >= threshold_pct and abs_change >= min_abs:
                sign     = "+" if change_pct > 0 else ""
                went_up  = change_pct > 0
                alerts.append(Alert(
                    alert_type  = "price_change",
                    severity    = "critical",
                    title       = f"{'עלייה' if went_up else 'ירידה'} בתשלום חודשי: {name}",
                    description = (
                        f"סה״כ חודשי: {current_total:.0f}₪ — "
                        f"ממוצע חודשים קודמים: {hist_mean:.0f}₪ "
                        f"({sign}{change_pct * 100:.0f}%)"
                    ),
                    merchant = name,
                    icon     = "⬆" if went_up else "⬇",
                    color    = "#e74c3c" if went_up else "#2ecc71",
                ))

        return alerts

    def _missing_recurring(self) -> List[Alert]:
        """
        Detect merchants that appeared every month for the last N consecutive
        months but are absent from the current month.

        Returns:
            List of critical Alerts, one per missing merchant.
        """
        lookback = self._cfg.get("recurring_lookback_months", 3)
        if len(self._history_spend) < lookback:
            return []

        lookback_dfs = self._history_spend[:lookback]

        # Merchants present in EVERY lookback month
        name_sets = [set(df["Name"].unique()) for df in lookback_dfs]
        recurring = name_sets[0].intersection(*name_sets[1:])

        # Remove merchants that do appear in the current month
        current_names = set(self._current_spend["Name"].unique())
        missing       = recurring - current_names

        alerts: List[Alert] = []
        for name in sorted(missing):
            hist_amounts = [
                abs(float(df[df["Name"] == name]["Final_Value"].sum()))
                for df in lookback_dfs
            ]
            avg_amt = float(np.mean(hist_amounts))
            alerts.append(Alert(
                alert_type  = "missing_recurring",
                severity    = "critical",
                title       = f"חיוב קבוע חסר: {name}",
                description = (
                    f"חויב בכל אחד מ-{lookback} החודשים האחרונים "
                    f"(ממוצע {avg_amt:.0f}₪) ולא נמצא החודש"
                ),
                merchant = name,
                icon     = "❓",
                color    = "#f0b429",
            ))

        return alerts

    def _new_subscription(self) -> List[Alert]:
        """
        Detect first-time merchant charges that look like a new subscription
        (small AND round amount not seen in any of the last N history months).
        Both conditions must hold to reduce false positives from one-time purchases.

        Returns:
            List of warning Alerts, one per suspected new subscription.
        """
        if not self._history_spend:
            return []

        max_amount = self._cfg.get("new_sub_max_amount", 300)

        # All merchant names seen in any history month
        hist_names: set[str] = set()
        for hist_df in self._history_spend:
            hist_names.update(str(n) for n in hist_df["Name"].unique())

        alerts: List[Alert] = []
        for name, group in self._current_spend.groupby("Name"):
            name = str(name)
            if name in hist_names:
                continue

            total     = abs(float(group["Final_Value"].sum()))
            is_small  = total <= max_amount
            is_round  = (total % 5 == 0)   # subscription prices are usually round numbers

            # Require BOTH conditions — reduces false positives from one-time
            # purchases that happen to be small or happen to be a round number.
            # A true subscription is typically a small AND round price (e.g. ₪25, ₪55).
            if is_small and is_round:
                alerts.append(Alert(
                    alert_type  = "new_subscription",
                    severity    = "warning",
                    title       = f"חיוב חדש: {name}",
                    description = (
                        f"חויב {total:.0f}₪ — לא נראה ב-{len(self._history_spend)} "
                        f"החודשים האחרונים. ייתכן שמדובר במנוי חדש"
                    ),
                    merchant = name,
                    icon     = "🆕",
                    color    = "#f0b429",
                ))

        return alerts

    def _duplicate_charge(self) -> List[Alert]:
        """
        Detect merchants charged twice (or more) in the same month with
        nearly identical amounts.

        Returns:
            List of critical Alerts, one per affected merchant.
        """
        tolerance = self._cfg.get("duplicate_amount_tolerance", 5)

        alerts: List[Alert] = []
        for name, group in self._current_spend.groupby("Name"):
            if len(group) < 2:
                continue

            amounts = sorted(abs(group["Final_Value"]).tolist())
            for i in range(len(amounts) - 1):
                if abs(amounts[i] - amounts[i + 1]) <= tolerance:
                    alerts.append(Alert(
                        alert_type  = "duplicate_charge",
                        severity    = "critical",
                        title       = f"חיוב כפול: {name}",
                        description = (
                            f"חויב פעמיים בסכומים דומים "
                            f"({amounts[i]:.0f}₪ ו-{amounts[i + 1]:.0f}₪) באותו חודש"
                        ),
                        merchant = str(name),
                        icon     = "⚡",
                        color    = "#f0b429",
                    ))
                    break  # one alert per merchant is enough

        return alerts

    def _category_spike(self) -> List[Alert]:
        """
        Detect spending categories whose total this month significantly
        exceeds their historical average.

        Returns:
            List of warning Alerts, one per spiking category.
        """
        if len(self._history_spend) < 2:
            return []

        multiplier = self._cfg.get("category_spike_multiplier", 1.5)
        min_abs    = self._cfg.get("category_spike_min_abs", 200)

        # Current month total per category
        current_cats: dict[str, float] = {
            str(cat): abs(float(group["Final_Value"].sum()))
            for cat, group in self._current_spend.groupby("Category")
        }

        # Historical totals per category across all history months
        hist_cat_totals: dict[str, list[float]] = {}
        for hist_df in self._history_spend:
            for cat, group in hist_df.groupby("Category"):
                hist_cat_totals.setdefault(str(cat), []).append(
                    abs(float(group["Final_Value"].sum()))
                )

        alerts: List[Alert] = []
        for cat, current_total in current_cats.items():
            hist_list = hist_cat_totals.get(cat, [])
            if len(hist_list) < 2:
                continue  # not enough history for this category

            hist_mean = float(np.mean(hist_list))
            if hist_mean == 0:
                continue

            excess = current_total - hist_mean
            if current_total > hist_mean * multiplier and excess >= min_abs:
                change_pct = excess / hist_mean * 100
                alerts.append(Alert(
                    alert_type  = "category_spike",
                    severity    = "warning",
                    title       = f"גידול בקטגוריה: {cat}",
                    description = (
                        f"הוצאות החודש: {current_total:.0f}₪ "
                        f"לעומת ממוצע של {hist_mean:.0f}₪ (+{change_pct:.0f}%)"
                    ),
                    category = cat,
                    icon     = "📊",
                    color    = "#f0b429",
                ))

        return alerts

    def _large_transaction(self) -> List[Alert]:
        """
        Detect individual transactions that are much larger than the
        merchant's historical per-transaction average.

        Returns:
            List of warning Alerts, one per affected merchant.
        """
        if len(self._history_spend) < 2:
            return []

        std_mult = self._cfg.get("large_tx_std_mult", 2.0)
        min_abs  = self._cfg.get("large_tx_min_abs", 100)

        # Gather all individual historical transaction amounts per merchant
        merchant_hist: dict[str, list[float]] = {}
        for hist_df in self._history_spend:
            for name, group in hist_df.groupby("Name"):
                merchant_hist.setdefault(str(name), []).extend(
                    abs(group["Final_Value"]).tolist()
                )

        # Keep only merchants with at least 2 historical data points
        merchant_hist = {k: v for k, v in merchant_hist.items() if len(v) >= 2}

        alerts: List[Alert] = []
        for name, group in self._current_spend.groupby("Name"):
            name = str(name)
            if name not in merchant_hist:
                continue

            hist_vals = merchant_hist[name]
            hist_mean = float(np.mean(hist_vals))
            hist_std  = float(np.std(hist_vals))
            threshold = hist_mean + std_mult * hist_std

            for _, row in group.iterrows():
                tx_amount = abs(float(row["Final_Value"]))
                if tx_amount > threshold and (tx_amount - hist_mean) >= min_abs:
                    alerts.append(Alert(
                        alert_type  = "large_transaction",
                        severity    = "warning",
                        title       = f"עסקה חריגה: {name}",
                        description = (
                            f"עסקה בודדת של {tx_amount:.0f}₪ — "
                            f"ממוצע עסקה רגילה: {hist_mean:.0f}₪ (±{hist_std:.0f}₪)"
                        ),
                        merchant = name,
                        icon     = "💰",
                        color    = "#e74c3c",
                    ))
                    break  # one alert per merchant

        return alerts

    def _high_spend_month(self) -> List[Alert]:
        """
        Detect whether overall spending this month (excluding investments)
        is significantly above the historical average.

        Returns:
            List with at most one info Alert.
        """
        if len(self._history_spend) < 2:
            return []

        threshold_pct = self._cfg.get("high_spend_threshold_pct", 25) / 100

        current_total = abs(float(self._current_spend["Final_Value"].sum()))
        hist_totals   = [abs(float(df["Final_Value"].sum())) for df in self._history_spend]
        hist_mean     = float(np.mean(hist_totals))

        if hist_mean == 0:
            return []

        change_pct = (current_total - hist_mean) / hist_mean
        if change_pct >= threshold_pct:
            return [Alert(
                alert_type  = "high_spend_month",
                severity    = "info",
                title       = "חודש הוצאות גבוה",
                description = (
                    f"הוצאות החודש: {current_total:.0f}₪ "
                    f"לעומת ממוצע של {hist_mean:.0f}₪ (+{change_pct * 100:.0f}%)"
                ),
                icon  = "📅",
                color = "#f0b429",
            )]

        return []

    def _spending_trend(self) -> List[Alert]:
        """
        Detect whether spending has increased month-over-month for N
        consecutive months.

        The check covers [current, 1-month-ago, 2-months-ago, ..., N-months-ago].
        A strictly increasing sequence (current > last month > ...) triggers the alert.

        Returns:
            List with at most one info Alert.
        """
        trend_months = self._cfg.get("trend_months", 3)
        if len(self._history_spend) < trend_months:
            return []

        # Build spending totals: index 0 = current, index 1 = 1 month ago, ...
        totals = [abs(float(self._current_spend["Final_Value"].sum()))] + [
            abs(float(df["Final_Value"].sum()))
            for df in self._history_spend[:trend_months]
        ]

        # "Increasing spending" means current > last month > two months ago > ...
        is_increasing = all(totals[i] > totals[i + 1] for i in range(trend_months))

        if is_increasing:
            # Show oldest → newest for readability
            values_str = " → ".join(f"{v:.0f}₪" for v in reversed(totals))
            return [Alert(
                alert_type  = "spending_trend",
                severity    = "info",
                title       = f"מגמת עלייה בהוצאות ({trend_months} חודשים)",
                description = f"ההוצאות עולות ברציפות: {values_str}",
                icon  = "📈",
                color = "#f0b429",
            )]

        return []

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _filter_spending(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Return a copy of df containing only spending transactions
        (Final_Value < 0) that do not belong to internal tracking categories.

        Args:
            df: Raw processed transaction DataFrame.

        Returns:
            Filtered DataFrame with spending rows only.
        """
        if df.empty:
            return df.copy()

        mask = df["Final_Value"] < 0
        if "Category" in df.columns:
            mask &= ~df["Category"].isin(self._SKIP_CATEGORIES)
        return df[mask].copy()
