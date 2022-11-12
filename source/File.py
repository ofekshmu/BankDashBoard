from abc import abstractmethod
from Constants import log, Local, Personal
import xlwings as xw
from xlwings import Sheet
from os.path import join
from typing import Union
from datetime import datetime
from BankTransactionsFile import BankTransactionsFile


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
        def to_date(str):
            date = str.split("_")
            import datetime
            return datetime.datetime(int(date[2]), int(date[1]), int(date[0]))

        def get_last_file_name(file_date: datetime) -> str:
            from Parser import Parser
            p = Parser()
            lst = []
            while next(p):
                name, type = p.identify()
                if type == BankTransactionsFile:
                    lst.append(name)
            
            # sorted_lst = sorted(date_lst, key=to_date)

            return ""

        file_date = to_date(self.name)
        old_file_name = get_last_file_name(file_date)
        self.table = compare_files(old_file_name, self.name)


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
