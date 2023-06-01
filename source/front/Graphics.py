from database import DataBase
import matplotlib.pyplot as plt
import pandas as pd
from src_utils.calculations import SimpleMath
from src_utils.utils import utils
import seaborn as sns


class Graphics:

    @staticmethod
    def plot_earnings(data: list) -> None:
        df = pd.DataFrame(data, columns=["Name", "Amount", "Category", "Date"])
        df = df.drop("Date", axis=1)
        df = df.groupby("Category").sum()
        df.index = df.index.map(lambda name: f"{utils.heb_conversion(name)}\n{round(df.loc[name,'Amount'], 2)}₪")
        gentle_blue = ['#BFD7EA', '#A5C6DB', '#8BB5CC', '#7194BD', '#577DAE', '#3D5C9F', '#233D90']
        title = f"Total Earnings: {int(sum([tup[1] for tup in data]))}₪"
        ax = df.plot.pie(y='Amount', figsize=(7, 5), legend=False, title=title, colors=gentle_blue)
        ax.set_ylabel('')

        plt.savefig('Earnings.png')

    @staticmethod
    def plot_spendings(data: list) -> None:
        if data != []:
            df = pd.DataFrame(data, columns=["Table name", "Name", "Card", "Amount", "Category", "Date"])
            df['Amount'] = df['Amount'].apply(lambda x: -x)
            print(df.to_markdown())
            df = df.groupby("Category").sum()
            df.index = df.index.map(lambda name: f"{utils.heb_conversion(name)}\n{round(df.loc[name,'Amount'], 2)}₪")
            gentle_orange = ['#FFF2CC', '#FFE699', '#FFD966', '#FFC533', '#FFB200', '#FFA000', '#FF8F00', '#FF8000', '#FF6B00']
            title = f"Total Spendings: {round(df['Amount'].sum(), 2)}₪"

            ax = df.plot.pie(y='Amount', figsize=(7, 5), legend=False, title=title, colors=gentle_orange)
            ax.set_ylabel('')

        else:
            _, ax = plt.subplots()
            ax.pie([], labels=[])
            # set the title of the plot
            ax.set_title('Empty Pie Chart')

        plt.savefig('Spendings.png')

    @staticmethod
    def plot_gas(data: list) -> pd.Series:
        # filter data:
        data = [(item[4], item[1], -item[2]) for item in data]
        # ------------
        plt.figure()
        labels = ["Date", "Business Name", "Amount"]
        df = pd.DataFrame(data, columns=labels)
        df['Date'] = pd.to_datetime(df['Date'])
        statistics = df['Amount'].describe().loc[["count", "mean", "std", "min", "max"]]

        start_date = pd.Timestamp.today().normalize() - pd.DateOffset(months=2, days=0)
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
        ax.set_xticklabels(df_merged.index.strftime('%d/%m'), rotation=55)

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
        data = [(item[4], item[1], -item[2]) for item in data]
        labels = ["Date", "Business Name", "Amount"]
        df = pd.DataFrame(data, columns=labels)
        df['Date'] = pd.to_datetime(df['Date'])
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

    @staticmethod
    def card_distribution(spendings: list):
        """
        
        """
        if spendings != []:
            df = pd.DataFrame(spendings, columns=["Table name", "Name", "Card", "Amount", "Category", "Date"])
            df['Amount'] = df['Amount'].apply(lambda x: -x)
            df = df.groupby("Card").sum()
            df.index = df.index.map(lambda card: f"{utils.heb_conversion(card)}\n{round(df.loc[card, 'Amount'] * 100 / df['Amount'].sum(), 2)}%")
            gentle_orange = ['#FFF2CC', '#FFE699', '#FFD966', '#FFC533', '#FFB200', '#FFA000', '#FF8F00', '#FF8000', '#FF6B00']
            title = "Card Distribution"

            ax = df.plot.pie(y='Amount', figsize=(3, 2), legend=False, title=title, colors=gentle_orange)
            ax.set_ylabel('')

        else:
            _, ax = plt.subplots()
            ax.pie([], labels=[])
            ax.set_ylabel('')
            # set the title of the plot
            ax.set_title('Empty Pie Chart')
            
        plt.savefig('Card_Distribution.png')