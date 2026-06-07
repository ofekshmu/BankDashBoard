from database import DataBase
from src_utils.utils import utils
from typing import Tuple, Optional
from datetime import datetime
import pandas as pd
from Constants import GENERAL_PLOT, ReservedNames


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

        The function will handle receiving multiple categories or businesses to filter data by - used by category analysis and user defined plot.

        The middle list represents the sum spending, subtructed by spending to another account (savings)
        all prices queried are being proccesed.
        """

        from Constants import INVESTMENT_CATEGORY

        current_date = datetime.now()
        initial_delta = 0 if GENERAL_PLOT.SHOW_CURRENT_MONTH else 1
        spendings_lst = []
        spendings_net_lst = []
        earnings_lst = []

        for i in range(initial_delta, shift):
            calculated_date = current_date - pd.DateOffset(months=i)
            df_i = SimpleMath.process_prices(
                        DataBase().query_monthly_transactions(date=calculated_date,
                                                              tables=['BankTransactions','CardTransactions']),
                        date=calculated_date)
            
            if category is not None:
                if isinstance(category, str):
                    category = [category]
                df_i = df_i[df_i['Category'].isin(category)]

            if business is not None:
                if isinstance(business, str):
                    business = [business]
                df_i = df_i[df_i['Name'].isin(business)]

            # if df_i.empty:
            #     utils.log("test", 'system')


            spendings_lst.append(df_i['Final_Value'][(df_i['Final_Value'] < 0)].sum())
            spendings_net_lst.append(df_i['Final_Value'][(df_i['Final_Value'] < 0) & (df_i['Category'] != INVESTMENT_CATEGORY)].sum())
            earnings_lst.append(df_i['Final_Value'][(df_i['Final_Value'] > 0)].sum())
            
        # data is returned backwards to fit the plot_general function.
        return spendings_lst, \
                spendings_net_lst, \
                earnings_lst

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
    def process_prices(df: pd.DataFrame, date: datetime = datetime(2000, 1, 1), general_analysis: bool = True) -> pd.DataFrame:
        """
        The function process the prices of the given dataframe according to the type of transaction.
        return arguments:
            @return df: pd.DataFrame - the processed dataframe with the following added columns:
                - Final_Value: int - the final value of the transaction after processing
                - Transaction_Type: Enum - the type of transaction according to the Constants.Trans_Type enum
                - Relevance: bool - True if the transaction is relevant to the given month and year, False otherwise
        The function will classify each transaction according to the following types:
            - Payment transactions: transactions that are payments for previous transactions
            - Flowing transactions: transactions that are charged 2 months after the executed date
            - Payback transactions: transactions that are paybacks for previous transactions
            - Withdrawl transactions: transactions that are withdrawls from an ATM
            - Bank transactions: transactions that are from the bank account
            - Default transactions: all other transactions
            - excluded transactions: transactions that are manually excluded by the user or credit card charge transactions
        see spec file for more information on each type of transaction

        inputs:
            @param df: pd.DataFrame - the dataframe to process
            @param date: datetime - process the transcations according to this month and year. 
             Default value - datetime(2000, 1, 1) is irelevant and used only when general_analysis is False,
             otherwise the function will return an error when the user does not specify a date for general analysis.
            @param general_analysis: bool - True if the function is used for general analysis, False otherwise

        """

        from Constants import Trans_Type

        def is_payment_transaction(row):
            """
            Function will recognize payment transactions according to the extra info field
            where a transaction will be recognized as a payment transaction by the structure:
            "תשלום ... מתוך ..."

            return arguments:
                @return True if the transaction is a payment, False otherwise
            """

            cond_different_values = row['Charge_Value'] != row['Transaction_Value']
            _extra = row['Extra_Info']
            cond_string_pattern = bool(_extra) and 'תשלום' in _extra and 'מתוך' in _extra
            cond_different_dates = row['Charge_Date'] != row['Executed_Date']
            cond_smaller_charge_value = row['Charge_Value'] > row['Transaction_Value']

            # Safeguard - in case the transaction is not a payment but still fits the pattern
            # if this triggers, conditions should be changed accordingly
            if cond_string_pattern and not (cond_different_values and cond_different_dates and cond_smaller_charge_value):
                utils.log(f"Warning: The following transaction might be wrongfully recognized:\n{row}", "warning")

            return cond_different_values & cond_string_pattern & cond_different_dates & cond_smaller_charge_value

        def handle_payments(row, date: datetime) -> pd.Series:
            """
            Function should receive only rows that has been recognized as payment transactions by the
            is_payment_transaction function."

            return arguments:
                @return date: datetime - charge date if the transaction is a payment, executed date otherwise
                @return amount: int - charge value if the transaction is a payment, transaction value otherwise
                @return is_relevant: bool - True if the payment is relevant to the given month and year, False otherwise

            amount will be returned to the Final_Value column
            date will be returned to the executed date column

            see spec file for more information on payment transactions
            """

            next_date = utils.next_month(date)
            is_relevant = (pd.to_datetime(row['Charge_Date']).month == next_date.month and
                            pd.to_datetime(row['Charge_Date']).year == next_date.year)

                # Minus value is added to indicate a negative transaction
            return pd.Series([row['Charge_Date'], -row['Transaction_Value'],  Trans_Type.payment, is_relevant])

        def is_flowing_transaction(row) -> bool:
            """
            The function is used to identify flowing transaction. (see spec file for more info)
            The follwing function checks only condition (1) - a difference of 2 months between the charged date and the value date.
            difference between dates calculates only the values of the months. different year/day will result in the same result.
            """
            return pd.to_datetime(row['Charge_Date']).month - pd.to_datetime(row['Executed_Date']).month == 2

        def handle_flowing(row, date: datetime) -> pd.Series:
            """
            Given a flowing transaction, the function will make sure it matches with the current date being analized.
            
            return Arguments:
                @return (Trans_Type(Enum) = "flowing", bool) - true if the executed month matches the given date month else, false.
            """
            # Assumption: flowing transactions are always relevant when the charge month is the next month of the given date

            return row['Executed_Date'],\
                    (-row['Transaction_Value']),\
                    Trans_Type.flowing,\
                     date.month + 1 == pd.to_datetime(row['Charge_Date']).month
    
        def handle_bank_transactions(row) -> pd.Series:
            """
            for each bank Transaction, outgoing transaction will receive a negative sign, Incoming will
            be left as they are (positive) 
            """
            relevance = False if row['Category'] == ReservedNames.EXCLUDED_CATEGORY or \
                                row['Category'] == ReservedNames.CC_CHARGE_CATEGORY_NAME else True

            return pd.Series([row['Date'],\
                row['Income'] if row['Income'] > row['Out'] else (-row['Out']),\
                Trans_Type.bank,\
                relevance])

        def is_payback_transaction(row):
            """
            identify payback transactions
            1. Transaction and Charge values have different signs
            2. Both values are negative
            """
            return row['Transaction_Value']*row['Charge_Value'] < 0 or \
                    (row['Transaction_Value'] < 0 and row['Charge_Value'] < 0)

        def handle_paybacks(row) -> pd.Series:
            """
            The function returns the Transactions value as a negative value for the amount:
            - Some cases feature the Transaction value as positive, while at some it is negative.
            - Transaction value shows the value in ILS for abroad transactions, when charge shows the value in foreign currency
            The executed Date is returned as the date to indicated the date in witch the payback was given
            this goes the opposit of other type of card transactions where they take affect on the charge date.
            """
            payback_value = row['Transaction_Value'] if row['Transaction_Value'] > 0 else -row['Transaction_Value']

            # Assumption: if charge month is equal to the executed month, given the transaction is a payback, it is not relevant
            # Fact - paybacks abroad/local can both be relevant and non relevant
            relevance = not (pd.to_datetime(row['Executed_Date']).month == pd.to_datetime(row['Charge_Date']).month)

            return pd.Series([row['Executed_Date'],
                             payback_value,
                             Trans_Type.payback,
                             relevance
        ])

        def is_withdrawls_transaction(row):
            """
            identify withdrawl transaction by the category
            """
            return row['TableName'] == 'CardTransactions' and row['Category'] == ReservedNames.WHITDRAWAL_CATEGORY
        
        def classify_and_handle(row) -> pd.Series:

            if row['TableName'] == "BankTransactions":
                return handle_bank_transactions(row)
            
            # Excluded transactions are manualy excluded by the user or credit card charge transactions
            elif row['Category'] == ReservedNames.EXCLUDED_CATEGORY or \
                  row['Category'] == ReservedNames.CC_CHARGE_CATEGORY_NAME or \
                    (pd.to_datetime(row['Charge_Date']).month == date.month and general_analysis): # Charge date is in the curren month and not the next
                return pd.Series([row['Executed_Date'], -row['Transaction_Value'], Trans_Type.excluded, False])
        
            elif is_payment_transaction(row):
                return handle_payments(row, date)

            elif is_flowing_transaction(row):
                return handle_flowing(row, date)
            
            elif is_payback_transaction(row):
                return handle_paybacks(row)

            elif is_withdrawls_transaction(row):
                return pd.Series([row['Executed_Date'] , -row['Transaction_Value'], Trans_Type.withdrawl, False])
            
            else:
                return pd.Series([row['Executed_Date'], -row['Transaction_Value'], Trans_Type.default, True])

        # Validate inputs:
        if general_analysis and date == datetime(2000, 1, 1): # default date value used
            utils.log("Invalid input combination calling process_prices:\nPlease specify date when using for General analysis", "error")

        if df.empty:
            utils.log("process_prices: df is empty", "debug")
            # add Final_Value and Transaction_Type columns to empty df
            df['Final_Value'] = pd.Series(dtype='float')
            df['Transaction_Type'] = pd.Series(dtype='object')
            return df
        
        df[['Executed_Date', 'Final_Value', 'Transaction_Type', 'Relevance']]  = df.apply(classify_and_handle, axis=1)
        
        utils.log(f"Processed transactions for given date {date} are:\n{utils.df_to_markdown(df)}","debug")      
        
        if general_analysis:
            df = df[df['Relevance']]
        else:
            # Drop excluded transactions only
            df = df[df['Transaction_Type'] != Trans_Type.excluded]

        return df   

