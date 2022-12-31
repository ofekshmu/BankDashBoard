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
            striped = re.sub(r'\d+', '', name)

            if amount > 0:
                earnings.append((striped, amount))
            else:
                spendings.append((striped, amount))

        df_1 = pd.DataFrame({'earnings': [tup[1] for tup in earnings]},
                            index=[gen_name(tup[0], tup[1]) for tup in earnings])
        df_1.plot.pie(y='earnings', figsize=(5, 5), legend=False, title=f"Total Earnings:{sum([tup[1] for tup in earnings])}")

        spendings = []
        lst = DataBase().get_transactions(table="", year=year, month=month)
        for ele in lst:
            import re
            card = re.sub("[^0-9]", "", ele[1])
            name = ele[3]
            amount = ele[4]
            charge_amount = ele[7]
            amount = transaction_value(amount, charge_amount)
            striped = re.sub(r'\d+', '', name)
            spendings.append((striped, amount, card))

        df_2 = pd.DataFrame({'spendings': [-tup[1] for tup in spendings]},
                            index=[gen_name(tup[0], tup[1], tup[2]) for tup in spendings])
        df_2.plot.pie(y='spendings', figsize=(5, 5), legend=False, title=f"Total Spendings:{round(sum([-tup[1] for tup in spendings]),2)}")

        plt.show()

        input()


def transaction_value(amount: int, charge_amount: int) -> int:
    if amount != charge_amount:
        return charge_amount
    return amount


def has_hebrew(string):
    """
    returns True if a string has any hebrew characters in it
    and False otherwise.
    """
    import re
    return bool(re.search(r'[\u0590-\u05FF]', string))


def gen_name(name, amount, card=""):
    """
    The function returns a readable string for ploting.

    @param name -   a string indicating transaction info
    @param amount - value of the transaction
    @param card -   the card asociated with the transaction
    """
    if has_hebrew(name):
        lst = name.split()
        name = ""
        for word in lst:
            if has_hebrew(word):
                name = f"{word[::-1]} " + name
            else:
                name = f"{word} " + name

    if card == "":
        return f"{name}- {amount}"
    return f"[{card}] {name}- {-amount}"
