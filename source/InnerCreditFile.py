from File import File
from Constants import log
from database import DataBase


class InnerCreditFile(File):

    def __init__(self,
                 name: str,
                 date_loc: str,
                 bank_num_loc: str,
                 headers,
                 initial_row: int,
                 table_skip: int):
        super().__init__(name, bank_num_loc, initial_row, headers)
        self.date_loc = date_loc
        self.data = None

    def parse(self) -> bool:
        '''
        The parse function for InnerCreditFile updates the following fields:
        self.counter1: number of transactions in the first table
        self.counter2: number of transaction in the second table
        self.data: table1 and table2 data in a 2d array
        self.date: the date specified in the file
        '''

        self.data_dict = {}
        none_counter = 4
        col_count = len(self.headers)        
        row_idx = self.initial_row + 1
        while none_counter > 0:
            cc_end = File.cell(row_idx, 0, self.sheet)
            if cc_end is None or not cc_end.isdigit():
                none_counter -= 1
            else:
                row = self.sheet[row_idx - 1: row_idx, 0: col_count].value
                if cc_end in self.data_dict.keys():
                    self.data_dict[cc_end] += [row]
                else:
                    self.data_dict[cc_end] = [row]
            row_idx += 1

        self.date = self.sheet[self.date_loc].value
        return True

    def clean(self):
        log("skipping clean...", 'system')
        return True

    def insert(self):
        """

        """
        def date_conversion(str):
            import re
            from datetime import datetime
            if isinstance(str, datetime):
                return str
            pattern = "\d{1,2}/\d{1,2}/\d{4}|\d{1,2}-\d{1,2}-\d{4}"
            str = re.search(pattern, str).group()
            print(str)
            if "/" in str:
                return datetime.strptime(str, "%d/%m/%Y")
            else:
                return datetime.strptime(str, "%d-%m-%Y")


        total = []
        for v in self.data_dict.values():
            total += v

        DataBase().insert_file(self.name, 
                               self.date, 
                               "Auto Insertion",
                               len(total),
                               len(total))

        counter = 0
        for row in total:
            counter += 1
            DataBase().insert_transaction(row[0], date_conversion(row[1]), row[2], -row[3], row[7], row[-1], self.name)
        return True

    def __str__(self):
        return f"\t -> InnerCreditFile"
