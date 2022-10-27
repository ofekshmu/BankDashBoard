from File import File


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
