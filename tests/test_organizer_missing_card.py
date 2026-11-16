"""Organizer: a card with no file for a month is flagged when an untagged bank charge with its name exists.

The matcher used to parse the bank date as text; Postgres returns a date object, so every charge was skipped
and no missing card was ever reported. No database."""
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))

from src_utils.utils import utils  # noqa: E402
from Configurations.Formats import Formats  # noqa: E402

DESC = ['TableName', 'ID', 'Date', 'Name', 'Ref', 'Out', 'Income', 'Extra_Info', 'Source_file', '?column?']
FULL, LEN = '%Y-%m-%d %H:%M:%S', 10
NAME = 'ישראכרט בע"מ'


def _row(d, name=NAME, out=577.89):
    return ('BankTransactions', 1, d, name, 1, out, 0, None, 'f.xlsx', None)


def _match(rows, month, names=frozenset({NAME})):
    return utils._find_untagged_transaction_match(list(rows), DESC, set(names), None, None, month, FULL, LEN)


def test_a_postgres_date_object_matches():
    m = _match([_row(date(2026, 11, 2))], datetime(2026, 10, 1))
    assert m == (date(2026, 11, 2), 577.89, NAME, 'missing')


def test_datetime_and_text_dates_still_match():
    assert _match([_row(datetime(2026, 11, 2, 0, 0))], datetime(2026, 10, 1))[3] == 'missing'
    assert _match([_row('2026-11-02 00:00:00')], datetime(2026, 10, 1))[3] == 'missing'
    assert _match([_row('2026-11-02')], datetime(2026, 10, 1))[3] == 'missing'


def test_only_the_following_month_counts():
    assert _match([_row(date(2026, 10, 2))], datetime(2026, 10, 1)) is None      # same month: not this card's charge
    assert _match([_row(date(2026, 12, 2))], datetime(2026, 10, 1)) is None      # two months on


def test_december_spending_is_charged_in_january_of_the_next_year():
    assert _match([_row(date(2027, 1, 2))], datetime(2026, 12, 1))[3] == 'missing'


def test_other_names_do_not_match():
    assert _match([_row(date(2026, 11, 2), name='משהו אחר')], datetime(2026, 10, 1)) is None


def test_every_isra_2026_card_has_its_bank_charge_name():
    """A card with no configured name is skipped by the alert and the organizer, so it can never be flagged."""
    names = Formats.FORMATS['Isra-Card-2026']['Transaction Names']
    for card in ('1565', '2922', '4046', '4603', '6046', '7574'):
        assert names.get(card), card


def test_a_column_replaced_by_a_newer_format_of_the_same_card_is_superseded():
    last = {'Isra-Card | 2922': datetime(2026, 1, 1), 'Isra-Card-2026 | 2922': datetime(2026, 10, 1),
            'Isra-Card-2026 | 1565': datetime(2026, 10, 1), 'Cal | 9999': datetime(2025, 3, 1)}
    assert utils._superseded_columns(last) == {'Isra-Card | 2922'}      # the old 2922; a stale unrelated card is still its own


def test_two_issuers_with_the_same_last_digits_are_different_cards():
    last = {'American-Express | 1565': datetime(2026, 11, 1), 'Isra-Card-2026 | 1565': datetime(2026, 10, 1)}
    assert utils._superseded_columns(last) == set()


def test_same_last_file_is_not_superseded():
    last = {'A | 1111': datetime(2026, 10, 1), 'B | 1111': datetime(2026, 10, 1)}
    assert utils._superseded_columns(last) == set()


def _cells(*cards):
    """One missing cell per card for the same month, all sharing the bank name."""
    return [(('Oct', f'c{c}'), {NAME}, None, None, datetime(2026, 10, 1), c) for c in cards]


def test_the_charge_goes_to_the_card_whose_last_charge_it_equals(monkeypatch):
    """Three cards share one bank name; the 577.89 charge repeats card 2922's last month (578)."""
    last = {'7574': 480.0, '1565': 1361.0, '2922': 578.0}
    monkeypatch.setattr(utils, '_recent_card_charge', staticmethod(lambda card, month, cache: last.get(card)))
    found = utils.match_missing_cells(_cells('7574', '1565', '2922'), [_row(date(2026, 11, 2))], DESC, FULL, LEN)
    assert list(found) == [('Oct', 'c2922')]
    assert found[('Oct', 'c2922')][3] == 'missing'


def test_without_a_matching_amount_the_first_card_takes_the_charge(monkeypatch):
    monkeypatch.setattr(utils, '_recent_card_charge', staticmethod(lambda card, month, cache: 5000.0))   # none is close
    found = utils.match_missing_cells(_cells('7574', '1565', '2922'), [_row(date(2026, 11, 2))], DESC, FULL, LEN)
    assert list(found) == [('Oct', 'c7574')]


def test_a_card_with_no_history_still_gets_a_charge_that_nobody_else_claims(monkeypatch):
    monkeypatch.setattr(utils, '_recent_card_charge', staticmethod(lambda card, month, cache: None))
    found = utils.match_missing_cells(_cells('7574'), [_row(date(2026, 11, 2))], DESC, FULL, LEN)
    assert list(found) == [('Oct', 'c7574')]


def test_one_charge_explains_one_card(monkeypatch):
    monkeypatch.setattr(utils, '_recent_card_charge', staticmethod(lambda card, month, cache: 578.0))
    found = utils.match_missing_cells(_cells('2922', '7574'), [_row(date(2026, 11, 2))], DESC, FULL, LEN)
    assert len(found) == 1
