from ast import Str
from asyncio import constants
from distutils.debug import DEBUG
from msilib.schema import Error
from unicodedata import category
import xlwings as xw
from os import listdir
from os.path import isfile, join
from config import local, Messaging, personal, creditFile, log
from database import DataBase


class Parser:

    def __init__(self):

        self.sheet = None
        self.files = []
        for f in listdir(local.XLSX_PATH):
            if isfile(join(local.XLSX_PATH, f)) and f.endswith(local.EXTENSION):
                self.files.append(f)

        log(f'found {len(self.files)} files in {local.XLSX_PATH} ending with {local.EXTENSION}.', category='system')

    def get_files(self) -> list[str]:
        '''
        Returns the names of all the xls files in the Downloads directory.
        '''
        return self.files

    def read(self, file_name: str) -> bool:
        '''
        Read a work book and store an active sheet in the self.sheet.
        File is read from local.XLSX_PATH, and true is returned upon succesful read,
        False otherwise.

        Parameters
        ----------
        file_name: a string indicating the name of the file
        '''
        try:
            log(f'Reading {file_name}...', category='system')
            wb = xw.Book(join(local.XLSX_PATH, file_name))
            self.sheet = wb.sheets[0]
            log(f'WorkBook Loaded succesfuly.', category='system')
            return True
        except Exception as e:
            log(e, category='debug')
            log(f'Failed reading file: {file_name}', category='error')
            return False

    def validate(self) -> bool:
        '''
        The function validates the file's validity by comparing known data
        to the variables in the config file.
        Table header names and bank account number is checked and returns
        True if both are valid, False otherwise.
        '''
        if self.sheet is None:
            log(f'No sheet loaded: self.sheet is None', category='error')
            return False
        else:
            s = self.sheet
            if s[creditFile.BANK_ACC].value != personal.BANK_ACC:
                log(f'Bank Account number does not match!', category='system')
                return False
            log('Bank account number match.', category='system')

            if not self.__validate_headers():
                log('Credit sheet is INVALID', category='system')
                return False
            log('Credit sheet is valid.', category='system')

            return True

    def get_metadata(self):
        '''
        Returns the date and the total transactions of the current file read.
        '''
        if self.sheet is None:
            log(f'No sheet loaded: self.sheet is None', category='error')
            return False
        else:
            date = self.sheet[creditFile.DATE].value
            c1, c2 = self.__count_transactions(self.sheet)
            return date, c1, c2

    def get_transactions(self):
        '''
        The function returns all the transactions in the active file.
        Transactions are returned as a List of Lists.
        '''
        c1, c2 = self.__count_transactions(self.sheet)
        table1 = self.crop_table(creditFile.HEADER_ROW,
                                 c1,
                                 creditFile.COL_COUNT)
        table2 = self.crop_table(creditFile.HEADER_ROW + c1 + creditFile.TABLE_SKIP,
                                 c2,
                                 creditFile.COL_COUNT)

        return table1 + table2

    def __count_transactions(self, sheet: xw.Sheet):
        '''
        Count the number of transaction.
        The function Takes into account 2 different charts by using the
        'skip' constant indicating the number of empty rows between charts.
        '''
        counter1 = 0
        row = creditFile.HEADER_ROW + 1
        cc_end = self.cell(row, 0)
        if Messaging.DEBUG:
            print(f'DEBUG: In function "__count_transactions":')
            print(f'DEBUG: cc_end = {cc_end}')
            print(f'DEBUG: cc_end type: {type(cc_end)}')
        while cc_end.isdigit() and len(cc_end) == 4:
            counter1 += 1
            row += 1
            cc_end = self.cell(row, 0)
            if Messaging.DEBUG:
                print(f'DEBUG: cc_end = {cc_end}, counter = {counter1}, row = {row}')
            if cc_end is None:
                break

        counter2 = 0
        row += creditFile.TABLE_SKIP
        cc_end = self.cell(row, 0)
        while cc_end.isdigit() and len(cc_end) == 4:
            counter2 += 1
            row += 1
            cc_end = self.cell(row, 0)
            if Messaging.DEBUG:
                print(f'DEBUG: cc_end = {cc_end}, counter = {counter1}, row = {row}')
            if cc_end is None:
                break

        return counter1, counter2

    def crop_table(self, initial_row, row_count, col_count):
        '''
        returns an array of values according to the inserted demensions.
        
        Parameters
        ----------
        initial_row: The index of the row with the header names
        row_count: The number of total rows with data (transactions)
        col_count: The number of columns in the table
        '''
        table = self.sheet[initial_row: initial_row + row_count, 0: col_count].value
        return [table] if row_count == 1 else table

    def __validate_headers(self) -> bool:
        '''
        The functions validates the credit file's structure.
        Returns true if the Bank account number and table headers location
        and value match, False otherwise
        '''
        col = 0
        row = creditFile.HEADER_ROW
        for name in creditFile.HEADERS:
            log(f'row = {row}, col = {col}, name = {name[::-1]}', category='debug')
            if not self.cell(row, col) == name:
                log(f'cell [{row},{col}] does not match the expected {name[::-1]}.\
                            got {self.cell(row, col)[::-1]} instead.', category='error')
                return False
            col += 1
        return True

    def cell(self, row: int, col: int) -> str:
        '''
        Returns the value of the cell with indexes [row, col]
        '''
        if row >= 0 and col >= 0:
            return self.sheet[f'{chr(65 + col)}{row}'].value
        else:
            raise Error("Invalid indexes.")




