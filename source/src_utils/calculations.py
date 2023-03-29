from database import DataBase
from src_utils.utils import utils
from typing import Tuple
from datetime import datetime


class SimpleMath:

    @staticmethod
    def generate_monthly_balance() -> int:

        row = DataBase().get_latest_bank_transaction()
        balance = row[6]
        return balance

    @staticmethod
    def generate_end_monthly_balance() -> int:
        return -1

    @staticmethod
    def prettify(name, amount, card="") -> str:
        """
        The function returns a readable string for ploting.

        @param name -   a string indicating transaction info
        @param amount - value of the transaction
        @param card -   the card asociated with the transaction
        """
        if utils.has_hebrew(name):
            lst = name.split()
            name = ""
            for word in lst:
                if utils.has_hebrew(word):
                    name = f"{word[::-1]} " + name
                else:
                    name = f"{word} " + name

        if card == "":
            return f"{name}- {amount}"
        return f"[{card}] {name}- {-amount}"

    @staticmethod
    def get_monthly_earnings(year: int, month: int) -> Tuple[int, list]:
        lst = DataBase().get_transactions(table="BankTransactions", year=year, month=month)
        earnings = []

        for ele in lst:
            amount = ele[5]
            name = ele[7]
            if name is None:
                name = ele[4]

            import re
            striped = re.sub(r'\d+', '', name)

            if amount > 0:
                earnings.append((striped, amount))

        total_amount = sum([tup[1] for tup in earnings])
        return total_amount, earnings

    @staticmethod
    def get_monthly_spendings(year: int, month: int) -> Tuple[int, list]:
        spendings = []

        # When looking for spendings. transaction will be queried by the date they will be 
        # effective in the bank account and not by the date they were exectued.
        # That is why, when given month x, we will search for transactions in month x + 1
        fit_month = month % 12 + 1
        if fit_month == 1:
            year += 1

        def transaction_value(amount: int, charge_amount: int, row: list) -> int:
            if row[5] == "תשלומים":
                return amount
            if amount != charge_amount:
                return charge_amount
            return amount

        lst = DataBase().get_transactions(table="", year=year, month=fit_month)
        for ele in lst:
            import re
            card = re.sub("[^0-9]", "", ele[1])
            name = ele[3]
            amount = ele[4]
            charge_amount = ele[7]
            amount = transaction_value(amount, charge_amount, ele)
            striped = re.sub(r'\d+', '', name)
            spendings.append((striped, amount, card))

        total_amount = round(sum([-tup[1] for tup in spendings]), 2)
        return total_amount, spendings

    @staticmethod
    def gas_info() -> list:
        word_lst = ["דור אלון צריפין", "תחנת דלק בני ברית", "דלק BULL אשדוד", "דלק נמל אשדוד"]
        raw_data = DataBase().get_gas_related(word_lst)
        res = []
        for t in raw_data:
            new_tuple = (datetime.strptime(t[0], '%Y-%m-%d %H:%M:%S'), t[1], -t[2])
            res.append(new_tuple)

        return res
