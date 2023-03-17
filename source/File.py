from abc import abstractmethod
from Constants import log, Local, Personal
import xlwings as xw
from xlwings import Sheet
from os.path import join
from typing import Union
from datetime import datetime
from Constants import BankTransactions
from database import DataBase


class File:
    def __init__(self,
                 name: str,
                 bank_num_loc: str,
                 initial_row: int,
                 headers: list):
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
        self.bank_num_loc = bank_num_loc
        self.initial_row = initial_row
        self.headers = headers

        try:
            wb = xw.Book(join(Local.XLSX_PATH, self.name))
            self.sheet = wb.sheets[0]
        except Exception as e:
            log(f"Original error: {str(e)}\nFile read Failed!\nFile name: {self.name}\
                In File -> line 39", 'error')

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
            wb = xw.Book(join(Local.XLSX_PATH, self.name))
            self.sheet = wb.sheets[0]
            return True
        except Exception as e:
            log(str(e), category='debug')
            return False

    @abstractmethod
    def validate_bank_number(self) -> bool:
        '''
        The function validates the Bank account specified in the file.
        The cell indicating the number is specified trough the Constants.py
        '''
        value = self.sheet[self.bank_num_loc].value
        if Personal.BANK_ACC in value:
            return True
        return False

    def validate_headers(self) -> bool:
        '''
        The function validates the table headers in the file.
        The values of the headers and the initial row are given in the Constants.py.
        '''
        err = 2
        for i in range(self.initial_row - err, self.initial_row + err):
            valid = True
            col = 0
            row = i
            for name in self.headers:
                log(f'row number = {row}, col = {col}, name = {name[::-1]}', 'debug')
                value = File.cell(row, col, self.sheet)
                if not value == name:
                    valid = False
                    break
                col += 1
            if valid:
                if row != self.initial_row:
                    log(f"\n\tHeaders were found at line {row}, Not in {self.initial_row} as specified.", "warning")
                self.initial_row = row
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
        row = self.initial_row + 1
        cc_end = File.cell(row, 0, self.sheet)

        # Empty cell is read as None
        while cc_end is not None:
            counter += 1
            row += 1
            cc_end = File.cell(row, 0, self.sheet)

        self.counter = counter

        # Inset the meta data of the file to db for future reference
        DataBase().insert_table_meta_data(self.name,
                                          self.initial_row + 1,
                                          self.counter)

        COL_COUNT = len(self.headers)
        table = self.sheet[self.initial_row: self.initial_row + self.counter, 0: COL_COUNT].value

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
            input folder
            """
            idx = self.sorted_names.index(self.name)
            if idx == 0:
                return None
            return self.sorted_names[idx - 1]

        def read_sheet(file_name: str) -> Sheet:
            wb = xw.Book(join(Local.XLSX_PATH, file_name))
            return wb.sheets[0]

        # def check_payment_string(s: str) -> bool:
        #     import re
        #     pattern = r"תשלום \d+ מתוך \d+"
        #     return bool(re.search(pattern, s))

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

            if flip:
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
                        log(f"""Missmatched trasaction while cleaning the file {self.name},
             in accordance with it's previous {old_file['name']}.
             Try checking index: {index + j} in old table vs {i + j} in new table!
             The rows are:
             => {old_table[index + j]}
             => {new_table[i + j]}""", "warning")
                        return []
            if i == -1:
                return new_table
            return new_table[:i]

        old_file_name = get_last_file_name()
        if old_file_name is None:
            DataBase().set_new_trans_count(self.name, self.counter)
            log(f"{self.name} has not earlier file - Nothing to clean", "system")
            return True

        trans_count = DataBase().total_transactions(old_file_name)
        initial_row = DataBase().get_table_Meta(old_file_name)[0][2]
        if not trans_count:
            log(f"There is a problem retriving transactions for {old_file_name}", "error")
        old_file = {"name": old_file_name,
                    "initial_row": initial_row - 1, # This was previously the header row, need to change
                    "trans_count": trans_count,
                    "col_count": len(self.headers)}
        new_file = {"name": self.name,
                    "initial_row": self.initial_row,
                    "trans_count": self.counter,
                    "col_count": len(self.headers)}
        new_table = compare_excel(old_file, new_file)
        log(f'Out of {len(self.data)} Transactions, {len(new_table)} new were found!', 'system')
        
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
            log(f"Invalid indexes -> ({row}, {col})", "error")
            return ""

    def __str__(self):
        return f"\t -> GenericFileClass"
