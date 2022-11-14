from os import listdir
from os.path import isfile, join
from Constants import InnerCredit, OuterCredit, BankTransactions
from OuterCreditFile import OuterCreditFile
from InnerCreditFile import InnerCreditFile
from BankTransactionsFile import BankTransactionsFile
from datetime import datetime
from File import File
from typing import Union

# Local
from Constants import log, Local


class Parser():

    __instance = None

    @staticmethod
    def getInstance():
        """ Static access method """
        if Parser.__instance is None:
            Parser()
        return Parser.__instance

    def __init__(self):
        """ Virtually private constructor. """
        if Parser.__instance is not None:
            raise Exception("This class is a singleton!")
        else:
            Parser.__instance = self

            self.n = 0
            self.file_dict = {}
            self.file_lst = []

            for file in listdir(Local.XLSX_PATH):
                cond1 = isfile(join(Local.XLSX_PATH, file))
                cond2 = file.endswith(Local.EXTENSION_1)
                cond3 = file.endswith(Local.EXTENSION_2)
                if cond1 and (cond2 or cond3):
                    self.file_dict[file] = self.__identify(file)

            def to_date(name: str) -> datetime:
                import re
                date_str = re.search("\w{1,2}_\w{1,2}_\w{4}", name).group()
                date = date_str.split("_")
                import datetime
                return datetime.datetime(int(date[2]), int(date[1]), int(date[0]))

            dict = {name: to_date(name) for name in self.file_dict.keys()}
            self.file_lst = [k for k, _ in sorted(dict.items(), key=lambda item: item[1])]

            log(f"found {len(self.file_dict)} files in {Local.XLSX_PATH}", 'system')

    def __next__(self):
        if self.n < len(self.file_lst):
            self.n += 1
            file_name = self.file_lst[self.n - 1]
            return file_name, self.file_dict[file_name]
        else:
            return None, None

    def __identify(self, file_name: str) -> File:
        res = None

        if InnerCredit.SUB_STRING in file_name:
            res = InnerCreditFile
        elif OuterCredit.SUB_STRING in file_name:
            res = OuterCreditFile
        elif BankTransactions.SUB_STRING in file_name:
            res = BankTransactionsFile
        else:
            log(f"The file name: {file_name} does not contain a known string.", 'error')

        return res

    def get_name_lst(self, obj_class: File):
        return [k for k, v in self.file_dict.items() if isinstance(obj_class, v)]
