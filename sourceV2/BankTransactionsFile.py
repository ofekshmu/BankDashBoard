from sourceV2.File import File
from Constants import BankTransactions


class BankTransactionsFile(File):
    def __init__(self,
                 name: str,
                 date_loc: str,
                 bank_num_loc: str,
                 headers: list,
                 initial_row: int):
        super().__init__(name, bank_num_loc, initial_row, headers)
        self.date_loc = date_loc

    def clean(self):
        """

        """
        pass

    def reduce(self):
        """

        """
        pass

    def insert(self):
        """

        """
        pass
