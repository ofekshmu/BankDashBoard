from File import File
from src_utils.utils import utils
from database import DataBase
from src_utils.ExcelReader import ExcelManager
from datetime import datetime


class Card(File):
    def __init__(self, name: str, format_info: dict):
        super().__init__(name, format_info)
        self.card_number = "Not Set"
        self.card_number_cell = format_info["Card number cell"]
        self.card_string_format = format_info["Card string format"]

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
        def read_card_number() -> str:
            text = ExcelManager().read_cell(*self.card_number_cell)
            if self.card_string_format is None:
                self.card_string_format = r'\d{4}'

            parsed_text = utils.reg_extract(self.card_string_format, text)
            if len(parsed_text) != 4:
                utils.log(f"The card number read does not meat the requirments:\n\
length is {len(parsed_text)} but should be 4\n\
The value parsed is {parsed_text}", "error")

            return parsed_text
            
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
                    a = int(res.group(1))
                    b = int(res.group(2))
                    if a <= 12 and a > 0:
                        month_number, year_number = a, b
                    elif b <= 12 and b > 0:
                        month_number, year_number = b, a
                    else:
                        utils.log(f"Problem extrcting month, values received are a={a}, b={b}", 'error')
                    
                    if year_number < 100:
                        year_number += 2000
                    # produce a pure date (no time component)
                    time_stamp = datetime(year_number, month_number, 1).date()
                else:
                    utils.log(f"The given time_stamp_format {self.time_stamp_format} for format {self.format_name} did not yield any result\n\
                              You can also check the cell read: {date_str}", 'error')
            else:
                utils.log(f"Error type for variable date_str, expected str/datetime. got ({date_str}) of type {type(date_str)}")

            return time_stamp
        
        self.card_number = read_card_number()
        parsed_date = read_file_date()
  
        # Before adding file to database, A check to see if the file was already inserted to the database is made:
        def check_duplicate() -> bool:
            """
            The function will check if the currently parsed file was allready inserted to the data base,
            based on the card number, format name and date specified in the File database.
            If the file was already inserted, the function will return False else True.
            """
            return DataBase().is_file_exists_v2(self.format_name, self.card_number, parsed_date)

        if check_duplicate():
            utils.log(f"File {self.name} was already inserted to the database.", "error")

        valid_rows = super().parse()


        DataBase().insert_file(self.name,
                               self.format_name,
                               self.card_number,
                               parsed_date,
                               -1,                    # Value is changed after the cleaning process
                               valid_rows)

        return True    
    

    def clean(self):
        """
        """
        return super().clean(flip=True)

    def insert(self) -> bool:
        
        if len(self.table_1) > 0:
            utils.log("Table 1... ", "system", e = "")
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
                case "Isra-Card":

                    DataBase().insert_card_transaction(CardID=self.card_number,
                                                       Name=row[1],
                                                       Executed_Date=utils.date_ready(row[0]),
                                                       Charge_Date=utils.date_ready(self.adittional_data_field_value), # self.adittional_data_field_value/ row[1]
                                                       Charge_Value=row[2],
                                                       Source_file=self.name,
                                                       Charge_Currency=row[3],
                                                       Transaction_Value=row[4],
                                                       Value_Currency=row[5],
                                                       Extra_Info=f"Serial: {row[6]} | Info: ({row[7]})")
                case "Isra-Card-2026":

                    # According to the format json for isra-card-2026,
                    # the first value should hold the year and second should hold the month and the day of the charge
                    # expected format for first value is *Month name in hebrew* *Year(4digits) example: ינואר 2026
                    # expected format for second value is *day(2 digits).month(2 digits)* *לחיוב ב-* exmaple: 02.01 לחיוב ב- 
                    if len(self.adittional_data_field_value) != 2:
                        utils.log(f"Error: For isra-card-2026 format, the adittional data field should contain 2 values, but {len(self.adittional_data_field_value)} were found. Check your format json and the file being parsed.", "error")
                    
                    year = utils.reg_extract(r'\d{4}', self.adittional_data_field_value[0])
                    month_day = utils.reg_extract(r'\d{2}\.\d{2}', self.adittional_data_field_value[1])
                    
                    charge_data = utils.date_ready(f"{month_day}.{year}")

                    DataBase().insert_card_transaction(CardID=self.card_number,
                                                       Name=row[1],
                                                       Executed_Date=utils.date_ready(row[0]),
                                                       Charge_Date=charge_data,
                                                       Charge_Value=row[2],
                                                       Source_file=self.name,
                                                       Charge_Currency=row[3],
                                                       Transaction_Value=row[4],
                                                       Value_Currency=row[5],
                                                       Extra_Info=f"Serial: {row[6]} | Info: ({row[7]})")
                case "American-Express":

                    DataBase().insert_card_transaction(CardID=self.card_number,
                                                       Name=row[1],
                                                       Executed_Date=utils.date_ready(row[0]),
                                                       Charge_Date=utils.date_ready(self.adittional_data_field_value),
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
                case "Cal":
                    if row[3] != row[2]:
                        utils.log("Cal_Sufersal Format cannot handel different currencies - a transaction with different currencies was found", "error")
                    
                    str_charge_date = utils.reg_extract(r'(\d{2}/\d{2}/\d{4})', self.adittional_data_field_value)
                    charge_date = datetime.strptime(str_charge_date, "%d/%m/%Y")
                    
                    DataBase().insert_card_transaction(CardID=self.card_number,
                                                       Name=row[1],
                                                       Executed_Date=row[0],
                                                       Charge_Date=charge_date,
                                                       Charge_Value=row[3],
                                                       Source_file=self.name,
                                                       Charge_Currency="₪",
                                                       Transaction_Value=row[2],
                                                       Value_Currency="₪",
                                                       Extra_Info=f"Type: {row[4]} - {row[5]} | Note: {row[6]}"
                                                       )
                case _:
                    utils.log(f"Internal error: The specified format {self.format_name} does not have a matching \
case in the match-case scope. Card Class, insert function.\
Check if the 'format_name was typed correctly or the case for the specified format\
does not exist.", "error")

        utils.log("Completed ", "system")
        
        if len(self.table_2) > 0:
            utils.log("Table 2... ", "system", e = "")
        for row in self.table_2:
            match self.format_name:
                case "Isra-Card":

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
                case "American-Express":

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
        
        utils.log("Completed ", "system")
        return True

    def __str__(self):
        return f"{self.format_name} of Type 「Card」"
