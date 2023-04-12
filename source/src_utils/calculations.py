from database import DataBase
from src_utils.utils import utils
from typing import Tuple
from datetime import datetime
import pandas as pd
import re


class SimpleMath:

    @staticmethod
    def generate_monthly_balance() -> int:
        """
        Return the current Account balance by identifying the most recent Transaction.
        """
        row = DataBase().get_latest_bank_transaction()
        balance = row[6]
        return balance

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
        """
        @parm year - the specified year
        @param month - the specifeid month
        Returns the sum of all the incoming transactions in the specified month, tuppled with
        a list containing tupples with the name and amount of each transaction.
        """
        lst = DataBase().get_transactions(table="BankTransactions", year=year, month=month)
        earnings = []

        for ele in lst:
            amount = ele[5]
            category = ele[10]
            name = ele[7]
            if name is None:
                name = ele[4]

            striped = re.sub(r'\d+', '', name)

            if amount > 0:
                earnings.append((striped, amount, category))

        total_amount = sum([tup[1] for tup in earnings])
        return total_amount, earnings

    @staticmethod
    def get_monthly_spendings(year: int, month: int) -> Tuple[int, list]:
        """
        @parm year - the specified year
        @param month - the specifeid month
        Returns the sum of all the spending transactions in the specified month, tuppled with
        a list containing tupples with the name and amount of each transaction.
        """
        spendings = []

        # When looking for spendings. transaction will be queried by the date they will be 
        # effective in the bank account and not by the date they were exectued.
        # That is why, when given month x, we will search for transactions in month x + 1
        fit_month = month % 12 + 1
        if fit_month == 1:
            year += 1

        def transaction_value(amount: int, charge_amount: int, row: list) -> int:
            """
            It seems like when applying payments the values are specified in a different column.
            The function return the value in the corrent column according to the transaction name.
            """
            
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
        """
        Returns a tupple containing the date, bussines name, amount of all 'Gas' related transactions.
        The dates are all in Datetime format.
        """
        word_lst = ['דור אלון ממר"צ', "דור אלון צריפין", "תחנת דלק בני ברית", "דלק BULL אשדוד", "דלק נמל אשדוד"]
        raw_data = DataBase().get_gas_related(word_lst)
        res = []
        for t in raw_data:
            new_tuple = (datetime.strptime(t[0], '%Y-%m-%d %H:%M:%S'), t[1], -t[2])
            res.append(new_tuple)

        return res

    @staticmethod
    def general_info(earnings, spendings):
        """
        Receives transactions both spendings and earnings and returns a dataframe with the columns Date, spendings, earnings
        Where the Date column groups all transaction dates by month, the rest of the columns conclude the sum of transactions
        amount in each month.
        """
        new_earnings = [(tup[0], datetime.strptime(tup[1], '%Y-%m-%d %H:%M:%S')) for tup in earnings]
        earnings_df = pd.DataFrame(new_earnings, columns=["Amount", "Date"])
        earnings_df = earnings_df.groupby(pd.Grouper(key='Date', freq='M')).sum()
        
        new_spendings = [(-tup[0], datetime.strptime(tup[1], '%Y-%m-%d %H:%M:%S')) for tup in spendings]
        spendings_df = pd.DataFrame(new_spendings, columns=["Amount", "Date"])
        spendings_df = spendings_df.groupby(pd.Grouper(key='Date', freq='M')).sum()

        df_merged = pd.merge(spendings_df, earnings_df, on='Date', how='left', suffixes=('_spendings', '_earnings'))
        
        return df_merged
