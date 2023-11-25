from File import File
from database import DataBase
from src_utils.utils import utils
from src_utils.ExcelReader import ExcelManager


class Bank(File):
    def __init__(self, name: str, format_info: dict):
        super().__init__(name, format_info)

    def parse(self):
        '''
        The parse function for InnerCreditFile updates the following fields:
        self.counter1: number of transactions in the first table
        self.counter2: number of transaction in the second table
        self.data: table1 and table2 data in a 2d array
        self.date: the date specified in the file
        '''
        valid_rows, time_stamp = super().parse()

        DataBase().insert_file(self.name,
                               time_stamp,
                               self.format_name,
                               -1,
                               valid_rows)
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
                                                       Out=row[4],
                                                       Income=row[5],
                                                       Balance=row[6],
                                                       Source_file=self.name,
                                                       Extra_Info=f"Info: {row[7]} | Note: {row[8]}")
                case "BeinLeumi-Bank":
                    DataBase().insert_bank_transaction(Date=row[0],
                                                       Value_Date=row[6],
                                                       Name=row[2],
                                                       Ref=row[3],
                                                       Out=utils.amount_ready(row[5]),
                                                       Income=utils.amount_ready(row[4]),
                                                       Balance=row[7],
                                                       Source_file=self.name,
                                                       Extra_Info=f"Info: {row[1]}")
                    
                
                case _:
                    utils.log("Format not supported for insertion into db class.Bank -> insert", "error")

        return True

    def __str__(self):
        return f"{self.format_name} of Type 「Bank」"
