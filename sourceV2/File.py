from abc import abstractmethod
from Constants import log, Local
import xlwings as xw
from os.path import join


class File:
    def __init__(self, name: str):
        self.name = name
        self.sheet = None

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
        """

        """
        pass

    @abstractmethod
    def clean(self):
        """

        """
        pass

    @abstractmethod
    def reduce(self):
        """

        """
        pass

    @abstractmethod
    def insert(self):
        """

        """
        pass

    @abstractmethod
    def read(self):
        """

        """
        pass
