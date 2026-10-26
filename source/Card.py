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

    def _read_card_number(self) -> str:
        text = ExcelManager().read_cell(*self.card_number_cell)
        if self.card_string_format is None:
            self.card_string_format = r'\d{4}'

        parsed_text = utils.reg_extract(self.card_string_format, text)
        if len(parsed_text) != 4:
            utils.log(f"The card number read does not meat the requirments:\n\
length is {len(parsed_text)} but should be 4\n\
The value parsed is {parsed_text}", "error")

        return parsed_text

    def _read_file_date(self) -> datetime:
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
                time_stamp = datetime(year_number, month_number, 1)
            else:
                utils.log(f"The given time_stamp_format {self.time_stamp_format} for format {self.format_name} did not yield any result\n\
                          You can also check the cell read: {date_str}", 'error')
        else:
            utils.log(f"Error type for variable date_str, expected str/datetime. got ({date_str}) of type {type(date_str)}")

        return time_stamp

    def parse(self) -> bool:
        """
        The parse function for InnerCreditFile updates the following fields:
        self.counter: number of transactions
        self.data: table data in a 2d array
        self.card_num: the card_num specified in the file
        """
        self.card_number = self._read_card_number()
        parsed_date = self._read_file_date()
        self.file_date = parsed_date

        if self.dry_run:
            # read-only pass (read_for_compare): only the tables' layout is collected
            super().parse()
            return True

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

        # The File row must exist before parse() can insert TableMeta rows for it
        # (TableMeta.File_Name/Format/Card_Number has a foreign key onto File).
        # Transaction_count isn't known until parsing finishes, so insert a
        # placeholder now and correct it below.
        DataBase().insert_file(self.name,
                               self.format_name,
                               self.card_number,
                               parsed_date,
                               -1,                    # Value is changed after the cleaning process
                               -1)

        valid_rows = super().parse()

        DataBase().set_transaction_count(self.name, self.format_name, self.card_number, valid_rows)

        return True

    def read_for_compare(self) -> bool:
        """
        Read-only pass over the file in the input folder: opens it, validates the headers, reads the
        card number, the month and both tables into self.table_1 / self.table_2 and self.meta.
        Nothing is written to the database. Returns False when the file cannot be read.
        """
        self.dry_run = True
        self.meta = []
        if not self.load() or not self.validate_headers():
            return False
        self.parse()
        from Constants import Paths
        self.table_1, self.table_2 = self.read_tables(self.meta, Paths.INPUT_FOLDER)
        return True

    def clean(self):
        """
        """
        return super().clean(flip=True)

    def records(self) -> list:
        """
        The rows of both tables as dicts with the CardTransactions columns (lower-case keys:
        cardid, name, executed_date, charge_date, charge_value, source_file, charge_currency,
        transaction_value, value_currency, extra_info) — exactly what insert() stores.
        """
        records = []
        for row in self.table_1:
            match self.format_name:
                case "Leumi-Max":
                    records.append(dict(cardid=row[3],
                                                       name=row[1],
                                                       executed_date=utils.date_ready(row[0]),
                                                       charge_date=utils.date_ready(row[9]),
                                                       charge_value=row[5],
                                                       source_file=self.name,
                                                       charge_currency=row[6],
                                                       transaction_value=row[7],
                                                       value_currency=row[8],
                                                       extra_info=f"Trans type: {row[4]} | \
                                                                    Method: {row[14]} | \
                                                                    Notes: {row[10]}"))
                case "Isra-Card":

                    records.append(dict(cardid=self.card_number,
                                                       name=row[1],
                                                       executed_date=utils.date_ready(row[0]),
                                                       charge_date=utils.date_ready(self.adittional_data_field_value), # self.adittional_data_field_value/ row[1]
                                                       charge_value=row[2],
                                                       source_file=self.name,
                                                       charge_currency=row[3],
                                                       transaction_value=row[4],
                                                       value_currency=row[5],
                                                       extra_info=f"Serial: {row[6]} | Info: ({row[7]})"))
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

                    records.append(dict(cardid=self.card_number,
                                                       name=row[1],
                                                       executed_date=utils.date_ready(row[0]),
                                                       charge_date=charge_data,
                                                       charge_value=row[2],
                                                       source_file=self.name,
                                                       charge_currency=row[3],
                                                       transaction_value=row[4],
                                                       value_currency=row[5],
                                                       extra_info=f"Serial: {row[6]} | Info: ({row[7]})"))
                case "American-Express":

                    records.append(dict(cardid=self.card_number,
                                                       name=row[1],
                                                       executed_date=utils.date_ready(row[0]),
                                                       charge_date=utils.date_ready(self.adittional_data_field_value),
                                                       charge_value=row[2],
                                                       source_file=self.name,
                                                       charge_currency=row[3],
                                                       transaction_value=row[4],
                                                       value_currency=row[5],
                                                       extra_info=f"Serial: {row[6]} | Info: ({row[7]})"))
                case "Leumi-Card6744":

                    records.append(dict(cardid="6744",
                                                       name=row[1],
                                                       executed_date=row[0],
                                                       charge_date="End of month",
                                                       charge_value=row[2],
                                                       source_file=self.name,
                                                       charge_currency="X",
                                                       transaction_value=row[5],
                                                       value_currency="X",
                                                       extra_info=f"Type: {row[3]} | Note: None"))
                case "Leumi-Cards":

                    records.append(dict(cardid=row[0],
                                                       name=row[2],
                                                       executed_date=row[1],
                                                       charge_date=row[9],
                                                       charge_value=row[3],
                                                       source_file=self.name,
                                                       charge_currency=row[4],
                                                       transaction_value=row[5],
                                                       value_currency=row[6],
                                                       extra_info=f"Type: {row[7]} | Note: None"))          
                case "Cal":
                    str_charge_date = utils.reg_extract(r'(\d{2}/\d{2}/\d{4})', self.adittional_data_field_value)
                    charge_date = datetime.strptime(str_charge_date, "%d/%m/%Y")

                    charge_value, charge_currency = row[2]
                    transaction_value, value_currency = row[3]

                    records.append(dict(cardid=self.card_number,
                                                       name=row[1],
                                                       executed_date=row[0],
                                                       charge_date=charge_date,
                                                       charge_value=charge_value,
                                                       source_file=self.name,
                                                       charge_currency=charge_currency,
                                                       transaction_value=transaction_value,
                                                       value_currency=value_currency,
                                                       extra_info=f"Type: {row[4]} - {row[5]} | Note: {row[6]}"
                                                       ))
                case _:
                    utils.log(f"Internal error: The specified format {self.format_name} does not have a matching \
case in the match-case scope. Card Class, insert function.\
Check if the 'format_name was typed correctly or the case for the specified format\
does not exist.", "error")

        for row in self.table_2:
            match self.format_name:
                case "Isra-Card":

                    records.append(dict(cardid=self.card_number,
                                                       name=row[2],
                                                       executed_date=utils.date_ready(row[0]),
                                                       charge_date=utils.date_ready(row[1]),
                                                       charge_value=row[3],
                                                       source_file=self.name,
                                                       charge_currency=row[4],
                                                       transaction_value=row[5],
                                                       value_currency=row[6],
                                                       extra_info="Transaction Abroad"))
                case "Leumi-Cards":

                    records.append(dict(cardid=row[0],
                                                       name=row[2],
                                                       executed_date=row[1],
                                                       charge_date=row[9],
                                                       charge_value=row[3],
                                                       source_file=self.name,
                                                       charge_currency=row[4],
                                                       transaction_value=row[5],
                                                       value_currency=row[6],
                                                       extra_info=f"Type: {row[7]} | Note: None"))                
                case "American-Express":

                    records.append(dict(cardid=self.card_number,
                                                       name=row[2],
                                                       executed_date=utils.date_ready(row[0]),
                                                       charge_date=utils.date_ready(row[1]),
                                                       charge_value=row[3],
                                                       source_file=self.name,
                                                       charge_currency=row[4],
                                                       transaction_value=row[5],
                                                       value_currency=row[6],
                                                       extra_info="Transaction Abroad"))
        
        return records

    def insert(self) -> bool:
        records = self.records()
        utils.log(f"Inserting {len(records)} transactions... ", "system", e = "")
        for r in records:
            DataBase().insert_card_transaction(CardID=r['cardid'],
                                               Name=r['name'],
                                               Executed_Date=r['executed_date'],
                                               Charge_Date=r['charge_date'],
                                               Charge_Value=r['charge_value'],
                                               Source_file=r['source_file'],
                                               Charge_Currency=r['charge_currency'],
                                               Transaction_Value=r['transaction_value'],
                                               Value_Currency=r['value_currency'],
                                               Extra_Info=r['extra_info'])
        utils.log("Completed ", "system")
        return True

    def __str__(self):
        return f"{self.format_name} of Type 「Card」"
