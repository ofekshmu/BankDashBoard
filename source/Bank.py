from File import File
from database import DataBase
from src_utils.utils import utils


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
        super().parse()
        # TODO this was commented when the code was moved to FILE
        # might cuase a problem in future run
        # self.new_trans_count = counter
        # self.date = self.sheet[self.date_loc].value

        match self.format_name:
            case "BeinLeumi-Bank":
                value = "Not implemanted"
            case _:
                (row, col) = self.adittional_data_field
                value = utils.cell(row, col, self.sheet)

        DataBase().insert_file(self.name,
                               value,
                               self.format_name,
                               -1,
                               self.counter)
        return True

    def clean(self):
        from Parser import Parser
        self.sorted_names = Parser.getInstance().get_names(self.format_name)
        return super().clean()

    def insert(self):

        for row in self.data:
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
                                                       Out=row[5],
                                                       Income=row[4],
                                                       Balance=row[7],
                                                       Source_file=self.name,
                                                       Extra_Info=f"Info: {row[1]}")
                    
                
                case _:
                    utils.log("Format not supported for insertion into db class.Bank -> insert", "error")

        return True

    def __str__(self):
        return f"{self.format_name} of Type 「Bank」"
