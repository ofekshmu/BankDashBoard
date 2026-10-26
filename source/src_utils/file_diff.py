"""Comparing a freshly uploaded credit-card file with the rows already stored for the same file.

Pure functions, no database and no Excel: both sides are lists of *records* — dicts with the
CardTransactions columns `name, executed_date, charge_date, charge_value, charge_currency,
transaction_value, value_currency, extra_info` (the stored ones also carry `id`, `category`, ...).
The new file's records come from `Card.records()` (the very mapping used to insert them), so both
sides are comparable field by field.

A new row matches a stored row when every compared field is equal. Rows that differ only in
amounts/dates but carry the same voucher serial ("Serial: 241496564" in extra_info) are *changed*:
the same purchase, corrected by the card company. What is left is *added* (only in the new file)
or *removed* (only in the stored file).
"""
import re
from collections import defaultdict, deque
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

COMPARED = ('name', 'executed_date', 'charge_date', 'charge_value', 'charge_currency',
            'transaction_value', 'value_currency', 'extra_info')

STATUS_IDENTICAL = 'identical'            # same rows
STATUS_NEW = 'new_transactions'           # the new file has rows the stored one lacks, nothing else differs
STATUS_MISSING = 'missing_rows'           # rows stored for the file are absent from the new one: an anomaly to investigate
STATUS_OTHER = 'other'                    # changed rows only, or not the same card / month / format

_SERIAL = re.compile(r'Serial:\s*(\S+)')


def norm_amount(value):
    """The amount as the database stores it: an integer, rounded half away from zero (None stays None)."""
    if value is None or value == '':
        return None
    try:
        return int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except Exception:
        return str(value).strip()


def norm_date(value):
    """ISO date text for dates/datetimes; other values (e.g. 'End of month') as stripped text."""
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def norm_text(value):
    """Text with runs of whitespace collapsed; None is ''."""
    return ' '.join(str(value).split()) if value is not None else ''


def normalize(rec):
    """The comparable form of a record: a dict with exactly the COMPARED fields, normalized."""
    return {
        'name': norm_text(rec.get('name')),
        'executed_date': norm_date(rec.get('executed_date')),
        'charge_date': norm_date(rec.get('charge_date')),
        'charge_value': norm_amount(rec.get('charge_value')),
        'charge_currency': norm_text(rec.get('charge_currency')),
        'transaction_value': norm_amount(rec.get('transaction_value')),
        'value_currency': norm_text(rec.get('value_currency')),
        'extra_info': norm_text(rec.get('extra_info')),
    }


def _key(norm):
    return tuple(norm[f] for f in COMPARED)


def serial_of(rec):
    """The voucher serial found in extra_info, or None."""
    m = _SERIAL.search(norm_text(rec.get('extra_info')))
    return m.group(1) if m and m.group(1) not in ('None', 'nan') else None


class Diff:
    """Result of compare(). Indexes refer to the lists given to compare().
    matched: [(stored_i, new_i)]            identical rows
    changed: [(stored_i, new_i, [fields])]  same voucher serial, other fields differ
    added:   [new_i]                        only in the new file
    removed: [stored_i]                     only in the stored file
    moved:   how many matched/changed rows are in a different relative order than in the stored file
    """

    def __init__(self, matched, changed, added, removed, moved):
        self.matched, self.changed, self.added, self.removed, self.moved = matched, changed, added, removed, moved

    def counts(self):
        return {'same': len(self.matched), 'changed': len(self.changed), 'added': len(self.added),
                'removed': len(self.removed), 'moved': self.moved}


def _longest_increasing(seq):
    """Length of the longest strictly increasing subsequence (patience sorting)."""
    import bisect
    tails = []
    for x in seq:
        i = bisect.bisect_left(tails, x)
        if i == len(tails):
            tails.append(x)
        else:
            tails[i] = x
    return len(tails)


def compare(stored, new):
    """Match `new` records against the `stored` ones (see the module docstring)."""
    s_norm = [normalize(r) for r in stored]
    n_norm = [normalize(r) for r in new]

    by_key = defaultdict(deque)
    for i, n in enumerate(s_norm):
        by_key[_key(n)].append(i)

    matched, unmatched_new = [], []
    used_stored = set()
    for j, n in enumerate(n_norm):
        q = by_key.get(_key(n))
        if q:
            i = q.popleft()
            used_stored.add(i)
            matched.append((i, j))
        else:
            unmatched_new.append(j)

    # same purchase (voucher serial), other values: changed
    by_serial = defaultdict(deque)
    for i, r in enumerate(stored):
        if i not in used_stored and serial_of(r):
            by_serial[serial_of(r)].append(i)
    changed, added = [], []
    for j in unmatched_new:
        sn = serial_of(new[j])
        q = by_serial.get(sn) if sn else None
        if q:
            i = q.popleft()
            used_stored.add(i)
            fields = [f for f in COMPARED if s_norm[i][f] != n_norm[j][f]]
            changed.append((i, j, fields))
        else:
            added.append(j)
    removed = [i for i in range(len(stored)) if i not in used_stored]

    pairs = sorted([(j, i) for i, j in matched] + [(j, i) for i, j, _ in changed])
    moved = len(pairs) - _longest_increasing([i for _, i in pairs])
    return Diff(sorted(matched, key=lambda p: p[1]), sorted(changed, key=lambda p: p[1]), added, removed, moved)


def classify(diff, identity_ok=True):
    """One of the STATUS_* values for the comparison.

    A stored row that is missing from the new file is never expected (a newer download only ever adds
    rows), so it gets its own status whatever else differs — unless the file is not the same card / month
    / format at all, which is reported as `other` since then everything is "missing"."""
    if not identity_ok:
        return STATUS_OTHER
    a, r, c = len(diff.added), len(diff.removed), len(diff.changed)
    if r:
        return STATUS_MISSING
    if not (a or c):
        return STATUS_IDENTICAL
    if a and not c:
        return STATUS_NEW
    return STATUS_OTHER


STRUCTURE_LABELS = (
    ('format', 'פורמט הקובץ'),
    ('card', 'מספר כרטיס'),
    ('charge_month', 'חודש החיוב'),
    ('header_row', 'שורת הכותרות'),
    ('first_col', 'עמודת התחלה'),
    ('columns', 'מספר עמודות'),
    ('headers', 'כותרות העמודות'),
    ('rows', 'שורות בטבלה'),
    ('tables', 'מספר טבלאות'),
)


def structure_diff(old, new):
    """Differences in layout between the stored file and the new one.

    `old` / `new` are dicts using any of the STRUCTURE_LABELS keys (a missing key on either side is
    skipped — e.g. the stored file's headers are unknown when its copy is gone). Returns
    [{'field', 'label', 'old', 'new', 'changed'}] for every key both sides know, in display order.
    """
    out = []
    for field, label in STRUCTURE_LABELS:
        if field not in old or field not in new:
            continue
        o, n = old[field], new[field]
        out.append({'field': field, 'label': label, 'old': o, 'new': n, 'changed': o != n})
    return out


# ── helpers for investigating rows that are missing from the new file ──────
def date_range(records, field='executed_date'):
    """(first, last) ISO date of the records' `field`, or None when none has a date."""
    days = sorted(d for d in (norm_date(r.get(field)) for r in records) if re.match(r'\d{4}-\d{2}-\d{2}$', d))
    return (days[0], days[-1]) if days else None


def total(records, field='charge_value'):
    """Sum of the records' normalised (integer) `field`."""
    return sum(v for v in (norm_amount(r.get(field)) for r in records) if isinstance(v, int))


def position_shape(indexes, count):
    """Where `indexes` (0-based positions of some rows among `count`) sit: 'none', 'all', 'tail' (the last
    rows), 'head' (the first rows), 'block' (a run in the middle) or 'scattered'."""
    idx = sorted(indexes)
    if not idx:
        return 'none'
    if len(idx) == count:
        return 'all'
    if idx != list(range(idx[0], idx[-1] + 1)):
        return 'scattered'
    if idx[-1] == count - 1:
        return 'tail'
    if idx[0] == 0:
        return 'head'
    return 'block'


def similar_candidates(rec, candidates, limit=3):
    """The rows of `candidates` ([(index, record)]) that look like the same purchase as `rec` recorded
    differently. Each result is {'index', 'same': [...], 'differs': [...]} over the fields name, date, amount;
    a candidate needs two of the three to match. Best first."""
    n = normalize(rec)
    out = []
    for idx, cand in candidates:
        c = normalize(cand)
        same = [f for f, ok in (('name', n['name'] == c['name']), ('date', n['executed_date'] == c['executed_date']),
                                ('amount', n['charge_value'] == c['charge_value'])) if ok]
        if len(same) >= 2:
            out.append({'index': idx, 'same': same, 'differs': [f for f in ('name', 'date', 'amount') if f not in same]})
    out.sort(key=lambda r: (-len(r['same']), r['index']))
    return out[:limit]
