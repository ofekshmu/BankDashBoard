from File import File


class OuterCreditFile(File):
    def __init__(self,
                 name: str,
                 date_loc: str,
                 headers: list,
                 initial_row: int):
        super().__init__(name, 'None Exsisting', initial_row, headers)
        self.loc = date_loc

    def validate(self):
        """

        """
        pass

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
