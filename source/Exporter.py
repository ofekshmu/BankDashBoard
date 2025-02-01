from datetime import datetime, date
from database import DataBase
import pandas as pd

class Exporter:
    
    def export_bank_transactions(self, since_d: date = date(2000, 1, 1)) -> pd.DataFrame:
        return DataBase().get_all_transactions_since(since_d)

    def generate_excel_file(self, df_lst: list, name_lst: list) -> None:
        # Define the Excel file name
        excel_filename = "Transactions_" + generate_timestamp()

        # Create an Excel writer object and write DataFrames to different sheets
        with pd.ExcelWriter(excel_filename, engine='xlsxwriter') as writer:
            for df, name in zip(df_lst, name_lst):
                df.to_excel(writer, sheet_name=name, index=False)
    

def generate_timestamp() -> str:
    return datetime.now().strftime("%d-%m-%Y %H-%M")