import matplotlib.pyplot as plt
import pandas as pd
from src_utils.calculations import SimpleMath
from src_utils.utils import utils
import seaborn as sns


class Graphics:

    @staticmethod
    def plot_earnings(df: pd.DataFrame) -> None:
        if not df.empty:
            df = df.groupby("Category").sum()
            df.index = df.index.map(lambda name: f"{utils.heb_conversion(name)}\n{round(df.loc[name,'Final_Value'], 2):,}₪")
            gentle_blue = ['#BFD7EA', '#A5C6DB', '#8BB5CC', '#7194BD', '#577DAE', '#3D5C9F', '#233D90']
            title = f"Total Earnings: {round(df['Final_Value'].sum(), 2):,}₪"
            ax = df.plot.pie(y='Final_Value', figsize=(7, 5), legend=False, title=title, colors=gentle_blue)
            ax.set_ylabel('')
        else:
            _, ax = plt.subplots()
            ax.pie([], labels=[])
            # set the title of the plot
            ax.set_title('Empty Pie Chart')

        plt.savefig(r'Outputs\Earnings.png')

    @staticmethod
    def plot_spendings(df: pd.DataFrame) -> None:

        if not df.empty:
            df = df.groupby("Category").sum()
            df.index = df.index.map(lambda name: f"{utils.heb_conversion(name)}\n{round(df.loc[name,'Final_Value'], 2):,}₪")
            gentle_orange = ['#FFF2CC', '#FFE699', '#FFD966', '#FFC533', '#FFB200', '#FFA000', '#FF8F00', '#FF8000', '#FF6B00']
            title = f"Total Spendings: {round(df['Final_Value'].sum(), 2):,}₪"

            ax = df.plot.pie(y='Final_Value', figsize=(7, 5), legend=False, title=title, colors=gentle_orange)
            ax.set_ylabel('')

        else:
            _, ax = plt.subplots()
            ax.pie([], labels=[])
            # set the title of the plot
            ax.set_title('Empty Pie Chart')

        plt.savefig(r'Outputs\Spendings.png')

    @staticmethod
    def plot_gas(df: pd.DataFrame) -> pd.Series:
        """
        The function assumes that df is never empty.
        Saves a plot image and returns a series of statistics.
        """
        # ------------
        df['Date'] = pd.to_datetime(df['Date'])
        statistics = df['Final_Value'].describe().loc[["count", "mean", "std", "min", "max"]]

        start_date = pd.Timestamp.today().normalize() - pd.DateOffset(months=2, days=0)
        end_date = pd.Timestamp.today().normalize()
        all_dates = pd.date_range(start=start_date, end=end_date, freq='D')
        df_all_dates = pd.DataFrame({'Date': all_dates})

        # merge the original DataFrame with the new DataFrame using a left join
        df_merged = pd.merge(df_all_dates, df, on='Date', how='left')

        # fill the missing values with 0
        df_merged['Final_Value'].fillna(0, inplace=True)

        # set the datetime column as the index of the DataFrame
        df_merged.set_index('Date', inplace=True)

        # create the bar plot
        plt.figure()
        fig, ax = plt.subplots(figsize=(15, 6))
        bars = ax.bar(df_merged.index.strftime('%d/%m'), df_merged['Final_Value'])

        for i, bar in enumerate(bars):
            height = bar.get_height()
            if height != 0:
                ax.text(bar.get_x() + bar.get_width()/2., height + 2,
                        utils.heb_conversion(df_merged['Name'][i]),
                        ha='center', va='bottom')

        # rotate x-axis labels by 45 degrees
        ax.set_xticklabels(df_merged.index.strftime('%d/%m'), rotation=55)

        # set the x-axis label
        ax.set_xlabel('Date (dd/mm)')
        # set the y-axis label
        ax.set_ylabel('Values')

        # set the title of the plot
        ax.set_title('Bar Plot')

        plt.savefig(r'Outputs\Gas_Info.png')
        return statistics

    @staticmethod
    def plot_monthly_gas(df: pd.DataFrame) -> None:

        if df.empty:
            return False

        plt.figure()
        # data = [(item[4], item[1], -item[2]) for item in data]
        # labels = ["Date", "Business Name", "Amount"]
        # df = pd.DataFrame(data, columns=labels)
        
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.groupby(pd.Grouper(key='Date', freq='M')).sum()
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(df.index.strftime('%b %Y'), df['Final_Value'])

        # set the x-axis label
        ax.set_xlabel('Month')
        # set the y-axis label
        ax.set_ylabel('Amount')

        # set the title of the plot
        ax.set_title('Monthly Payment')
        plt.savefig(r'Outputs\Gas_monthly.png')

    @staticmethod
    def plot_general(spendings, earnings) -> None:

        from datetime import datetime, timedelta

        def get_last_n_months_names(N):
            current_month = datetime.now().month
            return [(datetime(2023, (current_month - i) % 12 or 12, 1)).strftime('%B') for i in range(N)]

        months = get_last_n_months_names(len(spendings))  # == len(earnings)

        # Create a DataFrame
        data = pd.DataFrame({"Months": months, "Spendings": spendings, "Earnings": earnings})

        # Convert DataFrame to long format using pd.melt
        df = pd.melt(data, id_vars=["Months"], var_name="Category", value_name="Amount")

    #     # Sample dictionaries
    # spendings_dict = {"Jan": 100, "Feb": 150, "Mar": 200, "Apr": 180, "May": 220}
    # earnings_dict = {"Jan": 50, "Feb": 80, "Mar": 100, "Apr": 120, "May": 110}

    # # Create DataFrames from the dictionaries
    # spendings_df = pd.DataFrame(list(spendings_dict.items()), columns=["Months", "Spendings"])
    # earnings_df = pd.DataFrame(list(earnings_dict.items()), columns=["Months", "Earnings"])

    # # Merge the DataFrames into a single DataFrame (optional)
    # data = pd.merge(spendings_df, earnings_df, on="Months", how="outer")

        # Plot the bar plot using seaborn
        sns.set(style="whitegrid")
        plt.figure(figsize=(10, 6))

        _, ax = plt.subplots(figsize=(12, 6))
        sns.barplot(x="Months", y="Amount", hue="Category", data=df, ax=ax)

        # Add labels and title
        plt.xlabel("Months")
        plt.ylabel("Amount")
        plt.title("Monthly Spendings and Earnings")
        plt.legend()

        # # Show the month names below each bar
        # for index, row in df.iterrows():
        #     plt.text(index, row["Spendings"] + 5, row["Months"], ha="center")
      
        # for i in range(len(df)):
        #     delta = int(df['Earnings'][i] - df['Spendings'][i])
        #     (height, color) = (df['Earnings'][i], 'green') if df['Earnings'][i] > df['Spendings'][i] else (df['Earnings'][i], 'red')
        #     plt.text(i-.1, height + 50, str(delta), color=color, fontsize=10)

        # df['Date'] = df['Date'].apply(lambda x: x.strftime('%B'))
        # #df.index = df.index.strftime('%B')
        # #df = df.reset_index()
        # # Melt the dataframe to "long" format for easier plotting with Seaborn
        # df_melt = df.melt(id_vars='Date', value_vars=['Amount_spendings', 'Amount_earnings'], var_name='Type')
        # # Set Seaborn style
        # sns.set_style("whitegrid")
        # pastel = sns.color_palette("pastel")
        # pastel_reverse = list(reversed(pastel[:2]))
        # sns.set_palette(pastel_reverse)

        # fig, ax = plt.subplots(figsize=(12, 6))
        # sns.barplot(x="Date", y="value", hue="Type", data=df_melt, ax=ax)


        # ax.set_title("Spending and Earnings by Month")
        # ax.set_xlabel("Month")
        # ax.set_ylabel("Amount")
        # ax.legend(title="Type", loc="upper left")

        plt.savefig(r'Outputs\General_info.png')

    @staticmethod
    def card_distribution(spendings: pd.DataFrame):
        """

        """
        if not spendings.empty:
            # Since BankTransactions are indexed by a Ref Number, These needs to be caregorized by the TableName,
            # and not by CardNumber, unlike CardTransactions.
            # Sum Bank Transactions first:
            new_row = spendings[spendings['TableName'] == 'BankTransactions'].sum()
            # Set col Name for row identification
            new_row['Ref/CardID'] = 'Bank'
            # Filter out individual Bank transactions
            df = spendings[spendings['TableName'] != 'BankTransactions']
            # Add the summed transactions to create a new, summed, banktransaction row.
            # df = df.append(new_row, ignore_index=True) # Was removed in pandas version 2.0
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df = df.groupby("Ref/CardID").sum()

            df.index = df.index.map(lambda card: f"{utils.heb_conversion(card)}\n{round(df.loc[card, 'Final_Value'] * 100 / df['Final_Value'].sum(), 2)}%")
            gentle_orange = ['#FFF2CC', '#FFE699', '#FFD966', '#FFC533', '#FFB200', '#FFA000', '#FF8F00', '#FF8000', '#FF6B00']
            title = "Card Distribution"

            ax = df.plot.pie(y='Final_Value', figsize=(3, 2), legend=False, title=title, colors=gentle_orange)
            ax.set_ylabel('')

        else:
            _, ax = plt.subplots()
            ax.pie([], labels=[])
            ax.set_ylabel('')
            # set the title of the plot
            ax.set_title('Empty Pie Chart')
            
        plt.savefig(r'Outputs\Card_Distribution.png')