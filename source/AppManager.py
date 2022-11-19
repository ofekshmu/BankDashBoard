from Parser import Parser
from BankTransactionsFile import BankTransactionsFile
from InnerCreditFile import InnerCreditFile
from OuterCreditFile import OuterCreditFile
from Context import Context
from Constants import InnerCredit, BankTransactions, OuterCredit, log
from Constants import name_he
from database import DataBase


def exists(name: str) -> bool:
    return DataBase().is_file_exists(name)


class AppManager:

    def __init__(self):
        self.parser = Parser()

    def load_data(self):
        context = Context()
        Context.counter = 0
        while next(self.parser):
            name, type = self.parser.get_next()

            if exists(name):
                log(f'Skipping {name_he(name)}...', 'system')
                continue

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
                                                OuterCredit.HEADERS,
                                                OuterCredit.CARD_CELL,
                                                OuterCredit.INITIAL_ROW))
            else:
                log("The file type is not supported", 'error')

            Context.counter += 1
            context.render()

    def plot_data(self):
        lst = DataBase().get_transactions(year=2022, month=10)
        import matplotlib.pyplot as plt
        import pandas as pd
        spendings = []
        earnings = []
        for ele in lst:
            amount = ele[5]
            name = ele[7]
            if amount > 0:
                earnings.append((name[::-1], amount))
            else:
                spendings.append((name[::-1], amount))

        df = pd.DataFrame({'earnings': [tup[1] for tup in earnings]},
                          index=[tup[0] + f" ({tup[1]})" for tup in earnings])
        df.plot.pie(y='earnings', figsize=(5, 5), legend=False, title=f"Total Earnings:{sum([tup[1] for tup in earnings])}")

        input()
