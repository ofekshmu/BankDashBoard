from abc import abstractmethod
from Constants import Local, Personal
from src_utils.utils import utils
import xlwings as xw
from xlwings import Sheet
from os.path import join
from typing import Union
from database import DataBase


class File:
    def __init__(self, name: str, format_info: dict):
        '''
        Read a work book and store an active sheet in the self.sheet.
        File is read from local.XLSX_PATH.
        A File object will be rturned upon successful read.

        Parameters
        ----------
        name: a string indicating the name of the file
        bank_acc_loc: a 2 character string indicating the cell index
        initial row: a number indicating the header row
        headers: a list of string containing table headers
        '''
        self.name = name
        self.format_name = format_info["Format Name"]
        self.context = format_info["Context"]
        self.id_method = format_info["Identification method"]
        self.id_data = format_info["Identification data"]
        self.sortion_method = format_info["Sortion method"]
        self.sortion_key = format_info["Sortion key"]
        self.headers = format_info["Headers"]
        self.header_row_idx = format_info["Header row index"]
        self.adittional_data_field = format_info["Adittional data field"]

        self.data = []

        try:
            wb = xw.Book(join(Local.INPUT_FOLDER, self.name))
            self.sheet = wb.sheets[0]
        except Exception as e:
            utils.log(f"Original error: {str(e)}\nFile read Failed!\nFile name: {self.name}\
                In File -> line 39\nMake sure the file is not open.", 'error')

    def load(self) -> bool:
        '''
        Read a work book and store an active sheet in the self.sheet.
        File is read from local.XLSX_PATH, and true is returned upon succesful read,
        False otherwise.

        Parameters
        ----------
        file_name: a string indicating the name of the file
        '''
        try:
            wb = xw.Book(join(Local.INPUT_FOLDER, self.name))
            self.sheet = wb.sheets[0]
            return True
        except Exception as e:
            utils.log(str(e), category='debug')
            return False

    @abstractmethod
    def validate_bank_number(self) -> bool:
        '''
        The function validates the Bank account specified in the file.
        The cell indicating the number is specified trough the Constants.py
        '''
        if self.bank_num_loc is None:
            return True
        value = self.sheet[self.bank_num_loc].value
        if Personal.BANK_ACC in value:
            return True
        return False

    def validate_headers(self) -> bool:
        '''
        The function validates the table headers in the file.
        The values of the headers and the initial row are given in the Constants.py.
        '''
        # Looks for the headers in a @err area of the given estimated
        err = 2
        for row in range(self.header_row_idx - err, self.header_row_idx + err):
            for i in range(0, 5):
                valid = True
                col = i
                for name in self.headers:
                    utils.log(f'(FILE/Validate_headers) row number = {row}, col = {col}, name = {name[::-1]}', 'debug')
                    value = File.cell(row, col, self.sheet)
                    if not value == name:
                        valid = False
                        break
                    col += 1
                if valid:
                    if row != self.header_row_idx:
                        utils.log(f"Headers were found at line {row}, Not in {self.header_row_idx} as specified.", "warning")
                    self.header_row_idx = row
                    return True
        return False

    @abstractmethod
    def parse(self) -> bool:
        """
        Function responsibility is the complete parse of the data file.
        Currently, 'BankTransactionFile' and 'OuterCreditFile' are using this implementation.
        'Inner credit file is using a different one becuase of the complexity.
        """
        counter = 0
        row = self.header_row_idx + 1
        cc_end = File.cell(row, 0, self.sheet)

        # Empty cell is read as None
        while cc_end is not None:
            counter += 1
            row += 1
            cc_end = File.cell(row, 0, self.sheet)

        self.counter = counter - 1

        # Inset the meta data of the file to db for future reference
        DataBase().insert_table_meta_data(self.name,
                                          self.header_row_idx + 1,
                                          0,
                                          self.counter)

        utils.log("The parse function for catd 2922 is not generic - (-1) is added to ignore last row", "warning")
        utils.log("The parse method in the File class persumes the data is found in the first column.", "warning")

        COL_COUNT = len(self.headers)
        table = self.sheet[self.header_row_idx: self.header_row_idx + self.counter, 0: COL_COUNT].value

        # Happens if table is empty (No transactions)
        if table is None:
            table = []
        # To stay consistent with the data structure
        elif counter == 1:
            table = [table]

        self.data = table

    def clean(self, flip: bool = False) -> bool:
        """
        Function will clean the read data.
        Given a table of transactions, it will change the table to contain only new
        ones which did not appear before.
        """

        def get_last_file_name() -> Union[str, None]:
            """
            Function receives the date of the current file specified in its name
            and returns the name of the most recent file of the same type, in the
            input folder.
            self.sorted_names is defined in the derived class function.
            """
            idx = self.sorted_names.index(self.name)
            if idx == 0:
                return None
            return self.sorted_names[idx - 1]

        def read_sheet(file_name: str) -> Sheet:
            wb = xw.Book(join(Local.INPUT_FOLDER, file_name))
            return wb.sheets[0]

        # def check_payment_string(s: str) -> bool:
        #     import re
        #     pattern = r"תשלום \d+ מתוך \d+"
        #     return bool(re.search(pattern, s))

        def get_row(table):
            for i, row in enumerate(table):
                if len(row) < 9:
                    # this is an if stament sutied for a specific case of isra-card
                    return i, row
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

            if flip:
                if old_file['trans_count'] == 1:
                    old_table = [old_table]
                if new_file['trans_count'] == 1:
                    new_table = [new_table]

                old_table = old_table[::-1]
                new_table = new_table[::-1]

            i = -1
            index, row = get_row(old_table)
            if row in new_table:
                i = new_table.index(row)
                for j in range(1, len(new_table) - i):
                    if j >= len(old_table) or i + j >= len(new_table):
                        break
                    if old_table[index + j] != new_table[i + j]:
                        utils.log(f"""Missmatched trasaction while cleaning the file {self.name},
             in accordance with it's previous {old_file['name']}.
             Try checking index: {index + j} in old table vs {i + j} in new table!
             The rows are:
             => {old_table[index + j]}
             => {new_table[i + j]}

            What do you want to do?
            1 -> Difference in rows doesn't matter, continue as equal.
            2 -> Rows are different, Continue.
            3 -> Something is wrong, stop an let me debug.
            """, category="warning")
                        choise = int(input())
                        if choise == 2:
                            return []
                        elif choise == 3:
                            exit()
            if i == -1:
                return new_table
            return new_table[:i]

        old_file_name = get_last_file_name()
        if old_file_name is None:
            DataBase().set_new_trans_count(self.name, self.counter)
            utils.log(f"{self.name} has not earlier file - Nothing to clean", "system")
            return True

        trans_count = DataBase().total_transactions(old_file_name)
        initial_row = DataBase().get_table_Meta(old_file_name)[0][2]
        if not trans_count:
            utils.log(f"There is a problem retriving transactions for {old_file_name}", "error")
        old_file = {"name": old_file_name,
                    "initial_row": initial_row - 1, # This was previously the header row, need to change
                    "trans_count": trans_count,
                    "col_count": len(self.headers)}
        new_file = {"name": self.name,
                    "initial_row": self.header_row_idx,
                    "trans_count": self.counter,
                    "col_count": len(self.headers)}
        new_table = compare_excel(old_file, new_file)
        utils.log(f'\t     Out of {len(self.data)} Transactions, {len(new_table)} new were found!', '')
        
        DataBase().set_new_trans_count(self.name, len(new_table))
        self.data = new_table
        return True

    @abstractmethod
    def insert(self) -> bool:
        pass

    @staticmethod
    def cell(row: int, col: int, sheet: Sheet) -> Union[str, None]:
        '''
        Returns the value of the cell with indexes [row, col]
        '''
        if row >= 0 and col >= 0:
            return sheet[f'{chr(65 + col)}{row}'].value
        else:
            utils.log(f"Invalid indexes -> ({row}, {col})", "error")
            return ""

    def __str__(self):
        return f"\t -> GenericFileClass"
