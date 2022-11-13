from File import File
from Constants import log
from database import DataBase


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
        counter = 0
        row = self.initial_row + 1
        cc_end = File.cell(row, 0, self.sheet)

        # Empty cell is read as None
        while cc_end is not None:
            counter += 1
            row += 1
            cc_end = File.cell(row, 0, self.sheet)

        # Number of transactions
        self.counter = counter
        self.new_trans_count = counter
        log(f'First Loop End stats: cc_end={cc_end}, counter1={counter}, row={row}', 'debug')

        col_count = len(self.headers)
        # Extract table data
        table = self.sheet[self.initial_row: self.initial_row + self.counter, 0: col_count].value

        # Happens if table is empty (No transactions)
        if table is None:
            table = []
        # To stay consistent with the data structure
        elif counter == 1:
            table = [table]

        self.data = table
        self.date = self.sheet[self.date_loc].value
        return True

    def insert(self):
        """
        """
        DataBase().insert_file(self.name,
                               self.date,
                               "Auto Insertion",
                               self.new_trans_count,
                               self.counter)

        for row in self.data:
            ref = row[3]
            date = row[0]
            date_value = row[1]
            source_dest = row[2]
            balance = row[-3]
            decs = 'Empty'
            hova = row[4]
            zhoot = row[5]
            if hova == 0:
                amount = zhoot
            elif zhoot == 0:
                amount = hova
            else:
                raise ValueError('There is a bug here')
            DataBase().insert_bank_transaction(ref, date, date_value, source_dest, amount, balance, decs, self.name)
        return True

    def __str__(self):
        return f"\t -> BankTransactionFile"