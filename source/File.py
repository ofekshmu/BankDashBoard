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
            log(str(e), 'error')

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
        col = 0
        row = self.initial_row
        for name in self.headers:
            log(f'row number = {row}, col = {col}, name = {name[::-1]}', 'debug')
            value = File.cell(row, col, self.sheet)
            if not value == name:
                log(f"""cell ->[{row},{col}]<- did not match the expected value ->{name[::-1]}<-.
got ->{value[::-1]}<- instead.""", category='error')
                return False
            col += 1
        return True

    @abstractmethod
    def parse(self) -> bool:
        pass

    def clean(self) -> bool:
        """
        Function will clean the read data.
        Given a table of transactions, it will change the table to contain only new
        ones which did not appear before.
        """
        def to_date(name: str) -> datetime:
            import re
            date_str = re.search("\w{1,2}_\w{1,2}_\w{4}", name).group()
            date = date_str.split("_")
            import datetime
            return datetime.datetime(int(date[2]), int(date[1]), int(date[0]))

        def get_last_file_name(file_date: datetime) -> Union[str, None]:
            """
            Function receives the date of the current file specified in its name
            and returns the name of the most recent file of the same type, in the
            input folder
            """
            from Parser import Parser
            p = Parser()
            lst = []
            while next(p):
                name, type = p.identify()
                # if type == BankTransactionsFile:
                log('THE SYSTEM DOES NOT RECOGNIZE BETWEEN FILES', 'system')
                lst.append(name)

            dict = {to_date(name): name for name in lst}
            sorted_dates = sorted(dict.keys())
            idx = sorted_dates.index(file_date)
            if idx == 0:
                return None
            chosen_date = sorted_dates[idx - 1]
            return dict[chosen_date]

        def read_sheet(file_name: str) -> Sheet:
            wb = xw.Book(join("C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Inputs", file_name))
            return wb.sheets[0]

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

            i = -1
            index, row = get_row(old_table)
            if row in new_table:
                i = new_table.index(row)
                for j in range(1, len(new_table) - i):
                    if j >= len(old_table) or i + j >= len(new_table):
                        break
                    if old_table[index + j] != new_table[i + j]:
                        return []
            return new_table[:i]

        file_date = to_date(self.name)
        old_file_name = get_last_file_name(file_date)
        if old_file_name is None:
            log(f"{self.name} has not earlier file - Nothing to clean", "system")
            return True

        trans_count = DataBase().transaction_count(old_file_name)
        if not trans_count:
            log(f"There is a problem retriving transactions for {old_file_name}", "error")
        old_file = {"name": old_file_name,
                    "initial_row": BankTransactions.INITIAL_ROW,
                    "trans_count": trans_count,
                    "col_count": len(BankTransactions.HEADERS)}
        new_file = {"name": self.name,
                    "initial_row": BankTransactions.INITIAL_ROW,
                    "trans_count": self.counter,
                    "col_count": len(BankTransactions.HEADERS)}
        new_table = compare_excel(old_file, new_file)
        log(f'Out of {len(self.table)} Transactions, {len(new_table)} new were found!', 'system')
        self.table = new_table
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
