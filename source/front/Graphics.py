import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
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

        if pie_name not in ["Investments", "Spendings", "Earnings"]:
            utils.log("Bad input in function 'plot_transactions_pie_chart'", 'error')

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
            title = f"{pie_name}"
            
            if pie_name == "Investments":
                df = df[df["Category"] == "השקעה/חיסכון"]
            else:
                df = df.groupby("Category").sum()
            
            # -------------- Create a pie chart with category names --------------
            df_category = df.copy()
            if pie_name != "Investments":
                df_category.index = df_category.index.map(lambda name: f"{utils.heb_conversion(name)}")
                reduced_category_df, outliers_list = utils.seperate_high_std(df_category, 'Final_Value')
                ax = reduced_category_df.plot.pie(y='Final_Value', figsize=(7, 5), legend=False, title=title, colors=color_set)
            else:
                print(df_category.columns)
                df_category.index = df_category.apply(lambda row: utils.heb_conversion(f"{row['Name']}") if row['Description/Charge_Currency'] is None else utils.heb_conversion(f"{row['Description/Charge_Currency']}"), axis=1)
                print(df_category.to_markdown())
                ax = df_category.plot.pie(y='Final_Value', figsize=(7, 5), legend=False, title=title, colors=color_set)
                
            ax.set_title(title, fontsize = 20)
            ax.set_ylabel('')
            #converting plot into donut chart
            my_circle = plt.Circle((0, 0), 0.70, fc='white')
            fig = plt.gcf()
            fig.gca().add_artist(my_circle)

            centre_text = f"{df['Final_Value'].sum():,.2f} ₪"
            ax.text(0, 0, centre_text, horizontalalignment='center', 
                    verticalalignment='center', 
                    fontsize=22, fontweight='bold',
                    color='black', fontname='Arial')

            plt.savefig(rf'Outputs\{pie_name}_category.png')


            # ------------------ Create a pie chart with prices ------------------
            df_prices = df.copy()
            df_prices.index = df.index.map(lambda name: f"{df_prices.loc[name,'Final_Value']:,.2f}₪")   
            reduced_prices_df, _ = utils.seperate_high_std(df_prices, 'Final_Value')
            ax = reduced_prices_df.plot.pie(y='Final_Value', figsize=(7, 5), legend=False, title=title, colors=color_set)
            ax.set_title(title, fontsize = 20)
            ax.set_ylabel('')
            #converting plot into donut chart
            my_circle = plt.Circle((0, 0), 0.70, fc='white')
            fig = plt.gcf()
            fig.gca().add_artist(my_circle)

            centre_text = f"{df['Final_Value'].sum():,.2f} ₪"
            ax.text(0, 0, centre_text, horizontalalignment='center', 
                    verticalalignment='center', 
                    fontsize=22, fontweight='bold',
                    color='black', fontname='Arial')

            plt.savefig(rf'Outputs\{pie_name}_prices.png')

        return outliers_list


    @staticmethod
    def plot_general(spendings : list, spendings_overall : list, earnings: list, title_ext: str = "", fig_size=(14, 8)):
        """
        @spendings : list - A list of length n containing the total spending values of the last n months.
        @earnings  : list - A list of length n containing the total earning values of the last n months.
        @spendings_overall  : list - A list of length n containing the total net income across all accounts in the last n months.

        The function Will plot a graph describing general statistics and info and save it to 'Outputs\General_info.png'
        """
        from datetime import datetime
        def get_last_n_months_names(N):
            delta = 0 if GENERAL_PLOT.SHOW_CURRENT_MONTH else 1
            current_month = (datetime.now() - pd.DateOffset(months=delta)).month 
            return [(datetime(2023, (current_month - i) % 12 or 12, 1)).strftime('%B') for i in range(N)]

        months = get_last_n_months_names(len(spendings))  # == len(earnings)

        # --------------- Create a DataFrame for barplot data ----------------
        data = pd.DataFrame({"Months": months, "Spendings": spendings, "Earnings": earnings})
        # Convert DataFrame to long format using pd.melt
        df = pd.melt(data, id_vars=["Months"], var_name="Category", value_name="Amount")

        # ------------ Overlay bar plot to represent investments -------------
        import numpy as np
        top_bar_values = np.array(spendings) - np.array(spendings_overall)
        data2 = pd.DataFrame({"Months": months, "Spendings": top_bar_values, "Earnings": earnings})
        df2 = pd.melt(data2, id_vars=["Months"], var_name="Category", value_name="Amount")
        
        # ----------- Create a DataFrame for overall income line plot -----------
        overall_data = pd.DataFrame({"Months": months, "Overall Income": [x + y for x, y in zip(earnings, spendings_overall)]})
        
        # Color constants for Graph
        spendings_bar_color = "#f66b85"
        invest_bar_color = "#DAA520"
        earnings_bar_color = "#4fba89"
        net_income_line_color = "#58063f"
        overall_income_line_color = net_income_line_color
        
        # Plot the bar plot using seaborn
        sns.set(style="whitegrid")
        plt.figure(figsize=(10, 6))

        _, ax = plt.subplots(figsize=fig_size)
        # Data is flipped to flip the order of the x axis
        sns.barplot(x="Months", y="Amount", hue="Category", data=df[::-1], ax=ax, palette=[earnings_bar_color, spendings_bar_color])
        # Data is flipped to flip the order of the x axis
        sns.barplot(x="Months", y="Amount", hue="Category", data=df2[::-1], ax=ax, palette=[earnings_bar_color, invest_bar_color])
        # No need to flipp data in the following
        sns.lineplot(x="Months", y="Overall Income", color=overall_income_line_color, marker='o', data = overall_data, linestyle='--')

        # ----------- Plotting information next to line plot points -----------
        offset = 0.035   # For better visual
        max_value = overall_data['Overall Income'].abs().max()
        prev = 0
        for x, y_overall in zip(overall_data['Months'], overall_data['Overall Income']):

            if y_overall > prev:
                plt.text(x, y_overall + max_value*offset , f'{y_overall:,.0f}₪', ha='left', va='bottom', color=overall_income_line_color, fontweight='bold')
            else:
                plt.text(x, y_overall - 2*max_value*offset, f'{y_overall:,.0f}₪', ha='left', va='bottom', color=overall_income_line_color, fontweight='bold')

            prev = y_overall
        import matplotlib.patches as mpatches

        legend_handles = [
            mpatches.Patch(color=spendings_bar_color, label='Spendings', linestyle='-'),  
            mpatches.Patch(color=earnings_bar_color, label='Earnings', linestyle='-'),
            mpatches.Patch(color=invest_bar_color, label='Spendings (Investments)', linestyle='-'),
            mpatches.Patch(color=overall_income_line_color, label='Overall Net Income', linestyle='--')  
            ]

        # Add labels and title
        plt.xlabel("Months", fontsize=16)
        plt.ylabel("Amount (₪)", fontsize=16)
        plt.title("Monthly Spendings and Earnings", fontsize=18)
        plt.legend(handles=legend_handles)

        if not title_ext == "":
            title_ext = "_" + title_ext
        plt.savefig(r'Outputs\General_info' + title_ext + r'.png')


    @staticmethod
    def card_distribution(spendings: pd.DataFrame, color_dict: dict, df_card_status: pd.DataFrame):
        """
        Revceives the spending df of the current month,
        """
        df = spendings.copy()[['Ref/CardID', 'Final_Value', 'TableName']]

        if not df.empty:
            # Since BankTransactions are indexed by a Ref Number, These needs to be caregorized by the TableName,
            # and not by CardNumber, unlike CardTransactions, Therefor, we will change the ref number for all
            # BankTransactions
            
            df['Ref/CardID'] = df.apply(lambda row: 'Bank' if row['TableName'] == 'BankTransactions' else row['Ref/CardID'], axis=1)
            df = df.groupby("Ref/CardID").sum(numeric_only=True)
            # The status df is merged with the data df in order to annotate the status (see lower part)
            df = pd.merge(df, df_card_status, left_on='Ref/CardID', right_on='CardID', how='outer')
            # filling the NA in the df is crucial for displaying all the data (Bank transactions)
            df['CardID'] = df['CardID'].fillna("Bank")
            df['Out/Transaction_value'] = df['Out/Transaction_value'].fillna(df['Final_Value'][df['CardID'] == 'Bank'])
            utils.log(f'Card Status, merged data frame::\n{df.to_markdown()}','debug')

            # Plot the bar plot using seaborn
            sns.set(style="whitegrid")
            plt.figure(figsize=(6, 3))

            # Adding the values on top of the bar plots:
            ax = sns.barplot(x="CardID", hue="CardID", y="Out/Transaction_value", data=df, palette=color_dict, legend=False)
            for index ,p in enumerate(ax.patches):
                height = p.get_height()
                status = df['Status'].iloc[index]
                # ------------ annotate the value of the bar on top of it ------------
                ax.annotate(f'{height:,.0f}₪',
                            xy=(p.get_x() + p.get_width() / 2, height),
                            xytext=(0, 3),  # 3 points vertical offset
                            textcoords="offset points",
                            ha='center', va='bottom', fontweight='bold')
                # --------------------------------------------------------------------
                if status == "Verified":
                    ax.annotate(f'{status}',
                                xy=(p.get_x() + p.get_width() / 2, height),
                                xytext=(0, 17),  # 3 points vertical offset
                                textcoords="offset points",
                                ha='center', va='bottom', fontweight='bold', color = 'green')
                # --------------------------------------------------------------------
                if status == "Not Verified":
                    ax.annotate(f'{status}',
                                xy=(p.get_x() + p.get_width() / 2, height),
                                xytext=(0, 17),  # 3 points vertical offset
                                textcoords="offset points",
                                ha='center', va='bottom', fontweight='bold', color = 'red')
                    

            # The following section is responsible for changing the y label values
            # for better visual - Custom formatter for y-axis
            # -----------------------------------------------------------------------
            import matplotlib.ticker as ticker
            def format_ils(value, tick_number):
                return f'{value:,.0f}₪'

            # Apply custom formatter to y-axis
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(format_ils))
            # -----------------------------------------------------------------------
            # ax.set_xlabel("Card no'/Bank")
            # ax.set_ylabel("Amount")
            ax.set_title("Source Distribution")
            
        else:
            _, ax = plt.subplots()
            ax.pie([], labels=[])
            ax.set_ylabel('')
            # set the title of the plot
            ax.set_title('Empty Chart')

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
            
            if not outliers_df.empty:
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