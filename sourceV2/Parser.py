from os import listdir
from os.path import isfile, join
from Constants import InnerCredit, OuterCredit, BankTransactions
from OuterCreditFile import OuterCreditFile
from InnerCreditFile import InnerCreditFile
from BankTransactionsFile import BankTransactionsFile

# Local
from Constants import log, Local


class Parser():
    def __init__(self):
        self.n = 0
        self.file_names = []
        for file in listdir(Local.XLSX_PATH):
            if isfile(join(Local.XLSX_PATH, file)) and file.endswith(Local.EXTENSION):
                self.file_names.append(file)

        log(f"found {len(self.file_names)} files.", 'system')

    def __next__(self):
        if self.n < len(self.file_names):
            result = self.file_names[self.n]
            self.n += 1
            return result
        else:
            return None

    def identify(self):
        file_name = self.file_names[self.n]

        if InnerCredit.SUB_STRING in file_name:
            res = InnerCreditFile
        elif OuterCredit.SUB_STRING in file_name:
            res = OuterCreditFile
        elif BankTransactions.SUB_STRING in file_name:
            res = BankTransactionsFile
        else:
            raise ValueError(f"The file name: {file_name} does not contain a known string.")

        return file_name, res
