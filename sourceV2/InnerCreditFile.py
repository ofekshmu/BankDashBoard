from File import File
from Constants import log


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
