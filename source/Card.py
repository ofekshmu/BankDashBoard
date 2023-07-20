from File import File
from src_utils.utils import utils
from Configurations.Formats import Formats
from database import DataBase
from datetime import datetime


class Card(File):
    def __init__(self, name: str, format_info: dict):
        super().__init__(name, format_info)

    def validate_bank_number(self) -> bool:
        """ Outer credit has no Bank acc number """
        utils.log("Bank number is not being validated for this file", "system")
        return True

    def parse(self) -> bool:
        """
        The parse function for InnerCreditFile updates the following fields:
        self.counter: number of transactions
        self.data: table data in a 2d array
        self.card_num: the card_num specified in the file
        """
        super().parse()

        (row, col) = self.adittional_data_field
        value = utils.cell(row, col, self.sheet)

        DataBase().insert_file(self.name,
                               value,
                               "Auto Insertion",
                               "Error",
                               self.counter)

        # TODO: Should add some generic field for data inside files
        # self.card_num = self.sheet[self.card_cell].value
        return True

    def clean(self):
        from Parser import Parser
        self.sorted_names = Parser.getInstance().get_names(self.format_name)
        return super().clean(flip=True)

    def insert(self) -> bool:

        for row in self.data:
            match self.format_name:
                case "Leumi-Max":
                    DataBase().insert_card_transaction(CardID="1121",
                                                       Name=row[1],
                                                       Executed_Date=utils.date_ready(row[0]),
                                                       Charge_Date=utils.date_ready(row[9]),
                                                       Charge_Value=row[5],
                                                       Source_file=self.name,
                                                       Charge_Currency=row[6],
                                                       Transaction_Value=row[7],
                                                       Value_Currency=row[8],
                                                       Extra_Info=f"Trans type: {row[4]} | Method: {row[14]} | Notes: {row[10]}")
                case "Isra-Card":
                    (r, c) = self.adittional_data_field  # TODO: These code line are being reapted, improve
                    value = utils.cell(r, c, self.sheet)

                    DataBase().insert_card_transaction(CardID="2922",
                                                       Name=row[1],
                                                       Executed_Date=utils.date_ready(row[0]),
                                                       Charge_Date=utils.date_ready(value), #TODO
                                                       Charge_Value=row[2],
                                                       Source_file=self.name,
                                                       Charge_Currency=row[3],
                                                       Transaction_Value=row[4],
                                                       Value_Currency=row[5],
                                                       Extra_Info=f"Serial: {row[6]} | Info: ({row[7]})")
                case _:
                    utils.log("Internal error: format name for insertion into card db was not found! (card.py)""error")

        return True

    def __str__(self):
        return f"\t -> OuterCreditFile"
