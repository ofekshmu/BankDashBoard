from File import File
from src_utils.utils import utils
from database import DataBase
from src_utils.ExcelReader import ExcelManager


class Card(File):
    def __init__(self, name: str, format_info: dict):
        super().__init__(name, format_info)
        self.card_number = ""

        self.time_stamp = format_info["TimeStamp"]
        self.time_stamp_format = format_info["TimeStamp Format"]
        self.time_stamp_location = format_info["TimeStamp location"]

    def validate_bank_number(self) -> bool:
        """ Outer credit has no Bank acc number """
        utils.log("Bank number is not being validated for this file", "system")
        return True

    def parse(self) -> bool:
        """
        The parse function for InnerCreditFile updates the following fields:
        self.counter: number of transactions
        self.data: table data in a 2d array
        self.card_num: the card_num specified in the file
        """
        valid_rows = super().parse()
        
        # def is_updated_file():
        #     """
        #     Upon reading a new file, the function will check if a different file,
        #     for the same format and the same month has allready been parsed, if so,
        #     the function will propose to update the old file with the current one.
        #     This feature is only relevant for card files.
        #     """
        #     file_df = DataBase().get_file_table()
        #     condition_mask = (file_df['Date'].dt.month == time_stamp.month) & (file_df['Description'] == self.format_name)
        #     return any(condition_mask)

        # if is_updated_file():
        #     utils.log(f"File name {self.name} should be updated, not newly parsed.The format {self.format_name} is already updated for the relevant month.")
        #     return False

        from datetime import datetime

        def read_file_date() -> datetime:
            time_stamp = ""
            date_str = ""
            from Configurations.Formats import Location
            from datetime import datetime
            import re

            match self.time_stamp:
                case Location.FILE_NAME_DATE:
                    date_str = self.name
                case Location.INNER_CELL:
                    (r, c) = self.time_stamp_location  # TODO: These code line are being reapted, improve
                    date_str = ExcelManager().read_cell(r, c)
                case _:
                    utils.log('error', 'error')

            if date_str is None:
                utils.log('date_st Adittional data field read from the file is None.', 'error')
            pattern = re.compile(self.time_stamp_format)

            if isinstance(date_str, datetime):
                time_stamp = date_str
            elif isinstance(date_str, str):
                res = re.search(pattern, date_str)

                if res:
                    month_number = int(res.group(1))
                    year_number = int(res.group(2))
                    time_stamp = datetime(year_number, month_number, 1)
                else:
                    utils.log(f"The given time_stamp_format {self.time_stamp_format} for format {self.format_name} did not yield any result\n\
                              You can also check the cell read: {date_str}", 'error')
            else:
                utils.log(f"Error type for variable date_str, expected str/datetime. got ({date_str}) of type {type(date_str)}")

            return time_stamp
        
        match self.format_name:
            case "American-Express":
                text = ExcelManager().read_cell(4, 0)
                if text is not None:
                    self.card_number = utils.reg_extract(r'\d{4}', text)
                    value = "Empty"
                else:
                    utils.log("Bad cell read, this cell should have the card number.", "error")
            case "Leumi-Card6744":
                value = "Empty"
            case "Leumi-Cards":
                value = "Empty"
            case "Isra-Card":
                text = ExcelManager().read_cell(4, 0)
                if text is not None:
                    self.card_number = utils.reg_extract(r'\d+', text)
                    value = "Empty"
                else:
                    utils.log("Bad cell read, this cell should have the card number.", "error")
            case None:
                utils.log("None is not a valid 'Adittional data field' unless a specific case was mentioned", "error")
            case _:
                try:
                    (row, col) = self.adittional_data_field
                    value = ExcelManager().read_cell(row, col)
                except Exception as e:
                    utils.log(f"""Trouble reading adittional value from file.
                                    File Name: {self.name}
                                    Format: {self.format_name}
                                    Adottional data field: {self.adittional_data_field}
                            """, "error")

        DataBase().insert_file(self.name,
                               read_file_date(),
                               self.format_name,
                               -1,                    # Value is changed after the cleaning process
                               valid_rows)

        # TODO: Should add some generic field for data inside files
        # self.card_num = self.sheet[self.card_cell].value
        return True

    def clean(self):
        """
        """
        return super().clean(flip=True)

    def insert(self) -> bool:

        for row in self.table_1:
            match self.format_name:
                case "Leumi-Max":
                    DataBase().insert_card_transaction(CardID=row[3],
                                                       Name=row[1],
                                                       Executed_Date=utils.date_ready(row[0]),
                                                       Charge_Date=utils.date_ready(row[9]),
                                                       Charge_Value=row[5],
                                                       Source_file=self.name,
                                                       Charge_Currency=row[6],
                                                       Transaction_Value=row[7],
                                                       Value_Currency=row[8],
                                                       Extra_Info=f"Trans type: {row[4]} | \
                                                                    Method: {row[14]} | \
                                                                    Notes: {row[10]}")
                case "Isra-Card 2922":
                    (r, c) = self.adittional_data_field  # TODO: These code line are being reapted, improve
                    value = ExcelManager().read_cell(r, c)
                    if value is None:
                        utils.log('Adittional data field read from the file is None.', 'error')
                        return False

                    DataBase().insert_card_transaction(CardID=self.card_number,
                                                       Name=row[1],
                                                       Executed_Date=utils.date_ready(row[0]),
                                                       Charge_Date=utils.date_ready(value),
                                                       Charge_Value=row[2],
                                                       Source_file=self.name,
                                                       Charge_Currency=row[3],
                                                       Transaction_Value=row[4],
                                                       Value_Currency=row[5],
                                                       Extra_Info=f"Serial: {row[6]} | Info: ({row[7]})")

                case "American-Express 1565":
                    (r, c) = self.adittional_data_field  # TODO: These code line are being reapted, improve
                    value = ExcelManager().read_cell(r, c)
                    if value is None:
                        utils.log('Adittional data field read from the file is None.', 'error')
                        return False

                    DataBase().insert_card_transaction(CardID="1565",
                                                       Name=row[1],
                                                       Executed_Date=utils.date_ready(row[0]),
                                                       Charge_Date=utils.date_ready(value),
                                                       Charge_Value=row[2],
                                                       Source_file=self.name,
                                                       Charge_Currency=row[3],
                                                       Transaction_Value=row[4],
                                                       Value_Currency=row[5],
                                                       Extra_Info=f"Serial: {row[6]} | Info: ({row[7]})")

                case "Leumi-Card6744":

                    DataBase().insert_card_transaction(CardID="6744",
                                                       Name=row[1],
                                                       Executed_Date=row[0],
                                                       Charge_Date="End of month",
                                                       Charge_Value=row[2],
                                                       Source_file=self.name,
                                                       Charge_Currency="X",
                                                       Transaction_Value=row[5],
                                                       Value_Currency="X",
                                                       Extra_Info=f"Type: {row[3]} | Note: None")
                case "Leumi-Cards":

                    DataBase().insert_card_transaction(CardID=row[0],
                                                       Name=row[2],
                                                       Executed_Date=row[1],
                                                       Charge_Date=row[9],
                                                       Charge_Value=row[3],
                                                       Source_file=self.name,
                                                       Charge_Currency=row[4],
                                                       Transaction_Value=row[5],
                                                       Value_Currency=row[6],
                                                       Extra_Info=f"Type: {row[7]} | Note: None")
                case _:
                    utils.log(f"Internal error: The specified format {self.format_name} does not have a matching\
                              case in the match-case scope. Card Class, insert function.\
                              Check if the 'format_name was typed correctly or the case for the specified format\
                              does not exist.", "error")

        for row in self.table_2:
            match self.format_name:
                case "Isra-Card 2922":

                    DataBase().insert_card_transaction(CardID=self.card_number,
                                                       Name=row[2],
                                                       Executed_Date=utils.date_ready(row[0]),
                                                       Charge_Date=utils.date_ready(row[1]),
                                                       Charge_Value=row[3],
                                                       Source_file=self.name,
                                                       Charge_Currency=row[4],
                                                       Transaction_Value=row[5],
                                                       Value_Currency=row[6],
                                                       Extra_Info="Transaction Abroad")
                case "Leumi-Cards":

                    DataBase().insert_card_transaction(CardID=row[0],
                                                       Name=row[2],
                                                       Executed_Date=row[1],
                                                       Charge_Date=row[9],
                                                       Charge_Value=row[3],
                                                       Source_file=self.name,
                                                       Charge_Currency=row[4],
                                                       Transaction_Value=row[5],
                                                       Value_Currency=row[6],
                                                       Extra_Info=f"Type: {row[7]} | Note: None")
                
                case "American-Express 1565":

                    DataBase().insert_card_transaction(CardID="1565",
                                                       Name=row[2],
                                                       Executed_Date=utils.date_ready(row[0]),
                                                       Charge_Date=utils.date_ready(row[1]),
                                                       Charge_Value=row[3],
                                                       Source_file=self.name,
                                                       Charge_Currency=row[4],
                                                       Transaction_Value=row[5],
                                                       Value_Currency=row[6],
                                                       Extra_Info="Transaction Abroad")
        return True

    def __str__(self):
        return f"{self.format_name} of Type 「Card」"
