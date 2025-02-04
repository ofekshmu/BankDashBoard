from datetime import datetime, date
from database import DataBase
from typing import Tuple
import pandas as pd

class Exporter:

    def __init__(self):
        self.time_stamp = generate_timestamp()

    def export_bank_transactions(self, since_d: date = date(2000, 1, 1)) -> Tuple[pd.DataFrame, pd.DataFrame]:
        return DataBase().get_all_transactions_since(since_d)

    def add_sheet(self, sheet_name: str, bank_df: pd.DataFrame, card_df: pd.DataFrame,
                  excel_name : str = "Exported_data", excel_path : str = "Outputs\Exported_data") -> None:
        """
        
        """
        
        full_path = excel_path + '\\' + excel_name + '\\' + self.time_stamp

        # Create an Excel writer object and write DataFrames to different sheets
        with pd.ExcelWriter(full_path, engine='xlsxwriter') as writer:
            card_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=0)
            bank_df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=len(card_df) + 2)


    def generate_excel_file(self, df_lst: list, name_lst: list) -> None:
        """
        
        """
        # Define the Excel file name
        excel_filename = "Transactions_" + generate_timestamp()

        # Create an Excel writer object and write DataFrames to different sheets
        with pd.ExcelWriter(excel_filename, engine='xlsxwriter') as writer:
            for df, name in zip(df_lst, name_lst):
                df.to_excel(writer, sheet_name=name, index=False)
    

def generate_timestamp() -> str:
    return datetime.now().strftime("%d-%m-%Y %H-%M")