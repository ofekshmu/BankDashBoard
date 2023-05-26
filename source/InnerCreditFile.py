from File import File
from Constants import Local
from src_utils.utils import utils
from os.path import join
import xlwings as xw
from xlwings import Sheet
from database import DataBase
from typing import Union
from datetime import datetime

class InnerCreditFile(File):

    def __init__(self,
                 name: str,
                 date_loc: str,
                 bank_num_loc: str,
                 headers,
                 initial_row: int,
                 initial_col: int,
                 table_skip: int):
        super().__init__(name, bank_num_loc, initial_row, headers)
        self.date_loc = date_loc
        self.counter = 0
        self.table_skip = table_skip
        self.initial_col = initial_col
        self.data = []

    def parse(self) -> bool:
        '''
        The parse function for InnerCreditFile updates the following fields:
        self.counter1: number of transactions in the first table
        self.counter2: number of transaction in the second table
        self.data: table1 and table2 data in a 2d array
        self.date: the date specified in the file
        '''
        COL_COUNT = len(self.headers)
        # There might be a way to remove this dict, since data can be read again later
        self.data_dict = {}
        none_counter = 1 + self.table_skip  # Number of "None" fields in the file
        row_index = self.initial_row + 1    # The first data row

        table_row_counter = 0               # Counts the valid rows in each table (A file might have more than one table)
        total_counter = 0                   # The total valid Transations in the file
        initial_table_index = row_index     # The first row of data in a table

        curr_pos = File.cell(row_index, self.initial_col, self.sheet)
        next_pos = File.cell(row_index + 1, self.initial_col, self.sheet)

        def is_valid(value: Union[datetime, None, int, float, str]) -> bool:
            """
            The function returns False if the given values is invalid and True otherwise.
            valid values are one of the specified at the argument Typing.
            """
            if type(value) == datetime:
                return True
            if type(value) == int:
                return True
            if type(value) == float:
                return True
            if value is None:
                return False
            if value.isdigit():
                return True
            return False

        def check_digit(value: Union[datetime, None, int, str]) -> bool:
            """
            The function checks if the given value is a digit.
            It was made after figuring out the the read value can also be in datetime
            format which does not support the "isdigit()" function.
            """
            if type(value) == int:
                return True
            if type(value) == float:
                return True
            if type(value) == str:
                return value.isdigit()
            return False

        while none_counter > 0:
            # If the current row is invalid
            if not is_valid(curr_pos):
                none_counter -= 1
                # If the next row is valid ->
                # Than set the initial index of the next table
                if next_pos is not None and \
                   next_pos.isdigit():
                    initial_table_index = row_index + 1
            # If the current row is valid
            else:
                # Raise the counter for the current and total tables
                table_row_counter += 1
                total_counter += 1

                # Extract data (This might not be needed)
                row = self.sheet[row_index - 1: row_index, self.initial_col: COL_COUNT].value
                self.data.append(row)

                # If the next row is invalid ->
                # Add the data about the current table to db
                # The second conditioning is for establishing between different cards in the table -
                # both current and next are number values but the card changes -> create a new table for it.
                if not is_valid(next_pos) or \
                   (check_digit(next_pos) and check_digit(curr_pos) and curr_pos != next_pos):
                    DataBase().insert_table_meta_data(self.name,
                                                      initial_table_index,
                                                      self.initial_col,
                                                      table_row_counter)
                    # Reset table info
                    table_row_counter = 0
                    initial_table_index = row_index + 1

            # iterate over to the next row
            row_index += 1
            curr_pos = next_pos
            next_pos = File.cell(row_index + 1, self.initial_col, self.sheet)

        if self.date_loc is None:
            date = "Not avaliable"
        else:
            date = self.sheet[self.date_loc].value
        
        DataBase().insert_file(self.name,
                               date,
                               "Auto Insertion",
                               "Not checked",
                               total_counter)

        return True

    def clean(self):
        from Parser import Parser
        self.sorted_names = Parser.getInstance().get_names(InnerCreditFile)

        # TODO: This code is duplicated from the File class, need to improve this!
        def get_last_file_name() -> Union[str, None]:
            """
            Function receives the date of the current file specified in its name
            and returns the name of the most recent file of the same type, in the
            input folder
            """
            idx = self.sorted_names.index(self.name)
            if idx == 0:
                return None
            return self.sorted_names[idx - 1]

        def read_sheet(file_name: str) -> Sheet:
            wb = xw.Book(join(Local.INPUT_FOLDER, file_name))
            return wb.sheets[0]

        def onion(lst):
            if not isinstance(lst[0], list):
                return [lst]
            return lst

        def get_row(table):
            for i, row in enumerate(table):
                if row[8] == "  * תנועות היום":
                    pass
                else:
                    return i, row

        def compare_excel(old_file: dict, new_file: dict):
            """
            file_name1 will be the new excel
            file_name2 will be the old excel
            """

            old_sheet = read_sheet(old_file["name"])
            new_sheet = read_sheet(new_file["name"])
            old_table = old_sheet[old_file["initial_row"]: old_file["initial_row"] + old_file["trans_count"], 0: old_file["col_count"]].value
            new_table = new_sheet[new_file["initial_row"]: new_file["initial_row"] + new_file["trans_count"], 0: new_file["col_count"]].value

            old_table = onion(old_table)
            new_table = onion(new_table)

            i = -1
            index, row = get_row(old_table)
            if row in new_table:
                i = new_table.index(row)
                for j in range(1, len(new_table) - i):
                    if j >= len(old_table) or i + j >= len(new_table):
                        break
                    if old_table[index + j] != new_table[i + j]:
                        return []
            if i == -1:
                return new_table
            return new_table[:i]

        old_file_name = get_last_file_name()
        if old_file_name is None:
            DataBase().set_new_trans_count(self.name, self.counter)
            utils.log(f"{self.name} has not earlier file - Nothing to clean", "system")
            return True

        old_trans_count = DataBase().total_transactions(old_file_name)
        if not old_trans_count:
            utils.log(f"There is a problem retriving transactions for {old_file_name}", "error")

        old_table_stats = DataBase().get_table_Meta(old_file_name)
        curr_table_stats = DataBase().get_table_Meta(self.name)
        cleaned = []
        for curr_info, old_info in zip(curr_table_stats, old_table_stats):
            old_table_i = {"name": old_file_name,
                           "initial_row": old_info[-2] - 1,  # dict value represent the index of the header row (a row before the actual data)
                           "trans_count": old_info[-1],      # Number of transations in the current table
                           "col_count": len(self.headers)}
            new_table_i = {"name": self.name,
                           "initial_row": curr_info[-2] - 1,
                           "trans_count": curr_info[-1],
                           "col_count": len(self.headers)}
            # The current problem is that each table requires its length and i only have the length of the totals transactions
            cleaned += compare_excel(old_table_i, new_table_i)
        tot = sum([x[-1] for x in curr_table_stats])
        utils.log(f'\t     Out of {tot} Transactions, {len(cleaned)} new were found!', '')

        DataBase().set_new_trans_count(self.name, len(cleaned))
        self.data = cleaned
        return True

    def insert(self):
        """

        """
        from datetime import datetime
        import re

        def date_conversion(date) -> datetime:
            if isinstance(date, datetime):
                return date
                return str.replace(month=str.day, day=str.month)
            pattern = "\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{4}"
            str = re.search(pattern, str).group()
            if len(str.split('/')[-1]) == 2:
                str = str[:-2] + "20" + str[-2:]
            if "/" in str:
                return datetime.strptime(str, "%d/%m/%Y")
            else:
                return datetime.strptime(str, "%d-%m-%Y")

        counter = 0
        for row in self.data:
            counter += 1
            DataBase().insert_transaction(cardID=row[0],
                                          transaction_date=date_conversion(row[1]),
                                          business_name=row[2],
                                          amount=-row[3],
                                          transaction_type=row[7],
                                          charge_date=date_conversion(row[-1]),
                                          charge_amount=-row[5],
                                          source_file=self.name)
        return True

    def __str__(self):
        return f"\t -> InnerCreditFile"
