from os import listdir
from os.path import isfile, join
from Constants import InnerCredit, OuterCredit, BankTransactions
from OuterCreditFile import OuterCreditFile
from InnerCreditFile import InnerCreditFile
from BankTransactionsFile import BankTransactionsFile
from datetime import datetime

# Local
from Constants import log, Local


class Parser():
    def __init__(self):
        self.n = 0
        self.file_names = []
        for file in listdir(Local.XLSX_PATH):
            cond1 = isfile(join(Local.XLSX_PATH, file))
            cond2 = file.endswith(Local.EXTENSION_1)
            cond3 = file.endswith(Local.EXTENSION_2)
            if cond1 and (cond2 or cond3):
                self.file_names.append(file)

        log(f"found {len(self.file_names)} files.", 'system')
        
        def to_date(name: str) -> datetime:
            import re
            date_str = re.search("\w{1,2}_\w{1,2}_\w{4}", name).group()
            date = date_str.split("_")
            import datetime
            return datetime.datetime(int(date[2]), int(date[1]), int(date[0]))

        dict = {to_date(name): name for name in self.file_names}
        self.file_names = [v for k, v in sorted(dict.items(), key=lambda item: item[0])]
        print()

    def __next__(self) -> bool:
        if self.n < len(self.file_names):
            self.current = self.file_names[self.n]
            self.n += 1
            return True
        else:
            return False

    def identify(self):
        file_name = self.current
        res = None

        if InnerCredit.SUB_STRING in file_name:
            res = InnerCreditFile
        elif OuterCredit.SUB_STRING in file_name:
            res = OuterCreditFile
        elif BankTransactions.SUB_STRING in file_name:
            res = BankTransactionsFile
        else:
            log(f"The file name: {file_name} does not contain a known string.", 'error')

        return file_name, res
