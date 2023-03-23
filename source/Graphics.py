from database import DataBase
import matplotlib.pyplot as plt
import pandas as pd
import webbrowser


class Graphics:

    @staticmethod
    def basic_plots(year: int, month: int):
        """
        This is a temporary functions to draw basic plots of transactions
        """
        lst = DataBase().get_transactions(table="BankTransactions", year=year, month=month)

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

        labels = [gen_name(tup[0], tup[1]) for tup in earnings]
        df_earnings = pd.DataFrame({'Earnings': [tup[1] for tup in earnings]},
                                   index=labels)

        title = f"Total Earnings:{sum([tup[1] for tup in earnings])}"
        df_earnings.plot.pie(y='Earnings', figsize=(5, 5), legend=False, title=title)
        plt.savefig('Earnings.png')

        spendings = []

        # When looking for spendings. transaction will be queried by the date they will be 
        # effective in the bank account and not by the date they were exectued.
        # That is why, when given month x, we will search for transactions in month x + 1
        fit_month = month % 12 + 1
        if fit_month == 1:
            year += 1
        lst = DataBase().get_transactions(table="", year=year, month=fit_month)
        for ele in lst:
            import re
            card = re.sub("[^0-9]", "", ele[1])
            name = ele[3]
            amount = ele[4]
            charge_amount = ele[7]
            amount = transaction_value(amount, charge_amount, ele)
            striped = re.sub(r'\d+', '', name)
            spendings.append((striped, amount, card))

        labels = [gen_name(tup[0], tup[1], tup[2]) for tup in spendings]
        df_2 = pd.DataFrame({'Spendings': [-tup[1] for tup in spendings]},
                            index=labels)

        title = f"Total Spendings:{round(sum([-tup[1] for tup in spendings]),2)}"
        df_2.plot.pie(y='Spendings',
                      figsize=(5, 5),
                      legend=False,
                      title=title)
        plt.savefig('Spendings.png')
        webbrowser.open('source\html\output.html')

        # plt.show()

    @staticmethod
    def generate_monthly_balance():

        row = DataBase().get_latest_bank_transaction()
        balance = row[6]
        return balance

    @staticmethod
    def generate_html():

        html_template = """
<!DOCTYPE html>
<html>
<head>
	<title>My Banking Info</title>
	<style>
		body {
			font-family: Arial, sans-serif;
		}

		.container {
			display: flex;
			justify-content: center;
			align-items: center;
		}

		.container img {
			margin: 10px;
			max-width: 50%;
			height: auto;
		}

		h1 {
			text-align: center;
		}
	</style>
</head>
<body>
	<h1>My Banking Info</h1>
	<div class="balance">
		Current balance: """ + Graphics.generate_monthly_balance() + """
	</div>
	<div class="container">
		<img src="C:\Users\ofeks\OneDrive\Work\Projects\Personal\BankProject\Spendings.png">
		<img src="C:\Users\ofeks\OneDrive\Work\Projects\Personal\BankProject\Earnings.png">
	</div>
</body>
</html>
"""

def transaction_value(amount: int, charge_amount: int, row: list) -> int:
    if row[5] == "תשלומים":
        return amount
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
