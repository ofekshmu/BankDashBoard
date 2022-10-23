from Parser import Parser
from sourceV2.Constants import BankTransaction, InnerCredit, OuterCredit
from Context import Context


class AppManager:

    def __init__(self):
        self.parser = Parser()

    def run(self):
        context = Context()
        while next(self.parser):
            name, type = self.parser.identify()
            
            if type == BankTransaction:
                context.setFile(BankTransaction(name))
            elif type == InnerCredit:
                context.setFile(InnerCredit(name))
            elif type == OuterCredit:
                context.setFile(OuterCredit(name))

            context.render()