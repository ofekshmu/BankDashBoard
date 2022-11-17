from File import File
from Constants import log
from database import DataBase
from datetime import datetime


class OuterCreditFile(File):
    def __init__(self,
                 name: str,
                 headers: list,
                 card_cell: str,
                 initial_row: int):
        super().__init__(name, 'None Exsisting', initial_row, headers)
        self.card_cell = card_cell

    def validate_bank_number(self) -> bool:
        """ Outer credit has no Bank acc number """
        log("Bank number is not being validated for this file", "warning")
        return True

    def parse(self) -> bool:
        """
        The parse function for InnerCreditFile updates the following fields:
        self.counter: number of transactions
        self.data: table data in a 2d array
        self.card_num: the card_num specified in the file
        """
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
        log(f'First Loop End stats: cc_end={cc_end}, counter1={counter}, row={row}', category='debug')

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
        self.card_num = self.sheet[self.card_cell].value
        return True

    def clean(self):
        from Parser import Parser
        self.sorted_names = Parser.getInstance().get_names(OuterCreditFile)
        return super().clean()

    def insert(self) -> bool:

        def date_conversion(str):
            import re
            from datetime import datetime
            if isinstance(str, datetime):
                return str
            pattern = "\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{4}"
            str = re.search(pattern, str).group()
            if len(str.split('/')[-1]) == 2:
                str = str[:-2] + "20" + str[-2:]
            if "/" in str:
                return datetime.strptime(str, "%d/%m/%Y")
            else:
                return datetime.strptime(str, "%d-%m-%Y")

        DataBase().insert_file(self.name,
                               'None',
                               "Auto Insertion",
                               self.counter,
                               self.counter)

        for row in self.data:
            card_id = self.card_num
            transaction_date = date_conversion(row[0])
            business_name = row[1]
            amount = -row[5]
            trans_type = row[4]
            charge_date = date_conversion(row[9])
            source_file = self.name

            DataBase().insert_transaction(card_id,
                                          transaction_date,
                                          business_name,
                                          amount,
                                          trans_type,
                                          charge_date,
                                          source_file)
        return True

    def __str__(self):
        return f"\t -> OuterCreditFile"
