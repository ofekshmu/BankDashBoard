from ast import Str
from asyncio import constants
from distutils.debug import DEBUG
from msilib.schema import Error
from unicodedata import category
import xlwings as xw
from os import listdir
from os.path import isfile, join
from config import local, Messaging, personal, creditFile
from database import DataBase
from source.config import log


class Parser:

    def __init__(self):

        self.sheet = None
        self.files = []
        for f in listdir(local.XLSX_PATH):
            if isfile(join(local.XLSX_PATH, f)) and f.endswith(local.EXTENSION):
                self.files.append(f)

        log(f'SYSTEM: found {len(self.files)} files in {local.XLSX_PATH} ending with {local.EXTENSION}.', category='system')

    def get_files(self) -> list[str]:
        '''
        Returns the names of all the xls files in the Downloads directory.
        '''
        return self.files

    def __read(self, file_name: str):
        if Messaging.DEBUG:
            print(f'DEBUG: reading file...\n\t{file_name}')
        wb = xw.Book(join(local.XLSX_PATH, file_name))
        sheet = wb.sheets[0]
        if Messaging.SYSTEM:
            print('SYSTEM: WorkBook Loaded succesfuly.')
        return sheet

    def read(self, file_name: str):
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

    def validate(self):
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

    def parse_credit(self, file_name: str):
        '''
        The function receives the name of a file in the download Folder.
        Returns the data table and the date of the file.
        '''
        # file_name = self.files[1]

        sheet = self.__read(file_name)

        # TODO identify type of File

        if not self.__accept_file(file_name, sheet):
            log(f'SYSTEM: File: {file_name} is not Valid.', category='system')
            return False
        else:
            log(f'SYSTEM: File: {file_name} is Valid. Starting parse...', category='system')
        # -----------------------------------------------------------
        date_b = False
        name_b = False
        
        if DataBase().file_name_exists(file_name):
            name_b = True
            log(f'SYSTEM: {file_name} - Name already exists.', category='system')

        date = sheet[creditFile.DATE].value
        if DataBase().date_exists(date):
            date_b = True
            log(f'SYSTEM: {date} already exists.',category='system')

        c1, c2 = self.__count_transactions(sheet)
        log(f'c1: {c1} , c2: {c2}', category='debug')
        if date_b and name_b:
            count_existing = DataBase().transaction_count(file_name)
            if Messaging.DEBUG:
                print(f'count_existing: {count_existing}')
            if count_existing == c1 + c2:
                if Messaging.SYSTEM:
                    print(f'SYSTEM: Skipping File...')
            elif count_existing < c1 + c2:
                if Messaging.SYSTEM:
                    print(f'SYSTEM: Updating file...')
                    print(f"\n{'-'*30}\nSYSTEM: TODO THIS...\n{'-'*30}\n")
        else:
            if Messaging.SYSTEM:
                print(f'SYSTEM: date is {date_b} | name is {name_b}')
                print(f'SYSTEM: adding {file_name} to db.')
                DataBase().insert_file(file_name,
                                       date,
                                       description="Nothing",
                                       trans_count=c1 + c2)

        # -----------------------------------------------------------
        table1 = self.crop_table(sheet,
                                 creditFile.HEADER_ROW,
                                 c1,
                                 creditFile.COL_COUNT)
        table2 = self.crop_table(sheet,
                                 creditFile.HEADER_ROW + c1 + creditFile.TABLE_SKIP,
                                 c2,
                                 creditFile.COL_COUNT)

        return table1 + table2

    def __accept_file(self, file_name: str, sheet: xw.Sheet) -> bool:

        if sheet['B3'].value != personal.BANK_ACC:
            if Messaging.SYSTEM:
                print(f'SYSTEM: Bank Account number does not match!')
            return False
        if Messaging.SYSTEM:
            print('SYSTEM: Bank account number match.')
        
        if self.__validate_headers(sheet):
            print('Credit sheet is valid.')
        else:
            print('Credit sheet is INVALID')
            return False

        return True

    def __count_transactions(self, sheet: xw.Sheet):
        '''
        Count the number of transaction.
        '''
        counter1 = 0
        row = creditFile.HEADER_ROW + 1
        cc_end = self.cell(sheet, row, 0)
        if Messaging.DEBUG:
            print(f'DEBUG: In function "__count_transactions":')
            print(f'DEBUG: cc_end = {cc_end}')
            print(f'DEBUG: cc_end type: {type(cc_end)}')
        while cc_end.isdigit() and len(cc_end) == 4:
            counter1 += 1
            row += 1
            cc_end = self.cell(sheet, row, 0)
            if Messaging.DEBUG:
                print(f'DEBUG: cc_end = {cc_end}, counter = {counter1}, row = {row}')
            if cc_end is None:
                break

        counter2 = 0
        row += creditFile.TABLE_SKIP
        cc_end = self.cell(sheet, row, 0)
        while cc_end.isdigit() and len(cc_end) == 4:
            counter2 += 1
            row += 1
            cc_end = self.cell(sheet, row, 0)
            if Messaging.DEBUG:
                print(f'DEBUG: cc_end = {cc_end}, counter = {counter1}, row = {row}')
            if cc_end is None:
                break

        return counter1, counter2

    def crop_table(self, sheet: xw.Sheet, initial_row, row_count, col_count):
        '''
        returns an array of values according to the inserted demensions.
        '''
        table = sheet[initial_row: initial_row + row_count, 0: col_count].value
        return [table] if row_count == 1 else table

    def __validate_headers(self) -> bool:
        '''
        The functions validates the credit file's structure.
        Returns true if the Bank account number and table headers location
        and value match, False otherwise

        Parameters:
        -----------
        sheet: xw.Sheet
            The sheet to validate.
        '''

        # Validating headers
        for i in range(0, len(creditFile.HEADERS)):
            col = 65 + i  # 65 is for 'A' in ascii
            row = 10
            if not self.sheet[f'{chr(col)}{row}'].value == creditFile.HEADERS[i]:
                if Messaging.SYSTEM:
                    print(f'SYSTEM: cell {chr(col)}{row} does not match the expected {creditFile.HEADERS[i]}.\
                            got {self.sheet[f"{chr(col)}{row}"].value} instead.')
                    return False
        return True

    def cell(self, sheet: xw.Sheet, row: int, col: int) -> str:
        '''
        Returns the value of the cell with indexes [row, col]
        '''
        if row >= 0 and col >= 0:
            return sheet[f'{chr(65 + col)}{row}'].value
        else:
            raise Error("Invalid indexes.")




