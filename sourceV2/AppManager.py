from Parser import Parser
from BankTransactionsFile import BankTransactionsFile
from InnerCreditFile import InnerCreditFile
from OuterCreditFile import OuterCreditFile
from Context import Context


class AppManager:

    def __init__(self):
        self.parser = Parser()

    def run(self):
        context = Context()
        while next(self.parser):
            name, type = self.parser.identify()

            if type == BankTransactionsFile:
                context.setFile(BankTransactionsFile(name))
            elif type == InnerCreditFile:
                context.setFile(InnerCreditFile(name))
            elif type == OuterCreditFile:
                context.setFile(OuterCreditFile(name))

            context.render()
