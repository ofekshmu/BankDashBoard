from database import DataBase
from src_utils.calculations import SimpleMath
from src_utils.utils import utils

import pandas as pd
from datetime import datetime

class AppManagerUtils:

    @staticmethod
    def retrieve_and_initialize_data(t: datetime, std_out: bool = True) -> pd.DataFrame:
        """
        Retrieves and processes card and bank transaction data for a given month, then combines them into a single DataFrame.
        Args:
            t (datetime): The date for which to retrieve and process transactions. 
                          The month and year of this date will be used to filter transactions of that specific month and year
            std_out (bool): If True, logs will be printed to standard output. If False, logs will be suppressed.
        
        Returns:
            pd.DataFrame: A combined DataFrame containing processed card and bank transactions for the specified month.
        Note:
            - The method queries the database for card and bank transactions for the specified month.
            - It processes the transaction data using the SimpleMath class to calculate final values.
            - The processed data is then combined into a single DataFrame, which is returned for use in the application.
        """
        if std_out: utils.log("Processing card data...", "system")        
        monthly_card_transactions_df = DataBase().query_monthly_transactions(date=t, tables=["CardTransactions"])
        proceessed_card_transactions_df = SimpleMath.process_prices(monthly_card_transactions_df, date=t)

        if std_out: utils.log("Processing bank data...", "system")
        monthly_bank_transactions_df = DataBase().query_monthly_transactions(date=t, tables=["BankTransactions"])
        proceessed_bank_transactions_df = SimpleMath.process_prices(monthly_bank_transactions_df, date=t)
        
        # -------------------------- Collision of both df --------------------------
        if monthly_card_transactions_df.empty:
            utils.log("No card transactions found for the selected month.", "warning")
        else:
            proceessed_card_transactions_df=proceessed_card_transactions_df[['ID',
                                                                            'TableName', 
                                                                            'CardID',
                                                                            'Name',
                                                                            'Executed_Date',
                                                                            'Charge_Date',
                                                                            'Charge_Value',
                                                                            'Charge_Currency',
                                                                            'Value_Currency',
                                                                            'Final_Value',
                                                                            'Category',
                                                                            'Extra_Info',
                                                                            'Description',
                                                                            'Transaction_Type']]
        if monthly_bank_transactions_df.empty:
            utils.log("No bank transactions found for the selected month.", "warning")
        else:
            proceessed_bank_transactions_df=proceessed_bank_transactions_df[['ID',
                                                                             'TableName', 
                                                                             'Name',
                                                                             'Date', 
                                                                             'Final_Value',
                                                                             'Category',
                                                                             'Extra_Info',
                                                                             'Description',
                                                                             'Transaction_Type']]
            
        proceessed_bank_transactions_df = proceessed_bank_transactions_df.rename(columns={'Date': 'Executed_Date'})
        
        return pd.concat([proceessed_bank_transactions_df, proceessed_card_transactions_df], ignore_index=True)
