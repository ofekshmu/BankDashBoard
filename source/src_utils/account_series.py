"""The balance history of one account, as the accounts page and the totals read it.

Pure helpers (no database, no pandas required): the history is a list of (date, value) points.
"""


def collapse_same_day(points):
    """One point per date: when an account was given several balances on the same day, the one entered
    last is its balance that day (a correction replaces the earlier entry).

    `points` are (date, value) in the order they were entered (the database orders them by date, then
    entry ID); the result is sorted by date, oldest first. Without this a same-day correction could lose
    to the older entry — "set it to 0" would leave the old balance showing."""
    latest = {}
    for day, value in points:
        latest[day] = value            # a later entry of the same day overwrites the earlier one
    return sorted(latest.items(), key=lambda p: p[0])


def latest_value(points):
    """The balance at the latest date of `points` ([date, value] pairs, any order), or None when empty.
    Among points of the same date the last one listed wins (consistent with collapse_same_day)."""
    best = None
    for point in points or []:
        if best is None or point[0] >= best[0]:
            best = point
    return None if best is None else float(best[1] or 0)
