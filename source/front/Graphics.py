import matplotlib.pyplot as plt
import pandas as pd
from src_utils.calculations import SimpleMath
from src_utils.utils import utils
import seaborn as sns
from Constants import GENERAL_PLOT
from typing import Tuple


class Graphics:


    @staticmethod
    def plot_transactions_pie_chart(df: pd.DataFrame, pie_name: str, color_set: list) -> list:
        """
        The function Receives:
        1. A transactions data frame 
        2. the name of the data frame (choose any name that represents your data)
        3. a color set - a list of colors represented in hex form
        the function will sort transactions by category and plot 2 pie charts, one with the category names and one with
        the total category prices. piw charts will be saved to the output folder.
        the function will return a list with high/low std transactions, see the function 'seperate_high_std'
        """
        # card transactions are processed to negative value, such values are prohibited in pie plots.
        # since each card is shown separately, negative and positive values are not mixed, and 'abs' can be used.

        outliers_list = []

        if df.empty:
            _, ax = plt.subplots()
            ax.pie([], labels=[])
            # set the title of the plot
            ax.set_title('Empty Pie Chart')
            plt.savefig(rf'Outputs\{pie_name}_category.png')
            plt.savefig(rf'Outputs\{pie_name}_prices.png')        
        else:
            df['Final_Value'] = df['Final_Value'].abs()
            df = df.groupby("Category").sum()
            title = f"Total {pie_name}: {df['Final_Value'].sum():,.2f}₪"
            
            # -------------- Create a pie chart with category names --------------
            df_category = df.copy()
            df_category.index = df_category.index.map(lambda name: f"{utils.heb_conversion(name)}")   
            reduced_category_df, outliers_list = utils.seperate_high_std(df_category, 'Final_Value')
            ax = reduced_category_df.plot.pie(y='Final_Value', figsize=(7, 5), legend=False, title=title, colors=color_set)
            ax.set_ylabel('')
            plt.savefig(rf'Outputs\{pie_name}_category.png')

            # ------------------ Create a pie chart with prices ------------------
            df_prices = df.copy()
            df_prices.index = df.index.map(lambda name: f"{df_prices.loc[name,'Final_Value']:,.2f}₪")   
            reduced_prices_df, _ = utils.seperate_high_std(df_prices, 'Final_Value')
            ax = reduced_prices_df.plot.pie(y='Final_Value', figsize=(7, 5), legend=False, title=title, colors=color_set)
            ax.set_ylabel('')
            plt.savefig(rf'Outputs\{pie_name}_prices.png')

        return outliers_list


    @staticmethod
    def plot_gas(df: pd.DataFrame) -> pd.Series:
        """
        The function assumes that df is never empty.
        Saves a plot image and returns a series of statistics.
        """
        # ------------
        df['Date/Executed_Date'] = pd.to_datetime(df['Date/Executed_Date'])
        statistics = df['Final_Value'].describe().loc[["count", "mean", "std", "min", "max"]]

        start_date = pd.Timestamp.today().normalize() - pd.DateOffset(months=2, days=0)
        end_date = pd.Timestamp.today().normalize()
        all_dates = pd.date_range(start=start_date, end=end_date, freq='D')
        df_all_dates = pd.DataFrame({'Date/Executed_Date': all_dates})

        # merge the original DataFrame with the new DataFrame using a left join
        df_merged = pd.merge(df_all_dates, df, on='Date/Executed_Date', how='left')

        # fill the missing values with 0
        df_merged['Final_Value'].fillna(0, inplace=True)

        # set the datetime column as the index of the DataFrame
        df_merged.set_index('Date/Executed_Date', inplace=True)

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

        df['Date/Executed_Date'] = pd.to_datetime(df['Date/Executed_Date'])
        df = df.groupby(pd.Grouper(key='Date/Executed_Date', freq='M')).sum()
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
    def plot_general(spendings : list, spendings_overall : list, earnings: list, title_ext: str = "", fig_size=(14, 8), secondary_line: bool = True):
        """
        @spendings : list - A list of length n containing the total spending values of the last n months.
        @earnings  : list - A list of length n containing the total earning values of the last n months.
        @spendings_overall  : list - A list of length n containing the total net icome across all accounts in the last n months.

        The function Will plot a graph describing general statistics and info and save it to 'Outputs\General_info.png'
        """
        from datetime import datetime
        def get_last_n_months_names(N):
            delta = 0 if GENERAL_PLOT.SHOW_CURRENT_MONTH else 1
            current_month = (datetime.now() - pd.DateOffset(months=delta)).month 
            return [(datetime(2023, (current_month - i) % 12 or 12, 1)).strftime('%B') for i in range(N)]

        months = get_last_n_months_names(len(spendings))  # == len(earnings)

        # ----------- Create a DataFrame for barplot data -----------
        data = pd.DataFrame({"Months": months, "Spendings": spendings, "Earnings": earnings})
        # Convert DataFrame to long format using pd.melt
        df = pd.melt(data, id_vars=["Months"], var_name="Category", value_name="Amount")
        
        # ----------- Create a DataFrame for net income line plot -----------
        net_data = pd.DataFrame({"Months": months, "Net Income": [x + y for x, y in zip(earnings, spendings)]})
        
        # ----------- Create a DataFrame for overall income line plot -----------
        overall_data = pd.DataFrame({"Months": months, "Overall Income": [x + y for x, y in zip(earnings, spendings_overall)]})
        
        # Color constants for Graph
        spendings_bar_color = "#f66b85"
        earnings_bar_color = "#4fba89"
        net_income_line_color = "#58063f"
        overall_income_line_color = net_income_line_color
        
        # Plot the bar plot using seaborn
        sns.set(style="whitegrid")
        plt.figure(figsize=(10, 6))

        _, ax = plt.subplots(figsize=fig_size)
        # Data is flipped to flip the order of the x axis
        sns.barplot(x="Months", y="Amount", hue="Category", data=df[::-1], ax=ax, palette=[earnings_bar_color, spendings_bar_color])
        # No need to flipp data in the following
        sns.lineplot(x="Months", y="Net Income", color=net_income_line_color, marker='o', data = net_data)
        if secondary_line:
            sns.lineplot(x="Months", y="Overall Income", color=overall_income_line_color, marker='o', data = overall_data, linestyle='--')

        # ----------- Plotting information next to line plot points -----------
        offset = 40   # For better visual 
        for x, y_net, y_overall in zip(net_data['Months'], net_data['Net Income'], overall_data['Overall Income']):
            plt.text(x, y_net + offset, f'{y_net:,.0f}₪', ha='right', va='bottom', color=net_income_line_color,fontweight='bold')
            if secondary_line:
                if y_net == y_overall:
                    continue

                if abs(y_net - y_overall) < 5000:
                    if y_net > y_overall:
                        plt.text(x, y_overall + offset - 2000, f'{y_overall:,.0f}₪', ha='right', va='bottom', color=overall_income_line_color, fontweight='bold')
                    else:
                        plt.text(x, y_overall + offset + 2000, f'{y_overall:,.0f}₪', ha='right', va='bottom', color=overall_income_line_color, fontweight='bold')
                else:
                    plt.text(x, y_overall + offset, f'{y_overall:,.0f}₪', ha='right', va='bottom', color=overall_income_line_color, fontweight='bold')

        
        import matplotlib.patches as mpatches

        legend_handles = [
            mpatches.Patch(color=spendings_bar_color, label='Spendings', linestyle='-'),  
            mpatches.Patch(color=earnings_bar_color, label='Earnings', linestyle='-'),  
            mpatches.Patch(color=net_income_line_color, label='Net Income', linestyle='-')
            ]
        
        if secondary_line:
            legend_handles.append(mpatches.Patch(color=overall_income_line_color, label='Overall Net Income', linestyle='--'))

        # Add labels and title
        plt.xlabel("Months", fontsize=16)
        plt.ylabel("Amount (₪)", fontsize=16)
        plt.title("Monthly Spendings and Earnings", fontsize=18)
        plt.legend(handles=legend_handles)

        if not title_ext == "":
            title_ext = "_" + title_ext
        plt.savefig(r'Outputs\General_info' + title_ext + r'.png')

        return overall_data


    @staticmethod
    def card_distribution(spendings: pd.DataFrame, color_dict: dict):
        """

        """
        if not spendings.empty:
            # Since BankTransactions are indexed by a Ref Number, These needs to be caregorized by the TableName,
            # and not by CardNumber, unlike CardTransactions.
            # Sum Bank Transactions first:
            new_row = spendings[spendings['TableName'] == 'BankTransactions']
            # Set col Name for row identification
            new_row['Ref/CardID'] = 'Bank'
            # Filter out individual Bank transactions
            df = spendings[spendings['TableName'] != 'BankTransactions']
            # Add the summed transactions to create a new, summed, banktransaction row.
            # df = df.append(new_row, ignore_index=True) # Was removed in pandas version 2.0
            df = pd.concat([df, new_row], ignore_index=True)
            df = df.groupby("Ref/CardID").sum()

            title = "Card Distribution"

            color_list = [color_dict[card_id] for card_id in df.index]
            df.index = df.index.map(lambda card: f"{utils.heb_conversion(card)}\n{df.loc[card, 'Final_Value']:,.2f}")

            ax = df.plot.pie(y='Final_Value', figsize=(3, 2), legend=False, title=title, colors=color_list)
            ax.set_ylabel('')

        else:
            _, ax = plt.subplots()
            ax.pie([], labels=[])
            ax.set_ylabel('')
            # set the title of the plot
            ax.set_title('Empty Pie Chart')

        plt.savefig(r'Outputs\Card_Distribution.png')

    @staticmethod
    def plot_pie_distribution(df: pd.DataFrame) -> list:
        """
        The function receives a 'process_prices_ready' data frame and creates a distribution pie chart
        according to its index values. The pie chart is displayed with percentage values and index names.
        The chart will show entries below a certain treshold as 'other' and the following will be returned as
        a list. the outliers are marked according to the 'cover_outliers' function.
        """

        def cover_outliers(df) -> Tuple[pd.DataFrame, pd.DataFrame]:
            """
            The 'cover_outliers' replaces entries in the given input @df, that do not pass the threshold value,
            with a single entry that sums all of them. the index of the new intery will be named 'other'.
            The function will return the newly created df and another df that represents the removed entries.
            """
            numerical_col_name = 'Final_Value'

            total = df[numerical_col_name].sum()

            lower_treshold = total*0.02
            #lower_treshold = lower_treshold if lower_treshold > 0 else 0.05*mean 

            high_treshold = df[numerical_col_name].max()  + 10
            
            outliers_df = df[(df[numerical_col_name] > high_treshold) | (df[numerical_col_name] < lower_treshold)]
            df.index = df.index.map(lambda x: "אחר" if df.loc[x, numerical_col_name] > high_treshold or df.loc[x, numerical_col_name] < lower_treshold else x)

            # Step 1: Filter out the rows where the index is "אחר"
            removed_rows = df.loc[df.index == "אחר"]

            # Step 2: Calculate the sum of the 'Final_Value' column for the removed rows
            sum_removed = removed_rows['Final_Value'].sum()

            # Step 3: Remove the rows from the original DataFrame
            df = df.drop(index="אחר")

            # Step 4: Add a new row with the sum
            df.loc['אחר'] = sum_removed


            return df, outliers_df
    
        outliers_lst = []

        if not df.empty:
            df['Final_Value'] = df.apply(lambda row: abs(row['Final_Value']), axis=1)
            df, outliers_df = cover_outliers(df)
            outliers_lst = outliers_df.index.tolist()
            df['Percent'] = df.apply(lambda row: abs(row['Final_Value'])*100/df['Final_Value'].sum(), axis=1)
            df.index = df.index.map(lambda x: f"{utils.heb_conversion(x)}\n{df.loc[x, 'Percent']:,.2f}%")
            from Constants import Local
            ax = df.plot.pie(y='Final_Value', figsize=(5, 3), legend=False, title="Distribution", colors=Local.Colors)
            ax.set_ylabel('')

        else:
            _, ax = plt.subplots()
            ax.pie([], labels=[])
            ax.set_ylabel('')
            # set the title of the plot
            ax.set_title('Empty Pie Chart')

        plt.savefig(r'Outputs\Category_Distribution.png')
        return outliers_lst