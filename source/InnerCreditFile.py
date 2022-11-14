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
        self.table_skip = table_skip
        self.counter1 = -1
        self.counter2 = -1
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
        none_counter = 2
        col_count = len(self.headers)        
        row_idx = self.initial_row + 1
        while none_counter > 0:
            cc_end = File.cell(row_idx, 0, self.sheet)
            if cc_end is None:
                none_counter -= 1
            else:
                row = self.sheet[row_idx - 1: row_idx, 0: col_count].value
                if cc_end in self.data_dict.keys():
                    self.data_dict[cc_end] += [row]
                else:
                    self.data_dict[cc_end] = [row]
            row_idx += 1
        print("test")


        counter1 = 0
        row = self.initial_row + 1
        cc_end = File.cell(row, 0, self.sheet)
        log(f"""
                In function "__count_transactions"
                cc_end = {cc_end}, cc_end type: {type(cc_end)}')
            """, category='debug')
        while cc_end is not None:
            counter1 += 1
            row += 1
            cc_end = File.cell(row, 0, self.sheet)

        self.counter1 = counter1
        log(f'First Loop End stats: cc_end={cc_end}, counter1={counter1}, row={row}', category='debug')

        counter2 = 0
        row += self.table_skip
        cc_end = File.cell(row, 0, self.sheet)
        while cc_end is not None:
            counter2 += 1
            row += 1
            cc_end = File.cell(row, 0, self.sheet)
            log(f'(second loop)\ncc_end = {cc_end}, counter = {counter1}, row = {row}', category='debug')

        self.counter2 = counter2
        log(f'Second Loop End stats: cc_end={cc_end}, counter1={counter2}, row={row}', category='debug')

        col_count = len(self.headers)
        table1 = self.sheet[self.initial_row: self.initial_row + self.counter1, 0: col_count].value
        if table1 is None:
            table1 = []
        elif counter1 == 1:
            table1 = [table1]

        initial_row = self.initial_row + counter1 + self.table_skip
        table2 = self.sheet[initial_row: initial_row + counter2, 0: col_count].value
        if table2 is None:
            table2 = []
        elif counter2 == 1:
            table2 = [table2]

        self.data = table1 + table2
        self.date = self.sheet[self.date_loc].value
        return True

    def clean(self):
        print("skipping clean")

    def insert(self):
        """

        """
        print("skipping insert")
        # DataBase().insert_file(self.name, 
        #                        self.date, 
        #                        "Auto Insertion",
        #                        self.counter1 + self.counter2)

        # counter = 0
        # for row in self.data:
        #     counter += 1
        #     DataBase().insert_transaction(row[0], row[1], row[2], row[3], row[7], row[-1], self.name)
        # return True

    def __str__(self):
        return f"\t -> InnerCreditFile"
