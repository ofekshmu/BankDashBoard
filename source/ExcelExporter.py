from datetime import datetime
from src_utils.utils import utils
from database import DataBase
import pandas as pd
from src_utils.calculations import SimpleMath
import os

class ExcelExporter:
    
    @staticmethod
    def export_monthly_data(date: datetime) -> None:
        file_name = f"{date.year}_{date.month}_exported_Data.xlsx"
        relative_path = rf"Outputs/Exported_data/{file_name}.xlsx"
        if os.path.exists(relative_path):
            msg = f"You Asked to export the data of {date.year}_{date.month},"
            msg += "but the data of this date was allready exported,\n"
            msg += "What do you want to do?"
            if utils.template_menu(["abort", "Overwrite existing file"], msg):
                return
        utils.log(f"Creating file {file_name}...", "system")

        spendings, description = DataBase().get_monthly_spendings(date.year, date.month)
        spendings_df = SimpleMath.process_prices(spendings, description)

        earnings, description = DataBase().get_monthly_earnings(date.year, date.month)
        earnings_df = SimpleMath.process_prices(earnings, description)

        # Create a Pandas Excel writer using XlsxWriter as the engine
        writer = pd.ExcelWriter(relative_path, engine='xlsxwriter')

        # Write each dataframe to a separate worksheet
        earnings_df.to_excel(writer, sheet_name='Earnings', index=True)
        spendings_df.to_excel(writer, sheet_name='Spendings', index=False)

        # Close the Pandas Excel writer and output the Excel file
        writer.close()