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
        df['Date/Executed_Date'] = pd.to_datetime(df['Date/Executed_Date'])

        count = series.loc["count"]
        sum = df['Final_Value'].sum()
        min = series.loc["max"]
        max = series.loc["min"]

        # ----- Calculate the amount of months in total from intitial date to current time -----
        # Keep in mind that when using groupby, 'empty month' are not taken into account and
        # therfore the calculations are incorrect.
        start = df['Date/Executed_Date'].min()
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
    def get_monthly_shifted(shift: int = 5, category=None, business=None) -> Tuple[list[int], list[int], list[int]]:
        """
        The function receives as input the number of months to calculate from this current
        one backwards shift. And returns three lists contatining The monthly spendings and earnings of the last @shift
        months

        The middle list represents the sum spending, subtructed by spending to another account (savings)
        all prices queried are being proccesed.
        """

        def generate_date_range(n) -> list[str]:
            """
            The function a range of dates, from the last month, n months back.
            the dates will be in '%Y-%m' format.
            for the current date 29/6/24 and n = 6, the following will be returned:
            ['2023-12', '2024-01', '2024-02', '2024-03', '2024-04', '2024-05']
            """
            # Get the current date
            current_date = datetime.now() - pd.DateOffset(months=1)
            # Calculate the start date (n months back from the current month)
            start_date = (current_date.replace(day=1) - pd.DateOffset(months=n-1)).replace(day=1)
            # Generate a range of dates from the start date to the current month
            date_range = pd.date_range(start=start_date, end=current_date, freq='MS')
            # Convert the date range to the format '%Y-%m'
            date_range_str = date_range.strftime('%Y-%m').tolist()
            return date_range_str

        # Data is queried and proccessed
        earnings_df = SimpleMath.process_prices(DataBase().get_earnings())
        spendings_df = SimpleMath.process_prices(DataBase().get_spendings())
        print(spendings_df[spendings_df['Category'] == 'החזר'].sort_values(by='Date/Executed_Date').to_markdown())
        x = DataBase().get_spendings()
        print(x[x['Category'] == 'החזר'].sort_values(by='Date/Executed_Date').to_markdown())
        # filter the data according to the given arguments
        if category is not None:
            earnings_df = earnings_df[earnings_df['Category'] == category]
            spendings_df = spendings_df[spendings_df['Category'] == category]
        if business is not None:
            earnings_df = earnings_df[earnings_df['Name'] == business]
            spendings_df = spendings_df[spendings_df['Name'] == business]

        # Date format is converted to month resolution in order to enable proper 'Group-by'
        earnings_df['Date/Executed_Date'] = pd.to_datetime(earnings_df['Date/Executed_Date'], format="%Y-%m-%d %H:%M:%S").apply(lambda x: x.strftime('%Y-%m'))
        spendings_df['Date/Executed_Date'] = pd.to_datetime(spendings_df['Date/Executed_Date'], format="%Y-%m-%d %H:%M:%S").apply(lambda x: x.strftime('%Y-%m'))

        # date range is generated
        full_date_df = pd.DataFrame(generate_date_range(shift), columns=['Date/Executed_Date'])
        
        # conversion of all relevant data columns into datetime format
        full_date_df['Date/Executed_Date'] = pd.to_datetime(full_date_df['Date/Executed_Date'])
        earnings_df['Date/Executed_Date'] = pd.to_datetime(earnings_df['Date/Executed_Date'])
        spendings_df['Date/Executed_Date'] = pd.to_datetime(spendings_df['Date/Executed_Date'])

        # Merge the full date range DataFrame with the original DataFrame
        earnings_df = pd.merge(full_date_df, earnings_df, on='Date/Executed_Date', how='left')
        spendings_df = pd.merge(full_date_df, spendings_df, on='Date/Executed_Date', how='left')
        
        earnings_df = earnings_df.groupby('Date/Executed_Date').sum()
        spendings_df = spendings_df.groupby('Date/Executed_Date').sum()
        
        # calculation of net income
        # This section is not relevant when calculating the monthly shifted data per category but for all transactions
        spendings_net_df = spendings_df[spendings_df['Category'] != 'השקעה/חיסכון']
        spendings_net_df = spendings_net_df.groupby('Date/Executed_Date').sum()

        print(list(spendings_df['Final_Value'])[::-1])
        # data is returned backwards to fit the plot_general function.
        return list(spendings_df['Final_Value'])[::-1], \
                list(spendings_net_df['Final_Value'])[::-1], \
                list(earnings_df['Final_Value'])[::-1]

    @staticmethod
    def general_info(data):
        """
        Receives transactions both spendings and earnings and returns a dataframe with the columns Date, spendings,
        earnings Where the Date column groups all transaction dates by month, the rest of the columns conclude the
        sum of transactions amount in each month.
        """
        if data[1]:
            earnings_df = pd.DataFrame(data[1], columns=["Name", "Amount", "Category", "Date"])
            earnings_df['Date/Executed_Date'] = pd.to_datetime(earnings_df['Date/Executed_Date'])
            earnings_df = earnings_df.drop(["Name", "Category"], axis=1)
            earnings_df = earnings_df.groupby(pd.Grouper(key='Date/Executed_Date', freq='M')).sum()
        else:
            earnings_df = pd.DataFrame(columns=["Date", "Amount"])

        if data[0]:
            spendings_df = pd.DataFrame(data[0], columns=["Table name", "Name", "Card", "Amount", "Category", "Date"])
            spendings_df['Date/Executed_Date'] = pd.to_datetime(spendings_df['Date/Executed_Date'])
            spendings_df['Amount'] = spendings_df['Amount'].apply(lambda x: -x)
            spendings_df = spendings_df.drop(["Table name", "Name", "Card", "Category"], axis=1)
            spendings_df = spendings_df.groupby(pd.Grouper(key='Date/Executed_Date', freq='M')).sum()
        else:
            spendings_df = pd.DataFrame(columns=["Date", "Amount"])

        df_merged = pd.merge(spendings_df, earnings_df, on='Date/Executed_Date', how='left', suffixes=('_spendings', '_earnings'))
        # Fill NaN values with 0
        df_merged.fillna(0, inplace=True)
        return df_merged

    @staticmethod
    def process_prices(df: pd.DataFrame):
        """
        The function usess the lambda function to create the 'Final_Value' column
        Which describes the correct value to plot for each transaction. It returns
        a df representing the original input data along with the 'Final_Value column.
        """

        # print(df.to_markdown())
        def my_lambda(row):
            """
            The function returns the Actual value describing the given transactions.
            The function takes into acoount transactions made in payments, return transactions, income/outcome of
            BankTransactions.
            """
            match row['TableName']:
                case 'BankTransactions':
                    # Only one of the following should have a value that is not 0.
                    # This is the value that should be returned
                    if row['Income/Charge_Value'] > row['Out/Transaction_value']:
                        return row['Income/Charge_Value']
                    else:
                        return - row['Out/Transaction_value']

                case 'CardTransactions':
                    # When the transaction is part of payments, the fields Charge_Value/Transaction_value will have
                    # differet Values, one with the current payment and the other one with the full.
                    # This if will make sure that the smaller value is always used
                    cond_payments = row['Description/Charge_Currency'] == row['Reserved/Value_Currency'] and \
                            row['Income/Charge_Value'] != row['Out/Transaction_value'] # This can also be smaller than >
                    # If only one of the values is Negative, the transaction is indicating a return made directly to
                    # the card. in this case the negative value should be considered - the min of the two.
                    try:
                        cond_Credit_payback = row['Out/Transaction_value']*row['Income/Charge_Value'] < 0 or \
                                                (row['Out/Transaction_value'] < 0 and row['Income/Charge_Value'] < 0)

                    except Exception as e:
                        utils.log(f"Error: {e}\nValue 1: {row['Out/Transaction_value']}\nValue 2: {row['Income/Charge_Value']}", "error")
                    if cond_payments:
                        return -min(row['Income/Charge_Value'], row['Out/Transaction_value'])
                    if cond_Credit_payback:
                        return abs(row['Out/Transaction_value'])

                    # The actual value of the transaction in ILS is indicated in this field
                    return -row['Out/Transaction_value']
                case _:
                    utils.log("Unrecognized case in 'process_prices'...", "error")
                    return ""   # To avoid linter error - unreacheable code.

        def refund_wrapper(row):
            """
            """
            match row['TableName']:
                case 'BankTransactions':
                    # Function does not handle BankTransactions - leave as it is.
                    return row['Date/Executed_Date']
                case 'CardTransactions':
                    cond_Credit_payback = row['Out/Transaction_value']*row['Income/Charge_Value'] < 0
                    cond_payments = 'תשלום' in row['Extra_Info'] and 'מתוך' in row['Extra_Info']
                    if cond_Credit_payback or cond_payments:
                        return row['Value_Date/Charge_Date']

                    return row['Date/Executed_Date']
                case _:
                    utils.log("Unrecognized case in 'process_prices' -> 'refund_wrapper'...", "error")
                    return ""   # To avoid linter error - unreacheable code.

        if not df.empty:
            df["Final_Value"] = df.apply(my_lambda, axis=1)
            df["Date/Executed_Date"] = df.apply(refund_wrapper, axis=1)

        return df
