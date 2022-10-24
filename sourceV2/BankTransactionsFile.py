from sourceV2.File import File
from Constants import BankTransactions


class BankTransactionsFile(File):
    def __init__(self, name: str):
        super().__init__(name)
        self.constants = BankTransactions

    def validate(self):
        """

        """
        pass

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
