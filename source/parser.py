from ast import Str
from distutils.debug import DEBUG
from msilib.schema import Error
import xlwings as xw
from os import listdir
from os.path import isfile, join
from config import local, Messaging, personal, creditFile


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

    def parse_credit(self, file_name: str = None):
        '''
        The function receives the name of a file in the download Folder.
        Returns the data table and the date of the file.
        '''
        # file_name = self.files[1]

        if Messaging.DEBUG:
            print(f'DEBUG: reading file...\n\t{file_name}')
        wb = xw.Book(join(local.XLSX_PATH, file_name))
        sheet = wb.sheets[0]
        if Messaging.SYSTEM:
            print('SYSTEM: WorkBook Loaded succesfuly.')

        if self.__validate_credit(sheet):
            print('Credit sheet is valid.')
        else:
            print('Credit sheet is INVALID')
            return False

        row = 11  # initial row in table
        cc_end = self.cell(sheet, row, 0)  # cc stands for credits card

        if Messaging.DEBUG:
            print(f"DEBUG: This is the Call before entering the While\n\
                Cell value is {cc_end}, type is {type(cc_end)}")
        # Should also check if card exists in db TODO
        while cc_end.isdigit() and len(cc_end) == 4:
            row += 1
            cc_end = self.cell(sheet, row, 0)
            if cc_end is None:
                break
        
        col_count = len(creditFile.HEADERS)
        last_row = row - 1
        table = sheet[11:last_row, 0:col_count].value

        date = sheet['B5'].value
        return table, date

    def __validate_credit(self, sheet: xw.Sheet) -> False:
        '''
        The functions validates the credit file's structure.
        Returns true if the Bank account number and table headers location
        and value match, False otherwise

        Parameters:
        -----------
        sheet: xw.Sheet
            The sheet to validate.
        '''
        # validating bank account number
        if sheet['B3'].value != personal.BANK_ACC:
            if Messaging.SYSTEM:
                print(f'SYSTEM: Bank Account number does not match!')
            return False
        if Messaging.SYSTEM:
            print('SYSTEM: Bank account number match.')

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
