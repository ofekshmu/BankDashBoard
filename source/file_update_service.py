"""Updating a stored credit-card file with a newer copy of the same statement.

A card statement downloaded before the charge date is partial; the full one has the same name (or the
same card and month). Without this module the new file is either refused (the name exists) or inserted
as a second copy of the month. Here the new file is compared with the rows stored for the old one:

  analyze()  read-only. Reads the new file (no database writes), matches its rows with the stored rows
             (src_utils/file_diff.py) and reports the status — identical / new_transactions / missing_rows /
             other — the rows that would be added or changed and the layout differences. A stored row
             that is absent from the new file is an anomaly (a newer download only ever adds rows), so it
             gets its own status and an `investigation` block with everything known about those rows.
  apply()    the user's decision:
               'update'   the stored rows keep their ID, category, description, splits and every link to
                          them; rows only in the new file are inserted; changed rows are corrected in place.
                          Refused while stored rows are missing from the new file.
               'replace'  everything stored for the old file is deleted and the new file is inserted as is.
             Then the old file's archived copy goes to the trash folder and the new file takes its place.

The Excel reading is injected (`reader`) so the logic is testable without Excel; `read_new_file` is the
production reader.
"""
import logging
import os
import shutil
from collections import namedtuple
from datetime import date, datetime

import src_utils.file_diff as fd

logger = logging.getLogger(__name__)

Folders = namedtuple('Folders', 'input verified trash')

STATUS_LABELS = {
    fd.STATUS_IDENTICAL: 'קובץ זהה',
    fd.STATUS_NEW: 'קובץ עם פעולות חדשות',
    fd.STATUS_MISSING: 'חסרות פעולות שקיימות במערכת — חריגה שדורשת תחקור',
    fd.STATUS_OTHER: 'אחר — סטטוס לא ברור',
}
PREVIEW_ROWS = 60           # rows listed per group in the report
NOT_CATEGORIZED = 'NotCategorized'


class UpdateError(Exception):
    """A request the user can fix; the message (Hebrew) is shown to them."""


class NothingToCompare(UpdateError):
    pass


# ── reading the new file ───────────────────────────────────────────────────
def read_new_file(name, fmt):
    """Read `name` (in the input folder) as format `fmt` without touching the database.
    Returns {name, format, card, date, records, meta, columns, tables}."""
    from Card import Card
    from Configurations.Formats import Context_class, Formats
    from src_utils.ExcelReader import ExcelManager

    fmt_data = Formats.FORMATS.get(fmt)
    if not fmt_data or fmt_data['Context'] != Context_class.Card:
        raise UpdateError('עדכון קובץ נתמך כרגע רק לקבצי אשראי')
    card = Card(name, fmt_data)
    try:
        if not card.read_for_compare():
            raise UpdateError('לא ניתן לקרוא את הקובץ (כותרות לא תקינות או קובץ נעול)')
        records = card.records()
    finally:
        try:
            ExcelManager().close_and_kill_excel()
        except Exception:
            pass
    return {'name': name, 'format': fmt, 'card': card.card_number, 'date': card.file_date, 'records': records,
            'meta': card.meta, 'columns': len(fmt_data['Headers']), 'tables': len(card.meta)}


def read_header_cells(path, header_row, first_col, max_cols=40):
    """The header cells of the table in `path` (row `header_row`, from column `first_col`), without trailing
    empty cells — the real width and titles of the file's table."""
    from src_utils.ExcelReader import ExcelManager
    try:
        cells = ExcelManager().set_active_sheet(path).read_sheet(header_row, 1, first_col, max_cols)
    finally:
        try:
            ExcelManager().close_and_kill_excel()
        except Exception:
            pass
    if cells and isinstance(cells[0], list):
        cells = cells[0]
    cells = [(str(c).strip() if c is not None else '') for c in cells]
    while cells and not cells[-1]:
        cells.pop()
    return cells


# ── helpers ────────────────────────────────────────────────────────────────
def _month(d):
    if isinstance(d, datetime):
        d = d.date()
    return (d.year, d.month) if isinstance(d, date) else None


def _month_text(d):
    m = _month(d)
    return f'{m[0]}-{m[1]:02d}' if m else ''


def has_work(row, links):
    """True when the user did something to this stored row: tagged, described, split or linked."""
    cat = (row.get('category') or '').strip()
    return bool((cat and cat != NOT_CATEGORIZED) or (row.get('description') or '').strip()
                or links.get(row['id']))


def _preview(rec, extra=None):
    out = {'name': fd.norm_text(rec.get('name')), 'date': fd.norm_date(rec.get('executed_date')),
           'amount': rec.get('charge_value') if rec.get('charge_value') is not None else rec.get('transaction_value')}
    if extra:
        out.update(extra)
    return out


def check_input_copy(name, fmt, folders):
    """How the file waiting in the input folder relates to the archived copy of the same name:
    'same' (identical bytes), 'different' (an updated download), 'missing' (no archived copy)."""
    src = os.path.join(folders.input, name)
    dst = os.path.join(folders.verified, fmt, name)
    if not os.path.isfile(dst):
        return 'missing'
    import filecmp
    filecmp.clear_cache()      # its cache is keyed by size+mtime, which a quick re-download can leave unchanged
    return 'same' if filecmp.cmp(src, dst, shallow=False) else 'different'


# ── analysis ───────────────────────────────────────────────────────────────
class _Analysis:
    """Everything analyze() and apply() need: both sides, their match and the stored file's row."""

    def __init__(self, new, existing, stored, diff, identity_ok, links, existing_meta):
        self.new, self.existing, self.stored, self.diff = new, existing, stored, diff
        self.identity_ok, self.links, self.existing_meta = identity_ok, links, existing_meta
        self.status = fd.classify(diff, identity_ok)
        self.removed_with_work = [i for i in diff.removed if has_work(stored[i], links)]


def _find_existing(db, new, existing_name):
    """The File row the new file updates: the one named `existing_name`, else the same name, else the
    same card and month stored under another name."""
    fmt, card = new['format'], new['card']
    candidates = db.get_files_by_name(existing_name or new['name'])
    if not candidates and not existing_name:
        candidates = [r for r in db.get_files_by_identity(fmt, card, new['date'])]
    candidates = [r for r in candidates if r['format'] == fmt] or candidates
    if not candidates:
        raise NothingToCompare('אין קובץ קיים להשוואה')
    for r in candidates:
        if r['card'] == card:
            return r
    return candidates[0]


def _analyse(db, reader, name, fmt, existing_name=None):
    new = reader(name, fmt)
    existing = _find_existing(db, new, existing_name)
    stored = db.get_card_file_transactions(existing['name'], existing['card'])
    diff = fd.compare(stored, new['records'])
    identity_ok = (existing['format'] == new['format'] and existing['card'] == new['card']
                   and _month(existing['date']) == _month(new['date']))
    ids = [stored[i]['id'] for i in diff.removed]
    links = db.get_card_tx_links(ids) if ids else {}
    return _Analysis(new, existing, stored, diff, identity_ok, links, db.get_table_Meta(
        existing['name'], existing['format'], existing['card']))


def _file_facts(path):
    """Size and modification time of a file on disk, or None when it is not there."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return {'size': st.st_size, 'modified': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M')}


def _investigation(a, folders):
    """Everything known about stored rows that are absent from the new file, to help find out why:
    each row in full (with its category / links / closest look-alikes in the new file), both files' facts
    (rows, dates, totals, size, time) and a list of observations drawn from them."""
    d, stored, recs = a.diff, a.stored, a.new['records']
    removed = [stored[i] for i in d.removed]
    pool = [(j, recs[j]) for j in d.added]            # new rows that matched nothing: possible corrected versions
    missing = []
    for i in d.removed:
        r = stored[i]
        sims = [{'new_position': c['index'] + 1, 'name': fd.norm_text(recs[c['index']].get('name')),
                 'date': fd.norm_date(recs[c['index']].get('executed_date')),
                 'amount': recs[c['index']].get('charge_value'), 'same': c['same'], 'differs': c['differs']}
                for c in fd.similar_candidates(r, pool)]
        missing.append({
            'position': i + 1, 'id': r['id'], 'name': fd.norm_text(r.get('name')),
            'executed_date': fd.norm_date(r.get('executed_date')), 'charge_date': fd.norm_date(r.get('charge_date')),
            'amount': r.get('charge_value'), 'currency': r.get('charge_currency'),
            'transaction_value': r.get('transaction_value'), 'value_currency': r.get('value_currency'),
            'serial': fd.serial_of(r), 'extra_info': fd.norm_text(r.get('extra_info')),
            'category': r.get('category'), 'description': r.get('description'),
            'links': a.links.get(r['id'], []), 'work': has_work(r, a.links), 'similar': sims})

    s_range, n_range, m_range = fd.date_range(stored), fd.date_range(recs), fd.date_range(removed)
    stored_copy = _file_facts(os.path.join(folders.verified, a.existing['format'], a.existing['name']))
    new_copy = _file_facts(os.path.join(folders.input, a.new['name']))
    files = {
        'stored': {'name': a.existing['name'], 'rows': len(stored), 'first_date': s_range and s_range[0],
                   'last_date': s_range and s_range[1], 'total': fd.total(stored), 'file': stored_copy,
                   'saved_on': str(a.existing.get('last_update') or ''),
                   'updated_at': str(a.existing.get('updated_at') or '')[:16]},
        'new': {'name': a.new['name'], 'rows': len(recs), 'first_date': n_range and n_range[0],
                'last_date': n_range and n_range[1], 'total': fd.total(recs), 'file': new_copy},
    }
    shape = fd.position_shape(d.removed, len(stored))
    link_kinds = {}
    for m in missing:
        for k in m['links']:
            link_kinds[k] = link_kinds.get(k, 0) + 1
    work = {'tagged': sum(1 for r in removed if (r.get('category') or NOT_CATEGORIZED) != NOT_CATEGORIZED),
            'described': sum(1 for r in removed if (r.get('description') or '').strip()),
            'linked': sum(1 for m in missing if m['links']), 'link_kinds': link_kinds}

    n = len(removed)
    gone_total = fd.total(removed)
    where = {'tail': f'החסרות הן {n} הפעולות האחרונות בקובץ הקיים (לפי סדר הקובץ) — ייתכן שהקובץ החדש נחתך בסופו או הופק לפני שנרשמו',
             'head': f'החסרות הן {n} הפעולות הראשונות בקובץ הקיים (לפי סדר הקובץ) — ייתכן שהקובץ החדש מתחיל מאוחר יותר',
             'block': f'החסרות הן רצף של {n} פעולות באמצע הקובץ הקיים — ייתכן שנמחקו שורות ידנית או שהקובץ הוסב',
             'scattered': 'החסרות פזורות בין פעולות אחרות בקובץ הקיים — ייתכן שהן בוטלו, זוכו או שהקובץ הופק עם סינון אחר',
             'all': 'כל הפעולות הקיימות חסרות — כנראה שזה קובץ אחר לגמרי (חודש, כרטיס או חשבון אחר)'}
    hints = [where[shape]] if shape in where else []
    if m_range and n_range and m_range[1] < n_range[0]:
        hints.append(f'כל החסרות מתאריכים מוקדמים לתחילת הקובץ החדש ({n_range[0]}) — הקובץ החדש מכסה טווח תאריכים קצר יותר')
    elif m_range and n_range and m_range[0] > n_range[1]:
        hints.append(f'כל החסרות מתאריכים מאוחרים לסוף הקובץ החדש ({n_range[1]}) — הקובץ החדש מכסה טווח תאריכים קצר יותר')
    with_similar = sum(1 for m in missing if m['similar'])
    if with_similar:
        hints.append(f'ל־{with_similar} מהחסרות יש פעולה דומה בקובץ החדש (אותו שם / תאריך / סכום חלקית) — '
                     'ייתכן ששם בית העסק, הסכום או התאריך תוקנו או שפעולה פוצלה')
    if d.added:
        hints.append(f'במקביל, בקובץ החדש {len(d.added)} פעולות שאין להן מקבילה במערכת')
    hints.append(f'סכום החסרות: {gone_total:,}₪ מתוך {files["stored"]["total"]:,}₪ בקובץ הקיים; '
                 f'סכום הקובץ החדש: {files["new"]["total"]:,}₪')
    if stored_copy and new_copy and new_copy['modified'] < stored_copy['modified']:
        hints.append(f'הקובץ החדש נשמר ({new_copy["modified"]}) לפני העותק הישן בארכיון ({stored_copy["modified"]}) — '
                     'ייתכן שזו הורדה ישנה יותר')
    if work['tagged'] or work['described'] or work['linked']:
        hints.append(f'עבודה שתאבד בדריסה: {work["tagged"]} פעולות מתויגות, {work["described"]} עם תיאור, '
                     f'{work["linked"]} מקושרות לתכונות אחרות')
    return {'shape': shape, 'missing': missing[:PREVIEW_ROWS * 2], 'missing_total': n, 'missing_amount': gone_total,
            'missing_range': m_range, 'files': files, 'work': work, 'hints': hints}


def _structure(a, folders=None, header_reader=None):
    """Layout of the stored file (from its saved table meta) against the new one. With a `header_reader`
    the real header cells of both files are compared too (the stored file's only if its archived copy exists)."""
    em, nm = a.existing_meta, a.new['meta']

    def rows(meta):
        total = 0
        for m in meta:
            bad = [b for b in str(m.get('Bad_rows') or '').split(',') if b.strip()]
            total += int(m['Row_count']) - len(bad)
        return total
    old = {'format': a.existing['format'], 'card': a.existing['card'], 'charge_month': _month_text(a.existing['date']),
           'tables': len(em)}
    new = {'format': a.new['format'], 'card': a.new['card'], 'charge_month': _month_text(a.new['date']),
           'tables': len(nm), 'columns': a.new['columns']}
    if em:
        old.update({'header_row': int(em[0]['Initial_index']) - 1, 'first_col': int(em[0]['Initial_col']),
                    'rows': rows(em)})
        new.update({'header_row': int(nm[0]['Initial_index']) - 1, 'first_col': int(nm[0]['Initial_col']),
                    'rows': rows(nm)})
    if header_reader and folders and em:
        def headers(path, meta):
            try:
                return header_reader(path, int(meta[0]['Initial_index']) - 1, int(meta[0]['Initial_col']))
            except Exception:
                logger.exception('could not read the header cells of %s', path)
                return None
        got_new = headers(os.path.join(folders.input, a.new['name']), nm)
        old_path = os.path.join(folders.verified, a.existing['format'], a.existing['name'])
        got_old = headers(old_path, em) if os.path.isfile(old_path) else None
        for key, got, target in (('new', got_new, new), ('old', got_old, old)):
            if got is not None:
                target['columns'] = len(got)
                target['headers'] = got
        if 'headers' in old and 'headers' in new and old['headers'] == new['headers']:
            old['headers'] = new['headers'] = f"{len(new['headers'])} כותרות זהות"
        else:
            for t in (old, new):
                if isinstance(t.get('headers'), list):
                    t['headers'] = ', '.join(t['headers'])
    return fd.structure_diff(old, new)


def analyze(db, reader, name, fmt, folders, existing_name=None, header_reader=None):
    """The report shown before anything changes (see the module docstring); writes nothing."""
    a = _analyse(db, reader, name, fmt, existing_name)
    d, stored, recs = a.diff, a.stored, a.new['records']
    tagged = sum(1 for r in stored if (r.get('category') or NOT_CATEGORIZED) != NOT_CATEGORIZED)
    warnings = []
    if not a.identity_ok:
        warnings.append('הקובץ החדש אינו של אותו כרטיס / חודש / פורמט כמו הקובץ הקיים')
    if a.status == fd.STATUS_MISSING:
        warnings.append(f'{len(d.removed)} פעולות שקיימות במערכת חסרות בקובץ החדש. זו חריגה — בדרך כלל קובץ מעודכן רק מוסיף '
                        'פעולות. מומלץ לתחקר לפני שמחליטים (ראו "פרטי התחקור").')
    if d.moved:
        warnings.append(f'{d.moved} פעולות במיקום שונה ביחס לקובץ הקיים')
    layout = _structure(a, folders, header_reader)
    if any(s['changed'] for s in layout if s['field'] not in ('rows',)):
        warnings.append('יש הבדלי מבנה בין הקבצים — ראו את הטבלה')
    # an identical file can still be swapped in (a re-download, or no archived copy left)
    copy_state = (check_input_copy(name, a.existing['format'], folders)
                  if a.existing['name'] == name and os.path.isfile(os.path.join(folders.input, name)) else 'different')
    can_update = (a.identity_ok and a.status != fd.STATUS_MISSING
                  and (a.status != fd.STATUS_IDENTICAL or copy_state != 'same'))
    return {
        'status': a.status, 'status_label': STATUS_LABELS[a.status],
        'new': {'name': name, 'format': a.new['format'], 'card': a.new['card'],
                'month': _month_text(a.new['date']), 'rows': len(recs)},
        'existing': {'name': a.existing['name'], 'format': a.existing['format'], 'card': a.existing['card'],
                     'month': _month_text(a.existing['date']), 'rows': len(stored), 'tagged': tagged,
                     'updated': bool(a.existing.get('updated_at')),
                     'archived_copy': os.path.isfile(os.path.join(folders.verified, a.existing['format'], a.existing['name']))},
        'counts': {**d.counts(), 'existing_rows': len(stored), 'new_rows': len(recs), 'tagged_existing': tagged,
                   'removed_with_work': len(a.removed_with_work)},
        'structure': layout,
        'added': [_preview(recs[j]) for j in d.added[:PREVIEW_ROWS]],
        'removed': [_preview(stored[i], {'work': i in a.removed_with_work, 'category': stored[i].get('category')})
                    for i in d.removed[:PREVIEW_ROWS]],
        'changed': [_preview(recs[j], {'fields': f, 'old_amount': stored[i].get('charge_value')})
                    for i, j, f in d.changed[:PREVIEW_ROWS]],
        'warnings': warnings, 'identity_ok': a.identity_ok, 'can_update': can_update,
        'copy_state': copy_state,
        'investigation': _investigation(a, folders) if a.status == fd.STATUS_MISSING else None,
    }


def find_identity_conflict(db, reader, name, fmt):
    """When a *new* file (not stored under its own name) is the same card and month as a stored file,
    that stored file's File row; else None. Used to stop a second copy of a month being inserted."""
    new = reader(name, fmt)
    for row in db.get_files_by_identity(new['format'], new['card'], new['date']):
        if row['name'] != name:
            return row
    return None


# ── applying the decision ──────────────────────────────────────────────────
def _plan(a, mode):
    d, stored, recs, new = a.diff, a.stored, a.new['records'], a.new
    base = {'old_name': a.existing['name'], 'new_name': new['name'], 'format': a.existing['format'],
            'card': a.existing['card'], 'date': new['date'].date() if isinstance(new['date'], datetime) else new['date'],
            'meta': new['meta'], 'kind': mode}
    if mode == 'replace':
        keep, add, delete = [], list(recs), [r['id'] for r in stored]
        counts = {'added': len(add), 'changed': 0, 'removed': len(delete)}
    else:
        keep = [{'id': stored[i]['id'], 'record': None} for i, _ in d.matched]
        keep += [{'id': stored[i]['id'], 'record': recs[j]} for i, j, _ in d.changed]
        delete = []                       # update is refused while stored rows are missing (see apply)
        add = [recs[j] for j in d.added]
        counts = {'added': len(add), 'changed': len(d.changed), 'removed': 0}
    counts['transactions'] = len(keep) + len(add)
    counts['new'] = len(add)
    return {**base, 'keep': keep, 'add': add, 'delete': delete, 'counts': counts}


def group_history(rows):
    """The recorded updates (DataBase.get_file_update_history, newest first) grouped by the statement they
    belong to: {'<format>|<card>|<YYYY-MM-DD>': [entry, ...]}; dates and times are made JSON-friendly."""
    out = {}
    for r in rows:
        key = f"{r['format']}|{r['card']}|{str(r['month'])[:10]}"
        out.setdefault(key, []).append({
            'at': str(r['at'])[:16].replace('T', ' '), 'kind': r['kind'], 'old_name': r['old_name'],
            'new_name': r['new_name'], 'old_rows': r['old_rows'], 'old_tagged': r['old_tagged'],
            'old_saved_on': str(r['old_saved_on'] or '')[:10], 'new_rows': r['new_rows'], 'added': r['added'] or 0,
            'changed': r['changed'] or 0, 'removed': r['removed'] or 0, 'trashed': bool(r['trash_name'])})
    return out


def _trash_name(name, now):
    return f'{now:%Y%m%d_%H%M%S}_{name}'


def _swap_files(plan, folders, now):
    """The old archived copy goes to the trash, the new file takes its place in the archive.
    Returns warnings (the database is already consistent when this runs)."""
    warnings = []
    fmt = plan['format']
    old_copy = os.path.join(folders.verified, fmt, plan['old_name'])
    new_src = os.path.join(folders.input, plan['new_name'])
    new_dst = os.path.join(folders.verified, fmt, plan['new_name'])
    try:
        if os.path.isfile(old_copy):
            trash_dir = os.path.join(folders.trash, fmt)
            os.makedirs(trash_dir, exist_ok=True)
            shutil.move(old_copy, os.path.join(trash_dir, _trash_name(plan['old_name'], now)))
        else:
            warnings.append('העותק הישן של הקובץ לא נמצא בארכיון, לכן לא הועבר לפח')
    except OSError as e:
        warnings.append(f'העברת הקובץ הישן לפח נכשלה: {e}')
    try:
        os.makedirs(os.path.dirname(new_dst), exist_ok=True)
        if os.path.isfile(new_dst):
            os.remove(new_dst)
        shutil.move(new_src, new_dst)
    except OSError as e:
        warnings.append(f'העברת הקובץ החדש לארכיון נכשלה: {e}')
    return warnings


def apply(db, reader, name, fmt, folders, mode, existing_name=None, now=None):
    """Carry out the user's decision ('update' or 'replace'); returns {ok, counts, warnings}.
    The comparison is redone here, so the result always matches the database's current state."""
    if mode not in ('update', 'replace'):
        raise UpdateError('פעולה לא מוכרת')
    a = _analyse(db, reader, name, fmt, existing_name)
    if mode == 'update':
        if not a.identity_ok:
            raise UpdateError('אי אפשר לעדכן: הקובץ החדש אינו של אותו כרטיס וחודש. אפשר רק לדרוס.')
        if a.status == fd.STATUS_MISSING:
            raise UpdateError('אי אפשר לעדכן: חסרות בקובץ החדש פעולות שקיימות במערכת — נדרש תחקור. אפשר רק לדרוס.')
        if a.status == fd.STATUS_IDENTICAL and a.existing['name'] == name                 and check_input_copy(name, a.existing['format'], folders) == 'same':
            raise UpdateError('הקובץ זהה לקובץ הקיים — אין מה לעדכן')
    elif a.existing['format'] != a.new['format']:
        raise UpdateError('אי אפשר להחליף קובץ בפורמט אחר')
    plan = _plan(a, mode)
    if mode == 'replace' and plan['delete']:
        linked = db.get_card_tx_links(plan['delete'])
        if 'division' in {k for ks in linked.values() for k in ks}:
            raise UpdateError('אי אפשר לדרוס: פעולות בקובץ הקיים מחולקות בין בנק לכרטיס (Devision)')
    now = now or datetime.now()
    old_copy = os.path.join(folders.verified, plan['format'], plan['old_name'])
    plan['history'] = {
        'old_rows': len(a.stored),
        'old_tagged': sum(1 for r in a.stored if (r.get('category') or NOT_CATEGORIZED) != NOT_CATEGORIZED),
        'old_saved_on': a.existing.get('last_update'), 'new_rows': plan['counts']['transactions'],
        'trash_name': _trash_name(plan['old_name'], now) if os.path.isfile(old_copy) else None}
    db.apply_card_file_update(plan)
    warnings = _swap_files(plan, folders, now)
    return {'ok': True, 'counts': plan['counts'], 'warnings': warnings}
