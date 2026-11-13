from File import File
from database import DataBase
from src_utils.utils import utils
from datetime import datetime
from Constants import BANK_CARD_NUMBER

class Bank(File):
    def __init__(self, name: str, format_info: dict):
        super().__init__(name, format_info)

        self.card_number = BANK_CARD_NUMBER

    def parse(self):
        '''
        The parse function for InnerCreditFile updates the following fields:
        self.counter1: number of transactions in the first table
        self.counter2: number of transaction in the second table
        self.data: table1 and table2 data in a 2d array
        self.date: the date specified in the file
        '''
        # The File row must exist before parse() can insert TableMeta rows for it
        # (TableMeta.File_Name/Format/Card_Number has a foreign key onto File).
        # Transaction_count isn't known until parsing finishes, so insert a
        # placeholder now and correct it below.
        file_date = datetime.strptime(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "%Y-%m-%d %H:%M:%S")
        DataBase().insert_file(self.name,
                               self.format_name,
                               self.card_number,
                               # The following line removes the miliseconds (data after the decimal point) to avoid
                               # complicity in futute analysis
                               # TODO: The used date should be a date defining the month associated with the file, but
                               # the Bank files are not associated with a specific month.. should find a solution for this..
                               file_date,
                               -1,
                               -1)

        valid_rows = super().parse()

        DataBase().set_transaction_count(self.name, self.format_name, self.card_number, valid_rows)
        return True

    def clean(self):
        """
        """
        return super().clean()

    def insert(self):

        for row in self.table_1:
            match self.format_name:
                case "Leumi-Bank":
                    DataBase().insert_bank_transaction(Date=row[0],
                                                       Value_Date=row[1],
                                                       Name=row[2],
                                                       Ref=row[3],
                                                       Out=utils.amount_ready(row[4]),
                                                       Income=utils.amount_ready(row[5]),
                                                       Balance=utils.balance_ready(row[6]),
                                                       Source_file=self.name,
                                                       Extra_Info=f"Info: {row[7]} | Note: {row[8]}")
                case "BeinLeumi-Bank":
                    DataBase().insert_bank_transaction(Date=row[0],
                                                        Value_Date=row[6],
                                                        Name=row[2],
                                                        Ref=row[3],
                                                        Out=utils.amount_ready(row[5]),
                                                        Income=utils.amount_ready(row[4]),
                                                        Balance=utils.balance_ready(row[7]),
                                                        Source_file=self.name,
                                                        Extra_Info=f"Info: {row[1]}")

                case "BeinLeumi-Bank-Date-Range":
                    DataBase().insert_bank_transaction(Date=row[7],
                                                        Value_Date=row[1],
                                                        Name=row[4],
                                                        Ref=row[5],
                                                        Out=utils.amount_ready(row[3]),
                                                        Income=utils.amount_ready(row[2]),
                                                        Balance=utils.balance_ready(row[0]),
                                                        Source_file=self.name,
                                                        Extra_Info=f"Info: {row[6]}")

                case _:
                    utils.log("Format not supported for insertion into db class.Bank -> insert", "error")

        return True

    def __str__(self):
        return f"{self.format_name} of Type 「Bank」"
