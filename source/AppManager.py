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

    def run(self) -> None:
        print("""
                Hello Ofek!
                What would you like to do today?

                1. Update files
                2. Parse files
                3. Show statistics
                4. Change personal info
                5. Exit
            """)
        answer = input()
        match answer:
            case 1:
                self.__update_bank_files()
            case 2:
                self.__load_data()
            case 3:
                self.__plots_and_data()
            case 4:
                raise NotImplemented("This need implementation")
            case 5:
                exit()
            case _:
                print("Please insert a valid number.")

    def __update_bank_files(self):
        pass
        # Check if the function was already executed today

    def __load_data(self):
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

    def __plots_and_data(self):
        lst = DataBase().get_transactions(table="BankTransactions", year=2022, month=12)
        import matplotlib.pyplot as plt
        import pandas as pd
        spendings = []
        earnings = []
        for ele in lst:
            amount = ele[5]
            name = ele[7]
            if name is None:
                name = ele[4]

            import re
            striped = re.sub(r'\d+', '', name[::-1])

            if amount > 0:
                earnings.append((striped, amount))
            else:
                spendings.append((striped, amount))

        df_1 = pd.DataFrame({'earnings': [tup[1] for tup in earnings]},
                            index=[tup[0] + f" ({tup[1]})" for tup in earnings])
        df_1.plot.pie(y='earnings', figsize=(5, 5), legend=False, title=f"Total Earnings:{sum([tup[1] for tup in earnings])}")

        # df_2 = pd.DataFrame({'spendings': [-tup[1] for tup in spendings]},
        #                     index=[f"({tup[1]}) " + tup[0] for tup in spendings])
        # df_2.plot.pie(y='spendings', figsize=(5, 5), legend=False, title=f"Total Spendings:{sum([-tup[1] for tup in spendings])}")

        spendings = []
        lst = DataBase().get_transactions(table="", year=2022, month=12)
        for ele in lst:
            import re
            card = re.sub("[^0-9]", "", ele[1])
            name = ele[3]
            amount = ele[4]
            striped = re.sub(r'\d+', '', name[::-1])
            spendings.append((striped, amount, card))
            
        df_2 = pd.DataFrame({'spendings': [-tup[1] for tup in spendings]},
                            index=[f"({tup[1]}) " + tup[0] +" "+ tup[2] for tup in spendings])
        df_2.plot.pie(y='spendings', figsize=(5, 5), legend=False, title=f"Total Spendings:{sum([-tup[1] for tup in spendings])}")

        plt.show()

        input()
