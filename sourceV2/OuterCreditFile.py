from File import File
from Constants import log


class OuterCreditFile(File):
    def __init__(self,
                 name: str,
                 headers: list,
                 initial_row: int):
        super().__init__(name, 'None Exsisting', initial_row, headers)

    def validate_bank_number(self) -> bool:
        """ Outer credit has no Bank acc number """
        return True

    def parse(self) -> bool:
        """
        """
        counter = 0
        row = self.initial_row + 1
        cc_end = File.cell(row, 0, self.sheet)
        log(f"""
                In function "__count_transactions"
                cc_end = {cc_end}, cc_end type: {type(cc_end)}')
            """, category='debug')
        while cc_end is not None:
            counter += 1
            row += 1
            cc_end = File.cell(row, 0, self.sheet)

        self.counter = counter
        log(f'First Loop End stats: cc_end={cc_end}, counter1={counter}, row={row}', category='debug')

        col_count = len(self.headers)
        table = self.sheet[self.initial_row: self.initial_row + self.counter, 0: col_count].value
        if table is None:
            table = []
        elif counter == 1:
            table = [table]

        self.data = table
        return True


    def insert(self) -> bool:
        pass
