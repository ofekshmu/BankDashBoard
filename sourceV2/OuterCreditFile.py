from File import File


class OuterCreditFile(File):
    def __init__(self,
                 name: str,
                 date_loc: str,
                 headers: list,
                 initial_row: int):
        super().__init__(name, 'None Exsisting', initial_row, headers)
        self.loc = date_loc

    def validate_bank_number(self) -> bool:
        """ Outer credit has no Bank acc number """
        return True

    def validate_headers(self) -> bool:
        pass

    def parse(self) -> bool:
        pass

    def insert(self) -> bool:
        pass
