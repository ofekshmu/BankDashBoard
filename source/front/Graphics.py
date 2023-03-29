from database import DataBase
import matplotlib.pyplot as plt
import pandas as pd
from src_utils.calculations import SimpleMath
from src_utils.utils import utils


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

    @staticmethod
    def plot_gas(data: list) -> pd.Series:
        plt.figure()
        labels = ["Date", "Business Name", "Amount"]
        df = pd.DataFrame(data, columns=labels)
        statistics = df['Amount'].describe().loc[["count", "mean", "std", "min", "max"]]

        start_date = pd.Timestamp.today().normalize() - pd.DateOffset(months=1, days=20)
        end_date = pd.Timestamp.today().normalize()
        all_dates = pd.date_range(start=start_date, end=end_date, freq='D')
        df_all_dates = pd.DataFrame({'Date': all_dates})

        # merge the original DataFrame with the new DataFrame using a left join
        df_merged = pd.merge(df_all_dates, df, on='Date', how='left')

        # fill the missing values with 0
        df_merged['Amount'].fillna(0, inplace=True)

        # set the datetime column as the index of the DataFrame
        df_merged.set_index('Date', inplace=True)

        # create the bar plot
        fig, ax = plt.subplots(figsize=(15, 6))
        bars = ax.bar(df_merged.index.strftime('%d/%m'), df_merged['Amount'])

        for i, bar in enumerate(bars):
            height = bar.get_height()
            if height != 0:
                ax.text(bar.get_x() + bar.get_width()/2., height,
                        utils.name_he(df_merged['Business Name'][i]),
                        ha='center', va='bottom')

        # rotate x-axis labels by 45 degrees
        ax.set_xticklabels(df_merged.index.strftime('%d/%m'), rotation=45)

        # set the x-axis label
        ax.set_xlabel('Date (dd/mm)')
        # set the y-axis label
        ax.set_ylabel('Values')

        # set the title of the plot
        ax.set_title('Bar Plot')
    
        plt.savefig('Gas_Stats.png')
        return statistics
