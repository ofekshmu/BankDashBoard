from ast import Str
from distutils.debug import DEBUG
from msilib.schema import Error
import xlwings as xw
from os import listdir
from os.path import isfile, join
from config import local, Messaging, personal, creditFile
from database import DataBase


class Parser:

    def __init__(self):
        mypath = local.XLSX_PATH

        self.files = []
        for f in listdir(local.XLSX_PATH):
            if isfile(join(local.XLSX_PATH, f)) and f.endswith(local.EXTENSION):
                self.files.append(f)

        if Messaging.SYSTEM:
            print(f'SYSTEM: found {len(self.files)} files in {local.XLSX_PATH} ending with {local.EXTENSION}.')

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

    def parse_credit(self, file_name: str):
        '''
        The function receives the name of a file in the download Folder.
        Returns the data table and the date of the file.
        '''
        # file_name = self.files[1]

        sheet = self.__read(file_name)

        # TODO identify type of File
        
        if not self.__accept_file(file_name, sheet):
            if Messaging.SYSTEM:
                print(f'SYSTEM: File: {file_name} was not parsed.')
            return False
        
        c1, c2 = self.__count_transactions(sheet)

        table1 = self.crop_table(creditFile.HEADER_ROW + 1,
                                 c1,
                                 creditFile.COL_COUNT)
        table2 = self.crop_table(creditFile.HEADER_ROW + 1 + c1 + creditFile.TABLE_SKIP,
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

        if DataBase.file_name_exists(file_name):
            if Messaging.SYSTEM:
                print(f'file: {file_name} - Name already exists.')

        date = sheet['B5'].value
        if DataBase.date_exists(date):
            if Messaging.SYSTEM:
                print(f'date: {date} already exists.')


        count = self.__count_transactions(sheet)
        if count == DataBase.transaction_count(file_name):
            pass
            # TODO decide what happens
        
        return True

        # check the number of transactions and compare. if smaller than existsing-> reparse
        # change row date if file was changed.
        # update the new trans count

    def __count_transactions(self, sheet: xw.Sheet):
        '''
        Count the number of transaction.
        '''
        counter1 = 0
        row = creditFile.HEADER_ROW + 1
        cc_end = self.cell(sheet, row, 0)

        while cc_end.isdigit() and len(cc_end) == 4:
            counter1 += 1
            row += 1
            cc_end = self.cell(sheet, row, 0)

        counter2 = 0
        row += creditFile.TABLE_SKIP
        cc_end = self.cell(sheet, row, 0)
        while cc_end.isdigit() and len(cc_end) == 4:
            counter2 += 1
            row += 1
            cc_end = self.cell(sheet, row, 0)

        return counter1, counter2

    def crop_table(sheet: xw.Sheet, initial_row, row_count, col_count):
        '''
        returns an array of values according to the inserted demensions.
        '''
        return sheet[initial_row: initial_row + row_count, 0: col_count].value

    def __validate_headers(self, sheet: xw.Sheet) -> bool:
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
            if not sheet[f'{chr(col)}{row}'].value == creditFile.HEADERS[i]:
                if Messaging.SYSTEM:
                    print(f'SYSTEM: cell {chr(col)}{row} does not match the expected {creditFile.HEADERS[i]}.\
                            got {sheet[f"{chr(col)}{row}"].value} instead.')
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




