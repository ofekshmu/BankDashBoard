from File import File
from Constants import log
from database import DataBase
from datetime import datetime


class BankTransactionsFile(File):
    def __init__(self,
                 name: str,
                 date_loc: str,
                 bank_num_loc: str,
                 headers: list,
                 initial_row: int):
        super().__init__(name, bank_num_loc, initial_row, headers)
        self.date_loc = date_loc

    def parse(self):
        '''
        The parse function for InnerCreditFile updates the following fields:
        self.counter1: number of transactions in the first table
        self.counter2: number of transaction in the second table
        self.data: table1 and table2 data in a 2d array
        self.date: the date specified in the file
        '''
        super().parse()
        # TODO this was commented when the code was moved to FILE
        # might cuase a problem in future run
        # self.new_trans_count = counter
        # self.date = self.sheet[self.date_loc].value

        DataBase().insert_file(self.name,
                               self.sheet[self.date_loc].value,
                               "Auto Insertion",
                               -1,
                               self.counter,
                               self.initial_row)
        return True

    def clean(self):
        from Parser import Parser
        self.sorted_names = Parser.getInstance().get_names(BankTransactionsFile)
        return super().clean()

    def insert(self):
        """
        """
        def date_conversion(str):
            import re
            from datetime import datetime
            if isinstance(str, datetime):
                return datetime(str.year, str.day, str.month)
            pattern = "\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{4}"
            str = re.search(pattern, str).group()
            if len(str.split('/')[-1]) == 2:
                str = str[:-2] + "20" + str[-2:]
            if "/" in str:
                return datetime.strptime(str, "%d/%m/%Y")
            else:
                return datetime.strptime(str, "%d-%m-%Y")

        for row in self.data:
            ref = row[3]
            date = date_conversion(row[0])
            date_value = date_conversion(row[1])
            source_dest = row[2]
            balance = row[-3]
            decs = row[7]
            hova = row[4]
            zhoot = row[5]
            if hova == 0:
                amount = zhoot
            elif zhoot == 0:
                amount = -hova
            else:
                raise ValueError('There is a bug here')
            DataBase().insert_bank_transaction(ref, date, date_value, source_dest, amount, balance, decs, self.name)
        return True

    def __str__(self):
        return f"\t -> BankTransactionFile"