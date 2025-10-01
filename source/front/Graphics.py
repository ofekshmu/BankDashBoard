import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import pandas as pd
from src_utils.calculations import SimpleMath
from src_utils.utils import utils
import seaborn as sns
from Constants import GENERAL_PLOT
from Constants import Local, Paths
from typing import Tuple
import matplotlib.patches as mpatches
import numpy as np
from datetime import datetime


class Graphics:


    @staticmethod
    def _create_empty_chart(pie_name: str):
        """Helper method to create an empty chart when no data is present"""
        _, ax = plt.subplots()
        ax.pie([], labels=[])
        ax.set_title('Empty Pie Chart')
        plt.savefig(f'Outputs\\{pie_name}_category.png')
        plt.savefig(f'Outputs\\{pie_name}_prices.png')

    @staticmethod
    def plot_transactions_pie_chart(df: pd.DataFrame, pie_name: str, color_set: list) -> list:
        """
        Create and save two pie charts for transaction data analysis.
        
        Args:
            df (pd.DataFrame): Transaction data with columns ['Final_Value', 'Category', 'Name', 'Description/Charge_Currency']
            pie_name (str): Name of the chart (must be one of: "Investments", "Spendings", "Earnings")
            color_set (list): List of hex color codes for the chart
            
        Returns:
            list: List of transactions identified as outliers
            
        Saves two files:
            - {pie_name}_category.png: Pie chart showing category distribution
            - {pie_name}_prices.png: Pie chart showing price distribution
        """
        VALID_CHART_TYPES = ["Investments", "Spendings", "Earnings"]
        DONUT_HOLE_SIZE = 0.70
        FIG_SIZE = (7, 5)

        def create_donut_chart(ax, df, title, total_value):
            """Helper function to create a donut chart with consistent styling"""
            my_circle = plt.Circle((0, 0), DONUT_HOLE_SIZE, fc='white')
            fig = plt.gcf()
            fig.gca().add_artist(my_circle)
            
            # Add center text
            centre_text = f"{total_value:,.2f} ₪"
            ax.text(0, 0, centre_text,
                    horizontalalignment='center',
                    verticalalignment='center',
                    fontsize=22,
                    fontweight='bold',
                    color='black',
                    fontname='Arial')
            
            ax.set_title(title, fontsize = 20)
            ax.set_ylabel('')

        if pie_name not in VALID_CHART_TYPES:
            utils.log(f"pie_name must be one of {VALID_CHART_TYPES}", 'error')

        outliers_list = []

        if df.empty:
            Graphics._create_empty_chart(pie_name)  # Create an empty chart
            return []     

        # Preprocessing    
        df = df.copy()
        df['Final_Value'] = df['Final_Value'].abs()
        total_value = df['Final_Value'].sum()
        
        # -------------- Create a pie chart with category names --------------
        df_names = df.copy()

        if pie_name in ["Spendings", "Earnings"]:
            df_names.index = df_names.index.map(lambda name: f"{utils.heb_conversion(name)}")
            df_names, outliers_list = utils.seperate_high_std(df_names, 'Final_Value')
        elif pie_name == "Investments":
            def get_display_name(row) -> str:
                """Helper function to determine the display name for pie chart labels"""
                if row['Description/Charge_Currency'] is None:
                    base_text = row['Name']
                else:
                    base_text = row['Description/Charge_Currency']
                
                return utils.heb_conversion(str(base_text))
            df_names = df_names.set_index(df_names.apply(get_display_name, axis=1))

        # Create category pie chart
        ax = df_names.plot.pie(y='Final_Value',
                            figsize=FIG_SIZE,
                            legend=False,
                            title=pie_name,
                            colors=color_set)
        create_donut_chart(ax, df_names, pie_name, total_value)
        plt.savefig(f'Outputs\\{pie_name}_category.png')
        
        # Create prices pie chart
        prices_df = df.copy()
        prices_df.index = df.index.map(lambda name: f"{prices_df.loc[name,'Final_Value']:,.2f}₪")

        if pie_name in ["Spendings", "Earnings"]:
            prices_df, _ = utils.seperate_high_std(prices_df, 'Final_Value')
        
        ax = prices_df.plot.pie(y='Final_Value',
                                    figsize=FIG_SIZE,
                                    legend=False,
                                    title=pie_name,
                                    colors=color_set)
        create_donut_chart(ax, prices_df, pie_name, total_value)
        plt.savefig(f'Outputs\\{pie_name}_prices.png')
        
        return outliers_list

    @staticmethod
    def plot_general(spendings: list, 
                     spendings_overall: list,
                     earnings: list,
                     topic: str = "",
                     title_ext: str = "",
                     lp_Overall_income: bool = True,
                     lp_user_defined: bool = False,
                     user_spendings_sum: list = [],
                     user_earnings_sum: list = [],
                     fig_size=(14, 8)):
        """
        Plot general financial statistics showing spendings, earnings and overall income.
        
        Args:
            spendings (list): Monthly spending values
            spendings_overall (list): Monthly net income values across all accounts
            earnings (list): Monthly earning values
            title_ext (str, optional): Extension for output filename. Defaults to "".
            fig_size (tuple, optional): Figure dimensions. Defaults to (14, 8).
        
        Saves:
            PNG file at 'Outputs/General_info{title_ext}.png'
        """
        # Constants
        COLORS = {
            'spendings': "#f66b85",
            'investments': "#DAA520", 
            'earnings': "#4fba89",
            'net_income': "#58063f",
            'user_defined': "#99303f"
        }
        FONT_SIZES = {
            'title': 18,
            'labels': 16,
            'annotations': 10
        }
        OFFSET_FACTOR = 0.035

        def get_last_n_months_names(n_months: int) -> list:
            """Get list of last n month names."""
            delta = 0 if GENERAL_PLOT.SHOW_CURRENT_MONTH else 1
            current_month = (datetime.now() - pd.DateOffset(months=delta)).month
            return [(datetime(2023, (current_month - i) % 12 or 12, 1)).strftime('%B') 
                    for i in range(n_months)]

        def prepare_plot_data(months: list) -> dict:
            """Prepare DataFrames for plotting."""
            data = {}
            
            # Base data
            base_df = pd.DataFrame({
                "Months": months, 
                "Spendings": spendings, 
                "Earnings": earnings
            })
            
            # Investment data
            investment_values = np.array(spendings) - np.array(spendings_overall)
            invest_df = pd.DataFrame({
                "Months": months, 
                "Spendings": investment_values, 
                "Earnings": earnings
            })
            
            from Constants import INVESTMENT_CATEGORY
            # Used for when category analysis for "Investments" is selected
            spendings_overall_option = [0] * len(earnings) if topic == INVESTMENT_CATEGORY else spendings_overall

            # Overall income data
            if lp_Overall_income:
                data["overall_df"] = pd.DataFrame({
                                        "Months": months, 
                                        "Overall Income": [x + y for x, y in zip(earnings, spendings_overall_option)]
                                    })

            # user defined plot
            if lp_user_defined:
                data["user_defined_df"] = pd.DataFrame({
                                            "Months": months, 
                                            "Overall Income": [x + y for x, y in zip(user_earnings_sum, user_spendings_sum)]
                                        })
            

            data["base_df"] = pd.melt(base_df, id_vars=["Months"], var_name="Category", value_name="Amount")
            data["invest_df"] = pd.melt(invest_df, id_vars=["Months"], var_name="Category", value_name="Amount")
            
            return data

        def create_legend_handles() -> list:
            """Create legend handles for the plot."""
            return [
                mpatches.Patch(color=COLORS['spendings'], label='Spendings'),
                mpatches.Patch(color=COLORS['earnings'], label='Earnings'),
                mpatches.Patch(color=COLORS['investments'], label='Spendings (Investments)'),
                mpatches.Patch(color=COLORS['net_income'], label='Overall Net Income', linestyle='--')
            ]

        def add_value_annotations(ax, data_df: pd.DataFrame, color: str) -> None:
            """Add value annotations to the line plot."""
            # Filter out rows with NaN values in 'Overall Income'
            for x, y in zip(data_df['Months'], data_df['Overall Income']):
                ax.annotate(f'{y:,.0f}₪',
                        xy=(x, y),
                        xytext=(0, 10),  # 10 points vertical offset
                        textcoords="offset points",
                        ha='center',
                        va='bottom',
                        color=color,
                        fontweight='bold')

        # Main plotting logic
        months = get_last_n_months_names(len(spendings))
        data = prepare_plot_data(months)
        
        # Create plot
        sns.set(style="whitegrid")
        _, ax = plt.subplots(figsize=fig_size)
                
        # Plot layers
        sns.barplot(x="Months", y="Amount", hue="Category", 
                    data=data["base_df"][::-1], ax=ax, 
                    palette=[COLORS['earnings'], COLORS['spendings']])
        
        if not lp_user_defined:
            sns.barplot(x="Months", y="Amount", hue="Category", 
                        data=data["invest_df"][::-1], ax=ax,
                        palette=[COLORS['earnings'], COLORS['investments']])
            
        if lp_Overall_income:
            sns.lineplot(x="Months", y="Overall Income", 
                        data=data["overall_df"], ax=ax,
                        color=COLORS['net_income'],
                        marker='o', linestyle='--')
            add_value_annotations(ax, data["overall_df"], COLORS['net_income'])
        
        if lp_user_defined:
            sns.lineplot(x="Months", y="Overall Income", 
                        data=data["user_defined_df"], ax=ax,
                        color=COLORS['user_defined'],
                        marker='o', linestyle='--')

            add_value_annotations(ax, data["user_defined_df"], COLORS['user_defined'])

        # Styling
        ax.legend(handles=create_legend_handles())
        ax.set_xlabel("Months", fontsize=FONT_SIZES['labels'])
        ax.set_ylabel("Amount (₪)", fontsize=FONT_SIZES['labels'])
        ax.set_title(f"Monthly Spendings and Earnings {title_ext}", fontsize=FONT_SIZES['title'])
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda value, tick_number: f'{value:,.0f}₪' ))

        # Save plot
        output_path = f'Outputs\\General_info{"_" + title_ext if title_ext else ""}.png'
        plt.savefig(output_path, bbox_inches='tight')
        plt.close()

    @staticmethod
    def card_distribution(spendings: pd.DataFrame, color_dict: dict, df_card_status: pd.DataFrame):
        """
        Revceives the spending df of the current month,
        """
        df = spendings.copy()[['Ref/CardID', 'Final_Value', 'TableName']]

        if not df.empty:
            df['Final_Value'] = df['Final_Value'].abs()
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
    
    @staticmethod
    def plot_linear_plots_graph(data_dict: dict) -> None:
        """Plot line graphs for account balances over time with value annotations."""
        sns.set(style="whitegrid")
        plt.figure(figsize=(18, 8))  # Increased width from 12 to 15
        
        # Plot each account's data 
        for key, value in data_dict.items():
            x, y = zip(*value)
            line = plt.plot(x, y, label=key, marker='o')[0]
            
            # Add value annotations for each point
            for i, (xi, yi) in enumerate(zip(x, y)):
                plt.annotate(f'{yi:,.0f}₪', 
                           (xi, yi),
                           xytext=(0, 10),
                           textcoords='offset points',
                           ha='center',
                           va='bottom',
                           color=line.get_color(),
                           fontsize=8)

        plt.legend()
        plt.xticks(rotation=45)
        
        # Increase title font size and add padding
        plt.title("Account Balances Over Time", 
                 fontsize=20,        # Increased from default
                 pad=20)            # Added padding between title and plot
        
        plt.xlabel("Date")
        plt.ylabel("Balance (₪)")
        
        # Format y-axis values
        plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda value, tick_number: f'{value:,.0f}₪'))
        
        # Adjust layout with more bottom margin for rotated labels
        plt.tight_layout()
        
        plt.savefig(r'Outputs\accounts_liner_plots.png')
        plt.close()


    @staticmethod
    def generate_payment_pie_graphs(monthly_payments_df: pd.DataFrame) -> None:

        import matplotlib.pyplot as plt

        if monthly_payments_df.empty:
            _, ax = plt.subplots()
            ax.pie([], labels=[])
            ax.set_title('No Payments Data for this month')
            plt.savefig(r'Outputs\payments_pie_graphs.png')
            return None

        n = len(monthly_payments_df)
        fig, axes = plt.subplots(1, n, figsize=(4*n, 4))
        
        if n == 1:
            axes = [axes]

        for i, (ax, (_, row)) in  enumerate(zip(axes, monthly_payments_df.iterrows())):
            
            total_pieces = int(row['Number of Payments'])
            colored = int(row['Current Payment Number'])
            grayed_out = total_pieces - colored
            
            
            iteration_color = Local.Colors[i % len(Local.Colors)]

            colors = ["lightgray"] * grayed_out + [iteration_color] * colored 
            
            piece_count = [1] * row['Number of Payments']            

            ax.pie(
                piece_count,
                colors=colors,
                startangle=90,
                counterclock=False,
                wedgeprops={"linewidth": 6, "edgecolor": "white"}  # thick white lines
            )
            ax.set_title(f"{utils.heb_conversion(row['Transaction Name'])}\n", fontsize=12)
        
                # Text *under* the pie chart
            ax.text(
            0.5, -0.05,   # X center, Y a bit below axes
            f"Payment {row['Current Payment']* row['Current Payment Number']:,.2f} / {row['Total Amount']:,.2f} ₪",
            ha="center", va="top", fontsize=10, transform=ax.transAxes
            )

        plt.tight_layout()
        plt.savefig(r'Outputs\payments_pie_graphs.png')
        plt.close()

    @staticmethod
    def plot_monthly_cash_distribution(df_monthly_cash_transactions: pd.DataFrame) -> Tuple[float, float]:
        """
        Plot a pie graph according to the following guidelines:

        In the center, the value of the accumulative cash value of the month will be displayed.
        The pie chart is divided into two main sections: earnings in cash and spendings in cash of the given month,
        the transactions are provided by the df_monthly_cash_transactions data frame and are already filltered to include a single month.
        The pie chart will be displayed in the same ui as the other pie charts (spendings/earnings/investments).
        The pie chart will include spending transactions in red color and earnings transactions in green color.
        2 charts will be generated and saved to the output folder:
            1. A chart grouped by spending/earning and category, displaying the summed value.
            2. A chart grouped by spending/earning and category, displaying the the category name.

        amount spend in cash and the amount earned in cash in the given month will returned
        """
        chart_name = "Cash_Distribution"

        if df_monthly_cash_transactions.empty:
            Graphics._create_empty_chart(chart_name)  # Create an empty chart
            return 0.0, 0.0

        df = df_monthly_cash_transactions.copy()
        monthly_accumulative = df['Amount'].sum()

        # Separate spendings and earnings
        spendings_df = df[df['Amount'] < 0]
        earnings_df = df[df['Amount'] > 0]

        total_spendings = spendings_df['Amount'].sum() if not spendings_df.empty else 0.0
        total_earnings = earnings_df['Amount'].sum() if not earnings_df.empty else 0.0

        # add a column to identify if the transaction is a spending or an earning
        df['Type'] = df['Amount'].apply(lambda x: 'Spendings' if x < 0 else 'Earnings')
        df = df.groupby(['Type', 'Category'], as_index=False).sum(numeric_only=True)        
        df['Amount'] = df['Amount'].abs()       
        utils.log(f"Cash transactions for the month:\n{utils.df_to_markdown(df)}", 'system')
        # create a dounought pie plot with the created df
        DONUT_HOLE_SIZE = 0.70
        FIG_SIZE = (7, 5)
        COLORS = {
            'Spendings': "#f66b85",
            'Earnings': "#4fba89"
        }
        def create_donut_chart(ax, total_value):
            """Helper function to create a donut chart with consistent styling"""
            my_circle = plt.Circle((0, 0), DONUT_HOLE_SIZE, fc='white')
            fig = plt.gcf()
            fig.gca().add_artist(my_circle)
            
            # Add center text
            centre_text = f"{total_value:,.2f} ₪"
            ax.text(0, 0, centre_text,
                    horizontalalignment='center',
                    verticalalignment='center',
                    fontsize=22,
                    fontweight='bold',
                    color='black',
                    fontname='Arial')
            
            ax.set_title(chart_name, fontsize = 20)
            ax.set_ylabel('')
        # -------------- Create a pie chart with category names --------------
        df_names = df.copy()
        df_names = df_names.set_index(df_names.apply(lambda row: utils.heb_conversion(row['Category']), axis=1))
        ax = df_names.plot.pie(y='Amount',
                            figsize=FIG_SIZE,
                            legend=False,
                            title=chart_name,
                            colors=[COLORS[type] for type in df_names['Type']])
        create_donut_chart(ax, monthly_accumulative)
        plt.savefig(f'Outputs\\{chart_name}_category.png')
        plt.close()
        # -------------- Create a pie chart with prices --------------
        prices_df = df.copy()
        prices_df = prices_df.set_index(prices_df.apply(lambda row: row['Amount'], axis=1))

        ax = prices_df.plot.pie(y='Amount',
                                    figsize=FIG_SIZE,
                                    legend=False,
                                    title=chart_name,
                                    colors=[COLORS[type] for type in prices_df['Type']])
        create_donut_chart(ax, monthly_accumulative)
        plt.savefig(f'Outputs\\{chart_name}_prices.png')
        plt.close()
        return abs(total_spendings), total_earnings