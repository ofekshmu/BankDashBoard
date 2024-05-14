from datetime import datetime
from src_utils.utils import utils
from database import DataBase
import pandas as pd
import os

class ExcelExporter:
    
    @staticmethod
    def export_monthly_data(date: datetime) -> None:
        file_name = f"{date.year}_{date.month}_exported_Data.xlsx"
        relative_path = rf"Outputs\Exported_data\{file_name}"
        if os.path.exists(relative_path):
            msg = f"You Asked to export the data of {date.year}_{date.month},"
            msg += "but the data of this date was allready exported,\n"
            msg += "What do you want to do?"
            if utils.template_menu(["abort", "Overwrite existing file"], msg):
                return
        utils.log(f"Creating file {file_name}...", "system")

        data, columns = DataBase().get_monthly_earnings(date.year, date.month)
        df = pd.DataFrame(data, columns)
        