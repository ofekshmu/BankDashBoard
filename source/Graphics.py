from database import DataBase


class Graphics:

    @staticmethod
    def basic_plots(year: int, month: int):
        """
        This is a temporary functions to draw basic plots of transactions
        """
        lst = DataBase().get_transactions(table="BankTransactions", year=year, month=month)
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

        spendings = []
        lst = DataBase().get_transactions(table="", year=2022, month=11)
        for ele in lst:
            import re
            card = re.sub("[^0-9]", "", ele[1])
            name = ele[3]
            amount = ele[4]
            charge_amount = ele[7]
            amount = transaction_value(amount, charge_amount)
            striped = re.sub(r'\d+', '', name[::-1])
            spendings.append((striped, amount, card))

        df_2 = pd.DataFrame({'spendings': [-tup[1] for tup in spendings]},
                            index=[f"({tup[1]}) " + tup[0] +" "+ tup[2] for tup in spendings])
        df_2.plot.pie(y='spendings', figsize=(5, 5), legend=False, title=f"Total Spendings:{sum([-tup[1] for tup in spendings])}")

        plt.show()

        input()


def transaction_value(amount: int, charge_amount: int) -> int:
    if amount != charge_amount:
        return charge_amount
    return amount
