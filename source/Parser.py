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

            self.idx = 0
            self.type_to_name = {}
            self.names = []
            
            log(f"Looking for files...", 'system')

            def to_date(name: str) -> datetime:
                import re
                date_str = re.search("\w{1,2}_\w{1,2}_\w{4}", name).group()
                date = date_str.split("_")
                import datetime
                return datetime.datetime(int(date[2]), int(date[1]), int(date[0]))

            def to_num(name: str):
                import re
                num_str = re.search("_\d{1,}", name).group()
                return num_str[1:]

            for name in listdir(Local.XLSX_PATH):
                cond1 = isfile(join(Local.XLSX_PATH, name))
                cond2 = name.endswith(Local.EXTENSION_1)
                cond3 = name.endswith(Local.EXTENSION_2)
                if cond1 and (cond2 or cond3):
                    file_type = self.__identify(name)
                    if file_type == OuterCreditFile:
                        value = to_num(name)
                    else:
                        value = to_date(name)

                    if file_type in self.type_to_name.keys():
                        self.type_to_name[file_type][name] = value
                    else:
                        self.type_to_name[file_type] = {name: value}

                    self.names.append(name)

            for k, v in self.type_to_name.items():  
                self.type_to_name[k] = {name: value for name, value in sorted(v.items(), key=lambda item: item[1])}

            log(f"found {len(self.names)} files in {Local.XLSX_PATH}", 'system')

    def __next__(self):
        if self.idx < len(self.names):
            return True
        return False

    def get_next(self):
        name = self.names[self.idx]
        self.idx += 1
        return name, self.__identify(name)

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

    def get_names(self, obj_class: File):
        return [k for k in self.type_to_name[obj_class].keys()]
