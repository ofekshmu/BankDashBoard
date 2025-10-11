from database import DataBase
from src_utils.utils import utils
from typing import Tuple
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

        The function will handle receiving multiple categories or businesses to filter data by - used by category analysis and user defined plot.

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
            delta = 0 if GENERAL_PLOT.SHOW_CURRENT_MONTH else 1
            # Get the current date
            current_date = datetime.now() - pd.DateOffset(months=delta)
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

        # filter the data according to the given arguments
        if category is not None:
            # Handle both single category (string) and multiple categories (list)
            if isinstance(category, str):
                category = [category]
            earnings_df = earnings_df[earnings_df['Category'].isin(category)]
            spendings_df = spendings_df[spendings_df['Category'].isin(category)]
        if business is not None:
            # Handle both single business (string) and multiple businesses (list)
            if isinstance(business, str):
                business = [business]
            earnings_df = earnings_df[earnings_df['Name'].isin(business)]
            spendings_df = spendings_df[spendings_df['Name'].isin(business)]

        # Date format is converted to month resolution in order to enable proper 'Group-by'
        earnings_df['Date/Executed_Date'] = pd.to_datetime(earnings_df['Date/Executed_Date'], format="%Y-%m-%d %H:%M:%S").apply(lambda x: x.strftime('%Y-%m'))
        spendings_df['Date/Executed_Date'] = pd.to_datetime(spendings_df['Date/Executed_Date'], format="%Y-%m-%d %H:%M:%S").apply(lambda x: x.strftime('%Y-%m'))

        # date range is generated
        full_date_df = pd.DataFrame(generate_date_range(shift), columns=['Date/Executed_Date'])
        
        # conversion of all relevant data columns into datetime format
        full_date_df['Date/Executed_Date'] = pd.to_datetime(full_date_df['Date/Executed_Date'], format='%Y-%m')
        earnings_df['Date/Executed_Date'] = pd.to_datetime(earnings_df['Date/Executed_Date'], format='%Y-%m')
        spendings_df['Date/Executed_Date'] = pd.to_datetime(spendings_df['Date/Executed_Date'], format='%Y-%m')

        # Merge the full date range DataFrame with the original DataFrame
        earnings_df = pd.merge(full_date_df, earnings_df, on='Date/Executed_Date', how='left')
        spendings_df = pd.merge(full_date_df, spendings_df, on='Date/Executed_Date', how='left')
        
        # calculation of net income
        # This section is not relevant when calculating the monthly shifted data per category but for all transactions
        spendings_net_df = spendings_df[spendings_df['Category'] != 'השקעה/חיסכון']
        
        earnings_df = earnings_df.groupby('Date/Executed_Date').sum()
        spendings_df = spendings_df.groupby('Date/Executed_Date').sum()
        spendings_net_df = spendings_net_df.groupby('Date/Executed_Date').sum()

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
    def process_prices(df: pd.DataFrame, date: datetime, month: int = -1, year: int = -1):
        """
        The function usess the lambda function to create the 'Final_Value' column
        Which describes the correct value to plot for each transaction. It returns
        a df representing the original input data along with the 'Final_Value column.

        inputs:
        @param df - a dataframe containing transactions from both CardTransactions and BankTransactions
        @param month - when given, the function will remove payments that are not relevant to the given month
        @param year - when given, the function will remove payments that are not relevant to the
        
        default values will not be used and relevant method will not be used
        """

## --- refactored code below ---


        from enum import Enum

        class Trans_Type(Enum):
            payment = "payments"
            flowing = "flowing"
            payback = "payback"
            withdrawl = "withdrawl"
            excluded = "excluded"
            default = "default"
            bank = "bank"


        def is_payment_transaction(row):
            """
            Function will recognize payment transactions according to the extra info field
            where a transaction will be recognized as a payment transaction by the structure:
            "תשלום ... מתוך ..."

            return arguments:
                @return True if the transaction is a payment, False otherwise
            """

            cond_different_values = row['Charge_Value'] != row['Transaction_Value']
            cond_string_pattern = 'תשלום' in row['Extra_Info'] and 'מתוך' in row['Extra_Info']
            cond_different_dates = row['Charge_Date'] != row['Executed_Date']
            cond_smaller_charge_value = row['Charge_Value'] > row['Transaction_Value']

            # Safeguard - in case the transaction is not a payment but still fits the pattern
            # if this if triggers, conditions should be changed accordingly
            if cond_string_pattern and not (cond_different_values and cond_different_dates and cond_smaller_charge_value):
                utils.log(f"Warning: The following transaction might be wrongfully recognized:\n{row}", "error")

            return cond_different_values & cond_string_pattern & cond_different_dates & cond_smaller_charge_value

        def handle_payments(row, date: datetime):
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

            next_date = utils.next_month(datetime(year, month, 1))
            is_relevant = (pd.to_datetime(row['Charge_Date']).month == next_date.month and
                            pd.to_datetime(row['Charge_Date']).year == next_date.year)

                # Minus value is added to indicate a negative transaction
            return row['Charge_Date'], -row['Transaction_Value'],  (Trans_Type.payment, is_relevant)

        def is_flowing_transaction(row) -> bool:
            """
            The function is used to identify flowing transaction. (see spec file for more info)
            The follwing function checks only condition (1) - a difference of 2 months between the charged date and the value date.
            difference between dates calculates only the values of the months. different year/day will result in the same result.
            """
            return pd.to_datetime(row['Charge_Date']).month - pd.to_datetime(row['Executed_Date']).month == 2

        def handle_flowing(row, date: datetime) -> Tuple[Tuple[Trans_Type ,bool], int]:
            """
            Given a flowing transaction, the function will make sure it matches with the current date being analized.
            
            return Arguments:
                @return (Trans_Type(Enum) = "flowing", bool) - true if the executed month matches the given date month else, false.
            """
            return (Trans_Type.flowing, date.month == pd.to_datetime(row['Executed_Date']).month),\
                    -row['transaction_value']

        def handle_bank_transactions(row):
            """
            for each bank Transaction, outgoing transaction will receive a negative sign, Incoming will
            be left as they are (positive) 
            """
            return row['Income'] if row['Income'] > row['Out'] else (-row['Out']), (Trans_Type.bank, True)

        def is_payback_transaction(row):
            """
            identify payback transactions
            """
            return row['Transaction_Value']*row['Charge_Value'] < 0 or \
                    (row['Transaction_Value'] < 0 and row['Charge_Value'] < 0)
        
        def is_withdrawls_transaction(row):
            """
            identify withdrawl transaction by the category
            """
            return row['TableName'] == 'CardTransactions' and row['Category'] == ReservedNames.WHITDRAWAL_CATEGORY
        


        # the code will iterate over all rows in the dataframe and check the type of transaction,
        # then apply the proper handling. the code will be generic and easy to add more handling
        # the following will handle the identification of payments and handling
        if not df.empty:
            for _, row in df.iterrows():
                if is_payment_transaction(row):
                    row['Date/Executed_Date'], row['Final_Value'], row['transaction_type'] = handle_payments(row, date)
                #elif
                elif is_flowing_transaction(row):
                    row['transaction_type'], row['Final_Value'], = handle_flowing(row, date)
                
                elif row['TableName'] == "BankTransactions":
                    row['Final_Value'], row['transaction_type'] = handle_bank_transactions(row)
                
                elif is_payback_transaction(row):
                    row['Final_Value'], row['Executed_Date'], row['transaction_type'] = abs(row['Transaction_Value']), row['Charge_Date'], (Trans_Type.payback, True)

                elif is_withdrawls_transaction(row):
                    row['transaction_type'], row['Final_Value'], = (Trans_Type.withdrawl, False), -row['Transaction_Value']
                
                # Excluded transactios are manualy excluded by the user
                elif row['Category'] == ReservedNames.EXCLUDED_CATEGORY:
                    row['transaction_type'], row['Final_Value'], = (Trans_Type.excluded, False), -row['Transaction_Value']
                
                else:
                    row['transaction_type'], row['Final_Value'], = (Trans_Type.default, True), -row['Transaction_Value']
        
        utils.log(f"Processed transactions for given date {date} are:\n{utils.df_to_markdown(df)}","debug")
        
        # Drop all rows that have a false flag in their enum
        df = df[df['transaction_type'].value[1]]   
        return df   

## --- refactored code above ---

