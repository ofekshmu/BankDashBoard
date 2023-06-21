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

        DataBase().insert_file(self.name,
                               "None",
                               "Auto Insertion",
                               "Not checked",
                               self.counter)

        self.card_num = self.sheet[self.card_cell].value
        return True

    def clean(self):
        from Parser import Parser
        self.sorted_names = Parser.getInstance().get_names(OuterCreditFile)
        return super().clean(flip=True)

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

        for row in self.data:
            card_id = "NI - 2922"
            transaction_date = date_conversion(row[0])
            business_name = row[1]
            amount = -row[2]
            trans_type = row[3]
            charge_date = ""
            charge_amount = -row[4]
            source_file = self.name

            DataBase().insert_card_transaction(card_id,
                                               transaction_date,
                                               business_name,
                                               amount,
                                               charge_amount,
                                               f"{trans_type} | {charge_date}",
                                               source_file)
        return True

    def __str__(self):
        return f"\t -> OuterCreditFile"
