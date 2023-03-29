from database import DataBase
import matplotlib.pyplot as plt
import pandas as pd
import webbrowser
from src_utils.calculations import SimpleMath


class Graphics:

    @staticmethod
    def plot_earnings(data: list) -> None:
        labels = [SimpleMath.prettify(tup[0], tup[1]) for tup in data]
        df_earnings = pd.DataFrame({'Earnings': [tup[1] for tup in data]},
                                   index=labels)

        title = f"Total Earnings:{sum([tup[1] for tup in data])}"
        df_earnings.plot.pie(y='Earnings', figsize=(5, 5), legend=False, title=title)
        plt.savefig('Earnings.png')

    @staticmethod
    def plot_spendings(data: list) -> None:
        labels = [SimpleMath.prettify(tup[0], tup[1], tup[2]) for tup in data]
        df_2 = pd.DataFrame({'Spendings': [-tup[1] for tup in data]},
                            index=labels)

        title = f"Total Spendings:{round(sum([-tup[1] for tup in data]),2)}"
        df_2.plot.pie(y='Spendings',
                      figsize=(5, 5),
                      legend=False,
                      title=title)
        plt.savefig('Spendings.png')
