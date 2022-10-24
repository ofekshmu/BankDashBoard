from abc import abstractmethod
from Constants import log, Local
import xlwings as xw
from os.path import join


class File:
    def __init__(self, name: str):
        self.name = name
        self.sheet = xw.Sheet()
        self.constants = None

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
    def validate(self):
        '''
        The function validates the file's validity by comparing known data
        to the variables in the config file.
        Table header names and bank account number is checked and returns
        True if both are valid, False otherwise.
        '''
        s = self.sheet
        consts = self.constants
        temp = s[consts.].value
        if s[self.constants.BANK_ACC].value != personal.BANK_ACC and s[bank_acc_cell].value != personal.BANK_ACC_VisaFile:
            log(f'Bank Account number does not match!', category='system')
            return False

        if not self.__validate_headers(header_row_index, headers):
            log('Credit sheet is INVALID', category='system')
            return False

        return True

    @abstractmethod
    def clean(self):
        pass

    @abstractmethod
    def reduce(self):
        pass

    @abstractmethod
    def insert(self):
        pass

    @abstractmethod
    def read(self):
        pass
