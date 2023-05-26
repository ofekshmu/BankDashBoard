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

    # @staticmethod
    # def get_monthly_earnings(year: int, month: int) -> Tuple[int, list]:
    #     """
    #     @parm year - the specified year
    #     @param month - the specifeid month
    #     Returns the sum of all the incoming transactions in the specified month, tuppled with
    #     a list containing tupples with the name and amount of each transaction.
    #     """
    #     lst = DataBase().get_transactions(table="BankTransactions", year=year, month=month)
    #     earnings = []

    #     for ele in lst:
    #         amount = ele[5]
    #         category = ele[10]
    #         date = ele[2]
    #         name = ele[7]
    #         if name is None:
    #             name = ele[4]

    #         striped = re.sub(r'\d+', '', name)

    #         if amount > 0:
    #             earnings.append((striped, amount, category, date))

    #     total_amount = sum([tup[1] for tup in earnings])
    #     return total_amount, earnings

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
        lst2 = DataBase().get_transactions(table="BankTransactions", year=year, month=month)
        
        def filter_spendings(lst: list) -> list:
            # -- filter positive transactions
            negative_trans = [item for item in lst if item[5] < 0]
            # -- filter visa transactions
            return [(0, "Bank", item[2], item[4], item[5], 5, 6, item[5], 8, 9, item[10])
                    for item in negative_trans if item[10] != "אשראי"]

        lst2 = filter_spendings(lst2)
        lst += lst2
        for ele in lst:
            import re
            card = re.sub("[^0-9]", "", ele[1])
            name = ele[3]
            amount = ele[4]
            category = ele[10]
            charge_amount = ele[7]
            date = ele[2]
            amount = transaction_value(amount, charge_amount, ele)
            striped = re.sub(r'\d+', '', name)
            spendings.append((striped, amount, card, category, date))

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
    def cat_info(data: list[Tuple[str, str, int, str, str, str]]) -> dict:
        """
        Input:
        List of tuples containing: (source_table, business_name, amount, Category, transaction_date, Description)
        """
        if data == []:
            return False

        df = pd.DataFrame(data, columns=["Source table", "Name", "Amount", "Category", "Date", "Description"])
        series = df['Amount'].describe()
        
        # convert Date column to datetime format
        df['Date'] = pd.to_datetime(df['Date'])

        count = series.loc["count"]
        sum = df['Amount'].sum()
        min = series.loc["max"]
        max = series.loc["min"]

        # ----- Calculate the amount of months in total from intitial date to current time -----
        # Keep in mind that when using groupby, 'empty month' are not taken into account and
        # therfore the calculations are incorrect.
        start = df['Date'].min()
        end = datetime.now()

        months = (end.year - start.year) * 12 + (end.month - start.month) + 1
        if end.day < start.day:
            months -= 1
        # --------------------------------------------------------------------------------------

        return {"Total Spent":     f'{abs(round(sum, 2))}₪',
                "Total Activity":   int(count),
                "Activity Mean":    f'{abs(round(sum / series.loc["count"], 2))}₪',
                "Monthly Mean":     f'{round(abs(sum / months), 2)}₪',
                "Times per month":  round(count / months, 2),
                "Minimum Amount":   f'{abs(min)}₪',
                "Maximum Amount":   f'{abs(max)}₪'}

    @staticmethod
    def get_monthly_shifted(shift: int = 5):
        """
        The function receives as input the number of months to calculate from this current
        one backwards shift. And returns two lists contatining The monthly spendings and earnings of the last @shift
        months
        """
        from dateutil.relativedelta import relativedelta
        today = datetime.now()
        spendings_lst = []
        earnings_lst = []

        for i in range(0, shift):
            curr_date = (today - relativedelta(months=i)).replace(day=1)
            y = curr_date.year
            m = curr_date.month
            spendings_lst += DataBase().get_monthly_spendings(y, m)
            earnings_lst += DataBase().get_monthly_earnings(y, m)

        return spendings_lst, earnings_lst

    @staticmethod
    def general_info(data):
        """
        Receives transactions both spendings and earnings and returns a dataframe with the columns Date, spendings, earnings
        Where the Date column groups all transaction dates by month, the rest of the columns conclude the sum of transactions
        amount in each month.
        """
        if data[1]:
            earnings_df = pd.DataFrame(data[1], columns=["Name", "Amount", "Category", "Date"])
            earnings_df['Date'] = pd.to_datetime(earnings_df['Date'])
            earnings_df = earnings_df.drop(["Name", "Category"], axis=1)
            earnings_df = earnings_df.groupby(pd.Grouper(key='Date', freq='M')).sum()
        else:
            earnings_df = pd.DataFrame(columns=["Date", "Amount"])

        if data[0]:
            spendings_df = pd.DataFrame(data[0], columns=["Table name", "Name", "Card", "Amount", "Category", "Date"])
            spendings_df['Date'] = pd.to_datetime(spendings_df['Date'])
            spendings_df['Amount'] = spendings_df['Amount'].apply(lambda x: -x)
            spendings_df = spendings_df.drop(["Table name", "Name", "Card", "Category"], axis=1)
            spendings_df = spendings_df.groupby(pd.Grouper(key='Date', freq='M')).sum()
        else:
            spendings_df = pd.DataFrame(columns=["Date", "Amount"])

        df_merged = pd.merge(spendings_df, earnings_df, on='Date', how='left', suffixes=('_spendings', '_earnings'))
        # Fill NaN values with 0
        df_merged.fillna(0, inplace=True)
        return df_merged
