from database import DataBase
from src_utils.utils import utils
from typing import Tuple
from datetime import datetime
import pandas as pd
import re


class SimpleMath:

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
    def cat_info(df: pd.DataFrame) -> dict:
        """
        Input:
        List of tuples containing: (source_table, business_name, amount, Category, transaction_date, Description)
        """
        if df.empty:
            return False

        series = df['Final_Value'].describe()

        # convert Date column to datetime format
        df['Date'] = pd.to_datetime(df['Date'])

        count = series.loc["count"]
        sum = df['Final_Value'].sum()
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
    def get_monthly_shifted(shift: int = 5) -> Tuple[list[int], list[int]]:
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
            spendings, description = DataBase().get_monthly_spendings(year=y, month=m)
            spendings_df = SimpleMath.process_prices(spendings, description)
            spendings_df = utils.remove_leumi(spendings_df)
            spendings_sum = spendings_df['Final_Value'].sum()
            spendings_lst.append(spendings_sum)

            earnings, description = DataBase().get_monthly_earnings(year=y, month=m)
            earnings_df = SimpleMath.process_prices(earnings, description)
            earnings_df = utils.remove_leumi(earnings_df)
            earnings_sum = earnings_df['Final_Value'].sum()
            earnings_lst.append(earnings_sum)

        return spendings_lst, earnings_lst

    @staticmethod
    def general_info(data):
        """
        Receives transactions both spendings and earnings and returns a dataframe with the columns Date, spendings,
        earnings Where the Date column groups all transaction dates by month, the rest of the columns conclude the
        sum of transactions amount in each month.
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

    @staticmethod
    def process_prices(data: list, columns: list):

        df = pd.DataFrame(data, columns=columns)

        def my_lambda(row):
            match row['TableName']:
                case 'BankTransactions':
                    # Only one of the following should have a value that is not 0.
                    # This is the value that should be returned
                    return abs(max(row['Income/Charge_Value'], row['Out/Transaction_value']))
                case 'CardTransactions':
                    # When the transaction is part of payments, the fields Charge_Value/Transaction_value will have
                    # differet Values, one with the current payment and the other one with the full.
                    # This if will make sure that the smaller value is always used
                    cond_payments = row['Description/Charge_Currency'] == row['Reserved/Value_Currency'] and \
                            row['Income/Charge_Value'] != row['Out/Transaction_value']
                    # If only one of the values is Negative, the transaction is indicating a return made directly to
                    # the card. in this case the negative value should be considered - the min of the two.
                    cond_Credit_payback = row['Out/Transaction_value']*row['Income/Charge_Value'] < 0
                    if cond_payments or cond_Credit_payback:
                        return abs(min(row['Income/Charge_Value'], row['Out/Transaction_value']))

                    # The actual value of the transaction in ILS is indicated in this field
                    return abs(row['Out/Transaction_value'])
                case _:
                    utils.log("Unrecognized case in 'process_prices'...", "error")
                    return ""   # To avoid linter error - unreacheable code.

        if not df.empty:
            df["Final_Value"] = df.apply(my_lambda, axis=1)

        return df
