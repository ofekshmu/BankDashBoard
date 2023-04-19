from database import DataBase
import matplotlib.pyplot as plt
import pandas as pd
from src_utils.calculations import SimpleMath
from src_utils.utils import utils
import seaborn as sns


class Graphics:

    @staticmethod
    def plot_earnings(data: list) -> None:
        filtered_data = [item[:-1] for item in data]
        df = pd.DataFrame(filtered_data, columns=["Name", "Amount", "Category"])
        df = df.groupby("Category").sum()
        df.index = df.index.map(lambda name: f"{utils.heb_conversion(name)}\n{df.loc[name,'Amount']}")
        gentle_blue = ['#BFD7EA', '#A5C6DB', '#8BB5CC', '#7194BD', '#577DAE', '#3D5C9F', '#233D90']
        title = f"Total Earnings: {int(sum([tup[1] for tup in data]))}₪"
        ax = df.plot.pie(y='Amount', figsize=(5, 5), legend=False, title=title, colors=gentle_blue)

        plt.savefig('Earnings.png')

    @staticmethod
    def plot_spendings(data: list) -> None:
        # Do not include the date column when ploting data[:-1]
        filtered_data = [item[:-1] for item in data]
        df = pd.DataFrame(filtered_data, columns=["Name", "Amount", "Card", "Category"])
        df['Amount'] = df['Amount'].apply(lambda x: -x)
        df = df.groupby("Category").sum()
        df.index = df.index.map(lambda name: f"{utils.heb_conversion(name)}\n{df.loc[name,'Amount']}")
        gentle_orange = ['#FFF2CC', '#FFE699', '#FFD966', '#FFC533', '#FFB200', '#FFA000', '#FF8F00', '#FF8000', '#FF6B00']
        title = f"Total Spendings: {int(sum([-tup[1] for tup in data]))}₪"

        ax = df.plot.pie(y='Amount', figsize=(5, 5), legend=False, title=title, colors=gentle_orange)

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
                ax.text(bar.get_x() + bar.get_width()/2., height + 2,
                        utils.heb_conversion(df_merged['Business Name'][i]),
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

    @staticmethod
    def plot_monthly_gas(data: list) -> None:
        plt.figure()
        labels = ["Date", "Business Name", "Amount"]
        df = pd.DataFrame(data, columns=labels)
        df = df.groupby(pd.Grouper(key='Date', freq='M')).sum()
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(df.index.strftime('%b %Y'), df['Amount'])

        # set the x-axis label
        ax.set_xlabel('Month')
        # set the y-axis label
        ax.set_ylabel('Amount')

        # set the title of the plot
        ax.set_title('Monthly Payment')
        plt.savefig('Gas_monthly.png')

    @staticmethod
    def plot_general(df: pd.DataFrame) -> None:
        df.index = df.index.strftime('%B')
        df = df.reset_index()
        # Melt the dataframe to "long" format for easier plotting with Seaborn
        df_melt = df.melt(id_vars='Date', value_vars=['Amount_spendings', 'Amount_earnings'], var_name='Type')
        # Set Seaborn style
        sns.set_style("whitegrid")
        pastel = sns.color_palette("pastel")
        pastel_reverse = list(reversed(pastel[:2]))
        sns.set_palette(pastel_reverse)

        fig, ax = plt.subplots(figsize=(12, 6))
        sns.barplot(x="Date", y="value", hue="Type", data=df_melt, ax=ax)

        for i in range(len(df)):
            delta = int(df['Amount_earnings'][i] - df['Amount_spendings'][i])
            (height, color) = (df['Amount_earnings'][i], 'green') if df['Amount_earnings'][i] > df['Amount_spendings'][i] else (df['Amount_spendings'][i], 'red')
            plt.text(i-.1, height + 50, str(delta), color=color, fontsize=10)

        ax.set_title("Spending and Earnings by Month")
        ax.set_xlabel("Month")
        ax.set_ylabel("Amount")
        ax.legend(title="Type", loc="upper left")

        plt.savefig('General_info.png')
