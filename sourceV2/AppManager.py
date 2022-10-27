from Parser import Parser
from BankTransactionsFile import BankTransactionsFile
from InnerCreditFile import InnerCreditFile
from OuterCreditFile import OuterCreditFile
from Context import Context
from Constants import InnerCredit, BankTransactions, OuterCredit


class AppManager:

    def __init__(self):
        self.parser = Parser()

    def run(self):
        context = Context()
        while next(self.parser):
            name, type = self.parser.identify()

            if type == BankTransactionsFile:
                context.setFile(BankTransactionsFile(name,
                                                     BankTransactions.DATE,
                                                     BankTransactions.BANK_NUM_LOC,
                                                     BankTransactions.HEADERS,
                                                     BankTransactions.INITIAL_ROW))
            elif type == InnerCreditFile:
                context.setFile(InnerCreditFile(name,
                                                InnerCredit.DATE_LOC,
                                                InnerCredit.BANK_NUM_LOC,
                                                InnerCredit.HEADERS,
                                                InnerCredit.INITIAL_ROW,
                                                InnerCredit.TABLE_SKIP))
            elif type == OuterCreditFile:
                context.setFile(OuterCreditFile(name,
                                                OuterCredit.DATE,
                                                OuterCredit.HEADERS,
                                                OuterCredit.INITIAL_ROW))

            context.render()
